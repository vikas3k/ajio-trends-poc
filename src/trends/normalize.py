"""Clean and normalize the raw Impetus trend-forecast attributes.

The raw export is dirty in three ways that block good trend naming:
  1. Inconsistent casing  ("Black"/"black", "SOLID"/"solid"/"Solid")
  2. Mojibake             ("Tâ€'shirts" = T-shirts, a mis-encoded U+2011 hyphen)
  3. Overlapping columns  (Pattern and Print both carry "SOLID"/"STRIPES"/...)

Two-level design
----------------
Every attribute map has the shape:
    raw_value (lowercase) -> (display, family)

- display : human-readable name used in trend naming (e.g. "Rust", "Cobalt Blue")
- family  : coarse cluster key that groups near-synonyms (e.g. "Warm Tones", "Blue")

Clustering uses `family` so similar things group together.
Agent 2 sees `display` so it can name trends precisely ("Rust" ≠ "Mustard").

Values NOT in the map fall through: display = titlecase(raw), family = display.
Run `scripts/audit_mappings.py` after loading new Impetus data to find gaps.
"""
from __future__ import annotations

import re

import pandas as pd

# Generic / non-descriptive pattern tokens — treated as "no real pattern".
_GENERIC_PATTERN = {"", "solid", "plain", "printed", "none", "self design"}


def _fix_mojibake(s: str) -> str:
    """Repair mis-encoded U+2011 NON-BREAKING HYPHEN in this export.

    The sequence shows up as three bytes (0xC3A2 0xE282AC 0xE28098 or 0x27)
    depending on how the CSV was saved. Replace both variants with a plain hyphen.
    """
    # U+2018 LEFT SINGLE QUOTATION MARK variant (most common in this export)
    s = s.replace("â€‘", "-")
    # U+0027 APOSTROPHE variant (fallback)
    s = s.replace("â€'", "-")
    return s


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
        if "-" in p:
            out.append("-".join(w.capitalize() for w in p.split("-")))
        elif i > 0 and p.lower() in small:
            out.append(p.lower())
        else:
            out.append(p.capitalize())
    return " ".join(out)


