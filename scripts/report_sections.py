from __future__ import annotations

from typing import Iterable

from report_data import ANALYSIS_PENDING, DATA_MISSING


SECTOR_SPECS = [
    ("반도체", ["삼성전자", "SK하이닉스", "한미반도체", "리노공업"]),
    ("AI", ["네이버", "카카오", "폴라리스오피스", "솔트룩스"]),
    ("로봇", ["레인보우로보틱스", "두산로보틱스", "로보스타", "유일로보틱스"]),
    ("자동차/현대차", ["현대차", "기아", "현대모비스", "현대오토에버"]),
    ("바이오/헬스케어", ["삼성바이오로직스", "셀트리온", "유한양행", "디앤디파마텍"]),
    ("ETF: SCHD, QQQM, SPYG", ["SCHD", "QQQM", "SPYG"]),
]

WATCHLIST_FILE_STOCKS = ("현대차", "디앤디파마텍")

FLOW_RANKING_TITLES = {
    "kospi_foreign_buy": "코스피 외국인 순매수 상위 1~10",
    "kospi_foreign_sell": "코스피 외국인 순매도 상위 1~10",
    "kosdaq_foreign_buy": "코스닥 외국인 순매수 상위 1~10",
    "kosdaq_foreign_sell": "코스닥 외국인 순매도 상위 1~10",
    "kospi_institutional_buy": "코스피 기관 순매수 상위 1~10",
    "kospi_institutional_sell": "코스피 기관 순매도 상위 1~10",
    "kosdaq_institutional_buy": "코스닥 기관 순매수 상위 1~10",
    "kosdaq_institutional_sell": "코스닥 기관 순매도 상위 1~10",
}

FLOW_DUPLICATE_PAIRS = {
    "kospi_foreign_buy": "kospi_institutional_buy",
    "kospi_foreign_sell": "kospi_institutional_sell",
    "kosdaq_foreign_buy": "kosdaq_institutional_buy",
    "kosdaq_foreign_sell": "kosdaq_institutional_sell",
    "kospi_institutional_buy": "kospi_foreign_buy",
    "kospi_institutional_sell": "kospi_foreign_sell",
    "kosdaq_institutional_buy": "kosdaq_foreign_buy",
    "kosdaq_institutional_sell": "kosdaq_foreign_sell",
}


def with_missing_reason(value: str, reason: str) -> str:
    if value == DATA_MISSING:
        return f"{DATA_MISSING} ({reason})"
    return value


def comparison_text(snapshot: dict | None = None) -> str:
    snapshot = snapshot or {}
    return " | ".join(
        [
            f"현재 {snapshot.get('text', DATA_MISSING)}",
            f"1개월 전 기준 최신치 {snapshot.get('month_ago_text', DATA_MISSING)}",
            f"1주 전 기준 최신치 {snapshot.get('week_ago_text', DATA_MISSING)}",
            f"어제 기준 최신치 {snapshot.get('yesterday_text', DATA_MISSING)}",
        ]
    )


def latest_disclosure_line(items: list | None = None) -> str:
    items = items or []
    if not items:
        return DATA_MISSING
    latest = items[0]
    report_name = getattr(latest, "report_name", DATA_MISSING)
    filed_at = getattr(latest, "filed_at", DATA_MISSING)
    return f"{report_name} ({filed_at})"


def stock_label(name: str, sector: str) -> str:
    if name == DATA_MISSING:
        return DATA_MISSING
    if sector == DATA_MISSING:
        return name
    return f"{name} ({sector})"


def _flow_overlap_names(markets: dict[str, list[dict[str, str]]], key: str) -> set[str]:
    paired_key = FLOW_DUPLICATE_PAIRS.get(key)
    if not paired_key:
        return set()
    current_names = {
        str(item.get("name", "")).strip()
        for item in markets.get(key, [])
        if str(item.get("name", "")).strip() and item.get("name") != DATA_MISSING
    }
    paired_names = {
        str(item.get("name", "")).strip()
        for item in markets.get(paired_key, [])
        if str(item.get("name", "")).strip() and item.get("name") != DATA_MISSING
    }
    return current_names & paired_names


def _highlight_flow_name(name: str, overlaps: set[str]) -> str:
    clean = str(name or DATA_MISSING).strip() or DATA_MISSING
    if clean in overlaps:
        return f"**{clean}**"
    return clean


