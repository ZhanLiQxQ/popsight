"""
One-time ingestion script: parse PoP data files and load into Qdrant.

Run from repo root (Docker must be running):
    python -m backend.ingest

Or from inside the backend container:
    docker compose exec backend python -m backend.ingest
"""
from __future__ import annotations

import csv
import sys
import time
import uuid
from pathlib import Path

import openpyxl
import pypdf
from google import genai
from google.genai.errors import ClientError
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from .config import settings
from .vector_store import COLLECTION_NAME, EMBED_MODEL, VECTOR_DIM

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BATCH_SIZE = 10   # items per embed call (free tier: 100 items/min)
BATCH_SLEEP = 7   # seconds between batches → ~85 items/min, safely under limit


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def embed_batch(client: genai.Client, texts: list[str]) -> list[list[float]]:
    result = client.models.embed_content(model=EMBED_MODEL, contents=texts)
    return [e.values for e in result.embeddings]


def upsert_chunks(
    qdrant: QdrantClient,
    genai_client: genai.Client,
    chunks: list[dict],
) -> None:
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        # Retry once on rate-limit; server tells us how long to wait
        for attempt in range(2):
            try:
                vectors = embed_batch(genai_client, [c["content"] for c in batch])
                break
            except ClientError as e:
                if e.status_code == 429 and attempt == 0:
                    retry_secs = 65
                    print(f"  Rate limited — sleeping {retry_secs}s ...")
                    time.sleep(retry_secs)
                else:
                    raise
        points = [
            PointStruct(id=str(uuid.uuid4()), vector=vec, payload=chunk)
            for vec, chunk in zip(vectors, batch)
        ]
        qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"  {i + len(batch)}/{len(chunks)} chunks upserted")
        if i + BATCH_SIZE < len(chunks):
            time.sleep(BATCH_SLEEP)


# ---------------------------------------------------------------------------
# File parsers
# ---------------------------------------------------------------------------

def load_item_specs() -> list[dict]:
    """POP_ItemSpecMaster.xlsx — one chunk per SKU."""
    wb = openpyxl.load_workbook(DATA_DIR / "POP_ItemSpecMaster.xlsx", read_only=True, data_only=True)
    rows = list(wb.active.iter_rows(values_only=True))
    wb.close()

    chunks = []
    for row in rows[1:]:
        if not row[0]:
            continue
        item, desc, shelf_life, country, allergens, manufacturer, lead_time = (
            row[0], row[1] or "", row[10] or "", row[9] or "", row[14] or "", row[11] or "", row[12] or ""
        )
        chunks.append({
            "content": (
                f"Item: {item} | Description: {desc} | Shelf Life: {shelf_life} | "
                f"Country of Origin: {country} | Allergens: {allergens} | "
                f"Manufacturer: {manufacturer} | Lead Time: {lead_time}"
            ),
            "source": "ItemSpecMaster",
            "item_number": str(item),
        })
    print(f"ItemSpecMaster:       {len(chunks)} SKUs")
    return chunks


def load_vendor_master() -> list[dict]:
    """POP_VendorMaster.xlsx — one chunk per vendor/brand."""
    wb = openpyxl.load_workbook(DATA_DIR / "POP_VendorMaster.xlsx", read_only=True, data_only=True)
    rows = list(wb.active.iter_rows(values_only=True))
    wb.close()

    chunks = []
    for row in rows[1:]:
        if not row[0]:
            continue
        brand, product_line, category, vendor_id, status, country = (
            row[0] or "", row[1] or "", row[2] or "", row[4] or "", row[7] or "", row[8] or ""
        )
        skus, shipment_terms, payment_terms, currency = (
            row[11] or "", row[14] or "", row[15] or "", row[16] or ""
        )
        chunks.append({
            "content": (
                f"Brand: {brand} | Product Line: {product_line} | Category: {category} | "
                f"Vendor ID: {vendor_id} | Status: {status} | Country: {country} | "
                f"SKUs: {skus} | Shipment Terms: {shipment_terms} | "
                f"Payment Terms: {payment_terms} | Currency: {currency}"
            ),
            "source": "VendorMaster",
            "vendor_id": str(vendor_id),
            "brand": str(brand),
        })
    print(f"VendorMaster:         {len(chunks)} vendors")
    return chunks