# ---------------------------------------------------------------------------
# COLOR
# Two-level: raw (lowercase) -> (display, family)
#
# Family design principles:
#   - Neutrals (Black, White, Grey, Beige, Ivory, Cream) stay distinct —
#     they drive very different aesthetics.
#   - Trend colours that are standalone buzzwords keep their own family
#     (Butter Yellow, Cobalt Blue, Sage Green, Blush Pink, Hot Pink).
#   - Near-synonyms that aren't buzzwords collapse into a broad family
#     (Rust/Terracotta/Brick → Warm Tones; Navy/Cobalt/Royal → Blue).
# ---------------------------------------------------------------------------
_COLOR_MAP: dict[str, tuple[str, str]] = {
    # Blacks & Whites
    "black":          ("Black",        "Black"),
    "white":          ("White",        "White"),
    "off white":      ("Off-White",    "White"),
    "ivory":          ("Ivory",        "White"),
    "cream":          ("Cream",        "White"),
    "snow":           ("Snow",         "White"),

    # Greys
    "grey":           ("Grey",         "Grey"),
    "gray":           ("Grey",         "Grey"),
    "charcoal":       ("Charcoal",     "Grey"),
    "silver":         ("Silver",       "Grey"),
    "slate":          ("Slate",        "Grey"),
    "ash":            ("Ash",          "Grey"),

    # Neutrals / Earth
    "beige":          ("Beige",        "Neutral"),
    "neutral":        ("Neutral",      "Neutral"),
    "khaki":          ("Khaki",        "Neutral"),
    "camel":          ("Camel",        "Neutral"),
    "tan":            ("Tan",          "Neutral"),
    "sand":           ("Sand",         "Neutral"),
    "stone":          ("Stone",        "Neutral"),
    "taupe":          ("Taupe",        "Neutral"),
    "ecru":           ("Ecru",         "Neutral"),
    "nude":           ("Nude",         "Neutral"),
    "skin":           ("Skin",         "Neutral"),

    # Browns / Mocha (Mocha Girl is a trend buzzword — keep distinct)
    "brown":          ("Brown",        "Brown"),
    "mocha":          ("Mocha",        "Brown"),
    "chocolate":      ("Chocolate",    "Brown"),
    "coffee":         ("Coffee",       "Brown"),
    "espresso":       ("Espresso",     "Brown"),
    "walnut":         ("Walnut",       "Brown"),
    "chestnut":       ("Chestnut",     "Brown"),

    # Warm Tones (Rust/Terracotta/Brick — not the same but cluster together)
    "rust":           ("Rust",         "Warm Tones"),
    "terracotta":     ("Terracotta",   "Warm Tones"),
    "brick":          ("Brick",        "Warm Tones"),
    "copper":         ("Copper",       "Warm Tones"),
    "burnt orange":   ("Burnt Orange", "Warm Tones"),
    "amber":          ("Amber",        "Warm Tones"),

    # Reds
    "red":            ("Red",          "Red"),
    "maroon":         ("Maroon",       "Red"),
    "burgundy":       ("Burgundy",     "Red"),
    "wine":           ("Wine",         "Red"),
    "cherry":         ("Cherry",       "Red"),
    "crimson":        ("Crimson",      "Red"),
    "scarlet":        ("Scarlet",      "Red"),

    # Pinks (Hot Pink is a trend buzzword — keep distinct)
    "pink":           ("Pink",         "Pink"),
    "blush":          ("Blush Pink",   "Pink"),
    "blush pink":     ("Blush Pink",   "Pink"),
    "baby pink":      ("Baby Pink",    "Pink"),
    "dusty pink":     ("Dusty Pink",   "Pink"),
    "hot pink":       ("Hot Pink",     "Hot Pink"),   # standalone trend
    "fuchsia":        ("Fuchsia",      "Hot Pink"),
    "magenta":        ("Magenta",      "Hot Pink"),
    "rose":           ("Rose",         "Pink"),
    "mauve":          ("Mauve",        "Pink"),
    "peach":          ("Peach",        "Pink"),
    "salmon":         ("Salmon",       "Pink"),
    "coral":          ("Coral",        "Pink"),

    # Oranges
    "orange":         ("Orange",       "Orange"),
    "apricot":        ("Apricot",      "Orange"),
    "tangerine":      ("Tangerine",    "Orange"),

    # Yellows (Butter Yellow is a trend buzzword — keep distinct)
    "yellow":         ("Yellow",       "Yellow"),
    "butter yellow":  ("Butter Yellow","Butter Yellow"),  # standalone trend
    "butter":         ("Butter Yellow","Butter Yellow"),
    "mustard":        ("Mustard",      "Yellow"),
    "golden":         ("Golden",       "Yellow"),
    "gold":           ("Gold",         "Yellow"),
    "lemon":          ("Lemon",        "Yellow"),
    "lime":           ("Lime",         "Yellow"),

    # Greens (Sage Green is a trend buzzword — keep distinct)
    "green":          ("Green",        "Green"),
    "sage":           ("Sage Green",   "Sage Green"),    # standalone trend
    "sage green":     ("Sage Green",   "Sage Green"),
    "olive":          ("Olive",        "Green"),
    "khaki green":    ("Khaki Green",  "Green"),
    "forest":         ("Forest Green", "Green"),
    "forest green":   ("Forest Green", "Green"),
    "mint":           ("Mint",         "Green"),
    "teal":           ("Teal",         "Teal"),          # distinct — blue-green
    "emerald":        ("Emerald",      "Green"),
    "bottle green":   ("Bottle Green", "Green"),
    "dark green":     ("Dark Green",   "Green"),

    # Blues (Cobalt Blue is a trend buzzword — keep distinct)
    "blue":           ("Blue",         "Blue"),
    "navy":           ("Navy",         "Blue"),
    "cobalt":         ("Cobalt Blue",  "Cobalt Blue"),   # standalone trend
    "cobalt blue":    ("Cobalt Blue",  "Cobalt Blue"),
    "royal blue":     ("Royal Blue",   "Blue"),
    "sky blue":       ("Sky Blue",     "Blue"),
    "baby blue":      ("Baby Blue",    "Blue"),
    "denim blue":     ("Denim Blue",   "Blue"),
    "steel blue":     ("Steel Blue",   "Blue"),
    "powder blue":    ("Powder Blue",  "Blue"),
    "electric blue":  ("Electric Blue","Cobalt Blue"),
    "indigo":         ("Indigo",       "Blue"),
    "periwinkle":     ("Periwinkle",   "Blue"),
    "aqua":           ("Aqua",         "Teal"),
    "turquoise":      ("Turquoise",    "Teal"),

    # Purples
    "purple":         ("Purple",       "Purple"),
    "violet":         ("Violet",       "Purple"),
    "lavender":       ("Lavender",     "Purple"),
    "lilac":          ("Lilac",        "Purple"),
    "plum":           ("Plum",         "Purple"),

    # Multi / Special
    "multi":          ("Multi",        "Multi"),
    "multicolor":     ("Multi",        "Multi"),
    "multicolour":    ("Multi",        "Multi"),
    "printed":        ("Printed",      "Multi"),
    "tie dye":        ("Tie-Dye",      "Multi"),
    "tie & dye":      ("Tie-Dye",      "Multi"),
    "ombre":          ("Ombre",        "Multi"),
}


