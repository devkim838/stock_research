#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import sys
import tomllib
from zoneinfo import ZoneInfo

from report_sections import (
    SECTOR_SPECS,
    build_closing_decision_sections,
    build_common_sections,
    build_hyundai_section,
    build_sector_news_sections,
    build_session_specific_section,
)
from report_data import ReportDataBuilder


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "research_config.toml"


@dataclass(frozen=True)
class Asset:
    slug: str
    name: str
    category: str
    path: str
    tags: list[str]


class ResearchGenerator:
    def __init__(self, root: Path, config_path: Path) -> None:
        self.root = root
        self.config = self._load_config(config_path)
        self.timezone = ZoneInfo(self.config["timezone"])
        self.author = self.config["default_author"]
        self.naming = self.config["naming"]
        self.wiki = self.config["wiki"]
        self.assets = [Asset(**asset) for asset in self.config["assets"]]
        self.data_builder = ReportDataBuilder()

    def _load_config(self, config_path: Path) -> dict:
        with config_path.open("rb") as file:
            return tomllib.load(file)

    def generate_daily(self, session: str, target_date: date, overwrite: bool = False) -> Path:
        session_config = self.config["sessions"][session]
        file_name = self.naming["daily_pattern"].format(
            date=target_date.strftime(self.config["date_format"]),
            session=session,
        )
        destination = self.root / self.config["research_root"] / session_config["folder"] / file_name
        if destination.exists() and not overwrite:
            self._log_generation(
                kind="daily",
                destination=destination,
                metadata={"session": session, "date": target_date.isoformat(), "status": "skipped"},
            )
            return destination
        title = f"{target_date.strftime(self.config['date_format'])} {session_config['title']}"
        context = self._build_common_context(
            title=title,
            slug=f"{target_date.isoformat()}-{session}",
            generated_at=self._now_text(),
            tags=self._tags_for(session),
            summary_hint=session_config["summary_hint"],
            session=session,
            session_title=session_config["title"],
            date=target_date.isoformat(),
        )
        content = self._render_template(session_config["template"], context)
        self._write_file(destination, content)
        self._log_generation(
            kind="daily",
            destination=destination,
            metadata={"session": session, "date": target_date.isoformat(), "status": "generated"},
        )
        return destination

    def generate_weekly(self, target_date: date, overwrite: bool = False) -> Path:
        period_config = self.config["periods"]["weekly"]
        iso_year, iso_week, _ = target_date.isocalendar()
        file_name = self.naming["weekly_pattern"].format(year=iso_year, week=iso_week)
        destination = self.root / self.config["research_root"] / period_config["folder"] / file_name
        if destination.exists() and not overwrite:
            self._log_generation(
                kind="weekly",
                destination=destination,
                metadata={"week": f"{iso_year}-W{iso_week:02d}", "status": "skipped"},
            )
            return destination
        title = f"{iso_year}년 {iso_week}주차 {period_config['title']}"
        context = self._build_common_context(
            title=title,
            slug=f"{iso_year}-W{iso_week:02d}",
            generated_at=self._now_text(),
            tags=self._tags_for("weekly"),
            week_label=f"{iso_year}-W{iso_week:02d}",
        )
        content = self._render_template(period_config["template"], context)
        self._write_file(destination, content)
        self._log_generation(
            kind="weekly",
            destination=destination,
            metadata={"week": f"{iso_year}-W{iso_week:02d}", "status": "generated"},
        )
        return destination

    def generate_monthly(self, target_date: date, overwrite: bool = False) -> Path:
        period_config = self.config["periods"]["monthly"]
        file_name = self.naming["monthly_pattern"].format(year=target_date.year, month=target_date.month)
        destination = self.root / self.config["research_root"] / period_config["folder"] / file_name
        if destination.exists() and not overwrite:
            self._log_generation(
                kind="monthly",
                destination=destination,
                metadata={"month": f"{target_date.year}-{target_date.month:02d}", "status": "skipped"},
            )
            return destination
        title = f"{target_date.year}년 {target_date.month}월 {period_config['title']}"
        context = self._build_common_context(
            title=title,
            slug=f"{target_date.year}-{target_date.month:02d}",
            generated_at=self._now_text(),
            tags=self._tags_for("monthly"),
            month_label=f"{target_date.year}-{target_date.month:02d}",
        )
        content = self._render_template(period_config["template"], context)
        self._write_file(destination, content)
        self._log_generation(
            kind="monthly",
            destination=destination,
            metadata={"month": f"{target_date.year}-{target_date.month:02d}", "status": "generated"},
        )
        return destination

    def bootstrap_indexes(self) -> list[Path]:
        created: list[Path] = []
        for asset in self.assets:
            path = self.root / asset.path
            if path.exists():
                continue
            title = f"{asset.name} 투자 위키"
            tags = ", ".join(f'"{tag}"' for tag in sorted(set(asset.tags + [asset.category])))
            body = "\n".join(
                [
                    "---",
                    f'title: "{title}"',
                    f'slug: "{asset.slug}"',
                    f'category: "{asset.category}"',
                    'language: "ko"',
                    f"tags: [{tags}]",
                    "---",
                    "",
                    f"# {title}",
                    "",
                    "## 개요",
                    "",
                    f"- 대상: {asset.name}",
                    "- 투자 포인트:",
                    "- 핵심 리스크:",
                    "",
                    "## 연결 리서치",
                    "",
                    "- 일간:",
                    "- 주간:",
                    "- 월간:",
                ]
            )
            self._write_file(path, body)
            created.append(path)
        return created

    def _build_common_context(self, title: str, slug: str, generated_at: str, tags: list[str], **extra: str) -> dict[str, str]:
        asset_names = [asset.name for asset in self.assets]
        asset_links = [asset.path for asset in self.assets]
        tag_csv = ", ".join(f'"{tag}"' for tag in tags)
        watchlist_csv = ", ".join(f'"{name}"' for name in asset_names)
        asset_page_csv = ", ".join(f'"{path}"' for path in asset_links)
        session = extra.get("session", "")
        context_date = extra.get("date", slug[:10])
        report_data = self.data_builder.build(session, date.fromisoformat(context_date)) if session and extra.get("date") else {}
        context = {
            "title": title,
            "slug": slug,
            "date": context_date,
            "generated_at": generated_at,
            "author": self.author,
            "tag_csv": tag_csv,
            "watchlist_csv": watchlist_csv,
            "asset_page_csv": asset_page_csv,
            "wiki_index": self.wiki["base_url"],
            "common_sections": build_common_sections(report_data),
            "hyundai_section": build_hyundai_section(report_data),
            "sector_news_sections": build_sector_news_sections(report_data),
            "session_specific_sections": build_session_specific_section(session, extra.get("summary_hint", ""), report_data),
            "closing_decision_sections": build_closing_decision_sections(report_data) if session == "closing" else "",
        }
        context.update(extra)
        return context

    def _wiki_link(self, asset_path: str) -> str:
        if self.wiki["link_style"] == "relative":
            return f"/{asset_path.replace('index.md', '')}".rstrip("/")
        return f"{self.wiki['base_url']}/{asset_path}"

    def _render_template(self, template_path: str, context: dict[str, str]) -> str:
        template = (self.root / template_path).read_text(encoding="utf-8")
        return template.format(**context)

    def _write_file(self, destination: Path, content: str) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content.strip() + "\n", encoding="utf-8")

    def _log_generation(self, kind: str, destination: Path, metadata: dict[str, str]) -> None:
        log_path = self.root / self.config["log_file"]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "generated_at": datetime.now(self.timezone).isoformat(),
            "kind": kind,
            "output": str(destination.relative_to(self.root)),
            **metadata,
        }
        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _tags_for(self, cadence: str) -> list[str]:
        tags = {"투자", "리서치", cadence}
        for asset in self.assets:
            tags.add(asset.name)
        for sector_name, _ in SECTOR_SPECS:
            tags.add(sector_name)
        return sorted(tags)

    def _now_text(self) -> str:
        return datetime.now(self.timezone).strftime(self.config["timestamp_format"])


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate investment research markdown files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    daily = subparsers.add_parser("daily", help="Generate a daily research note.")
    daily.add_argument("--session", choices=["morning", "afternoon", "closing"], required=True)
    daily.add_argument("--date", type=str, help="Target date in YYYY-MM-DD format.")
    daily.add_argument("--overwrite", action="store_true", help="Overwrite an existing file.")

    all_daily = subparsers.add_parser("all-daily", help="Generate all daily sessions for one date.")
    all_daily.add_argument("--date", type=str, help="Target date in YYYY-MM-DD format.")
    all_daily.add_argument("--overwrite", action="store_true", help="Overwrite existing files.")

    weekly = subparsers.add_parser("weekly", help="Generate a weekly research note.")
    weekly.add_argument("--date", type=str, help="Any date within the target week in YYYY-MM-DD format.")
    weekly.add_argument("--overwrite", action="store_true", help="Overwrite an existing file.")

    monthly = subparsers.add_parser("monthly", help="Generate a monthly research note.")
    monthly.add_argument("--date", type=str, help="Any date within the target month in YYYY-MM-DD format.")
    monthly.add_argument("--overwrite", action="store_true", help="Overwrite an existing file.")

    subparsers.add_parser("bootstrap", help="Create missing asset wiki index files.")
    return parser.parse_args(argv)


def parse_date(value: str | None) -> date:
    if value is None:
        return datetime.now(ZoneInfo("Asia/Seoul")).date()
    return date.fromisoformat(value)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    generator = ResearchGenerator(ROOT, CONFIG_PATH)

    if args.command == "bootstrap":
        created = generator.bootstrap_indexes()
        if created:
            for path in created:
                print(path.relative_to(ROOT))
        else:
            print("No index files needed.")
        return 0

    target_date = parse_date(getattr(args, "date", None))

    if args.command == "daily":
        output = generator.generate_daily(args.session, target_date, overwrite=args.overwrite)
        print(output.relative_to(ROOT))
        return 0

    if args.command == "all-daily":
        for session in ("morning", "afternoon", "closing"):
            output = generator.generate_daily(session, target_date, overwrite=args.overwrite)
            print(output.relative_to(ROOT))
        return 0

    if args.command == "weekly":
        output = generator.generate_weekly(target_date, overwrite=args.overwrite)
        print(output.relative_to(ROOT))
        return 0

    if args.command == "monthly":
        output = generator.generate_monthly(target_date, overwrite=args.overwrite)
        print(output.relative_to(ROOT))
        return 0

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
