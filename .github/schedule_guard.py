"""Decide when a scheduled scrape was never started, and when a late one should stop.

GitHub's scheduler can create the 6:00 AM run hours late, or not at all.
A manual run starts immediately. This helper is what the 7:10 AM workflow
uses to press that button, and what the scrape uses to avoid doing the
work twice.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DENVER = ZoneInfo("America/Denver")
# Monday is 0. Class scrapes run Sunday, Monday, Wednesday, and Friday.
SCRAPE_WEEKDAYS = {0, 2, 4, 6}


def parse_time(value):
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def window_start(now, hour, minute):
    local = now.astimezone(DENVER)
    start = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return start.astimezone(timezone.utc)


def runs_since(runs, start, current_id=""):
    found = []
    for run in runs:
        if str(run.get("databaseId")) == str(current_id):
            continue
        if parse_time(run["createdAt"]) >= start:
            found.append(run)
    return found


def should_skip(runs, start, current_id, event_name, reason):
    """A late schedule, or the automatic makeup run, stops when any run already exists."""
    automatic = event_name == "schedule" or reason == "missed-schedule"
    if not automatic:
        return False
    return bool(runs_since(runs, start, current_id))


def workflows_to_kick(now, class_runs, pool_runs):
    """Return workflow files that have no run since their scheduled time today."""
    local = now.astimezone(DENVER)
    due = []
    if local.weekday() in SCRAPE_WEEKDAYS:
        if not runs_since(class_runs, window_start(now, 6, 0)):
            due.append("weekly-scrape.yml")
    if not runs_since(pool_runs, window_start(now, 6, 10)):
        due.append("check-pool-schedules.yml")
    return due


def list_runs(workflow):
    raw = subprocess.check_output(
        [
            "gh", "run", "list",
            "--workflow", workflow,
            "--limit", "20",
            "--json", "databaseId,event,status,conclusion,createdAt",
        ],
        text=True,
    )
    return json.loads(raw)


def write_output(skip):
    path = os.environ.get("GITHUB_OUTPUT")
    line = f"skip={'true' if skip else 'false'}\n"
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line)
    print(line.strip())


def gate(args):
    now = datetime.now(DENVER)
    start = window_start(now, args.hour, args.minute)
    runs = list_runs(args.workflow)
    skip = should_skip(
        runs,
        start,
        os.environ.get("GITHUB_RUN_ID", ""),
        os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch"),
        os.environ.get("REASON", ""),
    )
    if skip:
        print(f"A run of {args.workflow} was already created since {start.isoformat()}.")
    write_output(skip)


def kick(_args):
    now = datetime.now(DENVER)
    due = workflows_to_kick(
        now,
        list_runs("weekly-scrape.yml"),
        list_runs("check-pool-schedules.yml"),
    )
    if not due:
        print("Scheduled runs were already created.")
        return
    for workflow in due:
        print(f"Starting {workflow}.")
        subprocess.check_call([
            "gh", "workflow", "run", workflow,
            "--ref", "main",
            "-f", "reason=missed-schedule",
        ])


def self_check():
    start = datetime(2026, 11, 23, 13, 0, tzinfo=timezone.utc)  # 6:00 AM MST
    late = [{"databaseId": 1, "createdAt": "2026-11-23T20:12:15Z"}]
    assert runs_since(late, start)
    assert should_skip(late, start, "2", "schedule", "")
    assert should_skip(late, start, "2", "workflow_dispatch", "missed-schedule")
    assert not should_skip(late, start, "2", "workflow_dispatch", "manual")
    assert not should_skip(late, start, "1", "schedule", "")
    monday = datetime(2026, 11, 23, 14, 10, tzinfo=DENVER)
    assert workflows_to_kick(monday, [], []) == [
        "weekly-scrape.yml",
        "check-pool-schedules.yml",
    ]
    assert workflows_to_kick(monday, late, late) == []
    tuesday = datetime(2026, 11, 24, 14, 10, tzinfo=DENVER)
    assert workflows_to_kick(tuesday, [], []) == ["check-pool-schedules.yml"]
    print("ok")


def main():
    if "--self-check" in sys.argv:
        self_check()
        return
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    gate_parser = sub.add_parser("gate")
    gate_parser.add_argument("--workflow", required=True)
    gate_parser.add_argument("--hour", type=int, required=True)
    gate_parser.add_argument("--minute", type=int, required=True)
    gate_parser.set_defaults(func=gate)
    kick_parser = sub.add_parser("kick")
    kick_parser.set_defaults(func=kick)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