def build_flow_ranking_section(flow_rankings: dict | None = None, missing_reason: str = DATA_MISSING) -> str:
    flow_rankings = flow_rankings or {}
    markets = flow_rankings.get("markets", {})
    lines = [
        "## 국내 수급 상위",
        "",
        f"- 기준일: {flow_rankings.get('as_of', DATA_MISSING)}",
        f"- 출처: {flow_rankings.get('source', DATA_MISSING)}",
        f"- 금액 단위: {flow_rankings.get('amount_unit', '단위 미확인')}",
        f"- 투자주체 수량 단위: {flow_rankings.get('quantity_unit', '단위 미확인')}",
        f"- 총거래량 단위: {flow_rankings.get('volume_unit', '주')}",
        "",
    ]
    if not markets:
        lines.append(f"- 데이터 미수집 사유: {missing_reason}")
        return "\n".join(lines)

    for key, title in FLOW_RANKING_TITLES.items():
        lines.extend([f"### {title}", ""])
        items = markets.get(key, [])
        if not items:
            lines.append(f"- 데이터 미수집: {missing_reason}")
            lines.append("")
            continue
        overlaps = _flow_overlap_names(markets, key)
        if overlaps:
            lines.append(f"- 중복 종목 표시: {' , '.join(sorted(overlaps))}".replace(" , ", ", "))
        subject_label = "외국인수량" if "foreign" in key else "기관수량"
        for index, item in enumerate(items[:10], start=1):
            lines.append(
                f"{index}. {_highlight_flow_name(item.get('name', DATA_MISSING), overlaps)} | "
                f"금액 {item.get('amount', DATA_MISSING)}({flow_rankings.get('amount_unit', '단위 미확인')}) | "
                f"총거래량 {item.get('total_volume', DATA_MISSING)}{flow_rankings.get('volume_unit', '주')} | "
                f"{subject_label} {item.get('investor_quantity', DATA_MISSING)}({flow_rankings.get('quantity_unit', '단위 미확인')}) | "
                f"개인매수수량 {item.get('retail_buy_quantity', DATA_MISSING)}({flow_rankings.get('quantity_unit', '단위 미확인')}) | "
                f"개인매도수량 {item.get('retail_sell_quantity', DATA_MISSING)}({flow_rankings.get('quantity_unit', '단위 미확인')}) | "
                f"PER {item.get('per', DATA_MISSING)} | "
                f"PBR {item.get('pbr', DATA_MISSING)}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def build_us_proxy_section(report_data: dict | None = None) -> str:
    session_data = (report_data or {}).get("session", {})
    common = (report_data or {}).get("common", {})
    market_summary = common.get("market_summary", {})
    lines = [
        "## 미장 대체 지표",
        "",
        f"- 미장 핵심 섹터: {session_data.get('us_sector_focus', DATA_MISSING)}",
        f"- 산업 관련 이슈: {session_data.get('industry_major_issues', DATA_MISSING)}",
        f"- 산업 관련 이슈 해석: {session_data.get('industry_major_issues_view', ANALYSIS_PENDING)}",
        f"- 오늘/당일 핵심 변수: {market_summary.get('drivers', ANALYSIS_PENDING)}",
    ]
    return "\n".join(lines)


def build_top_news_lines(report_data: dict | None = None, limit: int = 3) -> list[str]:
    sectors = (report_data or {}).get("sectors", {})
    items: list[tuple[str, str]] = []
    for sector, data in sectors.items():
        headline = data.get("headline", DATA_MISSING)
        description = data.get("headline_description", DATA_MISSING)
        published_at = data.get("published_at", DATA_MISSING)
        source = data.get("source", DATA_MISSING)
        collection_path = data.get("collection_path", DATA_MISSING)
        url = data.get("url", DATA_MISSING)
        if headline == DATA_MISSING:
            continue
        if url != DATA_MISSING:
            if description != DATA_MISSING:
                text = f"  - {sector}: [{headline}]({url}) | {source} | {published_at} | {collection_path} | {description}"
            else:
                text = f"  - {sector}: [{headline}]({url}) | {source} | {published_at} | {collection_path}"
        else:
            if description != DATA_MISSING:
                text = f"  - {sector}: {headline} | {source} | {published_at} | {collection_path} | {description}"
            else:
                text = f"  - {sector}: {headline} | {source} | {published_at} | {collection_path}"
        items.append((published_at, text))
    items.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in items[:limit]]


def build_morning_top_news_section(report_data: dict | None = None) -> str:
    session_data = (report_data or {}).get("session", {})
    lines = [
        "### 오늘 가장 중요한 뉴스 10개",
        "",
        f"- 해외 주요 뉴스: {session_data.get('overseas_major_news', DATA_MISSING)}",
        f"- 해외 주요 뉴스 해석: {session_data.get('overseas_major_news_view', ANALYSIS_PENDING)}",
        "",
    ]
    top_news_lines = build_top_news_lines(report_data, limit=10)
    if top_news_lines:
        lines.extend(top_news_lines)
    else:
        lines.append(f"- {DATA_MISSING}")
    return "\n".join(lines)


def build_coverage_section(report_data: dict | None = None) -> str:
    coverage = (report_data or {}).get("coverage", {})
    krx_status = coverage.get("krx_status", DATA_MISSING)
    krx_reason = coverage.get("krx_reason", DATA_MISSING)
    sections = [
        "## 데이터 커버리지",
        "",
        f"- FRED: {coverage.get('fred_status', DATA_MISSING)}",
        f"- NewsAPI: {coverage.get('news_status', DATA_MISSING)}",
        f"- MarketAux: {coverage.get('marketaux_status', DATA_MISSING)}",
        f"- Massive: {coverage.get('massive_status', DATA_MISSING)}",
        f"- Alpha Vantage: {coverage.get('alpha_status', DATA_MISSING)}",
        f"- DART: {coverage.get('dart_status', DATA_MISSING)}",
        f"- KRX(KOSPI 지수): {krx_status}",
        f"- KIS(한국장 지수/수급): {coverage.get('kis_status', DATA_MISSING)}",
        f"- 한국장 데이터 미수집 이유: {coverage.get('kis_reason', DATA_MISSING)}",
        f"- 현대차 데이터 한계: {coverage.get('hyundai_reason', DATA_MISSING)}",
        f"- 뉴스 분석 한계: {coverage.get('news_reason', DATA_MISSING)}",
    ]
    if krx_status != "연결됨":
        sections.insert(8, f"- KRX 미수집 이유: {krx_reason}")
    return "\n".join(sections)


