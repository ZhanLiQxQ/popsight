from __future__ import annotations

import json
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_print_lock = threading.Lock()
_model_lock = threading.Lock()
_model_cache: dict[str, Any] = {}

# Zero-shot labels tuned for grocery / beverage / supplement listings (English prompts work on mixed listings).
DEFAULT_GLINER_LABELS: list[str] = [
    "brand name",
    "product flavor",
    "package size",
    "sweetener or sugar claim",
    "dietary or health claim",
    "ingredient",
    "country of origin",
    "product form",
]


def _build_gliner_text(item: dict[str, Any], max_chars: int) -> str:
    name = (item.get("item_name") or "").strip()
    detail = (item.get("item_detail") or "").strip()
    blob = f"{name}. {detail}".strip()
    if len(blob) > max_chars:
        return blob[: max_chars - 1] + "…"
    return blob


def _normalize_entities(raw_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in raw_entities:
        text = (e.get("text") or "").strip()
        label = (e.get("label") or "").strip()
        if not text or not label:
            continue
        try:
            score = float(e.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        out.append({"text": text, "label": label, "score": round(score, 4)})
    # de-dupe (label, text lower)
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in out:
        key = (row["label"].lower(), row["text"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    deduped.sort(key=lambda r: r["score"], reverse=True)
    return deduped[:24]


def _compact_entities(entities: list[dict[str, Any]], max_parts: int = 14) -> str:
    parts: list[str] = []
    for e in entities[:max_parts]:
        parts.append(f'{e["label"]}: {e["text"]}')
    if not parts:
        return ""
    tail = "" if len(entities) <= max_parts else f" (+{len(entities) - max_parts} more)"
    return "; ".join(parts) + tail


def _load_model(model_id: str) -> Any:
    with _model_lock:
        cached = _model_cache.get(model_id)
        if cached is not None:
            return cached
        from gliner import GLiNER

        logger.warning("GLiNER loading model %r (first load can take a while)…", model_id)
        model = GLiNER.from_pretrained(model_id)
        _model_cache[model_id] = model
        return model


def _emit_console_block(title: str, payload: dict[str, Any]) -> None:
    line = json.dumps(payload, ensure_ascii=False, indent=2)
    block = f"\n{'=' * 72}\n[PopSight GLiNER] {title}\n{line}\n"
    with _print_lock:
        print(block, flush=True)


def enrich_items_with_gliner(
    items: list[dict[str, Any]],
    *,
    model_id: str,
    threshold: float,
    max_input_chars: int,
    batch_size: int,
    console_samples: int,
    labels: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Synchronously enrich compressed Amazon items with GLiNER entities.
    On import/model failure, attaches empty entity fields and logs once.
    """
    if not items:
        return items

    label_list = labels or DEFAULT_GLINER_LABELS

    try:
        model = _load_model(model_id)
    except Exception:
        logger.exception("GLiNER unavailable; skipping entity extraction.")
        for it in items:
            it["gliner_entities"] = []
            it["item_entities_compact"] = ""
        return items

    texts = [_build_gliner_text(it, max_input_chars) for it in items]
    try:
        raw_lists = model.inference(
            texts,
            label_list,
            threshold=threshold,
            batch_size=max(1, min(batch_size, len(texts))),
            flat_ner=True,
        )
    except Exception:
        logger.exception("GLiNER inference failed; skipping entity extraction.")
        for it in items:
            it["gliner_entities"] = []
            it["item_entities_compact"] = ""
        return items

    samples = max(0, min(console_samples, len(items)))

    if len(raw_lists) != len(items):
        logger.warning(
            "GLiNER inference length mismatch (items=%s, raw_lists=%s); padding with empty lists.",
            len(items),
            len(raw_lists),
        )
        raw_lists = list(raw_lists) + [[]] * max(0, len(items) - len(raw_lists))
        raw_lists = raw_lists[: len(items)]

    for idx, it in enumerate(items):
        text = texts[idx]
        raw_ents = raw_lists[idx] if idx < len(raw_lists) else []
        normalized = _normalize_entities(list(raw_ents or []))
        it["gliner_entities"] = normalized
        it["item_entities_compact"] = _compact_entities(normalized)

        if idx < samples:
            preview_len = 700
            truncated = text if len(text) <= preview_len else text[: preview_len - 1] + "…"
            request_payload = {
                "schema": "popsight.gliner_request/v1",
                "model_id": model_id,
                "labels": label_list,
                "threshold": threshold,
                "batch_size": batch_size,
                "item_index": idx,
                "item_name": it.get("item_name"),
                "input_char_length": len(text),
                "input_text": truncated,
            }
            response_payload = {
                "schema": "popsight.gliner_response/v1",
                "item_index": idx,
                "item_name": it.get("item_name"),
                "entity_count": len(normalized),
                "entities": normalized,
            }
            merged_payload = {
                "schema": "popsight.amazon_item_after_gliner/v1",
                "item_index": idx,
                "item": {
                    "item_name": it.get("item_name"),
                    "item_detail": it.get("item_detail"),
                    "item_reviews_summarized": it.get("item_reviews_summarized"),
                    "item_price": it.get("item_price"),
                    "item_sold_quantity": it.get("item_sold_quantity"),
                    "item_rating": it.get("item_rating"),
                    "item_review_count": it.get("item_review_count"),
                    "asin": it.get("asin"),
                    "source_url": it.get("source_url"),
                    "item_entities_compact": it.get("item_entities_compact"),
                    "gliner_entities": it.get("gliner_entities"),
                },
            }
            logger.info("[PopSight GLiNER] request JSON (item %s)", idx)
            logger.info("%s", json.dumps(request_payload, ensure_ascii=False))
            logger.info("[PopSight GLiNER] response JSON (item %s)", idx)
            logger.info("%s", json.dumps(response_payload, ensure_ascii=False))
            logger.info("[PopSight GLiNER] merged item JSON (item %s)", idx)
            logger.info("%s", json.dumps(merged_payload, ensure_ascii=False))

            _emit_console_block(f"request JSON (item {idx})", request_payload)
            _emit_console_block(f"response JSON (item {idx})", response_payload)
            _emit_console_block(f"merged item JSON (item {idx})", merged_payload)

    return items
