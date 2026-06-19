from __future__ import annotations

import io
import json
import math
import os
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "research_config.toml"

DATA_MISSING = "데이터 미수집"
ANALYSIS_PENDING = "필수 데이터 부족으로 분석 보류"

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
ALPHA_BASE_URL = "https://www.alphavantage.co/query"
NEWS_API_BASE_URL = "https://newsapi.org/v2/everything"
DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"

NEWS_RELEVANCE_KEYWORDS = {
    "반도체": ["semiconductor", "memory", "chip", "hbm", "sk hynix", "samsung"],
    "AI": ["ai", "artificial intelligence", "openai", "nvidia", "model", "llm"],
    "로봇": ["robot", "robotics", "humanoid", "automation"],
    "자동차/현대차": ["hyundai", "kia", "automotive", "ev", "vehicle"],
    "바이오/헬스케어": ["biotech", "healthcare", "clinical", "fda", "drug", "pharma", "trial"],
    "ETF: SCHD, QQQM, SPYG": ["schd", "qqqm", "spyg", "etf", "dividend", "nasdaq"],
}

TITLE_TRANSLATION_RULES = {
    "반도체": [
        ("samsung", "삼성전자"),
        ("sk hynix", "SK하이닉스"),
        ("transistor", "트랜지스터"),
        ("chip", "반도체 칩"),
        ("semiconductor", "반도체"),
        ("memory", "메모리"),
        ("hbm", "HBM"),
        ("foundry", "파운드리"),
        ("scaling", "미세화"),
    ],
    "AI": [
        ("artificial intelligence", "인공지능"),
        ("deep learning", "딥러닝"),
        ("llm", "대규모언어모델"),
        ("model", "모델"),
        ("monitoring", "모니터링"),
        ("research", "연구"),
        ("nvidia", "엔비디아"),
        ("openai", "오픈AI"),
    ],
    "로봇": [
        ("robot", "로봇"),
        ("robotics", "로봇"),
        ("delivery", "배송"),
        ("automation", "자동화"),
        ("humanoid", "휴머노이드"),
        ("backlash", "반발"),
    ],
    "자동차/현대차": [
        ("hyundai", "현대차"),
        ("kia", "기아"),
        ("automotive", "자동차"),
        ("vehicle", "차량"),
        ("supply crunch", "공급 부족"),
        ("raise prices", "가격 인상"),
        ("ev", "전기차"),
    ],
    "바이오/헬스케어": [
        ("biotech", "바이오"),
        ("healthcare", "헬스케어"),
        ("clinical", "임상"),
        ("trial", "시험"),
        ("fda", "FDA"),
        ("drug", "신약"),
        ("pharma", "제약"),
        ("discovery", "발굴"),
    ],
    "ETF: SCHD, QQQM, SPYG": [
        ("dividend", "배당"),
        ("retirement", "은퇴"),
        ("portfolio", "포트폴리오"),
        ("core", "핵심"),
        ("slot", "비중"),
        ("etf", "ETF"),
        ("schd", "SCHD"),
        ("qqqm", "QQQM"),
        ("spyg", "SPYG"),
    ],
}

AUTO_STOCK_CANDIDATES = {
    "반도체": ["삼성전자", "SK하이닉스", "한미반도체"],
    "AI": ["네이버", "카카오", "폴라리스오피스"],
    "로봇": ["레인보우로보틱스", "두산로보틱스", "로보스타"],
    "자동차/현대차": ["기아", "현대모비스", "현대오토에버"],
    "바이오/헬스케어": ["삼성바이오로직스", "셀트리온", "유한양행"],
}


@dataclass(frozen=True)
class NewsItem:
    sector: str
    title: str
    source: str
    published_at: str
    url: str


@dataclass(frozen=True)
class DisclosureItem:
    company: str
    report_name: str
    filed_at: str
    receipt_no: str
    url: str


def _load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("rb") as file:
        return tomllib.load(file)


CONFIG = _load_config()
load_dotenv(ROOT / CONFIG["api"]["dotenv_path"])


def _safe_float(value: str | None) -> float | None:
    if value is None or value == "" or value == ".":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _fmt_number(value: float | None, digits: int = 2) -> str:
    if value is None or math.isnan(value):
        return DATA_MISSING
    return f"{value:,.{digits}f}"


def _fmt_int(value: int | None) -> str:
    if value is None:
        return DATA_MISSING
    return f"{value:,}"


def _fmt_pct(value: float | None, digits: int = 2) -> str:
    if value is None or math.isnan(value):
        return DATA_MISSING
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{digits}f}%"


def _latest_valid_observations(observations: list[dict[str, str]], count: int = 2) -> list[dict[str, str]]:
    valid = [obs for obs in observations if obs.get("value") not in (None, "", ".")]
    return valid[-count:]


def _rolling_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return mean(values[:window])