def build_common_sections(report_data: dict | None = None, *, include_flow_rankings: bool = True) -> str:
    common = (report_data or {}).get("common", {})
    session_name = (report_data or {}).get("session_name")
    market_summary = common.get("market_summary", {})
    fred = common.get("fred", {})
    rates = common.get("rates", {})
    fx_commodities = common.get("fx_commodities", {})
    korea_market = common.get("korea_market", {})
    flow_rankings = common.get("flow_rankings", {})
    missing_reasons = common.get("missing_reasons", {})
    korea_reference_date = (report_data or {}).get("korea_reference_date", DATA_MISSING)
    sections = ["<!-- TODO: API 연동 시 지수/금리/환율/원자재/수급 데이터를 자동 주입할 것. -->"]
    if session_name not in {"morning", "closing"}:
        sections.extend(
            [
                "## 시장 요약",
                "",
                f"- 시장 구조 해석: {market_summary.get('structure', ANALYSIS_PENDING)}",
                f"- 오늘/당일 핵심 변수: {market_summary.get('drivers', ANALYSIS_PENDING)}",
                f"- 투자 심리: {market_summary.get('sentiment', ANALYSIS_PENDING)}",
                "",
            ]
        )
    sections.extend(
        [
            "## FRED 매크로",
            "",
            f"- 미국 10년물 금리: {comparison_text(fred.get('us10y', {}))}",
            f"- CPI: {comparison_text(fred.get('cpi', {}))}",
            f"- PPI: {comparison_text(fred.get('ppi', {}))}",
            f"- 실업률: {comparison_text(fred.get('unemployment', {}))}",
            f"- 연방기금금리: {comparison_text(fred.get('fed_funds', {}))}",
            f"- 금리 변화 해석: {rates.get('analysis', ANALYSIS_PENDING)}",
            f"- 매크로 해석: {market_summary.get('structure', ANALYSIS_PENDING)} | {market_summary.get('drivers', ANALYSIS_PENDING)} | {market_summary.get('sentiment', ANALYSIS_PENDING)}",
            "",
            "## 환율/원자재",
            "",
            f"- 원/달러 환율: {comparison_text(fred.get('usdkrw', {}))}",
            f"- 금 시세: {comparison_text(fx_commodities.get('gold_snapshot', {}))}",
            f"- 해석: {fx_commodities.get('analysis', ANALYSIS_PENDING)}",
            "",
        ]
    )
    if session_name == "closing":
        sections.extend(
            [
                "## 시장 요약",
                "",
                f"- 시장 구조 해석: {market_summary.get('structure', ANALYSIS_PENDING)}",
                f"- 오늘/당일 핵심 변수: {market_summary.get('drivers', ANALYSIS_PENDING)}",
                f"- 투자 심리: {market_summary.get('sentiment', ANALYSIS_PENDING)}",
                "",
            ]
        )
    sections.extend(
        [
            "## 한국시장",
            "",
            f"- KOSPI: {korea_market.get('kospi', DATA_MISSING)}",
            f"- KOSDAQ: {korea_market.get('kosdaq', DATA_MISSING)}",
            f"- 한국장 기준일: {korea_reference_date}",
            f"- 주도 업종: {korea_market.get('leaders', ANALYSIS_PENDING)}",
            f"- 시장 폭과 질: {korea_market.get('breadth', ANALYSIS_PENDING)}",
            f"- 미수집 사유: {missing_reasons.get('korea_index', DATA_MISSING)}",
        ]
    )
    if include_flow_rankings and session_name in {"morning", "closing"}:
        sections.extend(
            [
                "",
                build_flow_ranking_section(flow_rankings, missing_reasons.get("flow_rankings", DATA_MISSING)),
            ]
        )
    return "\n".join(sections)


def build_hyundai_section(report_data: dict | None = None) -> str:
    return ""