def _color_display(s: str) -> str:
    entry = _COLOR_MAP.get(s.strip().lower())
    return entry[0] if entry else _titlecase(s.lower())


def _color_family(s: str) -> str:
    entry = _COLOR_MAP.get(s.strip().lower())
    return entry[1] if entry else _titlecase(s.lower())


# ---------------------------------------------------------------------------
# PATTERN (unified Print + Pattern)
# Single-level — pattern families are already distinct enough.
# ---------------------------------------------------------------------------
_PATTERN_MAP: dict[str, str] = {
    "floral":              "Floral",
    "stripes":             "Stripes",
    "checks":              "Checks",
    "plaid":               "Checks",
    "tartan":              "Checks",
    "houndstooth":         "Checks",
    "color block":         "Colour Block",
    "colour block":        "Colour Block",
    "brand logo":          "Logo / Graphic",
    "typography":          "Logo / Graphic",
    "graphic":             "Logo / Graphic",
    "graphics":            "Logo / Graphic",
    "varsity":             "Logo / Graphic",
    "sports":              "Logo / Graphic",
    "cartoon characters":  "Logo / Graphic",
    "conversational":      "Logo / Graphic",
    "people and places":   "Logo / Graphic",
    "slogan":              "Logo / Graphic",
    "abstract":            "Abstract / Geometric",
    "geometric":           "Abstract / Geometric",
    "aztec":               "Abstract / Geometric",
    "tribal":              "Abstract / Geometric",
    "motif":               "Abstract / Geometric",
    "tile":                "Abstract / Geometric",
    "ikat":                "Abstract / Geometric",
    "animal":              "Animal",
    "animal print":        "Animal",
    "leopard":             "Animal",
    "zebra":               "Animal",
    "camouflage":          "Animal",
    "snake":               "Animal",
    "paisley":             "Ethnic / Block",
    "block print":         "Ethnic / Block",
    "kalamkari":           "Ethnic / Block",
    "batik":               "Ethnic / Block",
    "schiffli":            "Texture / Self",
    "self design":         "Texture / Self",
    "structured":          "Texture / Self",
    "embroidered":         "Texture / Self",
    "lace":                "Texture / Self",
    "jacquard":            "Texture / Self",
    "polka dots":          "Polka Dots",
    "dots":                "Polka Dots",
    "ombre":               "Dyed / Wash",
    "tie & dye":           "Dyed / Wash",
    "tie dye":             "Dyed / Wash",
    "dyed":                "Dyed / Wash",
    "faded":               "Dyed / Wash",
    "washed":              "Dyed / Wash",
}


def _unified_pattern(print_v: str, pattern_v: str) -> str:
    """Pick the most descriptive pattern across the Print and Pattern columns."""
    for cand in (print_v, pattern_v):
        c = cand.strip().lower()
        if c and c not in _GENERIC_PATTERN:
            return _PATTERN_MAP.get(c, _titlecase(c))
    return "Solid"


