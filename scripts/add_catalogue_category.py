"""
Adds/refreshes the catalogue_category column in agentic_trends.csv.

Many-to-many: a trend maps to one or more catalogue categories.
Values are pipe-separated e.g. "Women - Tops & Tshirts | Women - Jeans & Jeggings"

Logic:
  1. bucket_label  → primary catalogue category (always used when it matches)
  2. raw_signal garment list → additional categories ONLY when ≥2 garments are
     explicitly listed and they span different catalogue categories
     (i.e. genuinely cross-category trends like "Garment: Shirts, Kaftans, Co-ords")
"""

import csv
import re
from pathlib import Path

OUTPUT_CSV = Path(__file__).parent.parent / "output" / "agentic_trends.csv"

# ── Impetus bucket_label → AJIO catalogue category ───────────────────────────
# Derived from Impetus subcategory taxonomy × actual AJIO catalogue category list.
# Each bucket maps to exactly one primary catalogue category.

BUCKET_MAP = {
    # ── Men ──────────────────────────────────────────────────────────────────
    "Men × SHIRTS":        "Men - Shirts",
    "Men × POLO":          "Men - Tshirts",
    "Men × T-shirts":      "Men - Tshirts",
    "Men × TOPS":          "Men - Tshirts",          # generic topwear
    "Men × TANKS & VESTS": "Men - Vests",
    "Men × FLAT KNITS":    "Men - Sweaters & Cardigans",
    "Men × SWEATERS":      "Men - Sweaters & Cardigans",
    "Men × SWEATSHIRTS":   "Men - Sweatshirt & Hoodies",
    "Men × Hoodies":       "Men - Sweatshirt & Hoodies",
    "Men × BLAZERS":       "Men - Blazers & Waistcoats",
    "Men × WAIST COATS":   "Men - Blazers & Waistcoats",
    "Men × JACKETS":       "Men - Jackets & Coats",
    "Men × Coats":         "Men - Jackets & Coats",
    "Men × KAFTAN":        "Men - Kurtas",
    "Men × JEANS":         "Men - Jeans",
    "Men × JEGGINGS":      "Men - Jeans",
    "Men × TROUSERS":      "Men - Trousers & Pants",
    "Men × PANTS":         "Men - Trousers & Pants",
    "Men × Chinos":        "Men - Trousers & Pants",
    "Men × CARGOS":        "Men - Trousers & Pants",
    "Men × SHORTS":        "Men - Shorts & 3/4ths",
    "Men × BERMUDAS":      "Men - Shorts & 3/4ths",
    "Men × KNIT BOTTOMS":  "Men - Track Pants",
    "Men × Joggers":       "Men - Track Pants",
    "Men × Tracksuits":    "Men - Tracksuits",
    "Men × Thermals":      "Men - Thermal Wear",

    # ── Women ─────────────────────────────────────────────────────────────────
    "Women × SHIRTS":       "Women - Shirts, Tops & Tunic",
    "Women × TOPS":         "Women - Tops & Tshirts",
    "Women × T-shirts":     "Women - Tops & Tshirts",
    "Women × POLO":         "Women - Tops & Tshirts",
    "Women × TANKS & VESTS":"Women - Tops & Tshirts",
    "Women × CAMISOLES":    "Women - Camisoles & Slips",
    "Women × BODY SUIT":    "Women - Tops & Tshirts",
    "Women × Corset":       "Women - Tops & Tshirts",
    "Women × FLAT KNITS":   "Women - Sweaters & Cardigans",
    "Women × SWEATSHIRTS":  "Women - Sweatshirt & Hoodies",
    "Women × Hoodies":      "Women - Sweatshirt & Hoodies",
    "Women × BLAZERS":      "Women - Blazers & Waistcoats",
    "Women × WAIST COATS":  "Women - Blazers & Waistcoats",
    "Women × Shrugs":       "Women - Shrugs & Jackets",
    "Women × JACKETS":      "Women - Jackets & Shrugs",
    "Women × TUNICS":       "Women - Kurtis & Tunics",
    "Women × KAFTAN":       "Women - Kurtas",
    "Women × Sets":         "Women - Co-ord Sets",
    "Women × Tracksuits":   "Women - Tracksuits",
    "Women × Thermals":     "Women - Thermal Wear",
    # Dresses
    "Women × Empire":        "Women - Dresses & Jumpsuits",
    "Women × Blazer Dresses":"Women - Dresses & Jumpsuits",
    "Women × Gown":          "Women - Dresses & Gowns",
    "Women × High-Low":      "Women - Dresses & Jumpsuits",
    "Women × Pinafore":      "Women - Dresses & Jumpsuits",
    "Women × Romper":        "Women - Jumpsuits &Playsuits",
    "Women × Sheath":        "Women - Dresses & Jumpsuits",
    "Women × JUMPSUIT":      "Women - Jumpsuits &Playsuits",
    "Women × Dungarees":     "Women - Jumpsuits &Playsuits",
    # Bottomwear
    "Women × JEANS":         "Women - Jeans & Jeggings",
    "Women × JEGGINGS":      "Women - Jeans & Jeggings",
    "Women × LEGGINGS":      "Women - Leggings & Trackpants",
    "Women × TIGHTS":        "Women - Leggings & Trackpants",
    "Women × TROUSERS":      "Women - Trousers & Pants",
    "Women × Chinos":        "Women - Trousers & Pants",
    "Women × CARGOS":        "Women - Trousers & Pants",
    "Women × PALAZZOS":      "Women - Pants",
    "Women × CULOTTES":      "Women - Pants",
    "Women × SKIRTS":        "Women - Skirts",
    "Women × SKORTS":        "Women - Skirts",
    "Women × BERMUDAS":      "Women - Shorts & Skirts",
    "Women × CAPRIS":        "Women - Trousers & Pants",
    "Women × Joggers":       "Women - Track Pants",
    "Women × KNIT BOTTOMS":  "Women - Track Pants",
}

