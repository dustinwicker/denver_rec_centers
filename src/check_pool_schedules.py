"""
Look for the next pool poster before the current one ends.

Checking starts five business days before valid_through, so an early winter
poster can be recorded while the fall hours are still on the calendar. The
fall hours stay up through valid_through. The next schedule can then start
the following day.

Centers in "watching" have no usable schedule, so their page is fetched every
run. Glenarm is watched until the maintenance closure is replaced by a schedule.
"""
import argparse
import json
import re
import ssl
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    SCRIPT_DIR = Path(__file__).parent
    DATA_DIR = SCRIPT_DIR.parent / "data"
except NameError:
    DATA_DIR = Path("/Users/dustinwicker/projects/denver_rec_centers/data")

SCHEDULE_PATH = DATA_DIR / "pool_schedules.json"
PENDING_PATH = DATA_DIR / "pool_schedule_pending.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CANVA_RE = re.compile(r"canva\.com/design/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)")
NOTICE_BUSINESS_DAYS = 5


def load_schedule():
    with SCHEDULE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def center_window(center, schedule):
    start = center.get("valid_from") or schedule.get("valid_from")
    end = center.get("valid_through") or schedule.get("valid_through")
    return start, end


def subtract_business_days(day, count):
    """Weekdays only. Five business days before Saturday Nov 14 is Monday Nov 9."""
    current = day
    remaining = count
    while remaining:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def due_for_check(center, schedule, today):
    _, end = center_window(center, schedule)
    if not end:
        return False, None
    end_day = date.fromisoformat(end)
    notice = subtract_business_days(end_day, NOTICE_BUSINESS_DAYS)
    if today < notice:
        return False, end
    return True, end


def fetch_html(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, context=context, timeout=45) as response:
        return response.read().decode("utf-8", "replace")


def pool_designs(html):
    """Return Canva design ids whose nearby label is the pool schedule, not the gym."""
    designs = []
    seen = set()
    for match in CANVA_RE.finditer(html):
        design_id, token = match.group(1), match.group(2)
        if design_id in seen:
            continue
        window = html[max(0, match.start() - 700):match.start()]
        label = re.sub(r"<[^>]+>", " ", window)
        label = re.sub(r"\s+", " ", label).lower()
        if "gymnasium" in label and "pool" not in label[-80:]:
            continue
        if "pool" not in label and "aquatic" not in label:
            continue
        seen.add(design_id)
        designs.append({
            "schedule_id": design_id,
            "canva_url": f"https://www.canva.com/design/{design_id}/{token}/view",
        })
    return designs


def page_says_closed(html):
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).lower()
    return "closed for maintenance" in text or "pool is closed" in text or "pool closed" in text


def describe_change(center, designs, closed):
    """Return (needs_update, message). Same poster, or a closed pool still waiting, is not an update."""
    known = center.get("schedule_id")
    found_ids = [item["schedule_id"] for item in designs]
    if not designs:
        if known:
            return True, f"Pool poster {known} is no longer on the page."
        if closed:
            return False, "Pool is still closed and no schedule is posted."
        return False, "No pool poster on the page."
    new_ids = [item for item in found_ids if item != known]
    if known and not new_ids:
        if closed and center.get("awaiting_schedule"):
            return False, f"Same closed poster {known} is still up."
        return False, f"Same poster {known} is still up."
    if not known and closed:
        return False, "Pool is still closed and no schedule is posted."
    posted = ", ".join(new_ids) if new_ids else ", ".join(found_ids)
    return True, f"New pool poster posted: {posted}."


def targets_for(schedule, today):
    due = []
    for center in schedule.get("centers", []):
        due_now, end = due_for_check(center, schedule, today)
        if due_now:
            end_day = date.fromisoformat(end)
            if today > end_day:
                reason = f"Poster ended {end}."
            else:
                reason = f"Poster ends {end}. Looking early for the next schedule."
            due.append({
                "gym": center["gym"],
                "url": center["url"],
                "schedule_id": center.get("schedule_id"),
                "valid_through": end,
                "reason": reason,
            })
    for center in schedule.get("watching", []):
        due.append({
            "gym": center["gym"],
            "url": center["url"],
            "schedule_id": center.get("schedule_id"),
            "awaiting_schedule": True,
            "reason": center.get("reason") or "Waiting for a pool schedule.",
        })
    return due


def check(today, fetch=fetch_html):
    schedule = load_schedule()
    findings = []
    checked = []
    for center in targets_for(schedule, today):
        try:
            html = fetch(center["url"])
        except Exception as exc:
            findings.append({
                "gym": center["gym"],
                "url": center["url"],
                "status": "error",
                "detail": str(exc),
            })
            continue
        designs = pool_designs(html)
        closed = page_says_closed(html)
        needs_update, detail = describe_change(center, designs, closed)
        checked.append(f"{center['gym']}: {detail}")
        if not needs_update:
            continue
        findings.append({
            "gym": center["gym"],
            "url": center["url"],
            "previous_schedule_id": center.get("schedule_id"),
            "designs": designs,
            "pool_closed": closed,
            "status": "needs_update",
            "detail": detail,
        })
    return checked, findings


def write_pending(today, findings):
    if not findings:
        if PENDING_PATH.exists():
            PENDING_PATH.unlink()
        return
    payload = {
        "checked_on": today.isoformat(),
        "note": "A new pool poster is on the rec center page. The hours still need to be copied into pool_schedules.json.",
        "centers": findings,
    }
    if PENDING_PATH.exists():
        existing = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
        if existing.get("centers") == findings:
            return
    PENDING_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", help="Check as if today were YYYY-MM-DD")
    parser.add_argument("--list-only", action="store_true", help="Print who would be checked and do not fetch")
    args = parser.parse_args()
    today = date.fromisoformat(args.as_of) if args.as_of else datetime.now().astimezone().date()
    schedule = load_schedule()
    due = targets_for(schedule, today)

    if args.list_only:
        if not due:
            print(f"{today.isoformat()}: no pool pages to check")
            return
        print(f"{today.isoformat()}: check {len(due)} page(s)")
        for center in due:
            print(f"  {center['gym']}: {center['reason']}")
        return

    checked, findings = check(today)
    skipped = len(schedule.get("centers", [])) - sum(
        1 for center in schedule.get("centers", []) if due_for_check(center, schedule, today)[0]
    )
    print(f"{today.isoformat()}: skipped {skipped} current posters, checked {len(checked)}, updates {len(findings)}")
    for line in checked:
        print(f"  {line}")
    for finding in findings:
        print(f"  {finding['gym']}: {finding.get('detail') or finding.get('status')}")
    write_pending(today, findings)


if __name__ == "__main__":
    main()
