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


def with_missing_reason(value: str, reason: str) -> str:
    if value == DATA_MISSING:
        return f"{DATA_MISSING} ({reason})"
    return value


def stock_label(name: str, sector: str) -> str:
    if name == DATA_MISSING:
        return DATA_MISSING
    if sector == DATA_MISSING:
        return name
    return f"{name} ({sector})"


def build_top_news_lines(report_data: dict | None = None) -> list[str]:
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
    return [item[1] for item in items[:3]]


def build_coverage_section(report_data: dict | None = None) -> str:
    coverage = (report_data or {}).get("coverage", {})
    sections = [
        "## 데이터 커버리지",
        "",
        f"- FRED: {coverage.get('fred_status', DATA_MISSING)}",
        f"- NewsAPI: {coverage.get('news_status', DATA_MISSING)}",
        f"- MarketAux: {coverage.get('marketaux_status', DATA_MISSING)}",
        f"- Massive: {coverage.get('massive_status', DATA_MISSING)}",
        f"- Alpha Vantage: {coverage.get('alpha_status', DATA_MISSING)}",
        f"- DART: {coverage.get('dart_status', DATA_MISSING)}",
        f"- KRX(KOSPI 지수): {coverage.get('krx_status', DATA_MISSING)}",
        f"- KRX 미수집 이유: {coverage.get('krx_reason', DATA_MISSING)}",
        f"- KIS(한국장 지수/수급): {coverage.get('kis_status', DATA_MISSING)}",
        f"- 한국장 데이터 미수집 이유: {coverage.get('kis_reason', DATA_MISSING)}",
        f"- 현대차 데이터 한계: {coverage.get('hyundai_reason', DATA_MISSING)}",
        f"- 뉴스 분석 한계: {coverage.get('news_reason', DATA_MISSING)}",
    ]
    return "\n".join(sections)


def build_common_sections(report_data: dict | None = None) -> str:
    common = (report_data or {}).get("common", {})
    market_summary = common.get("market_summary", {})
    fred = common.get("fred", {})
    rates = common.get("rates", {})
    fx_commodities = common.get("fx_commodities", {})
    korea_market = common.get("korea_market", {})
    flow = common.get("flow", {})
    missing_reasons = common.get("missing_reasons", {})
    sections = [
        "<!-- TODO: API 연동 시 지수/금리/환율/원자재/수급 데이터를 자동 주입할 것. -->",
        "## 시장 요약",
        "",
        f"- 시장 구조 해석: {market_summary.get('structure', ANALYSIS_PENDING)}",
        f"- 오늘/당일 핵심 변수: {market_summary.get('drivers', ANALYSIS_PENDING)}",
        f"- 투자 심리: {market_summary.get('sentiment', ANALYSIS_PENDING)}",
        "",
        "## FRED 매크로",
        "",
        f"- 미국 10년물 금리: {fred.get('us10y', {}).get('text', DATA_MISSING)}",
        f"- CPI: {fred.get('cpi', {}).get('text', DATA_MISSING)}",
        f"- PPI: {fred.get('ppi', {}).get('text', DATA_MISSING)}",
        f"- 실업률: {fred.get('unemployment', {}).get('text', DATA_MISSING)}",
        f"- 연방기금금리: {fred.get('fed_funds', {}).get('text', DATA_MISSING)}",
        f"- 금리 변화 해석: {rates.get('analysis', ANALYSIS_PENDING)}",
        "",
        "## 환율/원자재",
        "",
        f"- 원/달러 환율: {fx_commodities.get('usdkrw', DATA_MISSING)}",
        f"- 금 시세: {fx_commodities.get('gold', DATA_MISSING)}",
        f"- 해석: {fx_commodities.get('analysis', ANALYSIS_PENDING)}",
        "",
        "## 한국시장",
        "",
        f"- KOSPI: {korea_market.get('kospi', DATA_MISSING)}",
        f"- KOSDAQ: {korea_market.get('kosdaq', DATA_MISSING)}",
        f"- 주도 업종: {korea_market.get('leaders', ANALYSIS_PENDING)}",
        f"- 시장 폭과 질: {korea_market.get('breadth', ANALYSIS_PENDING)}",
        f"- 미수집 사유: {missing_reasons.get('korea_index', DATA_MISSING)}",
        "",
        "## 외국인/기관/개인 수급",
        "",
        f"- 외국인 수급: {with_missing_reason(flow.get('foreign', DATA_MISSING), missing_reasons.get('investor_flow', DATA_MISSING))}",
        f"- 기관 수급: {with_missing_reason(flow.get('institutional', DATA_MISSING), missing_reasons.get('investor_flow', DATA_MISSING))}",
        f"- 개인 수급: {with_missing_reason(flow.get('retail', DATA_MISSING), missing_reasons.get('investor_flow', DATA_MISSING))}",
        f"- 수급 해석: {flow.get('analysis', ANALYSIS_PENDING)}",
        f"- 미수집 사유: {missing_reasons.get('investor_flow', DATA_MISSING)}",
    ]
    return "\n".join(sections)