# ---------------------------------------------------------------------------
# STYLE
# Two-level: raw (lowercase) -> (display, family)
#
# Family design principles:
#   - Fit styles (Regular, Slim, Tapered, Relaxed, Oversized) stay DISTINCT
#     because they drive different trend clusters and shopper intent.
#   - Silhouette styles (Wide Leg, A-Line, Bodycon) stay distinct.
#   - Minor variants of the same silhouette collapse (Paperbag → Wide / Flared).
# ---------------------------------------------------------------------------
_STYLE_MAP: dict[str, tuple[str, str]] = {
    # Fit styles — keep distinct
    "regular":        ("Regular Fit",    "Regular Fit"),
    "slim":           ("Slim Fit",       "Slim Fit"),
    "tapered":        ("Tapered",        "Tapered"),
    "skinny":         ("Skinny",         "Slim Fit"),      # near-synonym of slim
    "fitted":         ("Fitted",         "Slim Fit"),

    # Relaxed / Oversized
    "relaxed":        ("Relaxed",        "Relaxed / Loose"),
    "oversized":      ("Oversized",      "Relaxed / Loose"),
    "loose":          ("Loose",          "Relaxed / Loose"),
    "blouson":        ("Blouson",        "Relaxed / Loose"),
    "balloon":        ("Balloon",        "Relaxed / Loose"),
    "longline":       ("Longline",       "Relaxed / Loose"),
    "layered":        ("Layered",        "Relaxed / Loose"),
    "boxy":           ("Boxy",           "Relaxed / Loose"),

    # Straight / Classic
    "straight":       ("Straight",       "Straight / Classic"),
    "classic":        ("Classic",        "Straight / Classic"),
    "button down":    ("Button-Down",    "Straight / Classic"),
    "shift":          ("Shift",          "Straight / Classic"),
    "column":         ("Column",         "Straight / Classic"),

    # Wide / Flared
    "wide leg":       ("Wide-Leg",       "Wide / Flared"),
    "wide-leg":       ("Wide-Leg",       "Wide / Flared"),
    "flared":         ("Flared",         "Wide / Flared"),
    "paperbag":       ("Paperbag",       "Wide / Flared"),
    "bootcut":        ("Bootcut",        "Wide / Flared"),
    "palazzo":        ("Palazzo",        "Wide / Flared"),
    "culottes":       ("Culottes",       "Wide / Flared"),
    "bell bottom":    ("Bell Bottom",    "Wide / Flared"),

    # A-Line / Skater
    "a-line":         ("A-Line",         "A-Line / Skater"),
    "a line":         ("A-Line",         "A-Line / Skater"),
    "fit and flare":  ("Fit and Flare",  "A-Line / Skater"),
    "tiered":         ("Tiered",         "A-Line / Skater"),
    "peplum":         ("Peplum",         "A-Line / Skater"),
    "handkerchief":   ("Handkerchief",   "A-Line / Skater"),
    "skater":         ("Skater",         "A-Line / Skater"),

    # Fitted / Bodycon
    "bodycon":        ("Bodycon",        "Fitted / Bodycon"),
    "pencil":         ("Pencil",         "Fitted / Bodycon"),
    "sheath":         ("Sheath",         "Fitted / Bodycon"),
    "corset":         ("Corset",         "Fitted / Bodycon"),
    "bandeau":        ("Bandeau",        "Fitted / Bodycon"),
    "tube":           ("Tube",           "Fitted / Bodycon"),

    # Distinct silhouettes
    "bubble hem":     ("Bubble Hem",     "A-Line / Skater"),
    "trapeze":        ("Trapeze",        "A-Line / Skater"),
    "twofer":         ("Twofer",         "Relaxed / Loose"),
    "cropped":        ("Cropped",        "Cropped"),
    "cargo":          ("Cargo",          "Utility"),
    "jogger":         ("Jogger",         "Utility"),
    "utility":        ("Utility",        "Utility"),
    "wrap":           ("Wrap",           "Wrap / Drape"),
    "draped":         ("Draped",         "Wrap / Drape"),
    "slip":           ("Slip",           "Slip / Cami"),
    "cami":           ("Cami",           "Slip / Cami"),
    "strappy":        ("Strappy",        "Slip / Cami"),
    "halter":         ("Halter",         "Slip / Cami"),
    "spaghetti":      ("Spaghetti",      "Slip / Cami"),
    "off shoulder":   ("Off-Shoulder",   "Statement Neckline"),
    "off-shoulder":   ("Off-Shoulder",   "Statement Neckline"),
    "one shoulder":   ("One-Shoulder",   "Statement Neckline"),
    "cold shoulder":  ("Cold-Shoulder",  "Statement Neckline"),
    "asymmetrical":   ("Asymmetric",     "Asymmetric"),
    "high low":       ("High-Low",       "Asymmetric"),
    "high-low":       ("High-Low",       "Asymmetric"),
    "cut-out":        ("Cut-Out",        "Cut-Out"),
    "cutout":         ("Cut-Out",        "Cut-Out"),
    "stylised":       ("Stylised",       "Stylised"),
    "pleated":        ("Pleated",        "Pleated"),
    "smocked":        ("Smocked",        "Smocked"),
    "gathered":       ("Gathered",       "Gathered"),
    "ruched":         ("Ruched",         "Fitted / Bodycon"),
    "empire":         ("Empire",         "A-Line / Skater"),
    "maxi":           ("Maxi",           "Maxi"),
    "midi":           ("Midi",           "Midi"),
    "mini":           ("Mini",           "Mini"),
}


