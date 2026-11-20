"""Read Denver pool hours from the Canva poster embedded on a rec center page.

The poster is often edited in place, so the design id stays the same when
winter or spring hours replace the previous season. The schedule text and the
printed date range are what change. A later season is stored beside the
current one so the calendar switches on the printed start date.
"""
import hashlib
import json
import re
import ssl
from datetime import date, datetime, timedelta
from pathlib import Path

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CANVA_RE = re.compile(r"canva\.com/design/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)")
TIME_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\s*[-–—]\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?",
    re.I,
)
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
SWIM_NAMES = {"lap swim", "open swim", "quiet swim", "adult swim", "family swim", "open/lap swim", "lap/adult swim"}

try:
    DATA_DIR = Path(__file__).parent.parent / "data"
except NameError:
    DATA_DIR = Path("/Users/dustinwicker/projects/denver_rec_centers/data")
SCHEDULE_PATH = DATA_DIR / "pool_schedules.json"


def fetch_html(url):
    import urllib.request
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, context=context, timeout=45) as response:
        return response.read().decode("utf-8", "replace")


def pool_links(html):
    """Canva posters under a pool or aquatics heading. Gymnasium posters are skipped."""
    links = []
    seen = set()
    for match in re.finditer(r"<h4>(.*?)</h4>", html, re.I | re.S):
        title = re.sub(r"<[^>]+>", " ", match.group(1))
        title = re.sub(r"\s+", " ", title).strip()
        if not re.search(r"pool|aquatic", title, re.I):
            continue
        end = html.find("<h4>", match.end())
        chunk = html[match.end(): end if end != -1 else match.end() + 15000]
        for found in CANVA_RE.finditer(chunk):
            if found.group(1) in seen:
                continue
            seen.add(found.group(1))
            links.append({"schedule_id": found.group(1), "token": found.group(2), "heading": title})
    if links:
        return links
    for found in CANVA_RE.finditer(html):
        window = re.sub(r"<[^>]+>", " ", html[max(0, found.start() - 600):found.start()])
        window = re.sub(r"\s+", " ", window).lower()
        if "pool" not in window and "aquatic" not in window:
            continue
        if "gymnasium" in window and "pool" not in window[-100:]:
            continue
        if found.group(1) in seen:
            continue
        seen.add(found.group(1))
        links.append({"schedule_id": found.group(1), "token": found.group(2), "heading": "pool"})
    return links


def _extract_object(raw):
    depth = 0
    in_str = False
    esc = False
    for index, char in enumerate(raw):
        if in_str:
            if esc:
                esc = False
            elif char == "\\":
                esc = True
            elif char == '"':
                in_str = False
            continue
        if char == '"':
            in_str = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                blob = raw[: index + 1].replace('\\\\"', '\\"')
                return json.loads(blob)
    return None


def design_doc(html, design_id):
    key = f'"A":"{design_id}"'
    index = html.find(key)
    if index < 0:
        return None
    start = html.find(',"D":{', index, index + 80)
    if start < 0:
        return None
    return _extract_object(html[start + len(',"D":'):])


def _cell_text(cell):
    texts = []

    def walk(node):
        if isinstance(node, dict):
            value = node.get("A")
            if isinstance(value, list) and value and isinstance(value[0], str):
                texts.append("".join(value).replace("\\n", " ").strip())
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(cell)
    seen = []
    for text in texts:
        if text and text not in seen:
            seen.append(text)
    return " | ".join(seen)


def _ktexts(node):
    found = []
    if isinstance(node, dict):
        if node.get("A?") == "K":
            body = (node.get("a") or {}).get("C") if isinstance(node.get("a"), dict) else None
            if isinstance(body, dict) and isinstance(body.get("A"), list):
                found.append("".join(body["A"]).replace("\\n", " ").strip())
        for child in node.values():
            found.extend(_ktexts(child))
    elif isinstance(node, list):
        for child in node:
            found.extend(_ktexts(child))
    return [text for text in found if text]


