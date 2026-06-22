"""Clean and normalize the raw Impetus trend-forecast attributes.

The raw export is dirty in three ways that block good trend naming:
  1. Inconsistent casing  ("Black"/"black", "SOLID"/"solid"/"Solid")
  2. Mojibake             ("Tâ€‘shirts" = T-shirts, a mis-encoded U+2011 hyphen)
  3. Overlapping columns  (Pattern and Print both carry "SOLID"/"STRIPES"/...)

This module produces, per row, a set of clean canonical attribute values plus
coarse *family* fields used for clustering. Display fields are Title-cased and
deduped; family fields collapse near-synonyms so similar trends group together.
"""
from __future__ import annotations

import re

import pandas as pd

# Generic / non-descriptive pattern tokens — treated as "no real pattern".
_GENERIC_PATTERN = {"", "solid", "plain", "printed", "none", "self design"}


def _fix_mojibake(s: str) -> str:
    """Repair the one mojibake sequence in this export (mis-encoded U+2011)."""
    return s.replace("â€‘", "-").replace("â€‘", "-")


def _clean(s) -> str:
    if not isinstance(s, str):
        return ""
    s = _fix_mojibake(s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _titlecase(s: str) -> str:
    """Title-case while keeping short joiners lowercase (A-Line, Fit and Flare)."""
    if not s:
        return ""
    small = {"and", "of", "the", "&", "in", "on", "with"}
    parts = s.split(" ")
    out = []
    for i, p in enumerate(parts):
        if "-" in p:  # A-line -> A-Line
            out.append("-".join(w.capitalize() for w in p.split("-")))
        elif i > 0 and p.lower() in small:
            out.append(p.lower())
        else:
            out.append(p.capitalize())
    return " ".join(out)


# --- Color ------------------------------------------------------------------
# Map every casing/synonym to a single display color, then to a broad family.
_COLOR_FAMILY = {
    "navy": "Blue", "blue": "Blue",
    "gray": "Grey", "grey": "Grey",
    "black": "Black", "white": "White", "beige": "Neutral", "neutral": "Neutral",
    "brown": "Brown", "maroon": "Red", "red": "Red", "pink": "Pink",
    "green": "Green", "orange": "Orange", "purple": "Purple", "yellow": "Yellow",
}


def _color_display(s: str) -> str:
    return _titlecase(s.lower())


def _color_family(s: str) -> str:
    return _COLOR_FAMILY.get(s.lower(), _titlecase(s.lower()))


# --- Pattern (unified Print + Pattern) --------------------------------------
_PATTERN_FAMILY = {
    "floral": "Floral",
    "stripes": "Stripes",
    "checks": "Checks",
    "color block": "Colour Block",
    "brand logo": "Logo / Graphic", "typography": "Logo / Graphic",
    "graphic": "Logo / Graphic", "graphics": "Logo / Graphic",
    "varsity": "Logo / Graphic", "sports": "Logo / Graphic",
    "cartoon characters": "Logo / Graphic", "conversational": "Logo / Graphic",
    "people and places": "Logo / Graphic",
    "abstract": "Abstract / Geometric", "geometric": "Abstract / Geometric",
    "aztec": "Abstract / Geometric", "tribal": "Abstract / Geometric",
    "motif": "Abstract / Geometric", "tile": "Abstract / Geometric",
    "animal": "Animal", "camouflage": "Animal", "paisley": "Ethnic / Block",
    "block print": "Ethnic / Block", "schiffli": "Texture / Self",
    "self design": "Texture / Self", "structured": "Texture / Self",
    "embroidered": "Texture / Self", "lace": "Texture / Self",
    "polka dots": "Polka Dots", "ombre": "Dyed / Wash", "tie & dye": "Dyed / Wash",
    "dyed": "Dyed / Wash", "faded": "Dyed / Wash",
}


def _unified_pattern(print_v: str, pattern_v: str) -> str:
    """Pick the most descriptive pattern across the Print and Pattern columns.

    Decorative values (Floral, Stripes, Logo, ...) win over generic Solid/Plain.
    """
    for cand in (print_v, pattern_v):
        c = cand.lower()
        if c and c not in _GENERIC_PATTERN:
            return _PATTERN_FAMILY.get(c, _titlecase(c))
    return "Solid"


# --- Style ------------------------------------------------------------------
_STYLE_FAMILY = {
    "relaxed": "Relaxed / Loose", "oversized": "Relaxed / Loose",
    "blouson": "Relaxed / Loose", "balloon": "Relaxed / Loose",
    "longline": "Relaxed / Loose", "layered": "Relaxed / Loose",
    "straight": "Straight / Classic", "classic": "Straight / Classic",
    "button down": "Straight / Classic", "shift": "Straight / Classic",
    "wide leg": "Wide / Flared", "flared": "Wide / Flared",
    "paperbag": "Wide / Flared", "bootcut": "Wide / Flared",
    "a-line": "A-Line / Skater", "a line": "A-Line / Skater",
    "fit and flare": "A-Line / Skater", "tiered": "A-Line / Skater",
    "peplum": "A-Line / Skater", "handkerchief": "A-Line / Skater",
    "bodycon": "Fitted / Bodycon", "pencil": "Fitted / Bodycon",
    "sheath": "Fitted / Bodycon", "corset": "Fitted / Bodycon",
    "bandeau": "Fitted / Bodycon",
    "cropped": "Cropped", "cargo": "Utility", "jogger": "Utility",
    "wrap": "Wrap / Drape", "slip": "Slip / Cami", "cami": "Slip / Cami",
    "strappy": "Slip / Cami", "halter": "Slip / Cami",
    "off shoulder": "Statement Neckline", "one shoulder": "Statement Neckline",
    "asymmetrical": "Asymmetric", "high low": "Asymmetric",
    "cut-out": "Cut-Out", "stylised": "Stylised",
}


def _style_family(s: str) -> str:
    return _STYLE_FAMILY.get(s.lower(), _titlecase(s.lower()))


# --- Subcategory family -----------------------------------------------------
_SUBCAT_FAMILY = {
    "JEANS": "Denim", "JEGGINGS": "Denim",
    "PANTS": "Trousers", "TROUSERS": "Trousers", "Chinos": "Trousers",
    "PALAZZOS": "Trousers", "CULOTTES": "Trousers", "CAPRIS": "Trousers",
    "CARGOS": "Trousers", "Joggers": "Joggers/Knit Bottoms",
    "KNIT BOTTOMS": "Joggers/Knit Bottoms", "LEGGINGS": "Leggings/Tights",
    "TIGHTS": "Leggings/Tights", "Thermals": "Leggings/Tights",
    "SHORTS": "Shorts", "BERMUDAS": "Shorts", "SKORTS": "Skirts",
    "SKIRTS": "Skirts",
    "TOPS": "Tops", "TUNICS": "Tops", "CAMISOLES": "Tops",
    "TANKS & VESTS": "Tops", "BODY SUIT": "Tops", "Corset": "Tops",
    "SHIRTS": "Shirts", "POLO": "Shirts",
    "T-shirts": "T-shirts",
    "SWEATERS": "Knitwear", "FLAT KNITS": "Knitwear",
    "SWEATSHIRTS": "Sweats/Hoodies", "Hoodies": "Sweats/Hoodies",
    "JACKETS": "Outerwear", "BLAZERS": "Outerwear", "Coats": "Outerwear",
    "Over Coats": "Outerwear", "Shrugs": "Outerwear", "WAIST COATS": "Outerwear",
    "Tracksuits": "Co-ords/Sets", "Sets": "Co-ords/Sets",
    "JUMPSUIT": "Jumpsuits/Rompers", "Dungarees": "Jumpsuits/Rompers",
    "Romper": "Jumpsuits/Rompers", "Pinafore": "Jumpsuits/Rompers",
    "Maxi Dresses": "Dresses", "Blazer Dresses": "Dresses", "Cape Dress": "Dresses",
    "Empire": "Dresses", "Frocks": "Dresses", "Gown": "Dresses",
    "Jumper Dress": "Dresses", "Nightie": "Dresses", "Sheath": "Dresses",
    "KAFTAN": "Dresses", "Drop-Waist": "Dresses", "High-Low": "Dresses",
}


def _subcat_family(s: str) -> str:
    return _SUBCAT_FAMILY.get(s, _titlecase(s))


# --- Length -----------------------------------------------------------------
def _length(s: str) -> str:
    if not s:
        return ""
    return _titlecase(s.lower())


NUMERIC_COLS = [
    "Confidence_Score", "Current_Score", "Current_Rank",
    "Predicted_Score_1Mo", "Predicted_Score_2Mo",
    "Predicted_Score_3Mo", "Predicted_Score_4Mo",
    "Score_Change_1Mo", "Score_Change_4Mo",
]


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `df` with added clean `n_*` and `*_family` columns."""
    out = df.copy()

    # Clean raw text columns in place (casing, mojibake, whitespace).
    text_cols = [
        "Gender", "Category", "Subcategory", "Color", "Pattern", "Print",
        "Style", "Neckline", "Sleeve", "Length", "Fabric", "Alert_Type",
        "Recent_Momentum", "Breakout_Likelihood", "Top_Performer_Today",
    ]
    for c in text_cols:
        if c in out.columns:
            out[c] = out[c].map(_clean)

    out["n_gender"] = out["Gender"].map(_titlecase)
    out["n_category"] = out["Category"].map(_titlecase)
    out["n_subcategory"] = out["Subcategory"].map(lambda s: _titlecase(_fix_mojibake(s)))
    out["subcat_family"] = out["Subcategory"].map(_subcat_family)

    out["n_color"] = out["Color"].map(_color_display)
    out["color_family"] = out["Color"].map(_color_family)

    out["n_pattern"] = [
        _unified_pattern(p, pat) for p, pat in zip(out["Print"], out["Pattern"])
    ]
    out["n_style"] = out["Style"].map(lambda s: _titlecase(s.lower()))
    out["style_family"] = out["Style"].map(_style_family)
    out["n_length"] = out["Length"].map(_length)
    out["n_fabric"] = out["Fabric"].map(lambda s: _titlecase(s.lower()))
    out["n_neckline"] = out["Neckline"].map(lambda s: _titlecase(s.lower()))
    out["n_sleeve"] = out["Sleeve"].map(lambda s: _titlecase(s.lower()))

    for c in NUMERIC_COLS:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    return out