def build_hyundai_section(report_data: dict | None = None) -> str:
    hyundai = (report_data or {}).get("hyundai", {})
    lines = [
        "<!-- TODO: API 연동 시 현대차 가격, 거래량, 투자주체 수급, 이동평균을 자동 채움. -->",
        "## 현대차 전용 분석",
        "",
        f"- 현재가/종가: {hyundai.get('current_close', DATA_MISSING)}",
        f"- 전일 종가: {with_missing_reason(hyundai.get('previous_close', DATA_MISSING), 'Alpha Vantage 일별 종가 이력 부족')}",
        f"- 장중 고가/저가: {hyundai.get('intraday_high_low', DATA_MISSING)}",
        f"- 거래량: {hyundai.get('volume', DATA_MISSING)}",
        f"- 52주 고가: {with_missing_reason(hyundai.get('week52_high', DATA_MISSING), 'Alpha Vantage 52주 범위 이력 부족')}",
        f"- 52주 저가: {with_missing_reason(hyundai.get('week52_low', DATA_MISSING), 'Alpha Vantage 52주 범위 이력 부족')}",
        f"- 외국인 순매수/순매도: {with_missing_reason(hyundai.get('foreign_flow', DATA_MISSING), '국내 투자주체 수급 API 미연동')}",
        f"- 기관 순매수/순매도: {with_missing_reason(hyundai.get('institutional_flow', DATA_MISSING), '국내 투자주체 수급 API 미연동')}",
        f"- 개인 순매수/순매도: {with_missing_reason(hyundai.get('retail_flow', DATA_MISSING), '국내 투자주체 수급 API 미연동')}",
        f"- 공매도: {with_missing_reason(hyundai.get('short_selling', DATA_MISSING), '공매도 잔고/거래비중 API 미연동')}",
        f"- 반대매매: {with_missing_reason(hyundai.get('forced_liquidation', DATA_MISSING), '반대매매 집계 데이터 소스 미연동')}",
        f"- 5일 이동평균: {with_missing_reason(hyundai.get('ma5', DATA_MISSING), '시세 히스토리 부족')}",
        f"- 20일 이동평균: {with_missing_reason(hyundai.get('ma20', DATA_MISSING), '시세 히스토리 부족')}",
        f"- 60일 이동평균: {with_missing_reason(hyundai.get('ma60', DATA_MISSING), '시세 히스토리 부족')}",
        f"- 지지선: {with_missing_reason(hyundai.get('support', DATA_MISSING), '충분한 가격 이력 부족')}",
        f"- 저항선: {with_missing_reason(hyundai.get('resistance', DATA_MISSING), '충분한 가격 이력 부족')}",
        f"- 오늘 해석: {hyundai.get('today_analysis', ANALYSIS_PENDING)}",
        f"- 내일 시나리오: {hyundai.get('tomorrow_scenario', ANALYSIS_PENDING)}",
        f"- 추가매수 기준: {hyundai.get('add_rule', ANALYSIS_PENDING)}",
        f"- 매도/탈출 기준: {hyundai.get('exit_rule', ANALYSIS_PENDING)}",
    ]
    return "\n".join(lines)


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
    lines = [
        "## 오늘의 1페이지 요약",
        "",
        f"- 시장 점수: {session_data.get('market_score', DATA_MISSING)}",
        f"- 공격 / 중립 / 방어: {session_data.get('stance', DATA_MISSING)}",
        "- 오늘 가장 중요한 뉴스 3개:",
    ]
    top_news_lines = build_top_news_lines(report_data)
    if top_news_lines:
        lines.extend(top_news_lines)
    else:
        lines.append(f"  - {DATA_MISSING}")
    lines.extend(
        [
            f"- 세계 주요 이슈: {session_data.get('global_major_issues', DATA_MISSING)}",
            f"- 산업 관련 이슈: {session_data.get('industry_major_issues', DATA_MISSING)}",
            f"- 현재 돈이 몰리는 곳: {session_data.get('capital_flow_now', DATA_MISSING)}",
            f"- 미장 핵심 섹터: {session_data.get('us_sector_focus', DATA_MISSING)}",
            f"- 오늘 예상 섹터: {session_data.get('expected_sector_today', DATA_MISSING)}",
            f"- ETF 핵심 시나리오: {session_data.get('etf_core', ANALYSIS_PENDING)}",
            f"- 절대 하지 말아야 할 행동: {session_data.get('dont_do', DATA_MISSING)}",
            f"- 근거 점수: {session_data.get('evidence_score', DATA_MISSING)}",
            f"- 근거 품질 코멘트: {session_data.get('evidence_comment', ANALYSIS_PENDING)}",
        ]
    )
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
                "## 개별주 실행 프레임",
                "",
                f"- 자동 선별 1: {stock_label(session_data.get('stock_1_name', DATA_MISSING), session_data.get('stock_1_sector', DATA_MISSING))}",
                f"- 선별 근거 1: {session_data.get('stock_1_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 1: {session_data.get('stock_1_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 1: {session_data.get('stock_1_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 1: {session_data.get('stock_1_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 1: {session_data.get('stock_1_invalid', ANALYSIS_PENDING)}",
                "",
                f"- 자동 선별 2: {stock_label(session_data.get('stock_2_name', DATA_MISSING), session_data.get('stock_2_sector', DATA_MISSING))}",
                f"- 선별 근거 2: {session_data.get('stock_2_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 2: {session_data.get('stock_2_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 2: {session_data.get('stock_2_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 2: {session_data.get('stock_2_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 2: {session_data.get('stock_2_invalid', ANALYSIS_PENDING)}",
                "",
                f"- 자동 선별 3: {stock_label(session_data.get('stock_3_name', DATA_MISSING), session_data.get('stock_3_sector', DATA_MISSING))}",
                f"- 선별 근거 3: {session_data.get('stock_3_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 3: {session_data.get('stock_3_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 3: {session_data.get('stock_3_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 3: {session_data.get('stock_3_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 3: {session_data.get('stock_3_invalid', ANALYSIS_PENDING)}",
                "",
                "## 공통 리스크 관리",
                "",
                f"- 신규 진입 금지 조건: {session_data.get('no_trade_condition', ANALYSIS_PENDING)}",
                f"- 허용 포지션 크기: {session_data.get('position_size_rule', ANALYSIS_PENDING)}",
                f"- 공통 반대 신호: {session_data.get('opposite_signal', ANALYSIS_PENDING)}",
                "",
                "## 최근 공시",
                "",
                f"- 최근 공시: {session_data.get('recent_disclosures', DATA_MISSING)}",
                f"- 공시 요약: {session_data.get('disclosure_summary', DATA_MISSING)}",
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
                "## 개별주 실행 프레임",
                "",
                f"- 자동 선별 1: {stock_label(session_data.get('stock_1_name', DATA_MISSING), session_data.get('stock_1_sector', DATA_MISSING))}",
                f"- 선별 근거 1: {session_data.get('stock_1_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 1: {session_data.get('stock_1_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 1: {session_data.get('stock_1_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 1: {session_data.get('stock_1_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 1: {session_data.get('stock_1_invalid', ANALYSIS_PENDING)}",
                "",
                f"- 자동 선별 2: {stock_label(session_data.get('stock_2_name', DATA_MISSING), session_data.get('stock_2_sector', DATA_MISSING))}",
                f"- 선별 근거 2: {session_data.get('stock_2_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 2: {session_data.get('stock_2_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 2: {session_data.get('stock_2_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 2: {session_data.get('stock_2_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 2: {session_data.get('stock_2_invalid', ANALYSIS_PENDING)}",
                "",
                f"- 자동 선별 3: {stock_label(session_data.get('stock_3_name', DATA_MISSING), session_data.get('stock_3_sector', DATA_MISSING))}",
                f"- 선별 근거 3: {session_data.get('stock_3_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 3: {session_data.get('stock_3_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 3: {session_data.get('stock_3_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 3: {session_data.get('stock_3_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 3: {session_data.get('stock_3_invalid', ANALYSIS_PENDING)}",
                "",
                "## 공통 리스크 관리",
                "",
                f"- 신규 진입 금지 조건: {session_data.get('no_trade_condition', ANALYSIS_PENDING)}",
                f"- 허용 포지션 크기: {session_data.get('position_size_rule', ANALYSIS_PENDING)}",
                f"- 공통 반대 신호: {session_data.get('opposite_signal', ANALYSIS_PENDING)}",
                "",
                "## 최근 공시",
                "",
                f"- 최근 공시: {session_data.get('recent_disclosures', DATA_MISSING)}",
                f"- 공시 요약: {session_data.get('disclosure_summary', DATA_MISSING)}",
            ]
        )
    if session == "closing":
        return "\n".join(
            [
                "## 오늘 매매 복기",
                "",
                summary_hint,
                "",
                f"- 진입/청산 내역: {session_data.get('trades', DATA_MISSING)}",
                f"- 잘한 판단: {session_data.get('good_call', ANALYSIS_PENDING)}",
                f"- 잘못한 판단: {session_data.get('bad_call', ANALYSIS_PENDING)}",
                f"- 규칙 위반 여부: {session_data.get('rule_break', ANALYSIS_PENDING)}",
                f"- 내일 보정할 습관: {session_data.get('habit_fix', ANALYSIS_PENDING)}",
                "",
                "## 시장 프레임",
                "",
                f"- 내일도 매매 가능한지: {session_data.get('market_tradeability', ANALYSIS_PENDING)}",
                f"- 시장 기본 방향: {session_data.get('market_bias', ANALYSIS_PENDING)}",
                f"- 시나리오 전환 조건: {session_data.get('scenario_switch', ANALYSIS_PENDING)}",
                f"- 시장 리스크 가드: {session_data.get('market_risk_guard', ANALYSIS_PENDING)}",
                "",
                "## 섹터 프레임",
                "",
                f"- 어디에 돈이 붙는지: {session_data.get('sector_money_flow', ANALYSIS_PENDING)}",
                f"- 내일 우선 볼 섹터: {session_data.get('sector_priority', ANALYSIS_PENDING)}",
                f"- 섹터 체크포인트: {session_data.get('sector_watchpoints', ANALYSIS_PENDING)}",
                f"- 섹터에서 하지 말아야 할 행동: {session_data.get('sector_avoid', ANALYSIS_PENDING)}",
                "",
                "## 개별주 실행 프레임",
                "",
                f"- 자동 선별 1: {stock_label(session_data.get('stock_1_name', DATA_MISSING), session_data.get('stock_1_sector', DATA_MISSING))}",
                f"- 선별 근거 1: {session_data.get('stock_1_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 1: {session_data.get('stock_1_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 1: {session_data.get('stock_1_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 1: {session_data.get('stock_1_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 1: {session_data.get('stock_1_invalid', ANALYSIS_PENDING)}",
                "",
                f"- 자동 선별 2: {stock_label(session_data.get('stock_2_name', DATA_MISSING), session_data.get('stock_2_sector', DATA_MISSING))}",
                f"- 선별 근거 2: {session_data.get('stock_2_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 2: {session_data.get('stock_2_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 2: {session_data.get('stock_2_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 2: {session_data.get('stock_2_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 2: {session_data.get('stock_2_invalid', ANALYSIS_PENDING)}",
                "",
                f"- 자동 선별 3: {stock_label(session_data.get('stock_3_name', DATA_MISSING), session_data.get('stock_3_sector', DATA_MISSING))}",
                f"- 선별 근거 3: {session_data.get('stock_3_reason', ANALYSIS_PENDING)}",
                f"- 진입 기준 3: {session_data.get('stock_3_entry', ANALYSIS_PENDING)}",
                f"- 추가매수 기준 3: {session_data.get('stock_3_add', ANALYSIS_PENDING)}",
                f"- 손절/탈출 기준 3: {session_data.get('stock_3_exit', ANALYSIS_PENDING)}",
                f"- 시나리오 무효화 3: {session_data.get('stock_3_invalid', ANALYSIS_PENDING)}",
                "",
                "## 공통 리스크 관리",
                "",
                f"- 신규 진입 금지 조건: {session_data.get('no_trade_condition', ANALYSIS_PENDING)}",
                f"- 내일 허용 포지션 크기: {session_data.get('position_size_rule', ANALYSIS_PENDING)}",
                f"- 내일 반대 신호: {session_data.get('opposite_signal', ANALYSIS_PENDING)}",
                "",
                "## 최근 공시",
                "",
                f"- 최근 공시: {session_data.get('recent_disclosures', DATA_MISSING)}",
                f"- 공시 요약: {session_data.get('disclosure_summary', DATA_MISSING)}",
            ]
        )
    raise ValueError(f"Unsupported session: {session}")


def build_closing_decision_sections(report_data: dict | None = None) -> str:
    closing = (report_data or {}).get("closing", {})
    return "\n".join(
        [
            "## 오늘의 결론",
            "",
            f"- 시장 점수: {closing.get('market_score', DATA_MISSING)}",
            f"- 현대차 점수: {closing.get('hyundai_score', DATA_MISSING)}",
            f"- 내일 공격/중립/방어 판단: {closing.get('stance', ANALYSIS_PENDING)}",
            f"- 내일 가장 중요한 체크포인트 3개: {closing.get('top3', ANALYSIS_PENDING)}",
            "",
            "## 내일 주문 전략",
            "",
            f"- 상승 시: {closing.get('upside_order', ANALYSIS_PENDING)}",
            f"- 횡보 시: {closing.get('flat_order', ANALYSIS_PENDING)}",
            f"- 하락 시: {closing.get('downside_order', ANALYSIS_PENDING)}",
            f"- 절대 하지 말아야 할 행동: {closing.get('dont_do', ANALYSIS_PENDING)}",
        ]
    )