def _tables(node):
    found = []
    if isinstance(node, dict):
        if node.get("A?") == "V":
            found.append(node)
        for child in node.values():
            found.extend(_tables(child))
    elif isinstance(node, list):
        for child in node:
            found.extend(_tables(child))
    return found


def grids_from_doc(doc):
    pages = doc.get("A", {}).get("A") if isinstance(doc.get("A"), dict) else None
    if not isinstance(pages, list):
        return []
    parsed = []
    for page in pages:
        grids = []
        for table in _tables(page):
            rows = []
            for row in table.get("d", {}).get("A", []):
                rows.append([_cell_text(table.get("c", {}).get(cell_id, {})) or "" for cell_id in row.get("A", {}).values()])
            if rows:
                grids.append(rows)
        parsed.append({"name": page.get("B") or "", "titles": _ktexts(page), "grids": grids})
    return parsed


def poster_from_html(html, design_id):
    doc = design_doc(html, design_id)
    if not doc:
        return None
    return grids_from_doc(doc)


def _ampm(token):
    if not token:
        return None
    return "am" if token.lower().startswith("a") else "pm"


def _minutes(hour, minute, meridiem):
    hour = int(hour)
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return hour * 60 + int(minute)


def _clock(hour, minute, meridiem):
    return f"{int(hour)}:{int(minute):02d}{meridiem}"


def parse_time_range(text, label=""):
    match = TIME_RE.search(text or "")
    if not match:
        return None
    start_hour, start_min, start_mer, end_hour, end_min, end_mer = match.groups()
    start_min = start_min or "00"
    end_min = end_min or "00"
    end_mer = _ampm(end_mer) or _ampm(start_mer)
    start_mer = _ampm(start_mer) or end_mer
    if not start_mer or not end_mer:
        return None
    start = _minutes(start_hour, start_min, start_mer)
    end = _minutes(end_hour, end_min, end_mer)
    if end <= start and start_mer == "pm":
        start_mer = "am"
        start = _minutes(start_hour, start_min, start_mer)
    label_key = re.sub(r"[^a-z/ ]", "", (label or "").lower()).strip()
    general_swim = any(name in label_key for name in SWIM_NAMES)
    if (
        label_key
        and not general_swim
        and end - start > 5 * 60
        and start_mer == "am"
        and end_mer == "pm"
        and int(end_hour) % 12 >= int(start_hour) % 12
    ):
        flipped = _minutes(end_hour, end_min, "am")
        if 15 <= flipped - start <= 3 * 60:
            end_mer = "am"
    return _clock(start_hour, start_min, start_mer), _clock(end_hour, end_min, end_mer)


def _title_pool(text):
    pieces = re.split(r"(\s+|/)", text.lower())
    out = []
    for piece in pieces:
        if piece.lower() == "ai":
            out.append("Ai")
        elif piece.isalpha():
            out.append(piece.capitalize())
        else:
            out.append(piece)
    return "".join(out).strip()


