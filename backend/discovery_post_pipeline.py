"""
Node 4–6 helpers: rank compressed Amazon rows, light supply attach, Markdown summary.

This is a self-contained fallback (no full BM25 catalog stack). Replace with ``pipeline_agents`` /
``pipeline_sources`` when you restore those modules for production parity.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .config import DATA_DIR


def lanes_compressed_to_external_by_category(lanes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        cat = str(lane.get("category_label") or lane.get("category_id") or "Unknown")
        rows: list[dict[str, Any]] = []
        for it in lane.get("compressed_items") or []:
            if not isinstance(it, dict):
                continue
            nm = str(it.get("item_name") or "").strip()
            if not nm:
                continue
            rows.append(
                {
                    "item_name": nm,
                    "item_sold_quantity": int(it.get("item_sold_quantity") or 0),
                    "item_price": it.get("item_price"),
                    "item_review_summarized": str(
                        it.get("item_reviews_summarized") or it.get("item_review_summarized") or ""
                    ),
                }
            )
        if rows:
            out.append({"category": cat, "top_products": rows[:16]})
    return out


def derive_scan_topic(lanes: list[dict[str, Any]]) -> str:
    labels = [str(l.get("category_label") or "").strip() for l in lanes if isinstance(l, dict)]
    labels = [x for x in labels if x]
    return " · ".join(labels[:5]) if labels else "discovery"


def _read_internal_metrics_stub() -> list[dict[str, Any]]:
    """Best-effort velocity rows from POP sales CSV when present."""
    path = DATA_DIR / "POP_SalesTransactionHistory.csv"
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as f:
            r = csv.DictReader(f)
            rows = list(r)[:400]
        if not rows:
            return []
        keys = {k.lower(): k for k in rows[0].keys()}
        desc_k = keys.get("itemdesc") or keys.get("description") or keys.get("item_desc")
        qty_k = keys.get("qty") or keys.get("quantity") or keys.get("units")
        if not desc_k:
            return []
        out: list[dict[str, Any]] = []
        for row in rows[:120]:
            nm = str(row.get(desc_k) or "").strip()
            if not nm:
                continue
            q = 0
            if qty_k:
                try:
                    q = int(float(str(row.get(qty_k) or "0").replace(",", "")))
                except ValueError:
                    q = 0
            out.append(
                {
                    "item_name": nm,
                    "product_id": "",
                    "internal_sales_velocity": min(0.95, 0.15 + (q % 5000) / 12000.0),
                    "inventory_health": 0.5,
                }
            )
        return out[:80]
    except OSError:
        return []


def load_pipeline_bundle(
    scan_topic: str,
    *,
    external_by_category: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    internal = _read_internal_metrics_stub()
    bundle: dict[str, Any] = {
        "scan_topic": scan_topic,
        "external_by_category": list(external_by_category or []),
        "internal_metrics": internal,
        "vendors": [
            {"name": "Selangor D.E. Malaysia (demo)", "region": "Malaysia", "categories": ["snacks", "beverages", "tea"]},
            {"name": "Guangzhou OEM Collective (demo)", "region": "China", "categories": ["beverages", "functional"]},
        ],
        "transfers": [],
        "catalog_rag_chunks": [],
    }
    return bundle, internal


def _slug(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else " " for c in s).strip()


def run_product_ranking(
    *,
    topic: str,
    external_by_category: list[dict[str, Any]],
    internal_metrics: list[dict[str, Any]],
    catalog_excerpt: str = "",
    catalog_rag_chunks: list[str] | None = None,
) -> list[dict[str, Any]]:
    _ = topic, catalog_excerpt, catalog_rag_chunks
    internal_by_slug = {_slug(str(m.get("item_name") or "")): m for m in internal_metrics}

    ranked: list[dict[str, Any]] = []
    for block in external_by_category:
        cat = str(block.get("category") or "Unknown")
        for p in block.get("top_products") or []:
            name = str(p.get("item_name") or "").strip()
            if not name:
                continue
            sold = int(p.get("item_sold_quantity") or 0)
            row = internal_by_slug.get(_slug(name))
            internal_match = row is not None
            vel = float(row.get("internal_sales_velocity", 0)) if row else 0.0
            inv = float(row.get("inventory_health", 0)) if row else 0.0
            if sold >= 11_000 and not internal_match:
                pri, reason = "HIGH", "Strong external signal; no internal line match in demo CSV slice — assortment gap candidate."
            elif sold >= 11_000 and internal_match and vel < 0.42:
                pri, reason = "MEDIUM", "Strong external + weak internal velocity in demo snapshot — refresh opportunity."
            else:
                pri, reason = "LOW", "Below demo HIGH threshold or already covered in internal snapshot."
            ranked.append(
                {
                    "product_name": name,
                    "category": cat,
                    "priority": pri,
                    "reason": reason,
                    "external_sold_quantity": sold,
                    "item_price": p.get("item_price"),
                    "item_review_summarized": str(p.get("item_review_summarized") or ""),
                    "internal_match": internal_match,
                    "internal_sales_velocity": vel if row else None,
                    "inventory_health": inv if row else None,
                    "catalog_rag_hit": False,
                    "rank_score": round(min(1.0, sold / 22_000.0), 4),
                }
            )
    pri_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    ranked.sort(key=lambda r: (pri_order.get(str(r.get("priority") or "LOW"), 9), -float(r.get("rank_score") or 0.0)))
    return ranked


def run_supply_planner(
    ranked: list[dict[str, Any]],
    vendors: list[dict[str, Any]],
    transfers: list[dict[str, Any]],
    *,
    internal_metrics: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    _ = transfers, internal_metrics
    actionable: list[dict[str, Any]] = []
    v = vendors[0] if vendors else {"name": "Demo Vendor", "region": "Asia"}
    for r in ranked:
        pri = str(r.get("priority") or "LOW")
        if pri == "LOW":
            continue
        sold = int(r.get("external_sold_quantity") or 0)
        est = round(10.0 + min(6.0, sold / 6000.0), 2)
        actionable.append(
            {
                "product_name": r.get("product_name"),
                "category": r.get("category"),
                "priority": pri,
                "reason": r.get("reason"),
                "supplier": v.get("name"),
                "supplier_region": v.get("region"),
                "estimated_cost": est,
                "external_sold_quantity": sold,
                "rank_score": r.get("rank_score"),
                "needs_vendor_development": False,
            }
        )
    return actionable


def run_summary_agent(
    *, topic: str, actionable: list[dict[str, Any]], ranked_full: list[dict[str, Any]]
) -> tuple[str, str, dict[str, Any]]:
    _ = ranked_full
    lines = [
        f"## Executive summary — {topic}",
        "",
        "### Action items",
        "",
    ]
    if not actionable:
        lines.append("- No SKUs passed the demo supply screen; triage the **ranked** list in the UI.")
    else:
        for a in actionable[:10]:
            lines.append(
                f"- **{a.get('product_name')}**: engage **{a.get('supplier')}** ({a.get('supplier_region')}); "
                f"demo landed est. **${a.get('estimated_cost')}**."
            )
    md = "\n".join(lines)
    return md, md, {"actionable_count": len(actionable), "ranked_count": len(ranked_full)}