def build_favorite_stock_block(name: str, data: dict | None = None) -> str:
    data = data or {}
    return "\n".join(
        [
            f"### {name}",
            "",
            f"- 현재가/종가: {data.get('current_close', DATA_MISSING)}",
            f"- 전일 종가: {with_missing_reason(data.get('previous_close', DATA_MISSING), '일별 종가 이력 부족')}",
            f"- 장중 고가/저가: {data.get('intraday_high_low', DATA_MISSING)}",
            f"- 거래량: {data.get('volume', DATA_MISSING)}",
            f"- 52주 고가: {with_missing_reason(data.get('week52_high', DATA_MISSING), '52주 범위 이력 부족')}",
            f"- 52주 저가: {with_missing_reason(data.get('week52_low', DATA_MISSING), '52주 범위 이력 부족')}",
            f"- PER: {with_missing_reason(data.get('per', DATA_MISSING), '밸류에이션 지표 미수집')}",
            f"- 포워드 PER: {with_missing_reason(data.get('forward_per', DATA_MISSING), '애널리스트 추정치 기반 지표 미수집')}",
            f"- 증권가 목표주가: {with_missing_reason(data.get('target_price', DATA_MISSING), '애널리스트 목표주가 미수집')}",
            f"- 목표주가 해석: {data.get('target_price_view', ANALYSIS_PENDING)}",
            f"- 목표주가 근거: {data.get('target_price_basis', ANALYSIS_PENDING)}",
            f"- 외국인 순매수/순매도: {with_missing_reason(data.get('foreign_flow', DATA_MISSING), '국내 투자주체 수급 API 미연동')}",
            f"- 기관 순매수/순매도: {with_missing_reason(data.get('institutional_flow', DATA_MISSING), '국내 투자주체 수급 API 미연동')}",
            f"- 개인 순매수/순매도: {with_missing_reason(data.get('retail_flow', DATA_MISSING), '국내 투자주체 수급 API 미연동')}",
            f"- 공매도: {with_missing_reason(data.get('short_selling', DATA_MISSING), '공매도 잔고/거래비중 API 미연동')}",
            f"- 반대매매: {with_missing_reason(data.get('forced_liquidation', DATA_MISSING), '반대매매 집계 데이터 소스 미연동')}",
            f"- 5일 이동평균: {with_missing_reason(data.get('ma5', DATA_MISSING), '시세 히스토리 부족')}",
            f"- 20일 이동평균: {with_missing_reason(data.get('ma20', DATA_MISSING), '시세 히스토리 부족')}",
            f"- 60일 이동평균: {with_missing_reason(data.get('ma60', DATA_MISSING), '시세 히스토리 부족')}",
            f"- 지지선: {with_missing_reason(data.get('support', DATA_MISSING), '충분한 가격 이력 부족')}",
            f"- 저항선: {with_missing_reason(data.get('resistance', DATA_MISSING), '충분한 가격 이력 부족')}",
            f"- 차트 구조: {data.get('chart_structure', ANALYSIS_PENDING)}",
            f"- 개미 털기 판단: {data.get('shakeout_view', ANALYSIS_PENDING)}",
            f"- 하락하는 이유: {data.get('down_reason', ANALYSIS_PENDING)}",
            f"- 상승하는 이유: {data.get('up_reason', ANALYSIS_PENDING)}",
            f"- 오늘 해석: {data.get('today_analysis', ANALYSIS_PENDING)}",
            f"- 내일 시나리오: {data.get('tomorrow_scenario', ANALYSIS_PENDING)}",
            f"- 예측: {data.get('forecast', ANALYSIS_PENDING)}",
            f"- 추가매수 기준: {data.get('add_rule', ANALYSIS_PENDING)}",
            f"- 매도/탈출 기준: {data.get('exit_rule', ANALYSIS_PENDING)}",
        ]
    )


def build_hyundai_dart_block(data: dict | None = None) -> str:
    data = data or {}
    return "\n".join(
        [
            "#### DART 기반 재무/자본정책/이벤트",
            "",
            f"- 최근 재무제표 기준: {data.get('dart_financial_period', DATA_MISSING)}",
            f"- 재무제표 요약: {data.get('dart_financial_summary', DATA_MISSING)}",
            f"- 재무 해석: {data.get('dart_financial_view', ANALYSIS_PENDING)}",
            f"- 자본 정책 공시: {data.get('dart_capital_policy', DATA_MISSING)}",
            f"- 자본 정책 해석: {data.get('dart_capital_policy_view', ANALYSIS_PENDING)}",
            f"- 이벤트성 공시: {data.get('dart_events', DATA_MISSING)}",
            f"- 이벤트 해석: {data.get('dart_events_view', ANALYSIS_PENDING)}",
        ]
    )


def build_sector_news_sections(report_data: dict | None = None) -> str:
    sector_data = (report_data or {}).get("sectors", {})
    return "\n\n".join(build_sector_section(title, related, sector_data.get(title, {})) for title, related in SECTOR_SPECS)