# ── Garment keyword → catalogue category (for raw_signal cross-category expansion) ──
# Applied only when raw_signal explicitly lists ≥2 garments spanning different categories.

GARMENT_RULES_WOMEN = [
    # Dresses / one-pieces first (most specific)
    (["gown"],                                          "Women - Dresses & Gowns"),
    (["dress", "maxi", "sheath", "empire", "pinafore",
      "high-low", "frocks", "nighty", "nightie"],       "Women - Dresses & Jumpsuits"),
    (["jumpsuit", "romper", "dungaree", "playsuit"],    "Women - Jumpsuits &Playsuits"),
    # Ethnic
    (["co-ord", "co ord", "coord"],                     "Women - Co-ord Sets"),
    (["kaftan", "kurta"],                               "Women - Kurtas"),
    (["tunic", "kurti"],                                "Women - Kurtis & Tunics"),
    (["saree", "sari"],                                 "Women - Sarees"),
    (["lehenga"],                                       "Women - Lehenga Choli Sets"),
    (["dupatta"],                                       "Women - Dupattas"),
    # Bottomwear
    (["jeans", "denim", "jeggings"],                    "Women - Jeans & Jeggings"),
    (["leggings", "tights"],                            "Women - Leggings & Trackpants"),
    (["palazzo", "culotte"],                            "Women - Pants"),
    (["trousers", "cargo", "capri", "chino"],           "Women - Trousers & Pants"),
    (["skirt", "skort", "ghagra"],                      "Women - Skirts"),
    (["shorts", "bermuda"],                             "Women - Shorts & Skirts"),
    (["jogger", "trackpant", "track pant", "knit bottom"], "Women - Track Pants"),
    (["tracksuit"],                                     "Women - Tracksuits"),
    # Topwear
    (["sweatshirt", "hoodie"],                          "Women - Sweatshirt & Hoodies"),
    (["blazer", "waistcoat"],                           "Women - Blazers & Waistcoats"),
    (["shrug", "jacket"],                               "Women - Shrugs & Jackets"),
    (["camisole", "cami", "slip"],                      "Women - Camisoles & Slips"),
    (["bodysuit", "body suit", "corset"],               "Women - Tops & Tshirts"),
    (["shirt", "blouse"],                               "Women - Shirts, Tops & Tunic"),
    (["top", "t-shirt", "tshirt", "polo", "tank", "vest",
      "flat knit", "knitwear"],                         "Women - Tops & Tshirts"),
    (["sweater", "cardigan"],                           "Women - Sweaters & Cardigans"),
    (["set", "coord"],                                  "Women - Co-ord Sets"),
]

