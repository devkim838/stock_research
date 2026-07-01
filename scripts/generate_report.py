#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from report_data import ReportDataBuilder
from report_sections import (
    build_closing_decision_sections,
    build_common_sections,
    build_coverage_section,
    build_flow_ranking_section,
    build_hyundai_section,
    build_morning_summary_section,
    build_morning_top_news_section,
    build_sector_news_sections,
    build_session_specific_section,
    build_us_proxy_section,
)


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_ROOT = ROOT / "research"
TIMEZONE = ZoneInfo("Asia/Seoul")
SESSIONS = ("morning", "afternoon", "closing")

SESSION_LABELS = {
    "morning": "오전 리서치",
    "afternoon": "오후 리서치",
    "closing": "마감 리서치",
}

SESSION_NOTES = {
    "morning": "장 시작 전 핵심 체크포인트와 오늘의 가설을 정리합니다.",
    "afternoon": "장중 변화와 오전 가설의 수정 여부를 정리합니다.",
    "closing": "종가 기준 해석과 다음 거래일 준비 사항을 정리합니다.",
}

DATA_BUILDER = ReportDataBuilder()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a daily research markdown report.")
    parser.add_argument("session", choices=SESSIONS, help="Report type to generate.")
    parser.add_argument("--date", type=str, help="Target date in YYYY-MM-DD format. Defaults to today in Asia/Seoul.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the report if it already exists.")
    return parser.parse_args(argv)


def resolve_date(raw_date: str | None) -> date:
    if raw_date is None:
        return datetime.now(TIMEZONE).date()
    return date.fromisoformat(raw_date)


def build_output_path(session: str, target_date: date) -> Path:
    file_name = f"{target_date.isoformat()}_{session}.md"
    return RESEARCH_ROOT / session / file_name


def build_content(session: str, target_date: date) -> str:
    title = f"# {target_date.isoformat()} {SESSION_LABELS[session]}"
    metadata = [
        f"- 작성일: {target_date.isoformat()}",
        f"- 세션: {session}",
        f"- 생성시각: {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
    ]
    report_data = DATA_BUILDER.build(session, target_date)
    session_block = build_session_specific_section(session, SESSION_NOTES[session], report_data)
    summary_block = build_morning_summary_section(report_data) if session == "morning" else None
    us_proxy_block = build_us_proxy_section(report_data) if session == "morning" else None
    top_news_block = build_morning_top_news_section(report_data) if session == "morning" else None
    sections = [
        title,
        "",
        *metadata,
        "<!-- TODO: 뉴스/시세/수급 API 연동 후 자동 채움 -->",
        "",
        "## 리포트 작성 원칙",
        "",
        "- 데이터가 없으면 `데이터 미수집`으로 기록한다.",
        "- 추정 수치와 임의 숫자는 입력하지 않는다.",
        "- 뉴스 출처와 가격/수급 데이터가 확보된 경우에만 투자 판단을 작성한다.",
        "",
        build_coverage_section(report_data),
        "",
    ]
    if session == "morning":
        sections.extend(
            [
                build_common_sections(report_data),
                "",
                *( [summary_block, ""] if summary_block else [] ),
                *( [us_proxy_block, ""] if us_proxy_block else [] ),
                *( [top_news_block, ""] if top_news_block else [] ),
            ]
        )
    else:
        sections.extend(
            [
                *( [summary_block, ""] if summary_block else [] ),
                build_common_sections(report_data, include_flow_rankings=session != "closing"),
                "",
            ]
        )
    if session == "morning":
        sections.extend(
            [
                build_hyundai_section(report_data),
            ]
        )
    elif session == "closing":
        sections.extend(
            [
                build_closing_decision_sections(report_data),
                "",
                build_flow_ranking_section(
                    report_data.get("common", {}).get("flow_rankings", {}),
                    report_data.get("common", {}).get("missing_reasons", {}).get("flow_rankings", "데이터 미수집"),
                ),
                "",
                build_hyundai_section(report_data),
            ]
        )
    else:
        sections.extend(
            [
                build_hyundai_section(report_data),
                "",
                session_block,
                "",
                "## 섹터별 뉴스 및 투자 판단",
                "",
                build_sector_news_sections(report_data),
            ]
        )
    return "\n".join(sections).rstrip() + "\n"


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    target_date = resolve_date(args.date)
    output_path = build_output_path(args.session, target_date)

    if output_path.exists() and not args.overwrite:
        print(f"File already exists: {output_path.relative_to(ROOT)}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_content(args.session, target_date), encoding="utf-8")
    print(output_path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