def build_sector_section(title: str, related_stocks: Iterable[str], data: dict | None = None) -> str:
    data = data or {}
    related = ", ".join(related_stocks)
    lines = [
        f"## {title}",
        "",
        "<!-- TODO: API 연동 시 뉴스 원문, 기사 시각, 관련 종목 반응률을 자동 채움. -->",
        f"- 오늘 핵심 뉴스: {data.get('headline', DATA_MISSING)}",
        f"- 원문 제목: {data.get('headline_original', DATA_MISSING)}",
        f"- 본문 요약: {data.get('headline_description', DATA_MISSING)}",
        f"- 출처: {data.get('source', DATA_MISSING)}",
        f"- 수집 경로: {data.get('collection_path', DATA_MISSING)}",
        f"- 발행일: {data.get('published_at', DATA_MISSING)}",
        f"- URL: {data.get('url', DATA_MISSING)}",
        f"- 주가 영향: {data.get('price_impact', ANALYSIS_PENDING)}",
        f"- 단기 영향: {data.get('short_term', ANALYSIS_PENDING)}",
        f"- 중장기 영향: {data.get('medium_term', ANALYSIS_PENDING)}",
        f"- 관련 종목: {related}",
        f"- 주요 일정/실적 발표: {data.get('schedule', DATA_MISSING)}",
        f"- 일정 상세: {data.get('schedule_detail', DATA_MISSING)}",
        f"- 일정 해석: {data.get('schedule_view', ANALYSIS_PENDING)}",
        f"- 투자 판단: {data.get('investment_judgment', ANALYSIS_PENDING)}",
        f"- 주의할 점: {data.get('risk', ANALYSIS_PENDING)}",
    ]
    if title == "바이오/헬스케어":
        lines.extend(
            [
                f"- 국내 바이오 주도주: {data.get('leaders', DATA_MISSING)}",
                f"- 임상 뉴스: {data.get('clinical_news', DATA_MISSING)}",
                f"- FDA/식약처 뉴스: {data.get('fda_news', DATA_MISSING)}",
                f"- 기술수출 뉴스: {data.get('licensing_news', DATA_MISSING)}",
                f"- 금리 영향: {data.get('rate_impact', ANALYSIS_PENDING)}",
                f"- 디앤디파마텍 관심종목 코멘트: {data.get('dnd_comment', ANALYSIS_PENDING)}",
            ]
        )
    if title == "ETF: SCHD, QQQM, SPYG":
        lines.extend(
            [
                f"- SCHD 코멘트: {data.get('schd_comment', ANALYSIS_PENDING)}",
                f"- QQQM 코멘트: {data.get('qqqm_comment', ANALYSIS_PENDING)}",
                f"- SPYG 코멘트: {data.get('spyg_comment', ANALYSIS_PENDING)}",
            ]
        )
    return "\n".join(lines)


def build_morning_summary_section(report_data: dict | None = None) -> str:
    session_data = (report_data or {}).get("session", {})
    market_summary = (report_data or {}).get("common", {}).get("market_summary", {})
    lines = [
        "## 시작 요약",
        "",
        f"- 오늘/당일 핵심 변수: {market_summary.get('drivers', ANALYSIS_PENDING)}",
        f"- 투자 심리: {market_summary.get('sentiment', ANALYSIS_PENDING)}",
        f"- 왜 {session_data.get('stance', DATA_MISSING)}인지: {session_data.get('stance_reason', ANALYSIS_PENDING)}",
    ]
    return "\n".join(lines)