def clean_label(raw):
    text = re.sub(r"\s+", " ", raw or "").strip()
    if not text or text == "·":
        return None
    lowered = text.lower()
    if "hours of operation" in lowered:
        return None
    if lowered.strip("* ") in {"closed", "pool closed", "pool maintenance"}:
        return None
    if re.fullmatch(r"\(?pool closed\)?", lowered):
        return None
    notes = []
    if text.startswith("**"):
        notes.append("Slide subject to availability.")
    elif text.startswith("*") or "registration required" in lowered:
        notes.append("Registration required.")
    if "pool closed for lessons" in lowered:
        notes.append("Pool closed for lessons.")
        text = "Swim Lessons"
    text = text.lstrip("*").strip()
    for note in re.findall(r"\(([^)]*)\)?", text):
        note = note.strip(" )")
        if note:
            notes.append(note[:1].upper() + note[1:])
    text = re.sub(r"\([^)]*\)?", "", text)
    text = re.sub(r"\s+", " ", text).strip(" /")
    if not text:
        return None
    if "/" in text:
        left, right = [part.strip() for part in text.split("/", 1)]
        if right.lower() in {"river walking", "water walking", "adult swim"}:
            notes.insert(0, _title_pool(right) + ".")
            text = left
        else:
            text = f"{left}/{right}"
    name = _title_pool(text)
    if name.lower() in {"closed", "pool closed", "pool maintenance"}:
        return None
    block = {"name": name}
    if notes:
        block["note"] = " ".join(notes)
    if name in {"Swim Lessons", "Adaptive Swim Lessons", "Vive Swim Lessons"} or "lesson" in name.lower():
        block["kind"] = "program"
    elif name.lower() not in SWIM_NAMES and "swim" not in name.lower():
        block["kind"] = "program"
    return block


def _is_day_header(row):
    tokens = [cell.strip().upper()[:3] for cell in row if cell.strip() and cell.strip() != "·"]
    return sum(1 for token in tokens if token in {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}) >= 5


def _sections(grid):
    sections = []
    current = []
    for row in grid:
        if _is_day_header(row):
            if current:
                sections.append(current)
            current = []
            continue
        if any("hours of operation" in (cell or "").lower() for cell in row):
            continue
        current.append(row)
    if current:
        sections.append(current)
    return sections


def blocks_from_grid(grid):
    """Pair each time with the next activity in that weekday column."""
    columns = [[] for _ in range(7)]
    for section in _sections(grid):
        pending = [None] * 7
        for row in section:
            for index in range(min(7, len(row))):
                cell = row[index].strip()
                if not cell or cell == "·":
                    continue
                times = parse_time_range(cell)
                letters = re.sub(r"(?i)[ap]\.?m\.?", "", cell)
                if times and len(cell) < 40 and not re.search(r"[A-Za-z]", letters):
                    pending[index] = times
                    continue
                label = clean_label(cell)
                if not label or not pending[index]:
                    continue
                start, end = pending[index]
                block = {"name": label["name"], "start": start, "end": end}
                if label.get("note"):
                    block["note"] = label["note"]
                if label.get("kind"):
                    block["kind"] = label["kind"]
                columns[index].append(block)
                pending[index] = None
    days = {}
    for index, name in enumerate(DAY_NAMES):
        if columns[index]:
            days[name] = columns[index]
    return days


def _year_from(revised, default_year):
    if revised:
        return int(revised[:4])
    return default_year


def parse_revised(titles):
    for title in titles:
        match = re.search(r"revised:?\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", title, re.I)
        if not match:
            continue
        month, day, year = (int(part) for part in match.groups())
        if year < 100:
            year += 2000
        return date(year, month, day).isoformat()
    return None


def _make_date(month, day, year):
    try:
        return date(year, month, day)
    except ValueError:
        return None


def date_ranges(text, revised=None):
    """Printed schedule windows, such as 11/15-3/6/2027 or Nov 16 - Jan 2, 2027."""
    default_year = _year_from(revised, 2026)
    found = []
    numeric = re.compile(
        r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*[-–—/]+\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?"
    )
    for match in numeric.finditer(text):
        sm, sd, sy, em, ed, ey = match.groups()
        start_year = int(sy) + (2000 if sy and int(sy) < 100 else 0) if sy else default_year
        end_year = int(ey) + (2000 if ey and int(ey) < 100 else 0) if ey else start_year
        start = _make_date(int(sm), int(sd), start_year)
        end = _make_date(int(em), int(ed), end_year)
        if start and end:
            if end < start:
                end = _make_date(end.month, end.day, end.year + 1)
            if end and end >= start:
                found.append((start, end))
    named = re.compile(
        r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?\s*[-–—]+\s*"
        r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?",
        re.I,
    )
    for match in named.finditer(text):
        sm, sd, sy, em, ed, ey = match.groups()
        start_year = int(sy) if sy else default_year
        end_year = int(ey) if ey else start_year
        start = _make_date(MONTHS[sm[:3].lower()], int(sd), start_year)
        end = _make_date(MONTHS[em[:3].lower()], int(ed), end_year)
        if start and end:
            if end < start:
                end = _make_date(end.month, end.day, end.year + 1)
            if end and end >= start:
                found.append((start, end))
    unique = []
    for window in found:
        if window not in unique:
            unique.append(window)
    return unique


