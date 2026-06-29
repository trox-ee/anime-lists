"""
update_timeline.py

Parses 'Animes Watched.txt' and 'Anime movies Watched.md', then injects
the structured data into index.html so the timeline website reflects the
latest anime list.

Usage:
    python update_timeline.py
"""

import re
import json
import os
from datetime import datetime

# ─── CONFIGURATION ────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERIES_FILE = os.path.join(SCRIPT_DIR, "Animes Watched.txt")
MOVIES_FILE = os.path.join(SCRIPT_DIR, "Anime movies Watched.md")
HTML_FILE = os.path.join(SCRIPT_DIR, "index.html")

# ─── DATE PARSING ─────────────────────────────────────────────
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def parse_date_string(raw: str) -> dict | None:
    """
    Attempt to parse various date formats found in the anime list.
    Returns { 'day': int, 'month': int, 'year': int, 'formatted': str, 'monthYear': str, 'sortKey': str }
    or None if unparseable.
    """
    raw = raw.strip().strip("<>").strip()
    if not raw:
        return None

    # Patterns to try:
    patterns = [
        # 14-4-2026 or 1-5-2026
        (r"(\d{1,2})-(\d{1,2})-(\d{4})", lambda m: (int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        # 20-62026 (malformed, missing dash before year)
        (r"(\d{1,2})-(\d{1,2})(\d{4})", lambda m: (int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        # feb28,2026
        (r"([a-zA-Z]+)\s*(\d{1,2})\s*,\s*(\d{4})", lambda m: (int(m.group(2)), _month_abbr(m.group(1)), int(m.group(3)))),
    ]

    for pattern, extractor in patterns:
        match = re.search(pattern, raw)
        if match:
            try:
                day, month, year = extractor(match)
                if 1 <= month <= 12 and 1 <= day <= 31:
                    month_name = MONTH_NAMES[month - 1]
                    return {
                        "day": day,
                        "month": month,
                        "year": year,
                        "formatted": f"{month_name} {day}, {year}",
                        "monthYear": f"{month_name} {year}",
                        "sortKey": f"{year:04d}-{month:02d}-{day:02d}",
                    }
            except (ValueError, IndexError):
                continue

    return None


def _month_abbr(name: str) -> int:
    """Convert month abbreviation to number."""
    abbrs = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "may": 5, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    return abbrs.get(name[:3].lower(), 0)


# ─── ENTRY PARSING ────────────────────────────────────────────
def parse_series_file(filepath: str) -> list[dict]:
    """Parse Animes Watched.txt into a list of entry dicts."""
    if not os.path.exists(filepath):
        print(f"[WARN] Series file not found: {filepath}")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    entries = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\r\n")

        # Match lines starting with "* "
        match = re.match(r"^\*\s+(.+)", line)
        if match:
            raw = match.group(1)

            # Check for continuation lines (indented lines with --------) 
            while i + 1 < len(lines):
                next_line = lines[i + 1].rstrip("\r\n")
                # Continuation if line starts with whitespace/tabs and contains dashes or descriptive content
                if re.match(r"^[\t ]+", next_line) and not re.match(r"^\*", next_line):
                    raw += " " + next_line.strip()
                    i += 1
                else:
                    break

            entry = _parse_entry_line(raw, "series")
            if entry:
                entries.append(entry)

        i += 1

    return entries


def parse_movies_file(filepath: str) -> list[dict]:
    """Parse Anime movies Watched.md into a list of entry dicts."""
    if not os.path.exists(filepath):
        print(f"[WARN] Movies file not found: {filepath}")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    entries = []
    for line in lines:
        line = line.rstrip("\r\n")
        match = re.match(r"^\*\s+(.+)", line)
        if match:
            raw = match.group(1)
            entry = _parse_entry_line(raw, "movie")
            if entry:
                entries.append(entry)

    return entries


def _parse_entry_line(raw: str, entry_type: str) -> dict | None:
    """Parse a single raw entry line into a structured dict."""
    # Try to extract date in angle brackets: <14-4-2026>
    date_info = None
    date_match = re.search(r"<([^>]+)>", raw)
    if date_match:
        date_info = parse_date_string(date_match.group(1))
        raw = raw[: date_match.start()] + raw[date_match.end():]

    # Try to extract date in format: >> feb28,2026
    if not date_info:
        alt_match = re.search(r">>\s*(.+)", raw)
        if alt_match:
            date_info = parse_date_string(alt_match.group(1))
            raw = raw[: alt_match.start()]

    # Split on dashes separator to get title and review
    # Pattern: Title---...---Review
    parts = re.split(r"-{3,}", raw)
    title = parts[0].strip().rstrip("-").strip()
    review = ""
    if len(parts) > 1:
        # Join remaining parts (could have multiple dash sections)
        review = " ".join(p.strip() for p in parts[1:] if p.strip())

    if not title:
        return None

    return {
        "title": title,
        "review": review,
        "type": entry_type,
        "date": date_info["formatted"] if date_info else "",
        "monthYear": date_info["monthYear"] if date_info else "",
        "sortKey": date_info["sortKey"] if date_info else "",
    }


# ─── DATA ASSEMBLY ────────────────────────────────────────────
def build_data() -> dict:
    """Build the full data structure for the HTML template."""
    series = parse_series_file(SERIES_FILE)
    movies = parse_movies_file(MOVIES_FILE)
    all_entries = series + movies

    # Separate dated vs undated
    dated = [e for e in all_entries if e["sortKey"]]
    undated = [e for e in all_entries if not e["sortKey"]]

    # Sort dated entries chronologically
    dated.sort(key=lambda e: e["sortKey"])

    # Add index numbers
    for i, entry in enumerate(dated, 1):
        entry["index"] = i
    for i, entry in enumerate(undated, 1):
        entry["index"] = i

    # Compute stats
    unique_months = set(e["monthYear"] for e in dated if e["monthYear"])
    stats = {
        "total": len(all_entries),
        "series": len(series),
        "movies": len(movies),
        "months": len(unique_months),
    }

    now = datetime.now()
    last_updated = now.strftime("%B %d, %Y at %I:%M %p")

    return {
        "dated": dated,
        "undated": undated,
        "stats": stats,
        "lastUpdated": last_updated,
    }


# ─── HTML INJECTION ──────────────────────────────────────────
def inject_into_html(data: dict) -> None:
    """Replace the ANIME_DATA constant in index.html with fresh data."""
    if not os.path.exists(HTML_FILE):
        print(f"[ERROR] HTML file not found: {HTML_FILE}")
        return

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Replace the ANIME_DATA JSON
    json_str = json.dumps(data, ensure_ascii=False)
    pattern = r"const ANIME_DATA = .+?;"
    replacement = f"const ANIME_DATA = {json_str};"

    new_html, count = re.subn(pattern, replacement, html, count=1)

    if count == 0:
        print("[ERROR] Could not find ANIME_DATA placeholder in index.html")
        return

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"[OK] Updated index.html with {data['stats']['total']} entries")
    print(f"     Series: {data['stats']['series']}")
    print(f"     Movies: {data['stats']['movies']}")
    print(f"     Dated entries: {len(data['dated'])}")
    print(f"     Undated entries: {len(data['undated'])}")
    print(f"     Active months: {data['stats']['months']}")
    print(f"     Last updated: {data['lastUpdated']}")


# ─── MAIN ────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  Anime Timeline Updater")
    print("=" * 50)
    data = build_data()
    inject_into_html(data)
    print("=" * 50)
    print("  Done! Open index.html in your browser.")
    print("=" * 50)