def load_inventory() -> list[dict]:
    """POP_InventorySnapshot.xlsx — combine SF + NJ per item."""
    wb = openpyxl.load_workbook(DATA_DIR / "POP_InventorySnapshot.xlsx", read_only=True, data_only=True)

    inventory: dict[str, dict] = {}
    for sheet_name in wb.sheetnames:
        site = "sf" if "1" in sheet_name or "SF" in sheet_name.upper() else "nj"
        for row in list(wb[sheet_name].iter_rows(values_only=True))[1:]:
            if not row[0]:
                continue
            item = str(row[0]).strip()
            desc = str(row[1]).strip() if row[1] else ""
            avail = int(row[2] or 0)
            on_hand = int(row[3] or 0)
            if item not in inventory:
                inventory[item] = {"desc": desc, "sf_avail": 0, "nj_avail": 0, "sf_on_hand": 0, "nj_on_hand": 0}
            inventory[item][f"{site}_avail"] += avail
            inventory[item][f"{site}_on_hand"] += on_hand
    wb.close()

    chunks = []
    for item, d in inventory.items():
        total = d["sf_avail"] + d["nj_avail"]
        chunks.append({
            "content": (
                f"Item: {item} | Description: {d['desc']} | "
                f"SF Available: {d['sf_avail']} | NJ Available: {d['nj_avail']} | "
                f"Total Available: {total} | SF On Hand: {d['sf_on_hand']} | NJ On Hand: {d['nj_on_hand']}"
            ),
            "source": "InventorySnapshot",
            "item_number": item,
        })
    print(f"InventorySnapshot:    {len(chunks)} items")
    return chunks


def load_sales_history(top_n: int = 200) -> list[dict]:
    """POP_SalesTransactionHistory.csv — aggregate by item, keep top N by quantity."""
    sales: dict[str, dict] = {}
    with open(DATA_DIR / "POP_SalesTransactionHistory.csv", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            item = row.get("ITEMNMBR", "").strip()
            if not item:
                continue
            qty = float(row.get("QTYBSUOM") or 0)
            revenue = float(row.get("XTNDPRCE_adj") or 0)
            state = row.get("STATE", "").strip()
            if item not in sales:
                sales[item] = {"desc": row.get("ITEMDESC", "").strip(), "qty": 0.0, "revenue": 0.0, "states": set()}
            sales[item]["qty"] += qty
            sales[item]["revenue"] += revenue
            if state:
                sales[item]["states"].add(state)

    top = sorted(sales.items(), key=lambda x: x[1]["qty"], reverse=True)[:top_n]
    chunks = []
    for item, d in top:
        chunks.append({
            "content": (
                f"Item: {item} | Description: {d['desc']} | "
                f"Total Units Sold: {int(d['qty'])} | Total Revenue: ${d['revenue']:,.0f} | "
                f"Key States: {', '.join(sorted(d['states'])[:5])}"
            ),
            "source": "SalesHistory",
            "item_number": item,
        })
    print(f"SalesHistory:         {len(chunks)} top items (of {len(sales)} total)")
    return chunks


def _is_readable(text: str) -> bool:
    """Return True if the page has mostly ASCII-printable characters."""
    if len(text) < 50:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128 and c.isprintable())
    return ascii_count / len(text) > 0.85


def load_catalog_pdf() -> list[dict]:
    """POP_Catalog_2024.pdf — one chunk per readable page."""
    reader = pypdf.PdfReader(str(DATA_DIR / "POP_Catalog_2024.pdf"))
    chunks = []
    for i, page in enumerate(reader.pages):
        text = " ".join((page.extract_text() or "").split())
        if not _is_readable(text):
            continue
        chunks.append({
            "content": f"[Catalog p{i + 1}] {text[:1200]}",
            "source": "Catalog",
            "page": i + 1,
        })
    print(f"Catalog PDF:          {len(chunks)} readable pages")
    return chunks


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    api_key = settings.gemini_api_key
    qdrant_url = settings.qdrant_url or "http://localhost:6333"

    if not api_key:
        print("ERROR: GEMINI_API_KEY not set.")
        sys.exit(1)

    print(f"Connecting to Qdrant at {qdrant_url} ...")
    qdrant = QdrantClient(url=qdrant_url, timeout=10)
    genai_client = genai.Client(api_key=api_key)

    # Recreate collection for a clean ingest
    existing = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION_NAME in existing:
        qdrant.delete_collection(COLLECTION_NAME)
        print(f"Dropped existing '{COLLECTION_NAME}' collection")
    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    print(f"Created '{COLLECTION_NAME}' collection\n")

    chunks: list[dict] = []
    chunks += load_item_specs()
    chunks += load_vendor_master()
    chunks += load_inventory()
    chunks += load_sales_history()
    chunks += load_catalog_pdf()

    print(f"\nTotal: {len(chunks)} chunks — embedding and upserting ...")
    upsert_chunks(qdrant, genai_client, chunks)
    print("\nDone. PoP documents are now searchable.")


if __name__ == "__main__":
    main()