GARMENT_RULES_MEN = [
    (["shirt"],                                         "Men - Shirts"),
    (["t-shirt", "tshirt", "polo", "tank", "vest",
      "top", "flat knit", "knitwear"],                  "Men - Tshirts"),
    (["sweatshirt", "hoodie"],                          "Men - Sweatshirt & Hoodies"),
    (["sweater", "cardigan"],                           "Men - Sweaters & Cardigans"),
    (["blazer", "waistcoat"],                           "Men - Blazers & Waistcoats"),
    (["jacket", "coat"],                                "Men - Jackets & Coats"),
    (["kaftan", "kurta"],                               "Men - Kurtas"),
    (["jeans", "denim", "jeggings"],                    "Men - Jeans"),
    (["trousers", "cargo", "chino", "pant"],            "Men - Trousers & Pants"),
    (["shorts", "bermuda"],                             "Men - Shorts & 3/4ths"),
    (["jogger", "knit bottom", "trackpant"],            "Men - Track Pants"),
    (["tracksuit"],                                     "Men - Tracksuits"),
    (["thermal"],                                       "Men - Thermal Wear"),
]

# Tokens that must NOT trigger "Men - Shirts" via the "shirt" keyword
_SHIRT_EXCLUSIONS = {"sweatshirt", "t-shirt", "tshirt"}

def extract_garments(raw_signal: str) -> list[str]:
    """Extract comma-separated garment tokens from 'Garment(s): X, Y, Z' in raw_signal."""
    m = re.search(r'garments?\s*:\s*([^;]+)', raw_signal, re.IGNORECASE)
    if not m:
        return []
    tokens = []
    for part in m.group(1).split(","):
        part = re.sub(r'\(.*?\)', '', part).strip().lower()
        if part:
            tokens.append(part)
    return tokens


def cat_from_garment(garment: str, rules: list) -> "str | None":
    for keywords, cat in rules:
        for kw in keywords:
            if kw not in garment:
                continue
            # Guard: "shirt" must not fire inside sweatshirt/t-shirt
            if kw == "shirt" and any(ex in garment for ex in _SHIRT_EXCLUSIONS):
                continue
            # Guard: "set" / "coord" must be a real word boundary match
            if kw in ("set", "coord") and not re.search(rf'\b{kw}', garment):
                continue
            return cat
    return None


def cats_from_garments(garments: list[str], gender: str) -> set[str]:
    rules = GARMENT_RULES_WOMEN if gender == "women" else GARMENT_RULES_MEN
    cats = set()
    for g in garments:
        c = cat_from_garment(g, rules)
        if c:
            cats.add(c)
    return cats


def map_row(row: dict) -> list[str]:
    bl = row["bucket_label"].strip()
    gender = "women" if "women" in bl.lower() else ("men" if "men" in bl.lower() else "")

    # Signal 1: bucket_label — primary anchor
    primary = BUCKET_MAP.get(bl)
    cats: set[str] = {primary} if primary else set()

    # Signal 2: raw_signal garment list — only for genuine cross-category trends
    # (skip if only 1 garment token — that's just describing the bucket garment itself)
    garments = extract_garments(row["raw_signal"])
    if len(garments) >= 2:
        if not gender:
            raw_lower = row["raw_signal"].lower()
            gender = "women" if "women" in raw_lower else ("men" if "men" in raw_lower else "")
        extra = cats_from_garments(garments, gender)
        # Only add if it brings genuinely new categories beyond primary
        if extra != {primary}:
            cats.update(extra)

    return sorted(cats)


def main():
    with open(OUTPUT_CSV, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    if "catalogue_category" not in fieldnames:
        bl_idx = fieldnames.index("bucket_label")
        fieldnames.insert(bl_idx + 1, "catalogue_category")

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            row["catalogue_category"] = " | ".join(map_row(row))
            writer.writerow(row)

    from collections import Counter
    unmapped = sum(1 for r in rows if not map_row(r))
    multi = sum(1 for r in rows if len(map_row(r)) > 1)
    cat_counts: Counter = Counter()
    for r in rows:
        for c in map_row(r):
            cat_counts[c] += 1

    print(f"Total : {len(rows)}  |  Mapped : {len(rows)-unmapped}  |  Unmapped : {unmapped}  |  Multi-cat : {multi}")
    print()
    print("Per catalogue category:")
    for cat, cnt in sorted(cat_counts.items()):
        print(f"  {cnt:3d}  {cat}")


if __name__ == "__main__":
    main()