def _pool_meta(page_name, titles, index, count):
    schedule_lines = [title for title in titles if re.search(r"schedule", title, re.I)]
    blob = " ".join(schedule_lines or [page_name]).lower()
    if "leisure" in blob and "lap" in blob and count >= 2:
        return ("lap", "Lap pool") if index == 0 else ("leisure", "Leisure pool")
    if "leisure" in blob:
        return "leisure", "Leisure pool"
    if "therapy" in blob:
        return "leisure", "Therapy pool"
    if "lap" in blob:
        return "lap", "Lap pool"
    if count >= 2:
        return ("lap", "Lap pool") if index == 0 else ("leisure", "Leisure pool")
    return "lap", "Indoor pool"


def _closed_range(titles, revised):
    text = " ".join(titles)
    if not re.search(r"pool\s+closed|closed\s+for\s+maintenance", text, re.I):
        return None
    windows = date_ranges(text, revised)
    if not windows:
        return None
    start, end = max(windows, key=lambda item: (item[1] - item[0]).days)
    return start.isoformat(), end.isoformat()


def seasons_from_pages(pages, today_year=2026):
    """Build season records from parsed Canva pages. Empty if the poster has no grid."""
    seasons = []
    for page in pages:
        titles = page.get("titles") or []
        revised = parse_revised(titles)
        closed = _closed_range(titles, revised)
        if closed and not any(page.get("grids")):
            seasons.append({
                "label": "Closed",
                "valid_from": closed[0],
                "valid_through": closed[1],
                "revised": revised,
                "closed": True,
                "pools": [],
            })
            continue
        grids = [grid for grid in page.get("grids") or [] if len(grid) > 2 and len(grid[0]) >= 7]
        if not grids:
            continue
        windows = date_ranges(" ".join(titles), revised)
        if windows:
            start, end = max(windows, key=lambda item: (item[1] - item[0]).days)
            valid_from, valid_through = start.isoformat(), end.isoformat()
        elif re.search(r"winter\s+2026\s*[-–]\s*2027", " ".join(titles), re.I):
            # These posters say winter 2026-2027 and do not print a start date.
            # Fall canvases end November 14, so this season starts the next day.
            valid_from = f"{today_year}-11-15"
            valid_through = f"{today_year + 1}-03-06"
        elif re.search(r"winter\s+2026", " ".join(titles), re.I):
            valid_from = revised or f"{today_year}-11-01"
            valid_through = f"{today_year}-12-31"
        elif re.search(r"\bfall\b", " ".join(titles), re.I):
            year = int((revised or f"{today_year}-01-01")[:4])
            valid_from = revised or f"{year}-08-09"
            valid_through = f"{year}-11-14"
        else:
            continue
        if closed and date.fromisoformat(closed[0]) >= date.fromisoformat(valid_from):
            seasons.append({
                "label": "Closed",
                "valid_from": closed[0],
                "valid_through": closed[1],
                "revised": revised,
                "closed": True,
                "pools": [],
            })
            continue
        pools = []
        for index, grid in enumerate(grids):
            sections = _sections(grid)
            pieces = sections if len(sections) >= 2 and len(grids) == 1 else [None]
            for piece_index, section in enumerate(pieces):
                days = blocks_from_grid(grid if section is None else _with_header(section))
                if not days:
                    continue
                if section is None:
                    pool_id, pool_name = _pool_meta(page.get("name") or "", titles, index, len(grids))
                elif piece_index == 0:
                    pool_id, pool_name = "lap", "Lap pool"
                elif all(block["name"] == "Adult Swim" for blocks in days.values() for block in blocks):
                    pool_id, pool_name = "leisure", "Therapy pool"
                else:
                    pool_id, pool_name = "leisure", "Leisure pool"
                pools.append({
                    "id": pool_id,
                    "name": pool_name,
                    "revised": revised,
                    "days": days,
                })
        if not pools:
            continue
        if re.search(r"slide", " ".join(titles), re.I):
            for pool in pools:
                for blocks in pool["days"].values():
                    for block in blocks:
                        if block["name"] == "Open Swim" and "slide" not in block.get("note", "").lower():
                            extra = "Slide subject to availability."
                            block["note"] = (block.get("note", "") + " " + extra).strip()
        label = next((title for title in titles if re.search(r"schedule", title, re.I)), "Pool schedule")
        seasons.append({
            "label": re.sub(r"\s+", " ", label).strip(),
            "valid_from": valid_from,
            "valid_through": valid_through,
            "revised": revised,
            "pools": pools,
        })
    return _merge_same_window(seasons)


