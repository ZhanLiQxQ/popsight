from __future__ import annotations

import re

# Curated high-signal terms for *automated pre-filtering* (not legal/compliance advice).
# Extend via POPSIGHT_FDA_BLOCKLIST_PATH env in Settings if needed later.
#
# `fda_banned` (NLP_Compressor / ingest): extra ingredient / drug names merged into the same matcher.
fda_banned: tuple[str, ...] = (
    "sibutramine",
    "fenfluramine",
    "dexfenfluramine",
    "phenolphthalein",
    "fluoxetine",
    "fluoxetina",
    "sildenafil",
    "tadalafil",
    "vardenafil",
)

FDA_RISK_PHRASES: tuple[str, ...] = (
    # Banned / high-risk dietary supplement ingredients (illustrative)
    "ephedra",
    "ephedrine alkaloids",
    "dmaa",
    "1,3-dimethylamylamine",
    "dmba",
    "bmpea",
    "picamilon",
    "phenibut",
    "tianeptine",
    "kratom",
    "mitragyna speciosa",
    "comfrey",
    "symphytum",
    "aristolochic acid",
    "chaparral",
    "germander",
    "yohimbe bark extract",
    "usnic acid",
    "kava kava",
    "pennyroyal oil",
    "sassafras oil",
    "safrole",
    "methylsynephrine",
    "dmha",
    "2-aminoisoheptane",
    "higenamine",
    "hordenine",
    "octodrine",
    # Unapproved drug claims in OTC-ish copy (coarse filter)
    "cures cancer",
    "treats covid",
    "fda approval pending",
)

FDA_BLOCKLIST: tuple[str, ...] = FDA_RISK_PHRASES + fda_banned

_WS = re.compile(r"[^a-z0-9]+")


def _normalize_for_match(text: str) -> str:
    lowered = text.lower()
    return f" {_WS.sub(' ', lowered).strip()} "


def fda_compliance_violation(*chunks: str | None) -> str | None:
    """
    Return a matched risk phrase if any chunk hits the blocklist, else None.
    """
    blob = _normalize_for_match(" ".join(c for c in chunks if c))
    if not blob.strip():
        return None
    for phrase in FDA_BLOCKLIST:
        needle = _normalize_for_match(phrase)
        needle_core = needle.strip()
        if len(needle_core) >= 3 and needle_core in blob:
            return phrase
    return None
