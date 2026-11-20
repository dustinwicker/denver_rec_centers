"""Look for the next pool poster before the current one ends.

Checking starts five business days before valid_through. The current hours stay
on the calendar through that date. A spring poster can be another page of the
same Canva design, or a new link, so the check reads the poster text and the
printed dates instead of stopping when the design id is unchanged.
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pool_poster import (
    SCHEDULE_PATH,
    existing_seasons,
    fetch_html,
    fingerprint,
    merge_seasons,
    pool_links,
    poster_from_html,
    seasons_from_pages,
)

NOTICE_BUSINESS_DAYS = 5
PENDING_PATH = SCHEDULE_PATH.parent / "pool_schedule_pending.json"


def load_schedule():
    with SCHEDULE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_schedule(schedule):
    with SCHEDULE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(schedule, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def subtract_business_days(day, count):
    current = day
    remaining = count
    while remaining:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def latest_end(center, schedule):
    seasons = existing_seasons(center, schedule)
    if seasons:
        return max(season["valid_through"] for season in seasons)
    return center.get("valid_through") or schedule.get("valid_through")


def due_for_check(center, schedule, today):
    if center.get("awaiting_schedule"):
        return True, latest_end(center, schedule)
    end = latest_end(center, schedule)
    if not end:
        return False, None
    end_day = date.fromisoformat(end)
    if today > end_day:
        return True, end
    notice = subtract_business_days(end_day, NOTICE_BUSINESS_DAYS)
    return today >= notice, end


def targets_for(schedule, today):
    due = []
    for center in schedule.get("centers", []):
        needed, end = due_for_check(center, schedule, today)
        if not needed:
            continue
        if end and today > date.fromisoformat(end):
            reason = f"Poster ended {end}. Looking for the next canvas."
        elif center.get("awaiting_schedule"):
            reason = "Waiting for the pool to reopen."
        else:
            reason = f"Poster ends {end}. Looking early for the next canvas, including spring."
        due.append({**center, "reason": reason})
    for center in schedule.get("watching", []):
        due.append({**center, "reason": center.get("reason") or "Waiting for a pool schedule."})
    return due


def apply_poster(center, schedule, pages, link):
    incoming = seasons_from_pages(pages)
    digest = fingerprint(pages)
    if digest and digest == center.get("poster_fingerprint") and not incoming:
        return False, "Same poster text is still up."
    if digest and digest == center.get("poster_fingerprint") and incoming:
        same_windows = {(season["valid_from"], season["valid_through"]) for season in incoming}
        stored = {(season["valid_from"], season["valid_through"]) for season in existing_seasons(center, schedule)}
        if same_windows <= stored:
            return False, "Same poster text is still up."
    if not incoming:
        return False, "Poster text changed, but it has no dated schedule grid yet."
    seasons = existing_seasons(center, schedule)
    for season in incoming:
        season["poster_fingerprint"] = digest
        seasons = merge_seasons(seasons, season)
    center["seasons"] = seasons
    center["schedule_id"] = link["schedule_id"]
    center["canva_token"] = link["token"]
    center["poster_fingerprint"] = digest
    center.pop("pools", None)
    center.pop("valid_from", None)
    center.pop("valid_through", None)
    if any(season.get("closed") for season in incoming):
        center["awaiting_schedule"] = True
    elif any(season.get("pools") for season in incoming):
        center.pop("awaiting_schedule", None)
    windows = ", ".join(f"{season['valid_from']} to {season['valid_through']}" for season in incoming)
    return True, f"Saved schedule for {windows}."


def check(today, fetch=fetch_html, write=True):
    schedule = load_schedule()
    notes = []
    changed = False
    pending = []
    for center in targets_for(schedule, today):
        gym = center["gym"]
        try:
            html = fetch(center["url"])
        except Exception as exc:
            notes.append(f"{gym}: could not open the rec center page ({exc}).")
            continue
        links = pool_links(html)
        if not links:
            notes.append(f"{gym}: no pool canvas on the page.")
            if center.get("awaiting_schedule") or gym in {item["gym"] for item in schedule.get("watching", [])}:
                continue
            pending.append({"gym": gym, "detail": "Pool canvas link is gone."})
            continue
        link = links[0]
        try:
            poster_html = fetch(f"https://www.canva.com/design/{link['schedule_id']}/{link['token']}/view?embed")
            pages = poster_from_html(poster_html, link["schedule_id"])
        except Exception as exc:
            notes.append(f"{gym}: could not read the canvas ({exc}).")
            continue
        if not pages:
            notes.append(f"{gym}: canvas {link['schedule_id']} had no readable text.")
            continue
        stored = next((item for item in schedule.get("centers", []) if item["gym"] == gym), None)
        if stored is None:
            if not seasons_from_pages(pages):
                notes.append(f"{gym}: still no dated pool schedule.")
                continue
            stored = {"gym": gym, "url": center["url"]}
            schedule.setdefault("centers", []).append(stored)
        updated, detail = apply_poster(stored, schedule, pages, link)
        if updated:
            schedule["watching"] = [item for item in schedule.get("watching", []) if item.get("gym") != gym]
        notes.append(f"{gym}: {detail}")
        changed = changed or updated
        if not updated and "no dated schedule" in detail:
            pending.append({"gym": gym, "schedule_id": link["schedule_id"], "detail": detail})
    if write and changed:
        save_schedule(schedule)
    if write:
        if pending:
            payload = {"checked": today.isoformat(), "centers": pending}
            if not PENDING_PATH.exists() or json.loads(PENDING_PATH.read_text()) != payload:
                PENDING_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        elif PENDING_PATH.exists():
            PENDING_PATH.unlink()
    return notes, changed


def main():
    parser = argparse.ArgumentParser(description="Check Denver pool posters for the next season")
    parser.add_argument("--as-of", help="YYYY-MM-DD, defaults to today")
    parser.add_argument("--list-only", action="store_true", help="Show who would be checked, without fetching")
    args = parser.parse_args()
    today = date.fromisoformat(args.as_of) if args.as_of else date.today()
    schedule = load_schedule()
    if args.list_only:
        for center in targets_for(schedule, today):
            print(f"{center['gym']}: {center['reason']}")
        return
    notes, changed = check(today)
    for note in notes:
        print(note)
    print(f"Updated the calendar: {changed}")


if __name__ == "__main__":
    main()