def build_session_specific_section(session: str, summary_hint: str, report_data: dict | None = None) -> str:
    session_data = (report_data or {}).get("session", {})
    if session == "morning":
        return "\n".join(
            [
                "## 시장 프레임",
                "",
                summary_hint,
                "",
                f"- 오늘 매매 가능한 날인지: {session_data.get('market_tradeability', ANALYSIS_PENDING)}",
                f"- 시장 기본 방향: {session_data.get('market_bias', ANALYSIS_PENDING)}",
                f"- 반드시 확인할 뉴스 3개: {session_data.get('must_check_news', DATA_MISSING)}",
                f"- 장 시작 후 30분 체크포인트: {session_data.get('first_30m_checkpoints', ANALYSIS_PENDING)}",
                f"- 시장 리스크 가드: {session_data.get('market_risk_guard', ANALYSIS_PENDING)}",
                "",
                "## 섹터 프레임",
                "",
                f"- 어디에 돈이 붙는지: {session_data.get('sector_money_flow', ANALYSIS_PENDING)}",
                f"- 오늘 우선 볼 섹터: {session_data.get('sector_priority', ANALYSIS_PENDING)}",
                f"- 섹터 체크포인트: {session_data.get('sector_watchpoints', ANALYSIS_PENDING)}",
                f"- 섹터에서 하지 말아야 할 행동: {session_data.get('sector_avoid', ANALYSIS_PENDING)}",
                "",
                "## 색터별 최근 공시",
                "",
                f"- 최근 공시: {session_data.get('recent_disclosures', DATA_MISSING)}",
                f"- 공시 요약: {session_data.get('disclosure_summary', DATA_MISSING)}",
                "",
                "## 섹터 개별주",
                "",
                f"- 자동 선별 1: {stock_label(session_data.get('stock_1_name', DATA_MISSING), session_data.get('stock_1_sector', DATA_MISSING))}",
                f"- 선별 근거 1: {session_data.get('stock_1_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 1: {session_data.get('stock_1_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 1: {session_data.get('stock_1_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 1: {session_data.get('stock_1_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 1: {session_data.get('stock_1_invalid', ANALYSIS_PENDING)}",
                f"- 증권가 목표주가 1: {session_data.get('stock_1_target_price', DATA_MISSING)}",
                f"- 목표주가 해석 1: {session_data.get('stock_1_target_price_view', ANALYSIS_PENDING)}",
                f"- 목표주가 근거 1: {session_data.get('stock_1_target_price_basis', ANALYSIS_PENDING)}",
                "",
                f"- 자동 선별 2: {stock_label(session_data.get('stock_2_name', DATA_MISSING), session_data.get('stock_2_sector', DATA_MISSING))}",
                f"- 선별 근거 2: {session_data.get('stock_2_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 2: {session_data.get('stock_2_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 2: {session_data.get('stock_2_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 2: {session_data.get('stock_2_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 2: {session_data.get('stock_2_invalid', ANALYSIS_PENDING)}",
                f"- 증권가 목표주가 2: {session_data.get('stock_2_target_price', DATA_MISSING)}",
                f"- 목표주가 해석 2: {session_data.get('stock_2_target_price_view', ANALYSIS_PENDING)}",
                f"- 목표주가 근거 2: {session_data.get('stock_2_target_price_basis', ANALYSIS_PENDING)}",
                "",
                f"- 자동 선별 3: {stock_label(session_data.get('stock_3_name', DATA_MISSING), session_data.get('stock_3_sector', DATA_MISSING))}",
                f"- 선별 근거 3: {session_data.get('stock_3_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 3: {session_data.get('stock_3_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 3: {session_data.get('stock_3_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 3: {session_data.get('stock_3_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 3: {session_data.get('stock_3_invalid', ANALYSIS_PENDING)}",
                f"- 증권가 목표주가 3: {session_data.get('stock_3_target_price', DATA_MISSING)}",
                f"- 목표주가 해석 3: {session_data.get('stock_3_target_price_view', ANALYSIS_PENDING)}",
                f"- 목표주가 근거 3: {session_data.get('stock_3_target_price_basis', ANALYSIS_PENDING)}",
            ]
        )
    if session == "afternoon":
        return "\n".join(
            [
                "## 오전장 복기",
                "",
                summary_hint,
                "",
                f"- 오전장 흐름 요약: {session_data.get('morning_flow', ANALYSIS_PENDING)}",
                f"- 오전장 고점/저점 체크: {session_data.get('morning_range', DATA_MISSING)}",
                f"- 거래대금 상위 섹터: {session_data.get('turnover_leaders', DATA_MISSING)}",
                f"- 오전 가설 적중 여부: {session_data.get('hypothesis_result', ANALYSIS_PENDING)}",
                "",
                "## 시장 프레임",
                "",
                f"- 오후에도 매매 가능한지: {session_data.get('market_tradeability', ANALYSIS_PENDING)}",
                f"- 시장 기본 방향: {session_data.get('market_bias', ANALYSIS_PENDING)}",
                f"- 종가까지 추적할 데이터: {session_data.get('close_watch', DATA_MISSING)}",
                f"- 시장 리스크 가드: {session_data.get('market_risk_guard', ANALYSIS_PENDING)}",
                "",
                "## 섹터 프레임",
                "",
                f"- 어디에 돈이 붙는지: {session_data.get('sector_money_flow', ANALYSIS_PENDING)}",
                f"- 오후 우선 볼 섹터: {session_data.get('sector_priority', ANALYSIS_PENDING)}",
                f"- 섹터 체크포인트: {session_data.get('sector_watchpoints', ANALYSIS_PENDING)}",
                f"- 섹터에서 하지 말아야 할 행동: {session_data.get('sector_avoid', ANALYSIS_PENDING)}",
                "",
                "## 색터별 최근 공시",
                "",
                f"- 최근 공시: {session_data.get('recent_disclosures', DATA_MISSING)}",
                f"- 공시 요약: {session_data.get('disclosure_summary', DATA_MISSING)}",
                "",
                "## 섹터 개별주",
                "",
                f"- 자동 선별 1: {stock_label(session_data.get('stock_1_name', DATA_MISSING), session_data.get('stock_1_sector', DATA_MISSING))}",
                f"- 선별 근거 1: {session_data.get('stock_1_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 1: {session_data.get('stock_1_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 1: {session_data.get('stock_1_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 1: {session_data.get('stock_1_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 1: {session_data.get('stock_1_invalid', ANALYSIS_PENDING)}",
                f"- 차트 구조 1: {session_data.get('stock_1_chart', ANALYSIS_PENDING)}",
                f"- 개미 털기 판단 1: {session_data.get('stock_1_shakeout', ANALYSIS_PENDING)}",
                f"- 하락 이유 1: {session_data.get('stock_1_down_reason', ANALYSIS_PENDING)}",
                f"- 상승 이유 1: {session_data.get('stock_1_up_reason', ANALYSIS_PENDING)}",
                f"- 예측 1: {session_data.get('stock_1_forecast', ANALYSIS_PENDING)}",
                f"- 증권가 목표주가 1: {session_data.get('stock_1_target_price', DATA_MISSING)}",
                f"- 목표주가 해석 1: {session_data.get('stock_1_target_price_view', ANALYSIS_PENDING)}",
                f"- 목표주가 근거 1: {session_data.get('stock_1_target_price_basis', ANALYSIS_PENDING)}",
                "",
                f"- 자동 선별 2: {stock_label(session_data.get('stock_2_name', DATA_MISSING), session_data.get('stock_2_sector', DATA_MISSING))}",
                f"- 선별 근거 2: {session_data.get('stock_2_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 2: {session_data.get('stock_2_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 2: {session_data.get('stock_2_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 2: {session_data.get('stock_2_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 2: {session_data.get('stock_2_invalid', ANALYSIS_PENDING)}",
                f"- 차트 구조 2: {session_data.get('stock_2_chart', ANALYSIS_PENDING)}",
                f"- 개미 털기 판단 2: {session_data.get('stock_2_shakeout', ANALYSIS_PENDING)}",
                f"- 하락 이유 2: {session_data.get('stock_2_down_reason', ANALYSIS_PENDING)}",
                f"- 상승 이유 2: {session_data.get('stock_2_up_reason', ANALYSIS_PENDING)}",
                f"- 예측 2: {session_data.get('stock_2_forecast', ANALYSIS_PENDING)}",
                f"- 증권가 목표주가 2: {session_data.get('stock_2_target_price', DATA_MISSING)}",
                f"- 목표주가 해석 2: {session_data.get('stock_2_target_price_view', ANALYSIS_PENDING)}",
                f"- 목표주가 근거 2: {session_data.get('stock_2_target_price_basis', ANALYSIS_PENDING)}",
                "",
                f"- 자동 선별 3: {stock_label(session_data.get('stock_3_name', DATA_MISSING), session_data.get('stock_3_sector', DATA_MISSING))}",
                f"- 선별 근거 3: {session_data.get('stock_3_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 3: {session_data.get('stock_3_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 3: {session_data.get('stock_3_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 3: {session_data.get('stock_3_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 3: {session_data.get('stock_3_invalid', ANALYSIS_PENDING)}",
                f"- 차트 구조 3: {session_data.get('stock_3_chart', ANALYSIS_PENDING)}",
                f"- 개미 털기 판단 3: {session_data.get('stock_3_shakeout', ANALYSIS_PENDING)}",
                f"- 하락 이유 3: {session_data.get('stock_3_down_reason', ANALYSIS_PENDING)}",
                f"- 상승 이유 3: {session_data.get('stock_3_up_reason', ANALYSIS_PENDING)}",
                f"- 예측 3: {session_data.get('stock_3_forecast', ANALYSIS_PENDING)}",
                f"- 증권가 목표주가 3: {session_data.get('stock_3_target_price', DATA_MISSING)}",
                f"- 목표주가 해석 3: {session_data.get('stock_3_target_price_view', ANALYSIS_PENDING)}",
                f"- 목표주가 근거 3: {session_data.get('stock_3_target_price_basis', ANALYSIS_PENDING)}",
                "",
                "## 공통 리스크 관리",
                "",
                f"- 신규 진입 금지 조건: {session_data.get('no_trade_condition', ANALYSIS_PENDING)}",
                f"- 허용 포지션 크기: {session_data.get('position_size_rule', ANALYSIS_PENDING)}",
                f"- 공통 반대 신호: {session_data.get('opposite_signal', ANALYSIS_PENDING)}",
            ]
        )
    if session == "closing":
        return "\n".join(
            [
                "## 시계열 전망",
                "",
                f"- 내일 전망: {session_data.get('tomorrow_outlook', ANALYSIS_PENDING)}",
                f"- 다음주 전망: {session_data.get('next_week_outlook', ANALYSIS_PENDING)}",
                f"- 1개월 전망: {session_data.get('one_month_outlook', ANALYSIS_PENDING)}",
                f"- 6개월 전망: {session_data.get('six_month_outlook', ANALYSIS_PENDING)}",
                f"- 상승 시나리오: {session_data.get('bull_case', ANALYSIS_PENDING)}",
                f"- 하락 시나리오: {session_data.get('bear_case', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 조건: {session_data.get('invalidation_case', ANALYSIS_PENDING)}",
                f"- 반드시 볼 체크포인트: {session_data.get('must_watch', ANALYSIS_PENDING)}",
                "",
                "## 섹터 프레임",
                "",
                f"- 어디에 돈이 붙는지: {session_data.get('sector_money_flow', ANALYSIS_PENDING)}",
                f"- 내일 우선 볼 섹터: {session_data.get('sector_priority', ANALYSIS_PENDING)}",
                f"- 섹터 체크포인트: {session_data.get('sector_watchpoints', ANALYSIS_PENDING)}",
                f"- 섹터에서 하지 말아야 할 행동: {session_data.get('sector_avoid', ANALYSIS_PENDING)}",
                "",
                "## 색터별 최근 공시",
                "",
                f"- 최근 공시: {session_data.get('recent_disclosures', DATA_MISSING)}",
                f"- 공시 요약: {session_data.get('disclosure_summary', DATA_MISSING)}",
                "",
                "## 섹터 개별주",
                "",
                f"- 자동 선별 1: {stock_label(session_data.get('stock_1_name', DATA_MISSING), session_data.get('stock_1_sector', DATA_MISSING))}",
                f"- 선별 근거 1: {session_data.get('stock_1_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 1: {session_data.get('stock_1_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 1: {session_data.get('stock_1_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 1: {session_data.get('stock_1_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 1: {session_data.get('stock_1_invalid', ANALYSIS_PENDING)}",
                f"- 차트 구조 1: {session_data.get('stock_1_chart', ANALYSIS_PENDING)}",
                f"- 개미 털기 판단 1: {session_data.get('stock_1_shakeout', ANALYSIS_PENDING)}",
                f"- 하락 이유 1: {session_data.get('stock_1_down_reason', ANALYSIS_PENDING)}",
                f"- 상승 이유 1: {session_data.get('stock_1_up_reason', ANALYSIS_PENDING)}",
                f"- 예측 1: {session_data.get('stock_1_forecast', ANALYSIS_PENDING)}",
                f"- 증권가 목표주가 1: {session_data.get('stock_1_target_price', DATA_MISSING)}",
                f"- 목표주가 해석 1: {session_data.get('stock_1_target_price_view', ANALYSIS_PENDING)}",
                f"- 목표주가 근거 1: {session_data.get('stock_1_target_price_basis', ANALYSIS_PENDING)}",
                "",
                f"- 자동 선별 2: {stock_label(session_data.get('stock_2_name', DATA_MISSING), session_data.get('stock_2_sector', DATA_MISSING))}",
                f"- 선별 근거 2: {session_data.get('stock_2_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 2: {session_data.get('stock_2_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 2: {session_data.get('stock_2_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 2: {session_data.get('stock_2_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 2: {session_data.get('stock_2_invalid', ANALYSIS_PENDING)}",
                f"- 차트 구조 2: {session_data.get('stock_2_chart', ANALYSIS_PENDING)}",
                f"- 개미 털기 판단 2: {session_data.get('stock_2_shakeout', ANALYSIS_PENDING)}",
                f"- 하락 이유 2: {session_data.get('stock_2_down_reason', ANALYSIS_PENDING)}",
                f"- 상승 이유 2: {session_data.get('stock_2_up_reason', ANALYSIS_PENDING)}",
                f"- 예측 2: {session_data.get('stock_2_forecast', ANALYSIS_PENDING)}",
                f"- 증권가 목표주가 2: {session_data.get('stock_2_target_price', DATA_MISSING)}",
                f"- 목표주가 해석 2: {session_data.get('stock_2_target_price_view', ANALYSIS_PENDING)}",
                f"- 목표주가 근거 2: {session_data.get('stock_2_target_price_basis', ANALYSIS_PENDING)}",
                "",
                f"- 자동 선별 3: {stock_label(session_data.get('stock_3_name', DATA_MISSING), session_data.get('stock_3_sector', DATA_MISSING))}",
                f"- 선별 근거 3: {session_data.get('stock_3_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 3: {session_data.get('stock_3_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 3: {session_data.get('stock_3_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 3: {session_data.get('stock_3_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 3: {session_data.get('stock_3_invalid', ANALYSIS_PENDING)}",
                f"- 차트 구조 3: {session_data.get('stock_3_chart', ANALYSIS_PENDING)}",
                f"- 개미 털기 판단 3: {session_data.get('stock_3_shakeout', ANALYSIS_PENDING)}",
                f"- 하락 이유 3: {session_data.get('stock_3_down_reason', ANALYSIS_PENDING)}",
                f"- 상승 이유 3: {session_data.get('stock_3_up_reason', ANALYSIS_PENDING)}",
                f"- 예측 3: {session_data.get('stock_3_forecast', ANALYSIS_PENDING)}",
                f"- 증권가 목표주가 3: {session_data.get('stock_3_target_price', DATA_MISSING)}",
                f"- 목표주가 해석 3: {session_data.get('stock_3_target_price_view', ANALYSIS_PENDING)}",
                f"- 목표주가 근거 3: {session_data.get('stock_3_target_price_basis', ANALYSIS_PENDING)}",
                "",
                "## 공통 리스크 관리",
                "",
                f"- 신규 진입 금지 조건: {session_data.get('no_trade_condition', ANALYSIS_PENDING)}",
                f"- 내일 허용 포지션 크기: {session_data.get('position_size_rule', ANALYSIS_PENDING)}",
                f"- 내일 반대 신호: {session_data.get('opposite_signal', ANALYSIS_PENDING)}",
            ]
        )
    raise ValueError(f"Unsupported session: {session}")


def build_closing_decision_sections(report_data: dict | None = None) -> str:
    closing = (report_data or {}).get("closing", {})
    return "\n".join(
        [
            "## 종가 기준 결론",
            "",
            f"- 오늘 장 요약: {closing.get('market_day_summary', ANALYSIS_PENDING)}",
            f"- 움직인 이유: {closing.get('market_move_reason', ANALYSIS_PENDING)}",
            f"- 오늘 확인된 약점: {closing.get('market_problem', ANALYSIS_PENDING)}",
            f"- 종가 기준 심리 해석: {closing.get('market_sentiment_view', ANALYSIS_PENDING)}",
            f"- 현대차 해석: {closing.get('hyundai_day_view', ANALYSIS_PENDING)}",
            f"- 다음 거래일 핵심 체크포인트: {closing.get('must_watch', ANALYSIS_PENDING)}",
        ]
    )
