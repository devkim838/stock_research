#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys
import tomllib
from zoneinfo import ZoneInfo

from generate_research import CONFIG_PATH, ROOT, ResearchGenerator


SCHEDULE_PATH = ROOT / "config" / "schedule.toml"


def load_schedule() -> dict:
    with SCHEDULE_PATH.open("rb") as file:
        return tomllib.load(file)


def resolve_session(schedule: dict, now: datetime) -> str:
    slots = schedule["slots"]
    ordered = sorted(
        ((name, config["hour"], config["minute"], config["session"]) for name, config in slots.items()),
        key=lambda item: (item[1], item[2]),
    )

    current_minutes = now.hour * 60 + now.minute
    selected = ordered[0][3]
    for _, hour, minute, session in ordered:
        if current_minutes >= hour * 60 + minute:
            selected = session
    return selected


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the scheduled daily research generation.")
    parser.add_argument("--session", choices=["morning", "afternoon", "closing"], help="Override automatic time slot selection.")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD format.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing research file.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    schedule = load_schedule()
    timezone = ZoneInfo(schedule["timezone"])
    now = datetime.now(timezone)
    target_date = now.date() if args.date is None else datetime.fromisoformat(args.date).date()
    session = args.session or resolve_session(schedule, now)

    generator = ResearchGenerator(ROOT, CONFIG_PATH)
    output = generator.generate_daily(session, target_date, overwrite=args.overwrite)
    print(output.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