def _with_header(section_rows):
    header = ["MON", "TUES", "WED", "THURS", "FRI", "SAT", "SUN"]
    return [header] + section_rows


def _merge_same_window(seasons):
    merged = []
    for season in seasons:
        key = (season["valid_from"], season["valid_through"], bool(season.get("closed")))
        match = next((item for item in merged if (item["valid_from"], item["valid_through"], bool(item.get("closed"))) == key), None)
        if not match:
            merged.append(season)
            continue
        seen = {pool["id"] for pool in match["pools"]}
        for pool in season["pools"]:
            if pool["id"] not in seen:
                match["pools"].append(pool)
                seen.add(pool["id"])
    return merged


def fingerprint(pages):
    payload = []
    for page in pages:
        payload.append(page.get("name") or "")
        payload.extend(page.get("titles") or [])
        for grid in page.get("grids") or []:
            for row in grid:
                payload.append(" | ".join(row))
    raw = "\n".join(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def previous_day(iso_day):
    return (date.fromisoformat(iso_day) - timedelta(days=1)).isoformat()


def next_day(iso_day):
    return (date.fromisoformat(iso_day) + timedelta(days=1)).isoformat()


def merge_seasons(existing, incoming):
    """Keep hours that end before the new poster starts, and add the new poster."""
    kept = []
    for old in existing:
        if old["valid_through"] < incoming["valid_from"] or old["valid_from"] > incoming["valid_through"]:
            kept.append(old)
            continue
        if old["valid_from"] < incoming["valid_from"]:
            trimmed = dict(old)
            trimmed["valid_through"] = previous_day(incoming["valid_from"])
            if trimmed["valid_from"] <= trimmed["valid_through"]:
                kept.append(trimmed)
        if old["valid_through"] > incoming["valid_through"]:
            tail = dict(old)
            tail["valid_from"] = next_day(incoming["valid_through"])
            if tail["valid_from"] <= tail["valid_through"]:
                kept.append(tail)
    kept.append(dict(incoming))
    kept.sort(key=lambda season: season["valid_from"])
    return kept


def resolved_window(center, schedule):
    return (
        center.get("valid_from") or schedule.get("valid_from"),
        center.get("valid_through") or schedule.get("valid_through"),
    )


def existing_seasons(center, schedule):
    if center.get("seasons"):
        return [dict(season) for season in center["seasons"]]
    start, end = resolved_window(center, schedule)
    if not start or not end or not center.get("pools"):
        return []
    return [{
        "label": schedule.get("season") or "Pool schedule",
        "valid_from": start,
        "valid_through": end,
        "pools": center["pools"],
    }]