def _style_display(s: str) -> str:
    entry = _STYLE_MAP.get(s.strip().lower())
    return entry[0] if entry else _titlecase(s.lower())


def _style_family(s: str) -> str:
    entry = _STYLE_MAP.get(s.strip().lower())
    return entry[1] if entry else _titlecase(s.lower())


# ---------------------------------------------------------------------------
# SUBCATEGORY
# Case-insensitive lookup (Impetus capitalisation is inconsistent across exports).
# Maps garment names → canonical family used as a clustering key.
# ---------------------------------------------------------------------------
_SUBCAT_MAP: dict[str, str] = {
    # Denim
    "jeans":                "Denim",
    "jeggings":             "Denim",
    "denim":                "Denim",

    # Trousers
    "pants":                "Trousers",
    "trousers":             "Trousers",
    "chinos":               "Trousers",
    "palazzos":             "Trousers",
    "culottes":             "Trousers",
    "capris":               "Trousers",
    "cargos":               "Trousers",

    # Joggers / Knit Bottoms
    "joggers":              "Joggers/Knit Bottoms",
    "knit bottoms":         "Joggers/Knit Bottoms",
    "trackpants":           "Joggers/Knit Bottoms",
    "sweatpants":           "Joggers/Knit Bottoms",

    # Leggings / Tights
    "leggings":             "Leggings/Tights",
    "tights":               "Leggings/Tights",
    "thermals":             "Leggings/Tights",
    "jeggings (tight fit)": "Leggings/Tights",

    # Shorts
    "shorts":               "Shorts",
    "bermudas":             "Shorts",
    "cycling shorts":       "Shorts",

    # Skirts
    "skirts":               "Skirts",
    "skorts":               "Skirts",
    "mini skirts":          "Skirts",

    # Tops
    "tops":                 "Tops",
    "tunics":               "Tops",
    "camisoles":            "Tops",
    "tanks & vests":        "Tops",
    "tank tops":            "Tops",
    "vests":                "Tops",
    "body suit":            "Tops",
    "bodysuit":             "Tops",
    "corset":               "Tops",
    "crop tops":            "Tops",
    "halter tops":          "Tops",

    # Shirts
    "shirts":               "Shirts",
    "polo":                 "Shirts",
    "polo shirts":          "Shirts",
    "formal shirts":        "Shirts",

    # T-shirts
    "t-shirts":             "T-shirts",
    "t shirts":             "T-shirts",
    "tshirts":              "T-shirts",
    "graphic tees":         "T-shirts",

    # Knitwear
    "sweaters":             "Knitwear",
    "flat knits":           "Knitwear",
    "knitwear":             "Knitwear",
    "pullovers":            "Knitwear",

    # Sweats / Hoodies
    "sweatshirts":          "Sweats/Hoodies",
    "hoodies":              "Sweats/Hoodies",
    "zip-up hoodies":       "Sweats/Hoodies",

    # Outerwear
    "jackets":              "Outerwear",
    "blazers":              "Outerwear",
    "coats":                "Outerwear",
    "over coats":           "Outerwear",
    "overcoats":            "Outerwear",
    "shrugs":               "Outerwear",
    "waist coats":          "Outerwear",
    "waistcoats":           "Outerwear",
    "bomber jackets":       "Outerwear",
    "denim jackets":        "Outerwear",
    "leather jackets":      "Outerwear",
    "windcheaters":         "Outerwear",

    # Suits
    "suits":                "Outerwear",

    # Co-ords / Sets
    "tracksuits":           "Co-ords/Sets",
    "sets":                 "Co-ords/Sets",
    "co-ords":              "Co-ords/Sets",
    "co ords":              "Co-ords/Sets",
    "coord sets":           "Co-ords/Sets",
    "matching sets":        "Co-ords/Sets",

    # Jumpsuits / Rompers
    "jumpsuit":             "Jumpsuits/Rompers",
    "jumpsuits":            "Jumpsuits/Rompers",
    "dungarees":            "Jumpsuits/Rompers",
    "romper":               "Jumpsuits/Rompers",
    "rompers":              "Jumpsuits/Rompers",
    "pinafore":             "Jumpsuits/Rompers",
    "playsuits":            "Jumpsuits/Rompers",

    # Dresses
    "dresses":              "Dresses",
    "maxi dresses":         "Dresses",
    "midi dresses":         "Dresses",
    "mini dresses":         "Dresses",
    "blazer dresses":       "Dresses",
    "cape dress":           "Dresses",
    "empire":               "Dresses",
    "frocks":               "Dresses",
    "gown":                 "Dresses",
    "gowns":                "Dresses",
    "jumper dress":         "Dresses",
    "nightie":              "Dresses",
    "sheath":               "Dresses",
    "kaftan":               "Dresses",
    "drop-waist":           "Dresses",
    "high-low":             "Dresses",
    "shirt dresses":        "Dresses",
    "wrap dresses":         "Dresses",
}