def _compact_iso(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value


def _contains_korean(text: str) -> bool:
    return any("가" <= char <= "힣" for char in text)


class ApiClient:
    def __init__(self) -> None:
        self.fred_key = os.getenv("FRED_API_KEY")
        self.news_key = os.getenv("NEWS_API_KEY")
        self.alpha_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        self.dart_key = os.getenv("DART_API_KEY")
        self.kis_app_key = os.getenv(CONFIG["api"]["kis"]["enabled_env"])
        self.kis_app_secret = os.getenv(CONFIG["api"]["kis"]["app_secret_env"])
        self.kis_access_token: str | None = None
        self._corp_code_map: dict[str, str] | None = None

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any] | None:
        request = Request(url, headers=headers or {"User-Agent": "devkim-research/1.0"})
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return None

    def get_bytes(self, url: str, headers: dict[str, str] | None = None) -> bytes | None:
        request = Request(url, headers=headers or {"User-Agent": "devkim-research/1.0"})
        try:
            with urlopen(request, timeout=20) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError):
            return None

    def fred_observations(self, series_id: str, target_date: date) -> list[dict[str, str]]:
        if not self.fred_key:
            return []
        params = {
            "series_id": series_id,
            "api_key": self.fred_key,
            "file_type": "json",
            "sort_order": "desc",
            "observation_end": target_date.isoformat(),
            "limit": "24",
        }
        payload = self.get_json(f"{FRED_BASE_URL}?{urlencode(params)}")
        if not payload:
            return []
        observations = payload.get("observations", [])
        observations.reverse()
        return observations

    def alpha_query(self, function: str, **params: str) -> dict[str, Any] | None:
        if not self.alpha_key:
            return None
        query = {"function": function, "apikey": self.alpha_key}
        query.update(params)
        return self.get_json(f"{ALPHA_BASE_URL}?{urlencode(query)}")

    def news_everything(self, query: str, page_size: int = 3) -> list[NewsItem]:
        if not self.news_key:
            return []
        params = {
            "q": query,
            "sortBy": "publishedAt",
            "pageSize": str(page_size),
            "apiKey": self.news_key,
        }
        payload = self.get_json(f"{NEWS_API_BASE_URL}?{urlencode(params)}")
        if not payload or payload.get("status") != "ok":
            return []
        items: list[NewsItem] = []
        for article in payload.get("articles", []):
            items.append(
                NewsItem(
                    sector="",
                    title=article.get("title") or DATA_MISSING,
                    source=(article.get("source") or {}).get("name") or DATA_MISSING,
                    published_at=article.get("publishedAt") or DATA_MISSING,
                    url=article.get("url") or DATA_MISSING,
                )
            )
        return items

    def alpha_symbol_search(self, keywords: str) -> str | None:
        payload = self.alpha_query("SYMBOL_SEARCH", keywords=keywords)
        if not payload:
            return None
        matches = payload.get("bestMatches", [])
        if not matches:
            return None
        return matches[0].get("1. symbol")

    def dart_disclosures(self, corp_name: str, target_date: date, lookback_days: int = 30) -> list[DisclosureItem]:
        corp_code = self.dart_corp_code(corp_name)
        if not self.dart_key or not corp_code:
            return []
        begin_date = (target_date - timedelta(days=lookback_days)).strftime("%Y%m%d")
        end_date = target_date.strftime("%Y%m%d")
        params = {
            "crtfc_key": self.dart_key,
            "corp_code": corp_code,
            "bgn_de": begin_date,
            "end_de": end_date,
            "last_reprt_at": "Y",
            "page_count": "5",
        }
        payload = self.get_json(f"{DART_LIST_URL}?{urlencode(params)}")
        if not payload or payload.get("status") != "000":
            return []
        items: list[DisclosureItem] = []
        for row in payload.get("list", []):
            receipt_no = row.get("rcept_no", "")
            items.append(
                DisclosureItem(
                    company=corp_name,
                    report_name=row.get("report_nm") or DATA_MISSING,
                    filed_at=_compact_iso(row.get("rcept_dt", DATA_MISSING)),
                    receipt_no=receipt_no,
                    url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_no}" if receipt_no else DATA_MISSING,
                )
            )
        return items

    def dart_corp_code(self, corp_name: str) -> str | None:
        if self._corp_code_map is None:
            self._corp_code_map = self._load_dart_corp_codes()
        return self._corp_code_map.get(corp_name)

    def kis_enabled(self) -> bool:
        return bool(self.kis_app_key and self.kis_app_secret)

    def kis_get_access_token(self) -> str | None:
        if self.kis_access_token:
            return self.kis_access_token
        if not self.kis_enabled():
            return None
        token_url = CONFIG["api"]["kis"]["base_url"] + CONFIG["api"]["kis"]["token_url"]
        payload = json.dumps(
            {
                "grant_type": "client_credentials",
                "appkey": self.kis_app_key,
                "appsecret": self.kis_app_secret,
            }
        ).encode("utf-8")
        request = Request(
            token_url,
            data=payload,
            headers={
                "content-type": "application/json; charset=utf-8",
                "User-Agent": "devkim-research/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return None
        token = data.get("access_token")
        if token:
            self.kis_access_token = token
        return token

    def kis_get(self, path: str, tr_id: str | None = None, params: dict[str, str] | None = None) -> dict[str, Any] | None:
        if not self.kis_enabled() or not path:
            return None
        token = self.kis_get_access_token()
        if not token:
            return None
        url = CONFIG["api"]["kis"]["base_url"] + path
        if params:
            url = f"{url}?{urlencode(params)}"
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": self.kis_app_key or "",
            "appsecret": self.kis_app_secret or "",
            "User-Agent": "devkim-research/1.0",
        }
        if tr_id:
            headers["tr_id"] = tr_id
        return self.get_json(url, headers=headers)

    def _load_dart_corp_codes(self) -> dict[str, str]:
        if not self.dart_key:
            return {}
        payload = self.get_bytes(f"{DART_CORP_CODE_URL}?crtfc_key={self.dart_key}")
        if not payload:
            return {}
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                xml_name = archive.namelist()[0]
                xml_bytes = archive.read(xml_name)
        except (zipfile.BadZipFile, IndexError, KeyError):
            return {}
        root = ET.fromstring(xml_bytes)
        corp_codes: dict[str, str] = {}
        for item in root.findall(".//list"):
            name = (item.findtext("corp_name") or "").strip()
            code = (item.findtext("corp_code") or "").strip()
            if name and code:
                corp_codes[name] = code
        return corp_codes


class ReportDataBuilder:
    def __init__(self) -> None:
        self.client = ApiClient()
        self.api_config = CONFIG["api"]
        self.fred_series = CONFIG["market_data"]["fred"]
        self.news_queries = CONFIG["market_data"]["news_queries"]
        self.tracked_companies = CONFIG["tracked_companies"]

    def build(self, session: str, target_date: date) -> dict[str, Any]:
        common = self._build_common_data(target_date)
        sectors = self._build_sector_data()
        disclosures = self._build_disclosures(target_date)
        hyundai = self._build_hyundai_data()
        session_data = self._build_session_data(session, common, hyundai, sectors, disclosures)
        return {
            "session": session_data,
            "common": common,
            "hyundai": hyundai,
            "sectors": sectors,
            "disclosures": disclosures,
            "coverage": self._build_coverage(common, hyundai, sectors, disclosures),
            "closing": self._build_closing_data(common, hyundai, sectors),
        }

    def _build_common_data(self, target_date: date) -> dict[str, dict[str, str]]:
        fred = self._build_fred_snapshot(target_date)
        kis_market = self._build_kis_market_data()
        return {
            "market_summary": {
                "indices": self._market_summary_text(fred),
                "structure": self._macro_structure_text(fred),
                "drivers": self._market_driver_text(fred),
                "sentiment": self._market_sentiment_text(fred),
            },
            "fred": fred,
            "rates": {
                "us10y": fred["us10y"]["text"],
                "analysis": self._rate_analysis(fred["us10y"]),
            },
            "korea_market": {
                "kospi": kis_market["kospi"],
                "kosdaq": kis_market["kosdaq"],
                "leaders": kis_market["leaders"],
                "breadth": kis_market["breadth"],
            },
            "flow": {
                "foreign": kis_market["foreign"],
                "institutional": kis_market["institutional"],
                "retail": kis_market["retail"],
                "analysis": kis_market["analysis"],
            },
            "missing_reasons": {
                "korea_index": kis_market["korea_index_reason"],
                "investor_flow": kis_market["investor_flow_reason"],
            },
        }

    def _build_fred_snapshot(self, target_date: date) -> dict[str, dict[str, str | float | None]]:
        output: dict[str, dict[str, str | float | None]] = {}
        for key, series_id in self.fred_series.items():
            observations = self.client.fred_observations(series_id, target_date)
            latest = _latest_valid_observations(observations, 2)
            latest_val = _safe_float(latest[-1]["value"]) if latest else None
            prev_val = _safe_float(latest[-2]["value"]) if len(latest) > 1 else None
            delta = (latest_val - prev_val) if latest_val is not None and prev_val is not None else None
            output[key] = {
                "value": latest_val,
                "prev_value": prev_val,
                "delta": delta,
                "date": latest[-1]["date"] if latest else DATA_MISSING,
                "text": f"{_fmt_number(latest_val)} ({_compact_iso(latest[-1]['date'])})" if latest_val is not None and latest else DATA_MISSING,
            }
        return output

    def _build_kis_market_data(self) -> dict[str, str]:
        kis = CONFIG["api"]["kis"]
        if not self.client.kis_enabled():
            return {
                "kospi": DATA_MISSING,
                "kosdaq": DATA_MISSING,
                "leaders": "KIS APP KEY/SECRET 미설정으로 분석 보류",
                "breadth": "KIS APP KEY/SECRET 미설정으로 분석 보류",
                "foreign": DATA_MISSING,
                "institutional": DATA_MISSING,
                "retail": DATA_MISSING,
                "analysis": "KIS APP KEY/SECRET 미설정으로 분석 보류",
                "korea_index_reason": "KIS_APP_KEY 또는 KIS_APP_SECRET 미설정",
                "investor_flow_reason": "KIS_APP_KEY 또는 KIS_APP_SECRET 미설정",
            }
        index_path = kis["index_price_path"]
        investor_path = kis["investor_flow_path"]
        index_payload = self.client.kis_get(index_path) if index_path else None
        flow_payload = self.client.kis_get(investor_path) if investor_path else None
        return {
            "kospi": DATA_MISSING,
            "kosdaq": DATA_MISSING,
            "leaders": "KIS 엔드포인트 설정 후 업종 강도 데이터 연결 필요",
            "breadth": "KIS 엔드포인트 설정 후 상승/하락 종목수 연결 필요",
            "foreign": DATA_MISSING,
            "institutional": DATA_MISSING,
            "retail": DATA_MISSING,
            "analysis": "KIS 토큰은 준비되지만 실제 조회 엔드포인트 설정 전까지 분석 보류",
            "korea_index_reason": "index_price_path 미설정 또는 응답 파싱 로직 미구현" if not index_payload else "응답 파싱 로직 미구현",
            "investor_flow_reason": "investor_flow_path 미설정 또는 응답 파싱 로직 미구현" if not flow_payload else "응답 파싱 로직 미구현",
        }

    def _build_kis_hyundai_data(self) -> dict[str, str]:
        kis = CONFIG["api"]["kis"]
        if not self.client.kis_enabled():
            return {
                "current_close": DATA_MISSING,
                "previous_close": DATA_MISSING,
                "volume": DATA_MISSING,
                "intraday_high_low": DATA_MISSING,
                "foreign_flow": DATA_MISSING,
                "institutional_flow": DATA_MISSING,
                "retail_flow": DATA_MISSING,
                "short_selling": DATA_MISSING,
                "forced_liquidation": DATA_MISSING,
            }
        current_path = kis["current_price_path"]
        daily_path = kis["daily_price_path"]
        current_payload = self.client.kis_get(current_path) if current_path else None
        daily_payload = self.client.kis_get(daily_path) if daily_path else None
        if current_payload or daily_payload:
            return {
                "current_close": DATA_MISSING,
                "previous_close": DATA_MISSING,
                "volume": DATA_MISSING,
                "intraday_high_low": DATA_MISSING,
                "foreign_flow": DATA_MISSING,
                "institutional_flow": DATA_MISSING,
                "retail_flow": DATA_MISSING,
                "short_selling": DATA_MISSING,
                "forced_liquidation": DATA_MISSING,
            }
        return {
            "current_close": DATA_MISSING,
            "previous_close": DATA_MISSING,
            "volume": DATA_MISSING,
            "intraday_high_low": DATA_MISSING,
            "foreign_flow": DATA_MISSING,
            "institutional_flow": DATA_MISSING,
            "retail_flow": DATA_MISSING,
            "short_selling": DATA_MISSING,
            "forced_liquidation": DATA_MISSING,
        }

    def _build_hyundai_data(self) -> dict[str, str]:
        company = next(item for item in self.tracked_companies if item["name"] == "현대차")
        kis_hyundai = self._build_kis_hyundai_data()
        symbol = os.getenv("HYUNDAI_ALPHA_SYMBOL") or company.get("alpha_symbol") or self._resolve_alpha_symbol(company)
        quote = self.client.alpha_query("GLOBAL_QUOTE", symbol=symbol) or {}
        daily = self.client.alpha_query("TIME_SERIES_DAILY", symbol=symbol, outputsize="full") or {}
        global_quote = quote.get("Global Quote", {})
        series = daily.get("Time Series (Daily)", {})
        rows = sorted(series.items(), reverse=True)
        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []
        prev_close: float | None = None
        latest_close: float | None = None
        latest_high: float | None = None
        latest_low: float | None = None
        latest_volume: int | None = None
        for index, (_, values) in enumerate(rows):
            high = _safe_float(values.get("2. high"))
            low = _safe_float(values.get("3. low"))
            close = _safe_float(values.get("4. close"))
            volume = _safe_float(values.get("5. volume"))
            if high is not None:
                highs.append(high)
            if low is not None:
                lows.append(low)
            if close is not None:
                closes.append(close)
                if index == 0:
                    latest_close = close
                    latest_high = high
                    latest_low = low
                    latest_volume = int(volume) if volume is not None else None
                if index == 1:
                    prev_close = close
        current_price = _safe_float(global_quote.get("05. price")) or latest_close
        current_volume = int(float(global_quote["06. volume"])) if global_quote.get("06. volume") else latest_volume
        intraday_high = _safe_float(global_quote.get("03. high")) or latest_high
        intraday_low = _safe_float(global_quote.get("04. low")) or latest_low
        ma20 = _rolling_average(closes, 20)
        ma60 = _rolling_average(closes, 60)
        return {
            "symbol": symbol or DATA_MISSING,
            "current_close": kis_hyundai["current_close"] if kis_hyundai["current_close"] != DATA_MISSING else _fmt_number(current_price),
            "previous_close": kis_hyundai["previous_close"] if kis_hyundai["previous_close"] != DATA_MISSING else _fmt_number(prev_close),
            "volume": kis_hyundai["volume"] if kis_hyundai["volume"] != DATA_MISSING else _fmt_int(current_volume),
            "week52_high": _fmt_number(max(highs[:252]) if highs else None),
            "week52_low": _fmt_number(min(lows[:252]) if lows else None),
            "intraday_high_low": kis_hyundai["intraday_high_low"] if kis_hyundai["intraday_high_low"] != DATA_MISSING else self._combine_values(intraday_high, intraday_low),
            "foreign_flow": kis_hyundai["foreign_flow"],
            "institutional_flow": kis_hyundai["institutional_flow"],
            "retail_flow": kis_hyundai["retail_flow"],
            "short_selling": kis_hyundai["short_selling"],
            "forced_liquidation": kis_hyundai["forced_liquidation"],
            "ma5": _fmt_number(_rolling_average(closes, 5)),
            "ma20": _fmt_number(ma20),
            "ma60": _fmt_number(ma60),
            "support": _fmt_number(min(lows[:20]) if len(lows) >= 20 else None),
            "resistance": _fmt_number(max(highs[:20]) if len(highs) >= 20 else None),
            "today_analysis": self._hyundai_analysis(current_price, ma20, ma60),
            "tomorrow_scenario": self._hyundai_scenario(current_price, ma20),
            "add_rule": self._hyundai_add_rule(current_price, ma20),
            "exit_rule": self._hyundai_exit_rule(current_price, ma20),
        }

    def _resolve_alpha_symbol(self, company: dict[str, Any]) -> str | None:
        for keyword in company.get("alpha_search_keywords", []):
            symbol = self.client.alpha_symbol_search(keyword)
            if symbol:
                return symbol
        return None

    def _build_sector_data(self) -> dict[str, dict[str, str]]:
        sector_data: dict[str, dict[str, str]] = {}
        for sector, query in self.news_queries.items():
            articles = self.client.news_everything(query, page_size=10)
            top = self._select_relevant_article(sector, articles)
            localized_title = self._localize_headline(sector, top.title if top else DATA_MISSING)
            data = {
                "headline": localized_title,
                "headline_original": top.title if top else DATA_MISSING,
                "source": top.source if top else DATA_MISSING,
                "published_at": top.published_at if top else DATA_MISSING,
                "url": top.url if top else DATA_MISSING,
                "price_impact": self._headline_based_view(localized_title),
                "short_term": self._headline_based_view(localized_title),
                "medium_term": self._headline_based_view(localized_title),
                "investment_judgment": self._investment_judgment_from_headline(localized_title),
                "risk": self._risk_from_headline(localized_title),
            }
            if sector == "바이오/헬스케어":
                data.update(self._build_bio_sector_data())
            sector_data[sector] = data
        return sector_data

    def _localize_headline(self, sector: str, headline: str) -> str:
        if headline == DATA_MISSING:
            return DATA_MISSING
        if _contains_korean(headline):
            return headline
        lowered = headline.lower()
        replacements = TITLE_TRANSLATION_RULES.get(sector, [])
        translated = headline
        for english, korean in replacements:
            translated = translated.replace(english, korean)
            translated = translated.replace(english.title(), korean)
            translated = translated.replace(english.upper(), korean)
        if translated != headline and not any("a" <= ch.lower() <= "z" for ch in translated if ch.isalpha()):
            return translated
        if sector == "반도체":
            return "반도체 공정·메모리·소자 관련 해외 뉴스"
        if sector == "AI":
            return "AI 모델·딥러닝 활용·연구 관련 해외 뉴스"
        if sector == "로봇":
            return "로봇·자동화·배송로봇 관련 해외 뉴스"
        if sector == "자동차/현대차":
            return "자동차·전기차·공급망 관련 해외 뉴스"
        if sector == "바이오/헬스케어":
            return "바이오·헬스케어·임상·신약 관련 해외 뉴스"
        if sector == "ETF: SCHD, QQQM, SPYG":
            return "SCHD·QQQM·SPYG 등 ETF 비교 또는 운용 관련 해외 뉴스"
        return headline

    def _select_relevant_article(self, sector: str, articles: list[NewsItem]) -> NewsItem | None:
        if not articles:
            return None
        keywords = NEWS_RELEVANCE_KEYWORDS.get(sector, [])
        ranked = sorted(
            articles,
            key=lambda article: self._relevance_score(article, keywords),
            reverse=True,
        )
        top = ranked[0]
        if self._relevance_score(top, keywords) == 0:
            return None
        return top

    def _relevance_score(self, article: NewsItem, keywords: list[str]) -> int:
        haystack = f"{article.title} {article.source} {article.url}".lower()
        return sum(1 for keyword in keywords if keyword in haystack)

    def _build_bio_sector_data(self) -> dict[str, str]:
        clinical = self.client.news_everything("clinical trial biotech", page_size=1)
        fda = self.client.news_everything("FDA biotech drug approval", page_size=1)
        licensing = self.client.news_everything("biotech licensing deal", page_size=1)
        dnd = self.client.news_everything("\"D&D Pharmatech\" OR \"디앤디파마텍\"", page_size=1)
        return {
            "leaders": "삼성바이오로직스, 셀트리온, 유한양행, 디앤디파마텍",
            "clinical_news": clinical[0].title if clinical else DATA_MISSING,
            "fda_news": fda[0].title if fda else DATA_MISSING,
            "licensing_news": licensing[0].title if licensing else DATA_MISSING,
            "rate_impact": "금리 데이터와 바이오 뉴스의 방향이 동시에 확인될 때만 비중 확대." if fda or clinical or licensing else ANALYSIS_PENDING,
            "dnd_comment": dnd[0].title if dnd else DATA_MISSING,
        }

    def _build_disclosures(self, target_date: date) -> dict[str, Any]:
        items_by_company: dict[str, list[DisclosureItem]] = {}
        flattened: list[DisclosureItem] = []
        lookback_days = int(self.api_config["dart_disclosure_lookback_days"])
        for company in self.tracked_companies:
            corp_name = company.get("dart_name") or company["name"]
            disclosures = self.client.dart_disclosures(corp_name, target_date, lookback_days=lookback_days)
            items_by_company[company["name"]] = disclosures
            flattened.extend(disclosures)
        flattened.sort(key=lambda item: item.filed_at, reverse=True)
        top3 = flattened[:3]
        recent = " | ".join(f"{item.company}: {item.report_name} ({item.filed_at})" for item in top3) if top3 else DATA_MISSING
        summary = " | ".join(f"{item.company} 공시 확인: {item.report_name}" for item in top3) if top3 else DATA_MISSING
        return {
            "items_by_company": items_by_company,
            "recent": recent,
            "summary": summary,
        }

    def _build_session_data(
        self,
        session: str,
        common: dict[str, Any],
        hyundai: dict[str, str],
        sectors: dict[str, dict[str, str]],
        disclosures: dict[str, Any],
    ) -> dict[str, str]:
        if session == "morning":
            evidence_score = self._evidence_score(common, hyundai, sectors, disclosures)
            no_trade = self._no_trade_condition(common, hyundai)
            top_news = self._top_news_summary(sectors)
            market_score = self._market_score(common)
            stance = self._stance_from_score(market_score)
            return {
                "market_score": str(market_score) if market_score is not None else DATA_MISSING,
                "stance": stance,
                "top_news_3": top_news,
                "global_major_issues": self._global_major_issues(common, disclosures),
                "industry_major_issues": self._industry_major_issues(sectors),
                "capital_flow_now": self._capital_flow_now(common, sectors),
                "us_sector_focus": self._us_sector_focus(sectors),
                "expected_sector_today": self._expected_sector_today(common, sectors),
                "market_tradeability": self._market_tradeability(stance, evidence_score),
                "market_bias": self._market_bias(common, stance),
                "market_risk_guard": self._market_risk_guard(common, hyundai),
                "sector_money_flow": self._capital_flow_now(common, sectors),
                "sector_priority": self._expected_sector_today(common, sectors),
                "sector_watchpoints": self._sector_watchpoints(sectors),
                "sector_avoid": self._sector_avoid_rule(stance, sectors),
                "hyundai_core": hyundai["tomorrow_scenario"],
                "etf_core": self._etf_core_scenario(sectors),
                "dont_do": self._dont_do_action(stance),
                "today_hypothesis": self._morning_hypothesis(common, hyundai),
                "must_check_news": top_news,
                "first_30m_checkpoints": "미국 10년물, 현대차 가격, 최근 공시 반영 여부를 함께 확인.",
                "entry_candidates": self._entry_candidates(hyundai, sectors),
                "watch_candidates": "현대차, 삼성전자, 디앤디파마텍",
                "risk_rules": self._dont_do_action(stance),
                "recent_disclosures": disclosures["recent"],
                "disclosure_summary": disclosures["summary"],
                "evidence_score": evidence_score,
                "evidence_comment": self._evidence_comment(evidence_score),
                "no_trade_condition": no_trade,
                "position_size_rule": self._position_size_rule(evidence_score, stance),
                "entry_trigger": self._entry_trigger(common, hyundai),
                "invalidation": self._invalidation_rule(common, hyundai),
                "opposite_signal": self._opposite_signal(common, hyundai, sectors),
                **self._individual_stock_frame(common, sectors, disclosures),
            }
        if session == "afternoon":
            evidence_score = self._evidence_score(common, hyundai, sectors, disclosures)
            stance = self._stance_from_score(self._market_score(common))
            return {
                "morning_flow": ANALYSIS_PENDING,
                "morning_range": DATA_MISSING,
                "turnover_leaders": DATA_MISSING,
                "hypothesis_result": ANALYSIS_PENDING,
                "afternoon_primary_scenario": self._stance_from_score(self._market_score(common)),
                "afternoon_buy_condition": hyundai["add_rule"],
                "afternoon_sell_condition": hyundai["exit_rule"],
                "close_watch": self._top_news_summary(sectors),
                "market_tradeability": self._market_tradeability(stance, evidence_score),
                "market_bias": self._market_bias(common, stance),
                "market_risk_guard": self._market_risk_guard(common, hyundai),
                "sector_money_flow": self._capital_flow_now(common, sectors),
                "sector_priority": self._expected_sector_today(common, sectors),
                "sector_watchpoints": self._sector_watchpoints(sectors),
                "sector_avoid": self._sector_avoid_rule(stance, sectors),
                "evidence_score": evidence_score,
                "evidence_comment": self._evidence_comment(evidence_score),
                "no_trade_condition": self._no_trade_condition(common, hyundai),
                "position_size_rule": self._position_size_rule(evidence_score, stance),
                "entry_trigger": self._entry_trigger(common, hyundai),
                "invalidation": self._invalidation_rule(common, hyundai),
                "opposite_signal": self._opposite_signal(common, hyundai, sectors),
                "recent_disclosures": disclosures["recent"],
                "disclosure_summary": disclosures["summary"],
                **self._individual_stock_frame(common, sectors, disclosures),
            }
        stance = self._stance_from_score(self._market_score(common))
        evidence_score = self._evidence_score(common, hyundai, sectors, disclosures)
        return {
            "trades": DATA_MISSING,
            "good_call": ANALYSIS_PENDING,
            "bad_call": ANALYSIS_PENDING,
            "rule_break": ANALYSIS_PENDING,
            "habit_fix": ANALYSIS_PENDING,
            "bull_scenario": hyundai["tomorrow_scenario"],
            "base_scenario": self._etf_core_scenario(sectors),
            "bear_scenario": self._dont_do_action(self._stance_from_score(self._market_score(common))),
            "scenario_switch": "현대차와 매크로 지표가 동시에 악화되면 방어로 전환.",
            "market_tradeability": self._market_tradeability(stance, evidence_score),
            "market_bias": self._market_bias(common, stance),
            "market_risk_guard": self._market_risk_guard(common, hyundai),
            "sector_money_flow": self._capital_flow_now(common, sectors),
            "sector_priority": self._expected_sector_today(common, sectors),
            "sector_watchpoints": self._sector_watchpoints(sectors),
            "sector_avoid": self._sector_avoid_rule(stance, sectors),
            "evidence_score": evidence_score,
            "evidence_comment": self._evidence_comment(evidence_score),
            "no_trade_condition": self._no_trade_condition(common, hyundai),
            "position_size_rule": self._position_size_rule(evidence_score, stance),
            "entry_trigger": self._entry_trigger(common, hyundai),
            "invalidation": self._invalidation_rule(common, hyundai),
            "opposite_signal": self._opposite_signal(common, hyundai, sectors),
            "recent_disclosures": disclosures["recent"],
            "disclosure_summary": disclosures["summary"],
            **self._individual_stock_frame(common, sectors, disclosures),
        }

    def _build_closing_data(self, common: dict[str, Any], hyundai: dict[str, str], sectors: dict[str, dict[str, str]]) -> dict[str, str]:
        score = self._market_score(common)
        stance = self._stance_from_score(score)
        return {
            "market_score": str(score) if score is not None else DATA_MISSING,
            "hyundai_score": str(self._hyundai_score(hyundai)) if self._hyundai_score(hyundai) is not None else DATA_MISSING,
            "stance": stance,
            "top3": self._top_news_summary(sectors),
            "upside_order": hyundai["add_rule"],
            "flat_order": self._etf_core_scenario(sectors),
            "downside_order": hyundai["exit_rule"],
            "dont_do": self._dont_do_action(stance),
        }

    def _build_coverage(
        self,
        common: dict[str, Any],
        hyundai: dict[str, str],
        sectors: dict[str, dict[str, str]],
        disclosures: dict[str, Any],
    ) -> dict[str, str]:
        fred_ok = "연결됨" if common["fred"]["us10y"]["text"] != DATA_MISSING else "미연결"
        news_ok = "연결됨" if any(data.get("headline") != DATA_MISSING for data in sectors.values()) else "미연결"
        dart_ok = "연결됨" if disclosures.get("recent") != DATA_MISSING else "미연결"
        alpha_ok = "부분 연결" if hyundai.get("current_close") != DATA_MISSING else "미연결"
        kis_key_name = self.api_config["kis"]["enabled_env"]
        kis_secret_name = self.api_config["kis"]["app_secret_env"]
        kis_ok = "준비됨" if os.getenv(kis_key_name) and os.getenv(kis_secret_name) else "미연결"
        return {
            "fred_status": fred_ok,
            "news_status": news_ok,
            "alpha_status": alpha_ok,
            "dart_status": dart_ok,
            "kis_status": kis_ok,
            "kis_reason": f"{kis_key_name} 또는 {kis_secret_name} 환경변수 미설정으로 한국장 지수/수급 미수집" if kis_ok == "미연결" else "KIS 키는 준비됨. 엔드포인트 경로와 응답 파싱 로직 연결 필요",
            "hyundai_reason": "Alpha Vantage 심볼 데이터가 OTC 기준이라 이동평균/52주 범위가 불완전할 수 있음" if alpha_ok != "미연결" else "현대차 가격 데이터 미수집",
            "flow_reason": "외국인/기관/개인 수급은 국내 브로커 또는 거래소 API가 필요함",
            "news_reason": "뉴스는 수집되지만 국내 관련 종목 가격 반응 데이터가 없어 정량 영향 평가는 제한적임",
        }

    def _market_score(self, common: dict[str, Any]) -> int | None:
        fred = common["fred"]
        us10y_delta = fred["us10y"]["delta"]
        cpi_delta = fred["cpi"]["delta"]
        ppi_delta = fred["ppi"]["delta"]
        unemployment_delta = fred["unemployment"]["delta"]
        fed_delta = fred["fed_funds"]["delta"]
        if all(value is None for value in (us10y_delta, cpi_delta, ppi_delta, unemployment_delta, fed_delta)):
            return None
        score = 3.0
        if us10y_delta is not None:
            score += -0.5 if us10y_delta > 0 else 0.5
        if cpi_delta is not None:
            score += -0.5 if cpi_delta > 0 else 0.5
        if ppi_delta is not None:
            score += -0.5 if ppi_delta > 0 else 0.5
        if unemployment_delta is not None:
            score += 0.5 if unemployment_delta <= 0.1 else -0.5
        if fed_delta is not None:
            score += -0.5 if fed_delta > 0 else 0.0
        return max(1, min(5, round(score)))

    def _stance_from_score(self, score: int | None) -> str:
        if score is None:
            return DATA_MISSING
        if score >= 4:
            return "공격"
        if score <= 2:
            return "방어"
        return "중립"

    def _hyundai_score(self, hyundai: dict[str, str]) -> int | None:
        current = _safe_float(hyundai["current_close"].replace(",", "")) if hyundai["current_close"] != DATA_MISSING else None
        ma20 = _safe_float(hyundai["ma20"].replace(",", "")) if hyundai["ma20"] != DATA_MISSING else None
        if current is None or ma20 is None:
            return None
        return 4 if current >= ma20 else 2

    def _market_summary_text(self, fred: dict[str, Any]) -> str:
        pieces = [
            f"미국 10년물 {fred['us10y']['text']}",
            f"CPI {fred['cpi']['text']}",
            f"PPI {fred['ppi']['text']}",
            f"실업률 {fred['unemployment']['text']}",
            f"연방기금금리 {fred['fed_funds']['text']}",
        ]
        return ", ".join(pieces)

    def _macro_structure_text(self, fred: dict[str, Any]) -> str:
        if fred["us10y"]["value"] is None or fred["fed_funds"]["value"] is None:
            return ANALYSIS_PENDING
        if fred["us10y"]["delta"] is not None and fred["us10y"]["delta"] > 0:
            return "금리 상방 압력이 살아 있어 성장주 멀티플 확장보다 선별 대응이 유리하다."
        return "금리 부담이 완화되는 구간이면 대형 성장주와 수출주를 함께 점검할 수 있다."

    def _market_driver_text(self, fred: dict[str, Any]) -> str:
        return " | ".join(
            [
                f"10년물: {fred['us10y']['text']}",
                f"CPI: {fred['cpi']['text']}",
                f"PPI: {fred['ppi']['text']}",
                f"실업률: {fred['unemployment']['text']}",
                f"연방기금금리: {fred['fed_funds']['text']}",
            ]
        )

    def _market_sentiment_text(self, fred: dict[str, Any]) -> str:
        score = self._market_score({"fred": fred})
        stance = self._stance_from_score(score)
        if stance == DATA_MISSING:
            return ANALYSIS_PENDING
        return f"매크로 점수 기준 오늘 기본 태도는 {stance}."

    def _rate_analysis(self, us10y: dict[str, Any]) -> str:
        delta = us10y["delta"]
        if delta is None:
            return ANALYSIS_PENDING
        return "전일 대비 상승이면 성장주 할인율 부담, 하락이면 반등 여지 점검."

    def _headline_based_view(self, headline: str) -> str:
        if headline == DATA_MISSING:
            return "관련 뉴스 미수집으로 영향 분석 보류"
        return "뉴스는 수집됐지만 국내 관련 종목의 가격 반응 데이터가 없어 정량 영향 평가는 보류"

    def _investment_judgment_from_headline(self, headline: str) -> str:
        if headline == DATA_MISSING:
            return "관련 뉴스 미수집으로 투자 판단 보류"
        return "기사 원문과 국내 관련 종목 가격 반응이 함께 확인될 때만 비중 확대."

    def _risk_from_headline(self, headline: str) -> str:
        if headline == DATA_MISSING:
            return "관련 뉴스 미수집으로 리스크 판단 보류"
        return "제목만 보고 추격하지 말고 거래량과 가격 반응을 함께 확인."

    def _top_news_summary(self, sectors: dict[str, dict[str, str]]) -> str:
        items = []
        for sector, data in sectors.items():
            published = data.get("published_at", DATA_MISSING)
            if data.get("headline") == DATA_MISSING:
                continue
            items.append((published, f"{sector}: {data['headline']} | {data.get('source', DATA_MISSING)} | {published}"))
        if not items:
            return DATA_MISSING
        items.sort(key=lambda item: item[0], reverse=True)
        return " || ".join(item[1] for item in items[:3])

    def _global_major_issues(self, common: dict[str, Any], disclosures: dict[str, Any]) -> str:
        issues = []
        fred = common.get("fred", {})
        us10y = fred.get("us10y", {})
        if us10y.get("text") != DATA_MISSING:
            delta = us10y.get("delta")
            direction = "상승" if delta is not None and delta > 0 else "하락/안정"
            issues.append(f"미국 10년물 {direction}: {us10y.get('text', DATA_MISSING)}")
        cpi = fred.get("cpi", {})
        if cpi.get("text") != DATA_MISSING:
            issues.append(f"미국 CPI: {cpi.get('text', DATA_MISSING)}")
        fed = fred.get("fed_funds", {})
        if fed.get("text") != DATA_MISSING:
            issues.append(f"연방기금금리: {fed.get('text', DATA_MISSING)}")
        if disclosures.get("recent") != DATA_MISSING:
            issues.append(f"최근 공시: {disclosures['recent']}")
        if issues:
            return " | ".join(issues[:3])
        return "세계 주요 이슈는 데이터 미수집 (FRED/DART 또는 해외 매크로 뉴스 데이터 부족)"

    def _industry_major_issues(self, sectors: dict[str, dict[str, str]]) -> str:
        issues = []
        priority = ("반도체", "AI", "자동차/현대차", "바이오/헬스케어", "로봇", "ETF: SCHD, QQQM, SPYG")
        for sector in priority:
            headline = sectors.get(sector, {}).get("headline", DATA_MISSING)
            if headline != DATA_MISSING:
                issues.append(f"{sector}: {headline}")
        if issues:
            return " | ".join(issues[:3])
        return "산업 관련 이슈는 데이터 미수집 (섹터 뉴스 API 응답 부족 또는 관련 기사 필터링 실패)"

    def _capital_flow_now(self, common: dict[str, Any], sectors: dict[str, dict[str, str]]) -> str:
        if common.get("flow", {}).get("foreign") != DATA_MISSING or common.get("flow", {}).get("institutional") != DATA_MISSING:
            return "외국인/기관 수급 데이터 기준 요약 필요. TODO: KIS 투자주체 수급 API 파싱 연결 후 자동 판정."
        priority = [sector for sector in ("반도체", "AI", "자동차/현대차", "바이오/헬스케어", "로봇") if sectors.get(sector, {}).get("headline") != DATA_MISSING]
        if priority:
            return f"실시간 수급 데이터는 미수집이며, 현재는 뉴스 기준으로 {', '.join(priority[:3])} 쪽으로 관심이 모이는 구조."
        return "현재 돈이 몰리는 곳은 데이터 미수집 (KIS 투자주체 수급 API 미연동으로 자금 유입 방향 판정 불가)"

    def _us_sector_focus(self, sectors: dict[str, dict[str, str]]) -> str:
        focus = []
        if sectors.get("AI", {}).get("headline") != DATA_MISSING:
            focus.append("미국 AI/대형 기술주")
        if sectors.get("반도체", {}).get("headline") != DATA_MISSING:
            focus.append("미국 반도체")
        if sectors.get("ETF: SCHD, QQQM, SPYG", {}).get("headline") != DATA_MISSING:
            focus.append("미국 ETF 성장/배당")
        if focus:
            return ", ".join(focus[:3])
        return "미장 핵심 섹터는 데이터 미수집 (해외 섹터 강도 비교용 가격/ETF 자금 유입 데이터 미연동)"

    def _expected_sector_today(self, common: dict[str, Any], sectors: dict[str, dict[str, str]]) -> str:
        market_score = self._market_score(common)
        candidates = []
        if sectors.get("반도체", {}).get("headline") != DATA_MISSING:
            candidates.append("반도체")
        if sectors.get("AI", {}).get("headline") != DATA_MISSING and market_score is not None and market_score >= 3:
            candidates.append("AI")
        if sectors.get("자동차/현대차", {}).get("headline") != DATA_MISSING:
            candidates.append("자동차/현대차")
        if sectors.get("바이오/헬스케어", {}).get("headline") != DATA_MISSING and market_score is not None and market_score <= 3:
            candidates.append("바이오/헬스케어")
        if candidates:
            return ", ".join(candidates[:3])
        return "오늘 예상 섹터는 데이터 미수집 (섹터별 체결강도·거래대금 비교 데이터 미연동)"

    def _market_tradeability(self, stance: str, evidence_score: str) -> str:
        if stance == DATA_MISSING or evidence_score == DATA_MISSING:
            return "오늘 매매 가능 여부는 데이터 미수집 (매크로·가격 근거 부족)"
        score = int(evidence_score.split("/")[0])
        if stance == "공격" and score >= 4:
            return "매매 가능한 날이다. 다만 시초가 추격 대신 확인 후 분할 진입이 전제다."
        if stance == "중립" and score >= 2:
            return "선별적으로 매매 가능한 날이다. 섹터와 종목의 동시 확인이 필요하다."
        return "보수적으로 접근해야 하는 날이다. 신규 진입보다 관망 또는 축소가 우선이다."

    def _market_bias(self, common: dict[str, Any], stance: str) -> str:
        if stance == DATA_MISSING:
            return "시장 방향성 판단 보류 (매크로 데이터 부족)"
        us10y = common.get("fred", {}).get("us10y", {}).get("text", DATA_MISSING)
        return f"{stance} 우세. 핵심 확인 지표는 미국 10년물({us10y})과 한국장 수급이다."

    def _market_risk_guard(self, common: dict[str, Any], hyundai: dict[str, str]) -> str:
        return self._no_trade_condition(common, hyundai)

    def _sector_watchpoints(self, sectors: dict[str, dict[str, str]]) -> str:
        issues = []
        for sector in ("반도체", "AI", "자동차/현대차", "바이오/헬스케어"):
            headline = sectors.get(sector, {}).get("headline", DATA_MISSING)
            if headline != DATA_MISSING:
                issues.append(f"{sector}: {headline}")
        if issues:
            return " | ".join(issues[:3])
        return "섹터 체크포인트는 데이터 미수집 (핵심 뉴스 부족)"

    def _sector_avoid_rule(self, stance: str, sectors: dict[str, dict[str, str]]) -> str:
        if stance == "방어":
            return "방어 구간에서는 뉴스만 있고 수급 확인이 안 되는 섹터 추격 금지"
        if not any(data.get("headline") != DATA_MISSING for data in sectors.values()):
            return "섹터 뉴스 미수집 상태에서는 업종 베팅 보류"
        return "주도 섹터가 확인되기 전까지 2순위 테마 순환매 추격 금지"

    def _morning_hypothesis(self, common: dict[str, Any], hyundai: dict[str, str]) -> str:
        stance = self._stance_from_score(self._market_score(common))
        return f"매크로 태도는 {stance}, 현대차는 {hyundai['tomorrow_scenario']}"

    def _entry_candidates(self, hyundai: dict[str, str], sectors: dict[str, dict[str, str]]) -> str:
        if hyundai["current_close"] != DATA_MISSING:
            return f"현대차: {hyundai['add_rule']}"
        semiconductor = sectors.get("반도체", {})
        if semiconductor.get("headline") != DATA_MISSING:
            return f"반도체: {semiconductor.get('investment_judgment', ANALYSIS_PENDING)}"
        return ANALYSIS_PENDING

    def _etf_core_scenario(self, sectors: dict[str, dict[str, str]]) -> str:
        etf = sectors.get("ETF: SCHD, QQQM, SPYG", {})
        if etf.get("headline") == DATA_MISSING:
            return ANALYSIS_PENDING
        return f"SCHD/QQQM/SPYG 점검: {etf.get('headline', DATA_MISSING)}"

    def _dont_do_action(self, stance: str) -> str:
        if stance == "공격":
            return "시초가 과열 추격매수 금지."
        if stance == "방어":
            return "데이터 없이 낙폭과대만 보고 저가매수하지 말 것."
        if stance == "중립":
            return "뉴스 제목만 보고 비중을 급격히 늘리지 말 것."
        return DATA_MISSING

    def _evidence_score(self, common: dict[str, Any], hyundai: dict[str, str], sectors: dict[str, dict[str, str]], disclosures: dict[str, Any]) -> str:
        score = 0
        if common["fred"]["us10y"]["text"] != DATA_MISSING:
            score += 1
        if disclosures.get("recent") != DATA_MISSING:
            score += 1
        if any(data.get("headline") != DATA_MISSING for data in sectors.values()):
            score += 1
        if hyundai.get("current_close") != DATA_MISSING:
            score += 1
        if hyundai.get("ma20") != DATA_MISSING:
            score += 1
        return f"{score}/5"

    def _evidence_comment(self, evidence_score: str) -> str:
        if evidence_score == DATA_MISSING:
            return "근거 데이터 부족"
        score = int(evidence_score.split("/")[0])
        if score >= 4:
            return "근거 품질이 높아 시나리오 기반 대응 가능"
        if score >= 2:
            return "근거는 일부 확보됐지만 포지션을 줄여야 하는 구간"
        return "근거 품질이 낮아 공격적 매매 금지"

    def _no_trade_condition(self, common: dict[str, Any], hyundai: dict[str, str]) -> str:
        if common["fred"]["us10y"]["text"] == DATA_MISSING and hyundai.get("current_close") == DATA_MISSING:
            return "매크로와 종목 핵심 데이터가 모두 비어 있으면 신규 진입 금지"
        if hyundai.get("ma20") == DATA_MISSING:
            return "현대차 추세선 부재 시 기준 없는 추격매수 금지"
        return "핵심 시나리오와 반대 신호가 나오면 신규 진입 보류"

    def _position_size_rule(self, evidence_score: str, stance: str) -> str:
        if evidence_score == DATA_MISSING or stance == DATA_MISSING:
            return "근거 데이터 부족으로 0~25% 이내 소규모만 허용"
        score = int(evidence_score.split("/")[0])
        if stance == "방어":
            return "총 예정 비중의 25% 이내로만 분할 진입"
        if score >= 4 and stance == "공격":
            return "총 예정 비중의 50%까지 분할 진입 가능"
        return "총 예정 비중의 33% 이내로만 분할 진입"

    def _entry_trigger(self, common: dict[str, Any], hyundai: dict[str, str]) -> str:
        if hyundai.get("ma20") != DATA_MISSING:
            return "현대차가 20일선 위를 유지하고 거래량이 전일 대비 증가할 때만 진입 검토"
        if common["fred"]["us10y"]["text"] != DATA_MISSING:
            return "금리 충격 완화와 장초반 수급 안정이 동시에 확인될 때만 진입 검토"
        return "핵심 데이터가 비어 있으면 진입 트리거 산출 보류"

    def _invalidation_rule(self, common: dict[str, Any], hyundai: dict[str, str]) -> str:
        if hyundai.get("support") != DATA_MISSING:
            return "지지선 이탈 후 회복 실패 시 시나리오 폐기"
        return "매수 근거로 사용한 뉴스/수급/가격 조건 중 하나라도 깨지면 시나리오 폐기"

    def _opposite_signal(self, common: dict[str, Any], hyundai: dict[str, str], sectors: dict[str, dict[str, str]]) -> str:
        if common["fred"]["us10y"]["value"] is not None and common["fred"]["us10y"]["delta"] is not None and common["fred"]["us10y"]["delta"] > 0:
            return "금리 급등 지속은 반대 신호"
        if hyundai.get("current_close") == DATA_MISSING:
            return "현대차 가격 미수집은 판단 보류 신호"
        if not any(data.get("headline") != DATA_MISSING for data in sectors.values()):
            return "뉴스 부재는 추격 진입 금지 신호"
        return "가격과 뉴스 방향이 엇갈리면 반대 신호로 해석"

    def _individual_stock_frame(self, common: dict[str, Any], sectors: dict[str, dict[str, str]], disclosures: dict[str, Any]) -> dict[str, str]:
        candidates = self._auto_select_stock_candidates(common, sectors, disclosures)
        payload: dict[str, str] = {}
        for index in range(3):
            slot = candidates[index] if index < len(candidates) else None
            prefix = f"stock_{index + 1}"
            payload[f"{prefix}_name"] = slot["name"] if slot else DATA_MISSING
            payload[f"{prefix}_sector"] = slot["sector"] if slot else DATA_MISSING
            payload[f"{prefix}_reason"] = slot["reason"] if slot else "자동 선별 후보 없음"
            payload[f"{prefix}_entry"] = slot["entry"] if slot else "자동 선별 후보 없음"
            payload[f"{prefix}_add"] = slot["add"] if slot else "자동 선별 후보 없음"
            payload[f"{prefix}_exit"] = slot["exit"] if slot else "자동 선별 후보 없음"
            payload[f"{prefix}_invalid"] = slot["invalid"] if slot else "자동 선별 후보 없음"
        return payload

    def _auto_select_stock_candidates(
        self,
        common: dict[str, Any],
        sectors: dict[str, dict[str, str]],
        disclosures: dict[str, Any],
    ) -> list[dict[str, str]]:
        selected: list[dict[str, str]] = []
        seen: set[str] = set()
        for sector in self._preferred_stock_sectors(common, sectors):
            for name in AUTO_STOCK_CANDIDATES.get(sector, []):
                if name in seen:
                    continue
                selected.append(self._build_stock_candidate(name, sector, sectors, disclosures))
                seen.add(name)
                if len(selected) == 3:
                    return selected
        return selected

    def _preferred_stock_sectors(self, common: dict[str, Any], sectors: dict[str, dict[str, str]]) -> list[str]:
        preferred: list[str] = []
        expected = self._expected_sector_today(common, sectors)
        if expected != DATA_MISSING and "데이터 미수집" not in expected:
            preferred.extend([item.strip() for item in expected.split(",") if item.strip() in AUTO_STOCK_CANDIDATES])
        for sector in ("반도체", "AI", "자동차/현대차", "바이오/헬스케어", "로봇"):
            if sector in preferred:
                continue
            if sectors.get(sector, {}).get("headline", DATA_MISSING) != DATA_MISSING:
                preferred.append(sector)
        return preferred

    def _build_stock_candidate(self, name: str, sector: str, sectors: dict[str, dict[str, str]], disclosures: dict[str, Any]) -> dict[str, str]:
        sector_data = sectors.get(sector, {})
        headline = sector_data.get("headline", DATA_MISSING)
        disclosure = self._latest_company_disclosure(name, disclosures)
        reason_parts = [f"{sector} 우선 관찰"]
        if headline != DATA_MISSING:
            reason_parts.append(f"섹터 뉴스: {headline}")
        if disclosure != DATA_MISSING:
            reason_parts.append(f"최근 공시: {disclosure}")
        if len(reason_parts) == 1:
            reason_parts.append("개별 종목 자동 선별 근거 데이터 부족")
        return {
            "name": name,
            "sector": sector,
            "reason": " | ".join(reason_parts),
            "entry": self._generic_stock_entry_rule(name, sector, headline, disclosure),
            "add": self._generic_stock_add_rule(name, disclosure),
            "exit": f"{name} 손절/탈출 기준은 데이터 미수집 (개별 종목 가격·거래량 API 미연동)",
            "invalid": self._generic_stock_invalid_rule(sector, headline, disclosure),
        }

    def _latest_company_disclosure(self, company_name: str, disclosures: dict[str, Any]) -> str:
        items = disclosures.get("items_by_company", {}).get(company_name, [])
        if not items:
            return DATA_MISSING
        latest = items[0]
        return f"{latest.report_name} ({latest.filed_at})"

    def _generic_stock_entry_rule(self, name: str, sector: str, headline: str, disclosure: str) -> str:
        if headline != DATA_MISSING or disclosure != DATA_MISSING:
            return f"{name} 진입 기준은 데이터 미수집 (개별 가격·거래량 API 미연동). 현재는 {sector} 뉴스/공시 확인 후 수동 판단 필요."
        return f"{name} 진입 기준은 데이터 미수집 (섹터 근거와 개별 시세 데이터 모두 부족)"

    def _generic_stock_add_rule(self, name: str, disclosure: str) -> str:
        if disclosure != DATA_MISSING:
            return f"{name} 추가매수 기준은 데이터 미수집. 공시 확인만으로 비중 확대하지 말고 가격 데이터 연동 후 결정."
        return f"{name} 추가매수 기준은 데이터 미수집 (개별 종목 시세 API 미연동)"

    def _generic_stock_invalid_rule(self, sector: str, headline: str, disclosure: str) -> str:
        if headline != DATA_MISSING and disclosure != DATA_MISSING:
            return f"{sector} 뉴스와 개별 공시 해석이 엇갈리면 시나리오 무효"
        if headline != DATA_MISSING:
            return f"{sector} 뉴스 방향이 바뀌거나 후속 기사로 반박되면 시나리오 무효"
        return "시나리오 무효화 조건은 데이터 미수집 (개별 근거 부족)"

    def _combine_values(self, high: float | None, low: float | None) -> str:
        if high is None or low is None:
            return DATA_MISSING
        return f"{_fmt_number(high)} / {_fmt_number(low)}"

    def _hyundai_analysis(self, current: float | None, ma20: float | None, ma60: float | None) -> str:
        if current is None or ma20 is None or ma60 is None:
            return "현대차 이동평균 또는 종가 이력이 부족해 추세 분석 보류"
        if current > ma20 > ma60:
            return "종가가 20일선과 60일선 위에 있어 추세 우위."
        if current < ma20 < ma60:
            return "종가가 주요 이동평균 아래에 있어 방어 우선."
        return "이동평균 혼재 구간이라 추세 재확인이 필요."

    def _hyundai_scenario(self, current: float | None, ma20: float | None) -> str:
        if current is None or ma20 is None:
            return "현대차 20일 이동평균 데이터가 부족해 시나리오 분석 보류"
        if current >= ma20:
            return f"20일선({_fmt_number(ma20)}) 위 유지 시 추세 지속 관점."
        return f"20일선({_fmt_number(ma20)}) 회복 전까지는 방어 우선."

    def _hyundai_add_rule(self, current: float | None, ma20: float | None) -> str:
        if current is None or ma20 is None:
            return "현대차 20일 이동평균 데이터가 부족해 추가매수 기준 산출 보류"
        if current >= ma20:
            return f"20일선({_fmt_number(ma20)}) 지지 확인 후 분할 추가."
        return "20일선 회복 전 추가매수 보류."

    def _hyundai_exit_rule(self, current: float | None, ma20: float | None) -> str:
        if current is None or ma20 is None:
            return "현대차 20일 이동평균 데이터가 부족해 매도 기준 산출 보류"
        if current < ma20:
            return f"20일선({_fmt_number(ma20)}) 이탈 지속 시 비중 축소."
        return "단기 급등 후 거래량 둔화 시 일부 이익실현."
