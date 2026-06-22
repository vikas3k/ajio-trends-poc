"""India apparel retail calendar — festivals, occasions, and seasonal windows.

Provides a data-driven festival/occasion list so the LLM generates context
trends tied to real dates, not model-recalled approximate windows.

Coverage: 2026 full year + early 2027 wedding season.
Add future years by appending to _EVENTS below.
"""
from __future__ import annotations

import datetime as _dt
from typing import TypedDict


class Event(_TypedDict := TypedDict("Event", {
    "name": str,
    "date": str,          # ISO date of the main day
    "window_start": str,  # ISO date — when shopping/dressing starts
    "window_end": str,    # ISO date — when the occasion ends
    "category": str,      # occasion_festival | event_driven | functional | seasonal
    "apparel_angle": str, # what shoppers typically buy
})):
    pass


# ---------------------------------------------------------------------------
# Master calendar — extend annually
# ---------------------------------------------------------------------------
_EVENTS: list[dict] = [
    # ── Seasonal / functional ───────────────────────────────────────────────
    {
        "name": "Monsoon Season",
        "date": "2026-06-15",
        "window_start": "2026-06-01",
        "window_end": "2026-09-30",
        "category": "functional",
        "apparel_angle": "Quick-dry fabrics, waterproof outerwear, dark colours, functional co-ords",
    },
    {
        "name": "Summer / High Summer",
        "date": "2026-05-01",
        "window_start": "2026-04-01",
        "window_end": "2026-06-30",
        "category": "functional",
        "apparel_angle": "Cotton, linen, resort wear, breathable silhouettes, pastel/white",
    },
    {
        "name": "Festive & Wedding Pre-Season",
        "date": "2026-08-15",
        "window_start": "2026-08-01",
        "window_end": "2026-10-31",
        "category": "functional",
        "apparel_angle": "Occasion-ready ethnic, embellished, indo-western — shopping peaks 6 weeks before Diwali",
    },
    {
        "name": "Winter / Party Season",
        "date": "2026-12-01",
        "window_start": "2026-11-01",
        "window_end": "2027-02-28",
        "category": "functional",
        "apparel_angle": "Knits, velvets, layering pieces, party-ready occasionwear",
    },

    # ── Festivals 2026 ──────────────────────────────────────────────────────
    {
        "name": "Eid al-Adha",
        "date": "2026-06-18",
        "window_start": "2026-06-05",
        "window_end": "2026-06-20",
        "category": "occasion_festival",
        "apparel_angle": "Festive kurtas, sherwanis, embroidered anarkalis, whites & pastels",
    },
    {
        "name": "Guru Purnima",
        "date": "2026-07-07",
        "window_start": "2026-07-01",
        "window_end": "2026-07-08",
        "category": "occasion_festival",
        "apparel_angle": "Subtle ethnic, cotton kurtas, understated occasionwear",
    },
    {
        "name": "Independence Day",
        "date": "2026-08-15",
        "window_start": "2026-08-10",
        "window_end": "2026-08-16",
        "category": "occasion_festival",
        "apparel_angle": "Tricolour palette (saffron, white, green), khadi, pride dressing",
    },
    {
        "name": "Raksha Bandhan",
        "date": "2026-08-22",
        "window_start": "2026-08-15",
        "window_end": "2026-08-23",
        "category": "occasion_festival",
        "apparel_angle": "Traditional sets, pastel kurtas, light ethnic for family gatherings",
    },
    {
        "name": "Janmashtami",
        "date": "2026-08-29",
        "window_start": "2026-08-22",
        "window_end": "2026-08-30",
        "category": "occasion_festival",
        "apparel_angle": "Yellow & peacock-blue ethnic, printed kurtas, festive dupattas",
    },
    {
        "name": "Ganesh Chaturthi",
        "date": "2026-09-07",
        "window_start": "2026-08-28",
        "window_end": "2026-09-17",
        "category": "occasion_festival",
        "apparel_angle": "Bright ethnic (orange, yellow, red), kurta sets, festive sarees",
    },
    {
        "name": "Onam",
        "date": "2026-09-10",
        "window_start": "2026-09-01",
        "window_end": "2026-09-15",
        "category": "occasion_festival",
        "apparel_angle": "Kerala-style kasavu sarees, white & gold, settu mundus, floral prints",
    },
    {
        "name": "Navratri / Garba",
        "date": "2026-10-08",
        "window_start": "2026-09-28",
        "window_end": "2026-10-17",
        "category": "occasion_festival",
        "apparel_angle": "Chaniya choli, lehengas, flared skirts, mirror-work, vibrant colours",
    },
    {
        "name": "Durga Puja",
        "date": "2026-10-08",
        "window_start": "2026-10-01",
        "window_end": "2026-10-14",
        "category": "occasion_festival",
        "apparel_angle": "New sarees, printed kurtas, red-white palette (Bengal), occasion sets",
    },
    {
        "name": "Dussehra",
        "date": "2026-10-17",
        "window_start": "2026-10-10",
        "window_end": "2026-10-18",
        "category": "occasion_festival",
        "apparel_angle": "Ethnic occasionwear, family outfits, embellished kurtas",
    },
    {
        "name": "Diwali",
        "date": "2026-11-05",
        "window_start": "2026-10-15",
        "window_end": "2026-11-10",
        "category": "occasion_festival",
        "apparel_angle": "Embellished ethnic (anarkalis, lehengas, kurta sets), gold/jewel tones, shimmer, gift sets",
    },
    {
        "name": "Bhai Dooj",
        "date": "2026-11-07",
        "window_start": "2026-11-05",
        "window_end": "2026-11-08",
        "category": "occasion_festival",
        "apparel_angle": "Ethnic casuals, brother-sister coordinated gifting looks",
    },
    {
        "name": "Chhath Puja",
        "date": "2026-11-09",
        "window_start": "2026-11-05",
        "window_end": "2026-11-11",
        "category": "occasion_festival",
        "apparel_angle": "Sarees, ethnic sets, traditional Bihar/UP regional wear",
    },
    {
        "name": "Christmas & New Year",
        "date": "2026-12-25",
        "window_start": "2026-12-10",
        "window_end": "2027-01-05",
        "category": "occasion_festival",
        "apparel_angle": "Party dresses, sequins, velvet, co-ords, NYE looks",
    },
    {
        "name": "Pongal / Makar Sankranti",
        "date": "2027-01-14",
        "window_start": "2027-01-10",
        "window_end": "2027-01-16",
        "category": "occasion_festival",
        "apparel_angle": "South Indian silks, half-sarees, festive pastels",
    },
    {
        "name": "Republic Day",
        "date": "2027-01-26",
        "window_start": "2027-01-20",
        "window_end": "2027-01-27",
        "category": "occasion_festival",
        "apparel_angle": "Formal ethnic, khadi, patriotic palette",
    },
    {
        "name": "Valentine's Day",
        "date": "2027-02-14",
        "window_start": "2027-02-07",
        "window_end": "2027-02-15",
        "category": "occasion_festival",
        "apparel_angle": "Date-night dresses, reds & pinks, bodycon, co-ords for couples",
    },
    {
        "name": "Holi",
        "date": "2027-03-22",
        "window_start": "2027-03-15",
        "window_end": "2027-03-23",
        "category": "occasion_festival",
        "apparel_angle": "White kurtas, colour-play outfits, easy-wash fabrics, ethnic streetwear",
    },

    # ── Wedding season windows ───────────────────────────────────────────────
    {
        "name": "Winter Wedding Season",
        "date": "2026-11-15",
        "window_start": "2026-11-01",
        "window_end": "2027-02-28",
        "category": "occasion_festival",
        "apparel_angle": "Wedding guest lehengas, sherwanis, cocktail gowns, sarees, bridesmaid sets",
    },
    {
        "name": "Summer Wedding Season",
        "date": "2026-04-20",
        "window_start": "2026-04-01",
        "window_end": "2026-06-15",
        "category": "occasion_festival",
        "apparel_angle": "Pastel lehengas, light-weight ethnic, destination wedding outfits",
    },

    # ── Key retail / fashion events ─────────────────────────────────────────
    {
        "name": "India Couture Week",
        "date": "2026-07-25",
        "window_start": "2026-07-23",
        "window_end": "2026-07-30",
        "category": "event_driven",
        "apparel_angle": "High-fashion ethnic, couture-inspired embellishments, runway trickle-down",
    },
    {
        "name": "Lakme Fashion Week (Mumbai)",
        "date": "2026-10-15",
        "window_start": "2026-10-14",
        "window_end": "2026-10-19",
        "category": "event_driven",
        "apparel_angle": "Contemporary Indian fashion, emerging designer styles, street-style looks",
    },
    {
        "name": "ICC T20 World Cup 2026",
        "date": "2026-06-01",
        "window_start": "2026-05-15",
        "window_end": "2026-07-15",
        "category": "event_driven",
        "apparel_angle": "Sporty fan dressing, team jerseys, athleisure, Indo-sporty fusion",
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upcoming_events(
    today: _dt.date | None = None,
    months_ahead: int = 3,
    categories: list[str] | None = None,
) -> list[dict]:
    """Return events whose window overlaps the next `months_ahead` months.

    Args:
        today: reference date (defaults to today).
        months_ahead: how far ahead to look.
        categories: filter by category list; None = all.
    """
    today = today or _dt.date.today()
    cutoff = _dt.date(
        today.year + (today.month + months_ahead - 1) // 12,
        ((today.month + months_ahead - 1) % 12) + 1,
        1,
    )

    results = []
    for ev in _EVENTS:
        try:
            win_start = _dt.date.fromisoformat(ev["window_start"])
            win_end = _dt.date.fromisoformat(ev["window_end"])
        except (KeyError, ValueError):
            continue
        # Include if window overlaps [today, cutoff]
        if win_end < today or win_start > cutoff:
            continue
        if categories and ev["category"] not in categories:
            continue
        results.append(ev)

    results.sort(key=lambda e: e["window_start"])
    return results


def calendar_block(
    today: _dt.date | None = None,
    months_ahead: int = 3,
) -> str:
    """Return a formatted text block for injection into the LLM prompt."""
    today = today or _dt.date.today()
    events = upcoming_events(today, months_ahead)
    if not events:
        return "(no upcoming events found in calendar)"

    lines = [f"INDIA RETAIL CALENDAR — next {months_ahead} months from {today.isoformat()}:"]
    for ev in events:
        lines.append(
            f"- {ev['name']} | main date: {ev['date']} | "
            f"shop window: {ev['window_start']} to {ev['window_end']} | "
            f"category: {ev['category']} | "
            f"apparel: {ev['apparel_angle']}"
        )
    return "\n".join(lines)