# Build a lowercase-keyed lookup for case-insensitive matching.
_SUBCAT_LOWER: dict[str, str] = {k.lower(): v for k, v in _SUBCAT_MAP.items()}


def _subcat_family(s: str) -> str:
    return _SUBCAT_LOWER.get(s.strip().lower(), _titlecase(s))


# ---------------------------------------------------------------------------
# Length — no family needed, just clean display
# ---------------------------------------------------------------------------
def _length(s: str) -> str:
    return _titlecase(s.lower()) if s else ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

NUMERIC_COLS = [
    "Confidence_Score", "Current_Score", "Current_Rank",
    "Predicted_Score_1Mo", "Predicted_Score_2Mo",
    "Predicted_Score_3Mo", "Predicted_Score_4Mo",
    "Score_Change_1Mo", "Score_Change_4Mo",
]

# Columns that unmapped-value logging should track (for audit_mappings.py).
MAPPED_COLS = {
    "Color":       (_COLOR_MAP,   "color"),
    "Style":       (_STYLE_MAP,   "style"),
    "Subcategory": (_SUBCAT_LOWER, "subcategory"),
}


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `df` with added clean `n_*` and `*_family` columns."""
    out = df.copy()

    text_cols = [
        "Gender", "Category", "Subcategory", "Color", "Pattern", "Print",
        "Style", "Neckline", "Sleeve", "Length", "Fabric", "Alert_Type",
        "Recent_Momentum", "Breakout_Likelihood", "Top_Performer_Today",
    ]
    for c in text_cols:
        if c in out.columns:
            out[c] = out[c].map(_clean)

    out["n_gender"]     = out["Gender"].map(_titlecase)
    out["n_category"]   = out["Category"].map(_titlecase)
    out["n_subcategory"]= out["Subcategory"].map(lambda s: _titlecase(_fix_mojibake(s)))
    out["subcat_family"]= out["Subcategory"].map(_subcat_family)

    out["n_color"]      = out["Color"].map(_color_display)
    out["color_family"] = out["Color"].map(_color_family)

    out["n_pattern"]    = [
        _unified_pattern(p, pat)
        for p, pat in zip(out.get("Print", pd.Series("", index=out.index)),
                          out.get("Pattern", pd.Series("", index=out.index)))
    ]

    out["n_style"]      = out["Style"].map(_style_display)
    out["style_family"] = out["Style"].map(_style_family)
    out["n_length"]     = out["Length"].map(_length)
    out["n_fabric"]     = out["Fabric"].map(lambda s: _titlecase(s.lower()))
    out["n_neckline"]   = out["Neckline"].map(lambda s: _titlecase(s.lower())) if "Neckline" in out.columns else ""
    out["n_sleeve"]     = out["Sleeve"].map(lambda s: _titlecase(s.lower())) if "Sleeve" in out.columns else ""

    for c in NUMERIC_COLS:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    return out
