from __future__ import annotations

import io
import json
import hashlib
import math
import os
import re
import calendar
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "research_config.toml"
KRX_CACHE_DIR = ROOT / ".cache" / "krx"

DATA_MISSING = "데이터 미수집"
ANALYSIS_PENDING = "필수 데이터 부족으로 분석 보류"

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
ALPHA_BASE_URL = "https://www.alphavantage.co/query"
NEWS_API_BASE_URL = "https://newsapi.org/v2/everything"
MARKETAUX_BASE_URL = "https://api.marketaux.com/v1/news/all"
YAHOO_CHART_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
YAHOO_QUOTE_SUMMARY_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary"
FNGUIDE_MAIN_URL = "https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp"
DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
DART_SINGLE_ACCOUNT_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"

NEWS_RELEVANCE_KEYWORDS = {
    "반도체": ["semiconductor", "memory", "chip", "hbm", "sk hynix", "samsung"],
    "AI": ["ai", "artificial intelligence", "openai", "nvidia", "model", "llm"],
    "로봇": ["robot", "robotics", "humanoid", "automation"],
    "자동차/현대차": ["hyundai", "kia", "automotive", "ev", "vehicle"],
    "바이오/헬스케어": ["biotech", "healthcare", "clinical", "fda", "drug", "pharma", "trial"],
    "ETF: SCHD, QQQM, SPYG": ["schd", "qqqm", "spyg", "etf", "dividend", "nasdaq"],
}

MARKETAUX_SEARCH_QUERIES = {
    "반도체": "semiconductor",
    "AI": "\"artificial intelligence\" OR Nvidia OR OpenAI OR Microsoft",
    "로봇": "\"humanoid robot\" OR robotics",
    "자동차/현대차": "Hyundai EV",
    "바이오/헬스케어": "FDA drug approval",
    "ETF: SCHD, QQQM, SPYG": "SCHD",
}

MASSIVE_SECTOR_TICKERS = {
    "반도체": "TSM",
    "AI": "MSFT",
    "로봇": "TSLA",
    "자동차/현대차": "TSLA",
    "바이오/헬스케어": "LLY",
    "ETF: SCHD, QQQM, SPYG": "SCHD",
}

TRUSTED_NEWS_SOURCES = {
    "reuters", "bloomberg", "cnbc", "wsj", "financial times", "marketwatch",
    "barron's", "yahoo finance", "investing.com", "the korea herald", "korea joongang daily",
    "businesskorea", "pulse", "mk.co.kr", "hankyung", "yna", "yonhap", "pr newswire",
    "globenewswire", "business wire", "seeking alpha", "the motley fool",
    "reuters.com", "bloomberg.com", "cnbc.com", "wsj.com", "marketwatch.com",
    "finance.yahoo.com", "seekingalpha.com", "digitimes.com", "techcrunch.com",
    "fiercebiotech.com", "endpts.com", "statnews.com",
}

LOW_QUALITY_SOURCE_KEYWORDS = {
    "pypi", "github", "gitlab", "npm", "stackoverflow", "reddit", "medium", "substack",
    "classmethod", "computerworld.dk", "dev.to", "ixbt", "terra.com.br", "digi24",
    "hwupgrade", "msn", "patch", "blog", "forum", "onefootball",
}

BLOCKED_URL_KEYWORDS = {
    "/articles/aws-", "/packages/", "/project/", "/docs/", "/tutorial", "/how-to",
    "/release-notes", "/tag/", "/category/", "/opinion/", "/lifestyle/", "/sports/",
    "/entertainment/", "/weather/", "/travel/",
}

SECTOR_ALLOWED_SOURCES = {
    "반도체": {"reuters", "bloomberg", "digitimes", "cnbc", "wsj", "marketwatch", "businesskorea", "hankyung", "yonhap", "yna", "finance.yahoo.com", "seekingalpha.com", "digitimes.com"},
    "AI": {"reuters", "bloomberg", "cnbc", "wsj", "marketwatch", "the information", "venturebeat", "techcrunch", "financial times", "yahoo finance", "finance.yahoo.com", "techcrunch.com"},
    "로봇": {"reuters", "bloomberg", "digitimes", "cnbc", "wsj", "marketwatch", "businesskorea", "yonhap", "yna", "finance.yahoo.com", "forbes.com", "businesswire.com", "prnewswire.com"},
    "자동차/현대차": {"reuters", "bloomberg", "cnbc", "wsj", "marketwatch", "pr newswire", "business wire", "yonhap", "yna", "hankyung", "businesskorea", "finance.yahoo.com", "zacks.com", "thehindubusinessline.com"},
    "바이오/헬스케어": {"reuters", "bloomberg", "cnbc", "wsj", "marketwatch", "fiercebiotech", "endpoints", "stat", "business wire", "globenewswire", "fiercebiotech.com", "endpts.com", "statnews.com", "finance.yahoo.com", "rttnews.com", "thehindubusinessline.com"},
    "ETF: SCHD, QQQM, SPYG": {"reuters", "bloomberg", "cnbc", "wsj", "marketwatch", "seeking alpha", "morningstar", "yahoo finance", "investing.com", "finance.yahoo.com", "seekingalpha.com"},
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

EXTRA_COMPANY_METADATA = {
    "SK하이닉스": {"market": "KOSPI", "stock_code": "000660"},
    "한미반도체": {"market": "KOSPI", "stock_code": "042700"},
    "네이버": {"market": "KOSPI", "stock_code": "035420"},
    "카카오": {"market": "KOSPI", "stock_code": "035720"},
    "기아": {"market": "KOSPI", "stock_code": "000270"},
    "현대모비스": {"market": "KOSPI", "stock_code": "012330"},
    "현대오토에버": {"market": "KOSPI", "stock_code": "307950"},
    "삼성바이오로직스": {"market": "KOSPI", "stock_code": "207940"},
    "셀트리온": {"market": "KOSPI", "stock_code": "068270"},
    "유한양행": {"market": "KOSPI", "stock_code": "000100"},
    "레인보우로보틱스": {"market": "KOSDAQ", "stock_code": "277810"},
    "두산로보틱스": {"market": "KOSPI", "stock_code": "454910"},
    "로보스타": {"market": "KOSDAQ", "stock_code": "090360"},
}

SECTOR_DART_COMPANIES = {
    "반도체": ["삼성전자", "SK하이닉스", "한미반도체"],
    "AI": ["NAVER", "카카오"],
    "로봇": ["레인보우로보틱스", "두산로보틱스", "로보스타"],
    "자동차/현대차": ["현대자동차", "기아", "현대모비스", "현대오토에버"],
    "바이오/헬스케어": ["삼성바이오로직스", "셀트리온", "유한양행", "디앤디파마텍"],
}


@dataclass(frozen=True)
class NewsItem:
    sector: str
    title: str
    description: str
    source: str
    published_at: str
    url: str
    provider: str


@dataclass(frozen=True)
class DisclosureItem:
    company: str
    report_name: str
    filed_at: str
    receipt_no: str
    url: str


@dataclass(frozen=True)
class DartFinancialSnapshot:
    report_name: str
    bsns_year: str
    revenue: int | None
    operating_income: int | None
    net_income: int | None
    assets: int | None
    liabilities: int | None
    equity: int | None


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


def _fmt_ratio(value: float | None, digits: int = 2) -> str:
    if value is None or math.isnan(value):
        return DATA_MISSING
    return f"{value:.{digits}f}"


def _parse_int_like(value: str | None) -> int | None:
    if value is None:
        return None
    cleaned = value.replace(",", "").replace(" ", "").strip()
    if not cleaned or cleaned in {"-", "."}:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    if not re.fullmatch(r"-?\d+", cleaned):
        return None
    parsed = int(cleaned)
    return -parsed if negative and parsed > 0 else parsed


def _fmt_krw_compact(value: int | None) -> str:
    if value is None:
        return DATA_MISSING
    abs_value = abs(value)
    sign = "-" if value < 0 else ""
    if abs_value >= 1_0000_0000_0000:
        return f"{sign}{abs_value / 1_0000_0000_0000:.1f}조원"
    if abs_value >= 1_0000_0000:
        return f"{sign}{round(abs_value / 1_0000_0000):,}억원"
    return f"{value:,}원"


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


def _shift_months(base_date: date, months: int) -> date:
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _snapshot_text(value: float | None, observed_date: str | None) -> str:
    if value is None or not observed_date or observed_date == DATA_MISSING:
        return DATA_MISSING
    return f"{_fmt_number(value)} ({_compact_iso(observed_date)})"


def _latest_point_asof(points: list[tuple[date, float]], ref_date: date) -> tuple[float | None, str]:
    chosen: tuple[date, float] | None = None
    for point_date, point_value in points:
        if point_date <= ref_date:
            chosen = (point_date, point_value)
        else:
            break
    if chosen is None:
        return None, DATA_MISSING
    point_date, point_value = chosen
    return point_value, point_date.isoformat()


def _contains_korean(text: str) -> bool:
    return any("가" <= char <= "힣" for char in text)


class ApiClient:
    def __init__(self) -> None:
        self.fred_key = os.getenv("FRED_API_KEY")
        self.news_key = os.getenv("NEWS_API_KEY")
        self.marketaux_key = os.getenv(CONFIG["api"]["marketaux"]["enabled_env"])
        self.massive_key = os.getenv(CONFIG["api"]["massive"]["enabled_env"])
        self.alpha_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        self.dart_key = os.getenv("DART_API_KEY")
        self.krx_key = os.getenv(CONFIG["api"]["krx"]["enabled_env"])
        self.kis_app_key = os.getenv(CONFIG["api"]["kis"]["enabled_env"])
        self.kis_app_secret = os.getenv(CONFIG["api"]["kis"]["app_secret_env"])
        self.kis_access_token: str | None = None
        self._corp_code_map: dict[str, str] | None = None
        self.krx_last_error: str | None = None
        self.marketaux_last_error: str | None = None
        self.marketaux_rate_limited = False
        self.massive_last_error: str | None = None
        self.massive_rate_limited = False

    def _krx_cache_path(self, path: str, params: dict[str, str]) -> Path:
        cache_key = json.dumps({"path": path, "params": params}, sort_keys=True, ensure_ascii=True)
        digest = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()
        return KRX_CACHE_DIR / f"{digest}.json"

    def _load_krx_cache(self, path: str, params: dict[str, str]) -> dict[str, Any] | None:
        cache_path = self._krx_cache_path(path, params)
        if not cache_path.exists():
            return None
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _save_krx_cache(self, path: str, params: dict[str, str], payload: dict[str, Any]) -> None:
        cache_path = self._krx_cache_path(path, params)
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            return

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any] | None:
        merged_headers = {"User-Agent": "devkim-research/1.0"}
        if headers:
            merged_headers.update(headers)
        request = Request(url, headers=merged_headers)
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

    def news_everything(self, query: str, target_date: date | None = None, page_size: int = 3) -> list[NewsItem]:
        if not self.news_key:
            return []
        params = {
            "q": query,
            "sortBy": "publishedAt",
            "pageSize": str(page_size),
            "apiKey": self.news_key,
        }
        if target_date is not None:
            lookback_days = int(CONFIG["api"]["news_lookback_days"])
            params["from"] = (target_date - timedelta(days=lookback_days)).isoformat()
            params["to"] = target_date.isoformat()
        payload = self.get_json(f"{NEWS_API_BASE_URL}?{urlencode(params)}")
        if not payload or payload.get("status") != "ok":
            return []
        items: list[NewsItem] = []
        for article in payload.get("articles", []):
            items.append(
                NewsItem(
                    sector="",
                    title=article.get("title") or DATA_MISSING,
                    description=article.get("description") or DATA_MISSING,
                    source=(article.get("source") or {}).get("name") or DATA_MISSING,
                    published_at=article.get("publishedAt") or DATA_MISSING,
                    url=article.get("url") or DATA_MISSING,
                    provider="NewsAPI",
                )
            )
        return items

    def marketaux_news(self, query: str, target_date: date | None = None, page_size: int | None = None) -> list[NewsItem]:
        if os.getenv("MARKETAUX_FORCE_DISABLED", "").lower() in {"1", "true", "yes", "on"}:
            self.marketaux_rate_limited = True
            self.marketaux_last_error = "사용자 지정으로 MarketAux 비활성화"
            return []
        if not self.marketaux_key:
            return []
        marketaux = CONFIG["api"]["marketaux"]
        limit = page_size or int(marketaux["limit"])
        params = {
            "api_token": self.marketaux_key,
            "search": query,
            "language": marketaux["language"],
            "limit": str(limit),
            "sort": "published_desc",
        }
        if target_date is not None:
            lookback_days = int(CONFIG["api"]["news_lookback_days"])
            params["published_after"] = (target_date - timedelta(days=lookback_days)).isoformat()
            params["published_before"] = f"{target_date.isoformat()}T23:59:59"
        url = f"{MARKETAUX_BASE_URL}?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": "devkim-research/1.0"})
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
                self.marketaux_last_error = None
                self.marketaux_rate_limited = False
        except HTTPError as error:
            self.marketaux_rate_limited = error.code == 429
            try:
                body = error.read().decode("utf-8")
                payload = json.loads(body)
                message = payload.get("error") or payload.get("message") or f"HTTP {error.code}"
                self.marketaux_last_error = str(message)
                lowered = self.marketaux_last_error.lower()
                if "limit" in lowered or "quota" in lowered or "rate" in lowered:
                    self.marketaux_rate_limited = True
            except (OSError, json.JSONDecodeError):
                self.marketaux_last_error = f"HTTP {error.code}"
            return []
        except (URLError, TimeoutError, json.JSONDecodeError):
            self.marketaux_last_error = "응답 파싱 실패"
            self.marketaux_rate_limited = False
            return []
        if not payload:
            return []
        items: list[NewsItem] = []
        for article in payload.get("data", []):
            description = article.get("description") or article.get("snippet") or DATA_MISSING
            items.append(
                NewsItem(
                    sector="",
                    title=article.get("title") or DATA_MISSING,
                    description=description,
                    source=article.get("source") or DATA_MISSING,
                    published_at=article.get("published_at") or DATA_MISSING,
                    url=article.get("url") or DATA_MISSING,
                    provider="MarketAux",
                )
            )
        return items

    def massive_reference_news(self, target_date: date | None = None, page_size: int | None = None, ticker: str | None = None) -> list[NewsItem]:
        if not self.massive_key or self.massive_rate_limited:
            return []
        massive = CONFIG["api"]["massive"]
        limit = page_size or int(massive["limit"])
        params = {
            "limit": str(limit),
            "apiKey": self.massive_key,
            "order": "desc",
            "sort": "published_utc",
        }
        if target_date is not None:
            lookback_days = int(CONFIG["api"]["news_lookback_days"])
            params["published_utc.gte"] = f"{(target_date - timedelta(days=lookback_days)).isoformat()}T00:00:00Z"
        if ticker:
            params["ticker"] = ticker
        url = f"{massive['base_url']}{massive['reference_news_path']}?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": "devkim-research/1.0"})
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
                self.massive_last_error = None
                self.massive_rate_limited = False
        except HTTPError as error:
            self.massive_rate_limited = error.code == 429
            try:
                body = error.read().decode("utf-8")
                payload = json.loads(body)
                self.massive_last_error = str(payload.get("message") or payload.get("error") or f"HTTP {error.code}")
            except (OSError, json.JSONDecodeError):
                self.massive_last_error = f"HTTP {error.code}"
            return []
        except (URLError, TimeoutError, json.JSONDecodeError):
            self.massive_last_error = "응답 파싱 실패"
            return []
        if not payload:
            return []
        items: list[NewsItem] = []
        for article in payload.get("results", []):
            description = article.get("description") or DATA_MISSING
            items.append(
                NewsItem(
                    sector="",
                    title=article.get("title") or DATA_MISSING,
                    description=description,
                    source=((article.get("publisher") or {}).get("name")) or DATA_MISSING,
                    published_at=article.get("published_utc") or DATA_MISSING,
                    url=article.get("article_url") or DATA_MISSING,
                    provider="Massive",
                )
            )
        return items

    def combined_news(self, query: str, target_date: date | None = None, page_size: int = 10, marketaux_query: str | None = None, massive_ticker: str | None = None) -> list[NewsItem]:
        articles = self.marketaux_news(marketaux_query or query, target_date=target_date, page_size=page_size)
        if self.marketaux_rate_limited:
            articles.extend(self.massive_reference_news(target_date=target_date, page_size=max(page_size, 20), ticker=massive_ticker))
        articles.extend(self.news_everything(query, target_date=target_date, page_size=page_size))
        unique: list[NewsItem] = []
        seen: set[tuple[str, str]] = set()
        for article in articles:
            key = ((article.url or "").strip().lower(), (article.title or "").strip().lower())
            if key in seen:
                continue
            seen.add(key)
            unique.append(article)
        return unique

    def alpha_symbol_search(self, keywords: str) -> str | None:
        payload = self.alpha_query("SYMBOL_SEARCH", keywords=keywords)
        if not payload:
            return None
        matches = payload.get("bestMatches", [])
        if not matches:
            return None
        return matches[0].get("1. symbol")

    def yahoo_chart(self, symbol: str, interval: str = "1d", range_: str = "1mo") -> dict[str, Any] | None:
        params = {"interval": interval, "range": range_}
        return self.get_json(f"{YAHOO_CHART_BASE_URL}/{symbol}?{urlencode(params)}")

    def yahoo_quote_summary(self, symbol: str | None, modules: tuple[str, ...] = ("defaultKeyStatistics", "financialData", "summaryDetail")) -> dict[str, Any] | None:
        if not symbol:
            return None
        params = {"modules": ",".join(modules)}
        payload = self.get_json(f"{YAHOO_QUOTE_SUMMARY_URL}/{symbol}?{urlencode(params)}")
        if not payload:
            return None
        result = ((payload.get("quoteSummary") or {}).get("result") or [None])[0]
        return result if isinstance(result, dict) else None

    def fnguide_consensus(self, stock_code: str | None) -> dict[str, Any] | None:
        code = str(stock_code or "").strip()
        if not code:
            return None
        params = {
            "pGB": "1",
            "gicode": f"A{code}",
            "cID": "",
            "MenuYn": "Y",
            "ReportGB": "",
            "NewMenuID": "101",
            "stkGb": "701",
        }
        request = Request(
            f"{FNGUIDE_MAIN_URL}?{urlencode(params)}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        try:
            with urlopen(request, timeout=20) as response:
                html = response.read().decode("utf-8", "ignore")
        except (HTTPError, URLError, TimeoutError, OSError):
            return None
        date_match = re.search(r'<h2>투자의견 컨센서스</h2>\s*<span class="date">\[(.*?)\]</span>', html, re.S)
        row_match = re.search(
            r'<div class="um_table" id="svdMainGrid9">.*?<tbody>\s*<tr[^>]*>\s*'
            r'<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>',
            html,
            re.S,
        )
        if not row_match:
            return None
        cells = [re.sub(r"<.*?>", "", value).replace("&nbsp;", " ").strip() for value in row_match.groups()]
        return {
            "date": date_match.group(1).strip() if date_match else DATA_MISSING,
            "opinion_score": cells[0] or DATA_MISSING,
            "target_price": cells[1] or DATA_MISSING,
            "eps": cells[2] or DATA_MISSING,
            "per": cells[3] or DATA_MISSING,
            "analyst_count": cells[4] or DATA_MISSING,
        }

    def krx_query(self, path: str, **params: str) -> dict[str, Any] | None:
        if not self.krx_key:
            return None
        query = dict(params)
        base = CONFIG["api"]["krx"]["base_url"]
        url = f"{base}{path}?{urlencode(query)}"
        request = Request(
            url,
            headers={
                "AUTH_KEY": self.krx_key,
                "User-Agent": "devkim-research/1.0",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
                self.krx_last_error = None
                self._save_krx_cache(path, query, payload)
                return payload
        except HTTPError as error:
            try:
                body = error.read().decode("utf-8")
                payload = json.loads(body)
                resp_code = payload.get("respCode")
                resp_msg = payload.get("respMsg")
                if resp_code and resp_msg:
                    self.krx_last_error = f"{resp_code} {resp_msg}"
                else:
                    self.krx_last_error = f"HTTP {error.code}"
            except (OSError, json.JSONDecodeError):
                self.krx_last_error = f"HTTP {error.code}"
            cached = self._load_krx_cache(path, query)
            if cached:
                self.krx_last_error = f"{self.krx_last_error} (cached)"
                return cached
            return None
        except (URLError, TimeoutError, json.JSONDecodeError):
            self.krx_last_error = "응답 파싱 실패"
            cached = self._load_krx_cache(path, query)
            if cached:
                self.krx_last_error = "응답 파싱 실패 (cached)"
                return cached
            return None

    def krx_kospi_daily(self, bas_date: str) -> list[dict[str, Any]]:
        payload = self.krx_query(
            CONFIG["api"]["krx"]["kospi_daily_path"],
            basDd=bas_date,
        )
        if not payload:
            return []
        items = payload.get("OutBlock_1")
        if not items:
            return []
        return items if isinstance(items, list) else [items]

    def krx_kosdaq_daily(self, bas_date: str) -> list[dict[str, Any]]:
        payload = self.krx_query(
            CONFIG["api"]["krx"]["kosdaq_daily_path"],
            basDd=bas_date,
        )
        if not payload:
            return []
        items = payload.get("OutBlock_1")
        if not items:
            return []
        return items if isinstance(items, list) else [items]

    def krx_stock_base_info(self, path: str, stock_code: str) -> dict[str, Any] | None:
        for params in ({"isuCd": stock_code}, {"likeSrtnCd": stock_code}):
            payload = self.krx_query(path, **params)
            if not payload:
                continue
            items = payload.get("OutBlock_1")
            if isinstance(items, list) and items:
                return items[0]
            if isinstance(items, dict) and items:
                return items
        return None

    def krx_stock_daily(self, path: str, bas_date: str, stock_code: str) -> list[dict[str, Any]]:
        param_candidates = (
            {"basDd": bas_date, "isuCd": stock_code},
            {"basDd": bas_date, "likeSrtnCd": stock_code},
        )
        for params in param_candidates:
            payload = self.krx_query(path, **params)
            if not payload:
                continue
            items = payload.get("OutBlock_1")
            if not items:
                continue
            return items if isinstance(items, list) else [items]
        return []

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

    def dart_single_account(self, corp_name: str, bsns_year: int, reprt_code: str) -> list[dict[str, str]]:
        corp_code = self.dart_corp_code(corp_name)
        if not self.dart_key or not corp_code:
            return []
        params = {
            "crtfc_key": self.dart_key,
            "corp_code": corp_code,
            "bsns_year": str(bsns_year),
            "reprt_code": reprt_code,
        }
        payload = self.get_json(f"{DART_SINGLE_ACCOUNT_URL}?{urlencode(params)}")
        if not payload or payload.get("status") != "000":
            return []
        rows = payload.get("list", [])
        return rows if isinstance(rows, list) else []

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
        sectors = self._build_sector_data(target_date)
        disclosures = self._build_disclosures(target_date)
        hyundai = self._build_hyundai_data(target_date, disclosures)
        favorites = self._build_favorite_stocks(target_date, hyundai, sectors, disclosures)
        session_data = self._build_session_data(session, common, hyundai, sectors, disclosures)
        return {
            "session_name": session,
            "session": session_data,
            "common": common,
            "hyundai": hyundai,
            "favorites": favorites,
            "sectors": sectors,
            "disclosures": disclosures,
            "coverage": self._build_coverage(common, hyundai, sectors, disclosures),
            "closing": self._build_closing_data(common, hyundai, sectors),
        }

    def _build_common_data(self, target_date: date) -> dict[str, dict[str, str]]:
        fred = self._build_fred_snapshot(target_date)
        gold = self._build_gold_snapshot(target_date)
        krx_market = self._build_krx_market_data(target_date)
        kis_market = self._build_kis_market_data()
        return {
            "market_summary": {
                "structure": self._macro_structure_text(fred),
                "drivers": self._market_driver_text(fred),
                "sentiment": self._market_sentiment_text(fred),
            },
            "fred": fred,
            "rates": {
                "us10y": fred["us10y"]["text"],
                "analysis": self._rate_analysis(fred["us10y"]),
            },
            "fx_commodities": {
                "usdkrw": fred["usdkrw"]["text"],
                "gold": gold["text"],
                "gold_snapshot": gold,
                "analysis": self._fx_gold_analysis(fred["usdkrw"], gold),
            },
            "korea_market": {
                "kospi": self._prefer_values(kis_market["kospi"], krx_market["kospi"]),
                "kosdaq": self._prefer_values(kis_market["kosdaq"], krx_market.get("kosdaq", DATA_MISSING)),
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
                "korea_index": self._compose_korea_index_reason(
                    self._prefer_values(kis_market["kospi"], krx_market["kospi"]),
                    self._prefer_values(kis_market["kosdaq"], krx_market.get("kosdaq", DATA_MISSING)),
                    krx_market["korea_index_reason"],
                    kis_market["korea_index_reason"],
                ),
                "investor_flow": kis_market["investor_flow_reason"],
            },
        }

    def _build_fred_snapshot(self, target_date: date) -> dict[str, dict[str, str | float | None]]:
        output: dict[str, dict[str, str | float | None]] = {}
        month_ago = _shift_months(target_date, -1)
        week_ago = target_date - timedelta(days=7)
        yesterday = target_date - timedelta(days=1)
        for key, series_id in self.fred_series.items():
            observations = self.client.fred_observations(series_id, target_date)
            latest = _latest_valid_observations(observations, 2)
            latest_val = _safe_float(latest[-1]["value"]) if latest else None
            prev_val = _safe_float(latest[-2]["value"]) if len(latest) > 1 else None
            delta = (latest_val - prev_val) if latest_val is not None and prev_val is not None else None
            points: list[tuple[date, float]] = []
            for obs in observations:
                value = _safe_float(obs.get("value"))
                obs_date_raw = obs.get("date")
                if value is None or not obs_date_raw or obs_date_raw == DATA_MISSING:
                    continue
                try:
                    obs_date = date.fromisoformat(obs_date_raw)
                except ValueError:
                    continue
                points.append((obs_date, value))
            month_val, month_date = _latest_point_asof(points, month_ago)
            week_val, week_date = _latest_point_asof(points, week_ago)
            day_val, day_date = _latest_point_asof(points, yesterday)
            output[key] = {
                "value": latest_val,
                "prev_value": prev_val,
                "delta": delta,
                "date": latest[-1]["date"] if latest else DATA_MISSING,
                "text": f"{_fmt_number(latest_val)} ({_compact_iso(latest[-1]['date'])})" if latest_val is not None and latest else DATA_MISSING,
                "month_ago_value": month_val,
                "month_ago_date": month_date,
                "month_ago_text": _snapshot_text(month_val, month_date),
                "week_ago_value": week_val,
                "week_ago_date": week_date,
                "week_ago_text": _snapshot_text(week_val, week_date),
                "yesterday_value": day_val,
                "yesterday_date": day_date,
                "yesterday_text": _snapshot_text(day_val, day_date),
            }
        return output

    def _build_gold_snapshot(self, target_date: date) -> dict[str, str | float | None]:
        payload = self.client.yahoo_chart("GC=F", interval="1d", range_="3mo") or {}
        result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
        timestamps = result.get("timestamp") or []
        quote = (((result.get("indicators") or {}).get("quote") or [None])[0]) or {}
        closes = quote.get("close") or []
        points: list[tuple[date, float]] = []
        for timestamp, close in zip(timestamps, closes):
            if close in (None, ""):
                continue
            point_date = datetime.utcfromtimestamp(timestamp).date()
            if point_date > target_date:
                continue
            points.append((point_date, float(close)))
        if not points:
            return {
                "value": None,
                "prev_value": None,
                "delta": None,
                "date": DATA_MISSING,
                "text": DATA_MISSING,
                "month_ago_value": None,
                "month_ago_date": DATA_MISSING,
                "month_ago_text": DATA_MISSING,
                "week_ago_value": None,
                "week_ago_date": DATA_MISSING,
                "week_ago_text": DATA_MISSING,
                "yesterday_value": None,
                "yesterday_date": DATA_MISSING,
                "yesterday_text": DATA_MISSING,
            }
        latest_date_obj, latest_value = points[-1]
        prev_value = points[-2][1] if len(points) > 1 else None
        delta = latest_value - prev_value if prev_value is not None else None
        latest_date = latest_date_obj.isoformat()
        month_ago = _shift_months(target_date, -1)
        week_ago = target_date - timedelta(days=7)
        yesterday = target_date - timedelta(days=1)
        month_val, month_date = _latest_point_asof(points, month_ago)
        week_val, week_date = _latest_point_asof(points, week_ago)
        day_val, day_date = _latest_point_asof(points, yesterday)
        return {
            "value": latest_value,
            "prev_value": prev_value,
            "delta": delta,
            "date": latest_date,
            "text": f"{_fmt_number(latest_value)} ({latest_date})",
            "month_ago_value": month_val,
            "month_ago_date": month_date,
            "month_ago_text": _snapshot_text(month_val, month_date),
            "week_ago_value": week_val,
            "week_ago_date": week_date,
            "week_ago_text": _snapshot_text(week_val, week_date),
            "yesterday_value": day_val,
            "yesterday_date": day_date,
            "yesterday_text": _snapshot_text(day_val, day_date),
        }

    def _build_krx_market_data(self, target_date: date) -> dict[str, str]:
        if not self.client.krx_key:
            return {
                "kospi": DATA_MISSING,
                "kosdaq": DATA_MISSING,
                "korea_index_reason": "KRX_API_KEY 환경변수 미설정",
            }
        kospi_value = DATA_MISSING
        kosdaq_value = DATA_MISSING
        kospi_reason = DATA_MISSING
        kosdaq_reason = DATA_MISSING
        for days_back in range(1, 8):
            query_date = (target_date - timedelta(days=days_back)).strftime("%Y%m%d")
            if kospi_value == DATA_MISSING:
                rows = self.client.krx_kospi_daily(query_date)
                row = self._select_krx_index_row(rows, "kospi") if rows else None
                if row:
                    kospi_value = self._format_krx_index_row(row)
                elif self.client.krx_last_error:
                    kospi_reason = f"KRX KOSPI 일별시세 API 미수집 ({self.client.krx_last_error})"
            if kosdaq_value == DATA_MISSING:
                rows = self.client.krx_kosdaq_daily(query_date)
                row = self._select_krx_index_row(rows, "kosdaq") if rows else None
                if row:
                    kosdaq_value = self._format_krx_index_row(row)
                elif self.client.krx_last_error:
                    kosdaq_reason = f"KRX KOSDAQ 일별시세 API 미수집 ({self.client.krx_last_error})"
            if kospi_value != DATA_MISSING and kosdaq_value != DATA_MISSING:
                break
        if kospi_reason == DATA_MISSING and kospi_value == DATA_MISSING:
            kospi_reason = "최근 7영업일 내 KOSPI 일별시세 응답 없음"
        if kosdaq_reason == DATA_MISSING and kosdaq_value == DATA_MISSING:
            kosdaq_reason = "최근 7영업일 내 KOSDAQ 일별시세 응답 없음"
        return {
            "kospi": kospi_value,
            "kosdaq": kosdaq_value,
            "korea_index_reason": self._compose_korea_index_reason(kospi_value, kosdaq_value, kospi_reason, kosdaq_reason),
        }

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

    def _dart_financial_report_candidates(self, target_date: date) -> list[tuple[int, str, str]]:
        year = target_date.year
        month = target_date.month
        if month >= 11:
            return [
                (year, "11014", "3분기보고서"),
                (year, "11012", "반기보고서"),
                (year, "11013", "1분기보고서"),
                (year - 1, "11011", "사업보고서"),
            ]
        if month >= 8:
            return [
                (year, "11012", "반기보고서"),
                (year, "11013", "1분기보고서"),
                (year - 1, "11011", "사업보고서"),
                (year - 1, "11014", "3분기보고서"),
            ]
        if month >= 5:
            return [
                (year, "11013", "1분기보고서"),
                (year - 1, "11011", "사업보고서"),
                (year - 1, "11014", "3분기보고서"),
                (year - 1, "11012", "반기보고서"),
            ]
        return [
            (year - 1, "11011", "사업보고서"),
            (year - 1, "11014", "3분기보고서"),
            (year - 1, "11012", "반기보고서"),
            (year - 1, "11013", "1분기보고서"),
        ]

    def _pick_dart_account_amount(self, rows: list[dict[str, str]], account_names: tuple[str, ...]) -> int | None:
        for fs_div in ("CFS", "OFS"):
            for row in rows:
                account_name = (row.get("account_nm") or "").strip()
                if row.get("fs_div") != fs_div or account_name not in account_names:
                    continue
                amount = _parse_int_like(row.get("thstrm_amount")) or _parse_int_like(row.get("thstrm_add_amount"))
                if amount is not None:
                    return amount
        return None

    def _build_company_dart_financial_snapshot(self, company: dict[str, Any], target_date: date) -> DartFinancialSnapshot | None:
        corp_name = company.get("dart_name") or company["name"]
        for bsns_year, reprt_code, report_name in self._dart_financial_report_candidates(target_date):
            rows = self.client.dart_single_account(corp_name, bsns_year, reprt_code)
            if not rows:
                continue
            return DartFinancialSnapshot(
                report_name=report_name,
                bsns_year=str(bsns_year),
                revenue=self._pick_dart_account_amount(rows, ("매출액", "영업수익")),
                operating_income=self._pick_dart_account_amount(rows, ("영업이익", "영업이익(손실)")),
                net_income=self._pick_dart_account_amount(rows, ("당기순이익", "당기순이익(손실)", "분기순이익", "반기순이익")),
                assets=self._pick_dart_account_amount(rows, ("자산총계",)),
                liabilities=self._pick_dart_account_amount(rows, ("부채총계",)),
                equity=self._pick_dart_account_amount(rows, ("자본총계",)),
            )
        return None

    def _capital_policy_summary(self, company_name: str, disclosures: list[DisclosureItem]) -> tuple[str, str]:
        keywords = ("자기주식", "유상증자", "무상증자", "유무상증자", "감자", "전환사채", "신주인수권부사채", "교환사채", "배당")
        matched = [item for item in disclosures if any(keyword in item.report_name for keyword in keywords)]
        if not matched:
            return (
                f"최근 90일 내 자사주·증자·사채·감자 관련 {company_name} 공시 미수집",
                "자본정책 새 이벤트가 없으면 기존 정책 유지로 해석",
            )
        top = matched[:3]
        summary = " | ".join(f"{item.report_name} ({item.filed_at})" for item in top)
        view = "자기주식·증자·사채 관련 공시는 주주환원 또는 자금조달 신호이므로 headline보다 조건을 확인해야 한다."
        return summary, view

    def _event_summary(self, company_name: str, disclosures: list[DisclosureItem]) -> tuple[str, str]:
        keywords = (
            "기업설명회", "실적", "분기보고서", "반기보고서", "사업보고서", "주주총회",
            "합병", "분할", "영업양수", "영업양도", "유형자산", "타법인 주식", "해외 증권시장",
        )
        matched = [item for item in disclosures if any(keyword in item.report_name for keyword in keywords)]
        if not matched:
            return (
                f"최근 90일 내 {company_name} 이벤트성 공시 미수집",
                "이벤트 공시가 비어 있으면 단기 주가 해석은 뉴스보다 업종 수급과 환율 영향이 더 크다.",
            )
        top = matched[:3]
        summary = " | ".join(f"{item.report_name} ({item.filed_at})" for item in top)
        view = "IR·정기보고서·구조개편 공시는 숫자와 일정 확인 전까지 기대감만으로 추격하지 않는 편이 낫다."
        return summary, view

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

    def _build_hyundai_data(self, target_date: date, disclosures: dict[str, Any]) -> dict[str, str]:
        company = next(item for item in self.tracked_companies if item["name"] == "현대차")
        return self._build_favorite_stock_data(company, target_date, disclosures)

    def _build_favorite_stock_data(self, company: dict[str, Any], target_date: date, disclosures: dict[str, Any]) -> dict[str, str]:
        company_name = company["name"]
        kis_data = self._build_kis_hyundai_data() if company_name == "현대차" else self._empty_stock_flow_data()
        krx_data = self._build_krx_stock_data(company, target_date)
        company_disclosures = disclosures.get("items_by_company", {}).get(company_name, [])
        dart_financial = self._build_company_dart_financial_snapshot(company, target_date)
        capital_policy_summary, capital_policy_view = self._capital_policy_summary(company_name, company_disclosures)
        event_summary, event_view = self._event_summary(company_name, company_disclosures)
        yahoo_symbol = self._yahoo_symbol_for_company(company)
        yahoo_history = self.client.yahoo_chart(yahoo_symbol, interval="1d", range_="1y") or {}
        yahoo_summary = self.client.yahoo_quote_summary(yahoo_symbol) or {}
        symbol = (
            os.getenv("HYUNDAI_ALPHA_SYMBOL") if company_name == "현대차" else None
        ) or company.get("alpha_symbol") or yahoo_symbol or self._resolve_alpha_symbol(company)
        quote = self.client.alpha_query("GLOBAL_QUOTE", symbol=symbol) or {}
        daily = self.client.alpha_query("TIME_SERIES_DAILY", symbol=symbol, outputsize="full") or {}
        global_quote = quote.get("Global Quote", {})
        alpha_series = daily.get("Time Series (Daily)", {})
        rows = sorted(alpha_series.items(), reverse=True)
        highs, lows, closes, prev_close, latest_close, latest_high, latest_low, latest_volume = self._extract_alpha_history(rows)
        yahoo_points = self._extract_yahoo_history(yahoo_history)
        if yahoo_points["highs"]:
            highs = yahoo_points["highs"]
        if yahoo_points["lows"]:
            lows = yahoo_points["lows"]
        if yahoo_points["closes"]:
            closes = yahoo_points["closes"]
            latest_close = yahoo_points["latest_close"] or latest_close
            prev_close = yahoo_points["prev_close"] or prev_close
            latest_high = yahoo_points["latest_high"] or latest_high
            latest_low = yahoo_points["latest_low"] or latest_low
            latest_volume = yahoo_points["latest_volume"] or latest_volume
        current_price, prev_close, current_volume, intraday_high, intraday_low = self._merge_stock_price_inputs(
            kis_data,
            krx_data,
            global_quote,
            latest_close,
            prev_close,
            latest_volume,
            latest_high,
            latest_low,
        )
        ma20 = _rolling_average(closes, 20)
        ma60 = _rolling_average(closes, 60)
        disclosure = self._latest_company_disclosure(company_name, disclosures)
        data = {
            "name": company_name,
            "symbol": symbol or DATA_MISSING,
            "current_close": self._prefer_values(kis_data["current_close"], krx_data["current_close"], _fmt_number(current_price)),
            "previous_close": self._prefer_values(kis_data["previous_close"], krx_data["previous_close"], _fmt_number(prev_close)),
            "volume": self._prefer_values(kis_data["volume"], krx_data["volume"], _fmt_int(current_volume)),
            "week52_high": _fmt_number(max(highs[:252]) if highs else None),
            "week52_low": _fmt_number(min(lows[:252]) if lows else None),
            "per": _fmt_ratio(self._yahoo_quote_metric(yahoo_summary, "trailingPE")),
            "forward_per": _fmt_ratio(self._yahoo_quote_metric(yahoo_summary, "forwardPE")),
            "intraday_high_low": self._prefer_values(kis_data["intraday_high_low"], krx_data["intraday_high_low"], self._combine_values(intraday_high, intraday_low)),
            "foreign_flow": kis_data["foreign_flow"],
            "institutional_flow": kis_data["institutional_flow"],
            "retail_flow": kis_data["retail_flow"],
            "short_selling": self._prefer_values(kis_data["short_selling"], krx_data["short_selling"]),
            "forced_liquidation": kis_data["forced_liquidation"],
            "ma5": _fmt_number(_rolling_average(closes, 5)),
            "ma20": _fmt_number(ma20),
            "ma60": _fmt_number(ma60),
            "support": _fmt_number(min(lows[:20]) if len(lows) >= 20 else None),
            "resistance": _fmt_number(max(highs[:20]) if len(highs) >= 20 else None),
            "chart_structure": self._favorite_chart_structure(current_price, ma20, ma60, company_name),
            "shakeout_view": self._shakeout_view(current_price, ma20, ma60, company_name),
            "down_reason": self._favorite_down_reason(current_price, ma20, ma60, disclosure, company_name),
            "up_reason": self._favorite_up_reason(current_price, ma20, ma60, disclosure, company_name),
            "forecast": self._favorite_forecast(current_price, ma20, ma60, company_name),
            "dart_financial_period": f"{dart_financial.bsns_year} {dart_financial.report_name}" if dart_financial else DATA_MISSING,
            "dart_financial_summary": (
                f"매출 {_fmt_krw_compact(dart_financial.revenue)} | 영업이익 {_fmt_krw_compact(dart_financial.operating_income)} | "
                f"순이익 {_fmt_krw_compact(dart_financial.net_income)} | 자산 {_fmt_krw_compact(dart_financial.assets)} | "
                f"부채 {_fmt_krw_compact(dart_financial.liabilities)} | 자본 {_fmt_krw_compact(dart_financial.equity)}"
                if dart_financial else DATA_MISSING
            ),
            "dart_financial_view": (
                "연결 기준 최근 제출 재무제표를 사용한다. 분기 수치는 누적 기준일 수 있으므로 전년 동기와 함께 해석해야 한다."
                if dart_financial else "DART 재무제표 미수집"
            ),
            "dart_capital_policy": capital_policy_summary,
            "dart_capital_policy_view": capital_policy_view,
            "dart_events": event_summary,
            "dart_events_view": event_view,
        }
        data.update(self._stock_target_snapshot(company_name, current_price))
        data.update(self._favorite_company_overrides(company_name, current_price, ma20, ma60, disclosures))
        return data

    def _build_krx_stock_data(self, company: dict[str, Any], target_date: date) -> dict[str, str]:
        stock_code = str(company.get("stock_code") or "").strip()
        market = str(company.get("market") or "KOSPI").upper()
        company_name = company["name"]
        if not self.client.krx_key or not stock_code:
            return {
                "current_close": DATA_MISSING,
                "previous_close": DATA_MISSING,
                "volume": DATA_MISSING,
                "intraday_high_low": DATA_MISSING,
                "short_selling": DATA_MISSING,
            }
        daily_path = CONFIG["api"]["krx"]["stk_daily_path"] if market == "KOSPI" else CONFIG["api"]["krx"]["ksq_daily_path"]
        for days_back in range(1, 8):
            query_date = (target_date - timedelta(days=days_back)).strftime("%Y%m%d")
            rows = self.client.krx_stock_daily(daily_path, query_date, stock_code)
            if not rows:
                continue
            row = self._select_krx_stock_row(rows, stock_code, company_name)
            if not row:
                continue
            close_value = self._fmt_krx_number(self._krx_row_value(row, "TDD_CLSPRC", "CLSPRC", "CLSPRC_IDX"))
            prev_value = self._krx_previous_close_text(row)
            volume_value = self._fmt_krx_int(self._krx_row_value(row, "ACC_TRDVOL", "TDD_TRDVOL", "TRDVOL"))
            high_low = self._fmt_krx_high_low(
                self._krx_row_value(row, "TDD_HGPRC", "HGPRC", "HGPRC_IDX"),
                self._krx_row_value(row, "TDD_LWPRC", "LWPRC", "LWPRC_IDX"),
            )
            return {
                "current_close": close_value,
                "previous_close": prev_value,
                "volume": volume_value,
                "intraday_high_low": high_low,
                "short_selling": DATA_MISSING,
            }
        return {
            "current_close": DATA_MISSING,
            "previous_close": DATA_MISSING,
            "volume": DATA_MISSING,
            "intraday_high_low": DATA_MISSING,
            "short_selling": DATA_MISSING,
        }

    def _build_favorite_stocks(
        self,
        target_date: date,
        hyundai: dict[str, str],
        sectors: dict[str, dict[str, str]],
        disclosures: dict[str, Any],
    ) -> dict[str, dict[str, str]]:
        favorites: dict[str, dict[str, str]] = {}
        for company in self.tracked_companies:
            if company["name"] == "현대차":
                favorites[company["name"]] = hyundai
                continue
            favorites[company["name"]] = self._build_favorite_stock_data(company, target_date, disclosures)
        return favorites

    def _favorite_company_overrides(
        self,
        company_name: str,
        current_price: float | None,
        ma20: float | None,
        ma60: float | None,
        disclosures: dict[str, Any],
    ) -> dict[str, str]:
        if company_name == "현대차":
            return {
                "today_analysis": self._hyundai_analysis(current_price, ma20, ma60),
                "tomorrow_scenario": self._hyundai_scenario(current_price, ma20),
                "add_rule": self._hyundai_add_rule(current_price, ma20),
                "exit_rule": self._hyundai_exit_rule(current_price, ma20),
            }
        if company_name == "디앤디파마텍":
            bio = self._build_dnd_sector_context(disclosures)
            disclosure = self._latest_company_disclosure(company_name, disclosures)
            return {
                "today_analysis": self._dnd_today_analysis(bio, disclosure),
                "tomorrow_scenario": self._dnd_tomorrow_scenario(bio, disclosure),
                "add_rule": self._dnd_add_rule(disclosure),
                "exit_rule": self._dnd_exit_rule(disclosure),
            }
        return {
            "today_analysis": self._favorite_forecast(current_price, ma20, ma60, company_name),
            "tomorrow_scenario": self._favorite_forecast(current_price, ma20, ma60, company_name),
            "add_rule": self._favorite_add_rule(current_price, ma20, company_name),
            "exit_rule": self._favorite_exit_rule(current_price, ma20, company_name),
        }

    def _build_dnd_sector_context(self, disclosures: dict[str, Any]) -> dict[str, str]:
        disclosure = self._latest_company_disclosure("디앤디파마텍", disclosures)
        return {
            "headline": DATA_MISSING,
            "clinical_news": DATA_MISSING,
            "fda_news": DATA_MISSING,
            "licensing_news": DATA_MISSING,
            "dnd_comment": disclosure,
        }

    def _empty_stock_flow_data(self) -> dict[str, str]:
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

    def _extract_alpha_history(
        self,
        rows: list[tuple[str, dict[str, str]]],
    ) -> tuple[list[float], list[float], list[float], float | None, float | None, float | None, float | None, int | None]:
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
        return highs, lows, closes, prev_close, latest_close, latest_high, latest_low, latest_volume

    def _extract_yahoo_history(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
        quote = (((result.get("indicators") or {}).get("quote") or [None])[0]) or {}
        highs_raw = quote.get("high") or []
        lows_raw = quote.get("low") or []
        closes_raw = quote.get("close") or []
        volumes_raw = quote.get("volume") or []
        highs = [float(value) for value in highs_raw if value not in (None, "")]
        lows = [float(value) for value in lows_raw if value not in (None, "")]
        closes = [float(value) for value in closes_raw if value not in (None, "")]
        volume_points = [int(value) for value in volumes_raw if value not in (None, "")]
        return {
            "highs": list(reversed(highs)),
            "lows": list(reversed(lows)),
            "closes": list(reversed(closes)),
            "latest_close": closes[-1] if closes else None,
            "prev_close": closes[-2] if len(closes) > 1 else None,
            "latest_high": highs[-1] if highs else None,
            "latest_low": lows[-1] if lows else None,
            "latest_volume": volume_points[-1] if volume_points else None,
        }

    def _merge_stock_price_inputs(
        self,
        kis_data: dict[str, str],
        krx_data: dict[str, str],
        global_quote: dict[str, str],
        latest_close: float | None,
        prev_close: float | None,
        latest_volume: int | None,
        latest_high: float | None,
        latest_low: float | None,
    ) -> tuple[float | None, float | None, int | None, float | None, float | None]:
        krx_close_num = _safe_float(krx_data["current_close"].replace(",", "")) if krx_data["current_close"] != DATA_MISSING else None
        krx_prev_close_num = _safe_float(krx_data["previous_close"].replace(",", "")) if krx_data["previous_close"] != DATA_MISSING else None
        krx_volume_num = _parse_int_like(krx_data["volume"]) if krx_data["volume"] != DATA_MISSING else None
        krx_high_num: float | None = None
        krx_low_num: float | None = None
        if krx_data["intraday_high_low"] != DATA_MISSING:
            high_text, _, low_text = krx_data["intraday_high_low"].partition("/")
            krx_high_num = _safe_float(high_text.replace(",", "").strip())
            krx_low_num = _safe_float(low_text.replace(",", "").strip())
        current_price = krx_close_num or _safe_float(global_quote.get("05. price")) or latest_close
        prev_close = krx_prev_close_num or prev_close
        current_volume = krx_volume_num or (int(float(global_quote["06. volume"])) if global_quote.get("06. volume") else latest_volume)
        intraday_high = krx_high_num or _safe_float(global_quote.get("03. high")) or latest_high
        intraday_low = krx_low_num or _safe_float(global_quote.get("04. low")) or latest_low
        return current_price, prev_close, current_volume, intraday_high, intraday_low

    def _yahoo_symbol_for_company(self, company: dict[str, Any]) -> str | None:
        stock_code = str(company.get("stock_code") or "").strip()
        market = str(company.get("market") or "").upper()
        if not stock_code or market not in {"KOSPI", "KOSDAQ"}:
            return None
        suffix = ".KS" if market == "KOSPI" else ".KQ"
        return f"{stock_code}{suffix}"

    def _yahoo_quote_metric(self, payload: dict[str, Any], field: str) -> float | None:
        for section_name in ("defaultKeyStatistics", "financialData", "summaryDetail"):
            section = payload.get(section_name)
            if not isinstance(section, dict):
                continue
            value = section.get(field)
            if isinstance(value, dict):
                raw = value.get("raw")
                if isinstance(raw, (int, float)):
                    return float(raw)
            if isinstance(value, (int, float)):
                return float(value)
        return None

    def _yahoo_quote_text(self, payload: dict[str, Any], field: str) -> str | None:
        for section_name in ("financialData", "defaultKeyStatistics", "summaryDetail"):
            section = payload.get(section_name)
            if not isinstance(section, dict):
                continue
            value = section.get(field)
            if isinstance(value, dict):
                fmt = value.get("fmt")
                raw = value.get("raw")
                if isinstance(fmt, str) and fmt.strip():
                    return fmt.strip()
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _company_reference(self, name: str) -> dict[str, Any]:
        for company in self.tracked_companies:
            if company.get("name") == name:
                return company
        return {"name": name, **EXTRA_COMPANY_METADATA.get(name, {})}

    def _stock_target_snapshot(self, name: str, current_price: float | None = None) -> dict[str, str]:
        company = self._company_reference(name)
        fnguide = self.client.fnguide_consensus(company.get("stock_code"))
        yahoo_symbol = self._yahoo_symbol_for_company(company)
        yahoo_summary = (self.client.yahoo_quote_summary(yahoo_symbol) or {}) if yahoo_symbol else {}
        if current_price is None and yahoo_symbol:
            yahoo_chart = self.client.yahoo_chart(yahoo_symbol, interval="1d", range_="5d") or {}
            yahoo_points = self._extract_yahoo_history(yahoo_chart)
            current_price = yahoo_points.get("latest_close") or current_price
        target_mean = self._yahoo_quote_metric(yahoo_summary, "targetMeanPrice")
        target_high = self._yahoo_quote_metric(yahoo_summary, "targetHighPrice")
        target_low = self._yahoo_quote_metric(yahoo_summary, "targetLowPrice")
        target_median = self._yahoo_quote_metric(yahoo_summary, "targetMedianPrice")
        analyst_count = self._yahoo_quote_metric(yahoo_summary, "numberOfAnalystOpinions")
        recommendation = self._yahoo_quote_text(yahoo_summary, "recommendationKey")
        if target_mean is None and fnguide and fnguide.get("target_price") not in (None, "", DATA_MISSING):
            target_mean = _safe_float(str(fnguide.get("target_price")).replace(",", ""))
        if analyst_count is None and fnguide and fnguide.get("analyst_count") not in (None, "", DATA_MISSING):
            analyst_count = _safe_float(str(fnguide.get("analyst_count")).replace(",", ""))
        if not recommendation and fnguide and fnguide.get("opinion_score") not in (None, "", DATA_MISSING):
            recommendation = f"score {fnguide['opinion_score']}"
        target_text = self._target_price_text(target_mean, target_median, target_high, target_low, analyst_count, recommendation)
        target_view = self._target_price_view(name, current_price, target_mean, target_high, target_low)
        target_basis = self._target_price_basis(analyst_count, recommendation, target_high, target_low, fnguide)
        return {
            "target_price": target_text,
            "target_price_view": target_view,
            "target_price_basis": target_basis,
        }

    def _target_price_text(
        self,
        target_mean: float | None,
        target_median: float | None,
        target_high: float | None,
        target_low: float | None,
        analyst_count: float | None,
        recommendation: str | None,
    ) -> str:
        if target_mean is None and target_median is None and target_high is None and target_low is None:
            return DATA_MISSING
        parts: list[str] = []
        if target_mean is not None:
            parts.append(f"평균 {_fmt_number(target_mean, 0)}")
        if target_median is not None:
            parts.append(f"중앙값 {_fmt_number(target_median, 0)}")
        if target_high is not None and target_low is not None:
            parts.append(f"범위 {_fmt_number(target_low, 0)}~{_fmt_number(target_high, 0)}")
        elif target_high is not None:
            parts.append(f"상단 {_fmt_number(target_high, 0)}")
        elif target_low is not None:
            parts.append(f"하단 {_fmt_number(target_low, 0)}")
        if analyst_count is not None:
            parts.append(f"커버리지 {int(analyst_count)}명")
        if recommendation:
            parts.append(f"컨센서스 {recommendation}")
        return " | ".join(parts) if parts else DATA_MISSING

    def _target_price_view(
        self,
        name: str,
        current_price: float | None,
        target_mean: float | None,
        target_high: float | None,
        target_low: float | None,
    ) -> str:
        if target_mean is None:
            return f"{name} 목표주가 해석은 데이터 미수집 (애널리스트 평균 목표가 미제공)"
        if current_price is None or current_price <= 0:
            return f"{name} 목표주가는 평균 {_fmt_number(target_mean, 0)} 수준으로 보이지만 현재가 비교 데이터가 없어 괴리 해석은 보류한다."
        gap_pct = ((target_mean - current_price) / current_price) * 100
        gap_text = _fmt_pct(gap_pct)
        if gap_pct >= 15:
            stance = "현재가 대비 의미 있는 상방여력이 반영된 상태다"
        elif gap_pct >= 5:
            stance = "현재가 대비 완만한 상방여력을 반영한 중립 이상 시각이다"
        elif gap_pct > -5:
            stance = "현재가와 목표주가 괴리가 크지 않아 대체로 적정가 근처 시각에 가깝다"
        else:
            stance = "현재가가 컨센서스 목표에 근접했거나 일부 구간에서는 선반영됐다고 볼 수 있다"
        range_note = ""
        if target_high is not None and target_low is not None and current_price > 0:
            spread_pct = ((target_high - target_low) / current_price) * 100
            range_note = f" 목표가 밴드도 약 {_fmt_pct(spread_pct)} 폭이라 의견 분산을 함께 봐야 한다."
        return f"{name} 평균 목표주가는 현재가 대비 {gap_text} 괴리다. 즉 {stance}.{range_note}"

    def _target_price_basis(
        self,
        analyst_count: float | None,
        recommendation: str | None,
        target_high: float | None,
        target_low: float | None,
        fnguide: dict[str, Any] | None = None,
    ) -> str:
        if analyst_count is None and recommendation is None and target_high is None and target_low is None and not fnguide:
            return "목표주가 근거 미수집"
        parts: list[str] = []
        if analyst_count is not None:
            parts.append(f"애널리스트 {int(analyst_count)}명 컨센서스 기준")
        if recommendation:
            parts.append(f"추천 키워드 {recommendation}")
        if target_high is not None and target_low is not None:
            parts.append(f"상단/하단 목표가 차이가 {_fmt_number(target_high - target_low, 0)} 수준이라 전망 분산도 확인 필요")
        if fnguide:
            fg_date = fnguide.get("date", DATA_MISSING)
            fg_eps = fnguide.get("eps", DATA_MISSING)
            fg_per = fnguide.get("per", DATA_MISSING)
            if fg_date != DATA_MISSING:
                parts.append(f"FnGuide 컨센서스 기준일 {fg_date}")
            if fg_eps != DATA_MISSING and fg_per != DATA_MISSING:
                parts.append(f"FY1 기준 EPS {fg_eps} / PER {fg_per}")
        return " | ".join(parts) if parts else "목표주가 근거 미수집"

    def _resolve_alpha_symbol(self, company: dict[str, Any]) -> str | None:
        for keyword in company.get("alpha_search_keywords", []):
            symbol = self.client.alpha_symbol_search(keyword)
            if symbol:
                return symbol
        return None

    def _build_sector_data(self, target_date: date) -> dict[str, dict[str, str]]:
        sector_data: dict[str, dict[str, str]] = {}
        for sector, query in self.news_queries.items():
            marketaux_query = MARKETAUX_SEARCH_QUERIES.get(sector, query)
            massive_ticker = MASSIVE_SECTOR_TICKERS.get(sector)
            articles = self.client.combined_news(
                query,
                target_date=target_date,
                page_size=10,
                marketaux_query=marketaux_query,
                massive_ticker=massive_ticker,
            )
            top = self._select_relevant_article(sector, articles)
            localized_title = self._localize_headline(sector, top.title if top else DATA_MISSING)
            localized_description = self._localize_description(sector, localized_title, top.description if top else DATA_MISSING)
            schedule = self._build_sector_schedule(sector, target_date)
            data = {
                "headline": localized_title,
                "headline_original": top.title if top else DATA_MISSING,
                "headline_description": localized_description,
                "source": top.source if top else DATA_MISSING,
                "published_at": top.published_at if top else DATA_MISSING,
                "url": top.url if top else DATA_MISSING,
                "collection_path": self._collection_path_label(top),
                "price_impact": self._headline_based_view(localized_title),
                "short_term": self._headline_based_view(localized_title),
                "medium_term": self._headline_based_view(localized_title),
                "investment_judgment": self._investment_judgment_from_headline(localized_title),
                "risk": self._risk_from_headline(localized_title),
                "schedule": schedule["summary"],
                "schedule_detail": schedule["detail"],
                "schedule_view": schedule["view"],
            }
            if sector == "바이오/헬스케어":
                data.update(self._build_bio_sector_data(target_date))
            sector_data[sector] = data
        return sector_data

    def _collection_path_label(self, article: NewsItem | None) -> str:
        if not article:
            return DATA_MISSING
        if article.provider == "NewsAPI":
            return "기본 뉴스 소스"
        return f"보조 소스 기반 ({article.provider})"

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

    def _localize_description(self, sector: str, localized_title: str, description: str) -> str:
        if description == DATA_MISSING:
            return DATA_MISSING
        if _contains_korean(description):
            return description
        if sector == "반도체":
            return f"{localized_title} 관련 기사로, 반도체 업종의 실적 기대와 밸류에이션 해석이 핵심이다."
        if sector == "AI":
            return f"{localized_title} 관련 기사로, AI 투자 지출이 실제 수익성으로 연결되는지 점검하는 내용이다."
        if sector == "로봇":
            return f"{localized_title} 관련 기사로, 로봇 상용화 속도와 경쟁 심리 변화에 영향을 줄 수 있다."
        if sector == "자동차/현대차":
            return f"{localized_title} 관련 기사로, 전기차 전개 속도와 자동차 수요 흐름 점검에 의미가 있다."
        if sector == "바이오/헬스케어":
            return f"{localized_title} 관련 기사로, 허가·임상·신약 모멘텀 측면에서 바이오 투자심리에 영향을 줄 수 있다."
        if sector == "ETF: SCHD, QQQM, SPYG":
            return f"{localized_title} 관련 기사로, 배당형과 성장형 ETF의 상대 매력 비교에 참고할 수 있다."
        return "영문 기사 요약은 한국어 해석 로직으로 치환됨"

    def _select_relevant_article(self, sector: str, articles: list[NewsItem]) -> NewsItem | None:
        if not articles:
            return None
        keywords = NEWS_RELEVANCE_KEYWORDS.get(sector, [])
        filtered = [article for article in articles if not self._is_low_quality_article(article, sector)]
        filtered = [article for article in filtered if self._is_allowed_source(article, sector)]
        if not filtered and self._is_fallback_news_mode():
            filtered = [article for article in articles if not self._is_low_quality_article(article, sector)]
        if not filtered and self._is_fallback_news_mode():
            filtered = [article for article in articles if self._is_fallback_candidate(article, sector)]
        if not filtered:
            return None
        ranked = sorted(filtered, key=lambda article: self._relevance_score(article, keywords), reverse=True)
        top = ranked[0]
        min_score = 0 if self._is_fallback_news_mode() else 1
        if self._relevance_score(top, keywords) < min_score:
            return None
        return top

    def _is_fallback_news_mode(self) -> bool:
        return self.client.marketaux_rate_limited or self.client.massive_rate_limited

    def _is_fallback_candidate(self, article: NewsItem, sector: str) -> bool:
        haystack = f"{article.title} {article.description} {article.source} {article.url}".lower()
        if sector == "반도체":
            return any(self._keyword_present(haystack, word) for word in ("semiconductor", "chip", "memory", "hbm", "foundry", "tsmc", "intel", "nvidia"))
        if sector == "AI":
            return any(self._keyword_present(haystack, word) for word in ("ai", "artificial intelligence", "openai", "nvidia", "microsoft", "amazon", "cloud"))
        if sector == "로봇":
            return any(self._keyword_present(haystack, word) for word in ("robot", "robotics", "humanoid", "automation", "tesla"))
        if sector == "자동차/현대차":
            return any(self._keyword_present(haystack, word) for word in ("hyundai", "kia", "automotive", "ev", "electric vehicle", "tesla", "motor"))
        if sector == "바이오/헬스케어":
            return any(self._keyword_present(haystack, word) for word in ("biotech", "healthcare", "clinical", "fda", "drug", "pharma", "trial", "therapeutic"))
        if sector == "ETF: SCHD, QQQM, SPYG":
            return any(self._keyword_present(haystack, word) for word in ("schd", "qqqm", "spyg", "etf", "dividend", "growth"))
        return False

    def _relevance_score(self, article: NewsItem, keywords: list[str]) -> int:
        haystack = f"{article.title} {article.description} {article.source} {article.url}".lower()
        score = sum(2 for keyword in keywords if self._keyword_present(haystack, keyword))
        source = (article.source or "").lower()
        url = (article.url or "").lower()
        domain = urlparse(url).netloc.lower()
        if any(source_name in source for source_name in TRUSTED_NEWS_SOURCES):
            score += 3
        if any(source_name in domain for source_name in TRUSTED_NEWS_SOURCES):
            score += 2
        if self._contains_market_structure_terms(haystack):
            score += 1
        if self._is_low_quality_article(article, ""):
            score -= 5
        return score

    def _is_low_quality_article(self, article: NewsItem, sector: str) -> bool:
        haystack = f"{article.title} {article.description} {article.source} {article.url}".lower()
        domain = urlparse((article.url or "").lower()).netloc
        if any(keyword in haystack for keyword in LOW_QUALITY_SOURCE_KEYWORDS):
            return True
        if any(keyword in (article.url or "").lower() for keyword in BLOCKED_URL_KEYWORDS):
            return True
        if sector == "자동차/현대차" and not any(self._keyword_present(haystack, word) for word in ("hyundai", "kia", "automotive", "ev", "vehicle", "electric vehicle")):
            return True
        if sector == "AI" and not any(self._keyword_present(haystack, word) for word in ("ai", "artificial intelligence", "llm", "nvidia", "openai", "microsoft", "generative ai")):
            return True
        if sector == "로봇" and not any(self._keyword_present(haystack, word) for word in ("robot", "robotics", "humanoid", "automation")):
            return True
        if sector == "반도체" and not any(self._keyword_present(haystack, word) for word in ("semiconductor", "chip", "memory", "hbm", "foundry", "samsung", "hynix")):
            return True
        if sector == "바이오/헬스케어" and not any(self._keyword_present(haystack, word) for word in ("biotech", "healthcare", "clinical", "fda", "drug", "pharma", "trial", "ultrasound", "medical")):
            return True
        return False

    def _contains_market_structure_terms(self, haystack: str) -> bool:
        return any(
            keyword in haystack
            for keyword in (
                "guidance", "earnings", "forecast", "demand", "supply", "investment",
                "production", "shipment", "approval", "trial", "tariff", "policy",
            )
        )

    def _is_allowed_source(self, article: NewsItem, sector: str) -> bool:
        allowed = SECTOR_ALLOWED_SOURCES.get(sector)
        if not allowed:
            return True
        source = (article.source or "").lower()
        domain = urlparse((article.url or "").lower()).netloc
        return any(name in source or name in domain for name in allowed)

    def _keyword_present(self, haystack: str, keyword: str) -> bool:
        normalized = keyword.lower().strip()
        if " " in normalized:
            return normalized in haystack
        if len(normalized) <= 3:
            return bool(re.search(rf"(?<![a-z]){re.escape(normalized)}(?![a-z])", haystack))
        return normalized in haystack

    def _build_bio_sector_data(self, target_date: date) -> dict[str, str]:
        clinical = self.client.combined_news("clinical trial biotech", target_date=target_date, page_size=3)
        fda = self.client.combined_news("FDA biotech drug approval", target_date=target_date, page_size=3)
        licensing = self.client.combined_news("biotech licensing deal", target_date=target_date, page_size=3)
        dnd = self.client.combined_news("\"D&D Pharmatech\" OR \"디앤디파마텍\"", target_date=target_date, page_size=3)
        return {
            "leaders": "삼성바이오로직스, 셀트리온, 유한양행, 디앤디파마텍",
            "clinical_news": self._localize_bio_extra("임상", clinical[0].title) if clinical else DATA_MISSING,
            "fda_news": self._localize_bio_extra("FDA", fda[0].title) if fda else DATA_MISSING,
            "licensing_news": self._localize_bio_extra("기술수출", licensing[0].title) if licensing else DATA_MISSING,
            "rate_impact": "금리 데이터와 바이오 뉴스의 방향이 동시에 확인될 때만 비중 확대." if fda or clinical or licensing else ANALYSIS_PENDING,
            "dnd_comment": self._localize_bio_extra("디앤디파마텍", dnd[0].title) if dnd else DATA_MISSING,
        }

    def _localize_bio_extra(self, category: str, title: str) -> str:
        if title == DATA_MISSING:
            return DATA_MISSING
        if _contains_korean(title):
            return title
        if category == "임상":
            return "해외 바이오 임상 관련 기사 확인"
        if category == "FDA":
            return "해외 FDA 승인 또는 허가 관련 기사 확인"
        if category == "기술수출":
            return "해외 기술수출 또는 제휴 관련 기사 확인"
        if category == "디앤디파마텍":
            return "디앤디파마텍 직접 언급 해외 기사 미수집, 동종 바이오 모멘텀만 참고"
        return "해외 바이오 기사 확인"

    def _build_sector_schedule(self, sector: str, target_date: date) -> dict[str, str]:
        companies = SECTOR_DART_COMPANIES.get(sector, [])
        if not companies:
            return {
                "summary": DATA_MISSING,
                "detail": f"{DATA_MISSING} (섹터 일정 매핑 미구성)",
                "view": "섹터 일정 해석 보류",
            }
        lookback_days = int(self.api_config["dart_disclosure_lookback_days"])
        matched: list[tuple[str, DisclosureItem]] = []
        for company in companies:
            items = self.client.dart_disclosures(company, target_date, lookback_days=lookback_days)
            if not items:
                continue
            for item in items[:3]:
                if self._is_schedule_disclosure(item.report_name):
                    matched.append((company, item))
            if len(matched) >= 3:
                break
        if not matched:
            return {
                "summary": DATA_MISSING,
                "detail": f"{DATA_MISSING} (최근 {lookback_days}일 내 실적발표/IR/정기공시 일정성 공시 미수집)",
                "view": "섹터 대표 종목의 일정성 공시가 부족해 이벤트 드리븐 해석 보류",
            }
        matched.sort(key=lambda pair: pair[1].filed_at, reverse=True)
        top = matched[:3]
        summary = " | ".join(f"{company}: {item.report_name} ({item.filed_at})" for company, item in top)
        detail = " / ".join(f"{company} -> {item.report_name} ({item.filed_at})" for company, item in top)
        view = self._sector_schedule_view(top)
        return {
            "summary": summary,
            "detail": detail,
            "view": view,
        }

    def _is_schedule_disclosure(self, report_name: str) -> bool:
        keywords = (
            "기업설명회", "ir", "실적", "잠정실적", "분기보고서", "반기보고서", "사업보고서",
            "주주총회", "소집공고", "소집결의", "결산", "매출액또는손익구조", "영업(잠정)",
        )
        lowered = report_name.lower()
        return any(keyword in report_name or keyword in lowered for keyword in keywords)

    def _sector_schedule_view(self, items: list[tuple[str, DisclosureItem]]) -> str:
        names = [item.report_name for _, item in items]
        if any("기업설명회" in name or "ir" in name.lower() for name in names):
            return "IR/실적 커뮤니케이션 이벤트가 있어 단기 변동성 확대 가능성 점검 필요"
        if any("분기보고서" in name or "반기보고서" in name or "사업보고서" in name for name in names):
            return "정기공시 구간으로 숫자 확인 전 선반영 추격보다 공시 내용 확인이 우선"
        if any("잠정" in name or "실적" in name or "매출액" in name for name in names):
            return "실적 이벤트 성격이 강해 뉴스보다 숫자 확인 이후 대응이 유리"
        return "섹터 일정은 확인되지만 구체 수치 전까지 이벤트 해석은 보수적으로 접근"

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
        stock_frame = self._individual_stock_frame(common, sectors, disclosures)
        if session == "morning":
            evidence_score = self._evidence_score(common, hyundai, sectors, disclosures)
            no_trade = self._no_trade_condition(common, hyundai)
            top_news = self._top_news_summary(sectors)
            market_score = self._market_score(common)
            stance = self._stance_from_score(market_score)
            return {
                "market_score": str(market_score) if market_score is not None else DATA_MISSING,
                "stance": stance,
                "stance_reason": self._stance_reason(common, stance),
                "top_news_3": top_news,
                "overseas_major_news": self._overseas_major_news(sectors),
                "overseas_major_news_view": self._overseas_major_news_view(sectors),
                "industry_major_issues": self._industry_major_issues(sectors),
                "industry_major_issues_view": self._industry_major_issues_view(sectors),
                "capital_flow_now": self._capital_flow_now(common, sectors),
                "us_sector_focus": self._us_sector_focus(sectors),
                "expected_sector_today": self._expected_sector_today(common, sectors),
                "expected_sector_reason": self._expected_sector_reason(common, sectors),
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
                "recent_disclosures": self._sector_stock_recent_disclosures(stock_frame, disclosures),
                "disclosure_summary": self._sector_stock_disclosure_summary(stock_frame, disclosures),
                "evidence_score": evidence_score,
                "evidence_comment": self._evidence_comment(evidence_score),
                "no_trade_condition": no_trade,
                "position_size_rule": self._position_size_rule(evidence_score, stance),
                "entry_trigger": self._entry_trigger(common, hyundai),
                "invalidation": self._invalidation_rule(common, hyundai),
                "opposite_signal": self._opposite_signal(common, hyundai, sectors),
                **stock_frame,
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
                "recent_disclosures": self._sector_stock_recent_disclosures(stock_frame, disclosures),
                "disclosure_summary": self._sector_stock_disclosure_summary(stock_frame, disclosures),
                **stock_frame,
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
            "recent_disclosures": self._sector_stock_recent_disclosures(stock_frame, disclosures),
            "disclosure_summary": self._sector_stock_disclosure_summary(stock_frame, disclosures),
            **stock_frame,
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
            "market_day_summary": self._closing_market_day_summary(common, hyundai),
            "market_move_reason": self._closing_market_move_reason(common, sectors, hyundai),
            "market_problem": self._closing_market_problem(common, sectors, hyundai),
            "market_sentiment_view": self._closing_market_sentiment_view(common, hyundai, sectors),
            "hyundai_day_view": self._closing_hyundai_day_view(hyundai),
            "tomorrow_outlook": self._closing_horizon_outlook("tomorrow", common, hyundai, sectors),
            "next_week_outlook": self._closing_horizon_outlook("next_week", common, hyundai, sectors),
            "one_month_outlook": self._closing_horizon_outlook("one_month", common, hyundai, sectors),
            "six_month_outlook": self._closing_horizon_outlook("six_month", common, hyundai, sectors),
            "bull_case": self._closing_bull_case(common, hyundai, sectors),
            "bear_case": self._closing_bear_case(common, hyundai, sectors),
            "invalidation_case": self._closing_invalidation_case(common, hyundai, sectors),
            "must_watch": self._closing_must_watch(common, hyundai, sectors),
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
        if self.client.marketaux_rate_limited:
            marketaux_ok = "한도 초과(우회 중)"
        else:
            marketaux_ok = "연결됨" if self.client.marketaux_key else "미연결"
        if self.client.massive_rate_limited:
            massive_ok = "한도 초과"
        else:
            massive_ok = "연결됨" if self.client.massive_key else "미연결"
        dart_ok = "연결됨" if disclosures.get("recent") != DATA_MISSING else "미연결"
        alpha_ok = "부분 연결" if hyundai.get("current_close") != DATA_MISSING else "미연결"
        krx_ok = "연결됨" if common["korea_market"]["kospi"] != DATA_MISSING else ("권한 오류" if self.client.krx_key and self.client.krx_last_error else "미연결")
        kis_key_name = self.api_config["kis"]["enabled_env"]
        kis_secret_name = self.api_config["kis"]["app_secret_env"]
        kis_ok = "준비됨" if os.getenv(kis_key_name) and os.getenv(kis_secret_name) else "미연결"
        if hyundai.get("current_close") != DATA_MISSING and hyundai.get("volume") != DATA_MISSING:
            hyundai_reason = "KRX 일별매매정보로 현대차 종가·고가·저가·거래량은 연결됨. 투자자 수급·공매도는 추가 API 필요"
        elif self.client.krx_key and self.client.krx_last_error:
            hyundai_reason = f"KRX_API_KEY는 설정됐지만 현대차 개별종목 API 응답이 불완전함. KRX 최근 오류: {self.client.krx_last_error}"
        elif alpha_ok != "미연결":
            hyundai_reason = "Alpha Vantage 심볼 데이터가 OTC 기준이라 이동평균/52주 범위가 불완전할 수 있음"
        else:
            hyundai_reason = "현대차 가격 데이터 미수집"
        return {
            "fred_status": fred_ok,
            "news_status": news_ok,
            "marketaux_status": marketaux_ok,
            "massive_status": massive_ok,
            "alpha_status": alpha_ok,
            "dart_status": dart_ok,
            "krx_status": krx_ok,
            "kis_status": kis_ok,
            "krx_reason": common["missing_reasons"]["korea_index"],
            "kis_reason": f"{kis_key_name} 또는 {kis_secret_name} 환경변수 미설정으로 한국장 지수/수급 미수집" if kis_ok == "미연결" else "KIS 키는 준비됨. 엔드포인트 경로와 응답 파싱 로직 연결 필요",
            "hyundai_reason": hyundai_reason,
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

    def _macro_structure_text(self, fred: dict[str, Any]) -> str:
        if fred["us10y"]["value"] is None or fred["fed_funds"]["value"] is None:
            return ANALYSIS_PENDING
        if fred["us10y"]["delta"] is not None and fred["us10y"]["delta"] > 0:
            return "금리 상방 압력이 살아 있어 성장주 멀티플 확장보다 선별 대응이 유리하다."
        return "금리 부담이 완화되는 구간이면 대형 성장주와 수출주를 함께 점검할 수 있다."

    def _market_driver_text(self, fred: dict[str, Any]) -> str:
        drivers = []
        if fred["us10y"]["delta"] is not None:
            if fred["us10y"]["delta"] > 0:
                drivers.append("미국 10년물 상승으로 성장주 할인율 부담 확대")
            else:
                drivers.append("미국 10년물 안정/하락으로 밸류에이션 부담 완화")
        if fred["cpi"]["value"] is not None and fred["ppi"]["value"] is not None:
            drivers.append("물가 둔화 재확인 전까지 인플레이션 경계 유지")
        if fred["unemployment"]["value"] is not None:
            drivers.append("고용지표는 경기 둔화와 연착륙 해석이 엇갈릴 수 있어 방향성 확인 필요")
        if fred["fed_funds"]["value"] is not None:
            drivers.append("정책금리 고점 유지 여부가 위험자산 선호 회복의 핵심 변수")
        if not drivers:
            return ANALYSIS_PENDING
        return " | ".join(drivers[:3])

    def _market_sentiment_text(self, fred: dict[str, Any]) -> str:
        score = self._market_score({"fred": fred})
        stance = self._stance_from_score(score)
        if stance == DATA_MISSING:
            return ANALYSIS_PENDING
        return f"매크로 점수 기준 오늘 기본 태도는 {stance}."

    def _stance_reason(self, common: dict[str, Any], stance: str) -> str:
        if stance == DATA_MISSING:
            return ANALYSIS_PENDING
        fred = common.get("fred", {})
        reasons: list[str] = []
        us10y_delta = fred.get("us10y", {}).get("delta")
        if us10y_delta is not None:
            if us10y_delta > 0:
                reasons.append("미국 10년물이 올라 성장주 밸류에이션 부담이 남아 있다")
            else:
                reasons.append("미국 10년물이 안정돼 금리 부담은 다소 완화됐다")
        if fred.get("cpi", {}).get("value") is not None and fred.get("ppi", {}).get("value") is not None:
            reasons.append("물가 둔화가 재확인되기 전까지는 공격적으로 확신하기 어렵다")
        if fred.get("fed_funds", {}).get("value") is not None:
            reasons.append("정책금리 고점 유지 여부가 아직 위험자산 방향을 완전히 열어주지 못하고 있다")
        if not reasons:
            return ANALYSIS_PENDING
        if stance == "중립":
            return "중립인 이유: " + " | ".join(reasons[:3])
        if stance == "공격":
            return "공격인 이유: " + " | ".join(reasons[:3])
        return "방어인 이유: " + " | ".join(reasons[:3])

    def _rate_analysis(self, us10y: dict[str, Any]) -> str:
        delta = us10y["delta"]
        if delta is None:
            return ANALYSIS_PENDING
        return "전일 대비 상승이면 성장주 할인율 부담, 하락이면 반등 여지 점검."

    def _fx_gold_analysis(self, usdkrw: dict[str, Any], gold: dict[str, Any]) -> str:
        usdkrw_delta = usdkrw.get("delta")
        gold_delta = gold.get("delta")
        notes: list[str] = []
        if usdkrw_delta is not None:
            if usdkrw_delta > 0:
                notes.append("원/달러 환율 상승은 외국인 수급과 수입물가 부담 측면에서 한국 증시에 부담")
            elif usdkrw_delta < 0:
                notes.append("원/달러 환율 하락은 외국인 위험선호 회복에 우호적")
        if gold_delta is not None:
            if gold_delta > 0:
                notes.append("금 가격 상승은 안전자산 선호 강화 신호로 해석 가능")
            elif gold_delta < 0:
                notes.append("금 가격 하락은 위험자산 선호 회복 여부를 함께 점검할 구간")
        if not notes:
            return ANALYSIS_PENDING
        return " | ".join(notes)

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
        usdkrw = fred.get("usdkrw", {})
        if usdkrw.get("text") != DATA_MISSING:
            issues.append(f"원/달러 환율: {usdkrw.get('text', DATA_MISSING)}")
        gold = common.get("fx_commodities", {}).get("gold", DATA_MISSING)
        if gold != DATA_MISSING:
            issues.append(f"금 시세: {gold}")
        if disclosures.get("recent") != DATA_MISSING:
            issues.append(f"최근 공시: {disclosures['recent']}")
        if issues:
            return " | ".join(issues[:5])
        return "세계 주요 이슈는 데이터 미수집 (FRED/DART 또는 해외 매크로 뉴스 데이터 부족)"

    def _global_major_issues_view(self, common: dict[str, Any], disclosures: dict[str, Any]) -> str:
        fred = common.get("fred", {})
        notes: list[str] = []
        us10y_delta = fred.get("us10y", {}).get("delta")
        if us10y_delta is not None:
            if us10y_delta > 0:
                notes.append("미국 10년물 상승은 한국 성장주와 고밸류 종목에 할인율 부담으로 연결될 수 있다")
            else:
                notes.append("미국 10년물 안정/하락은 한국 대형 성장주와 반도체에 심리 완충재가 될 수 있다")
        usdkrw_delta = fred.get("usdkrw", {}).get("delta")
        if usdkrw_delta is not None:
            if usdkrw_delta > 0:
                notes.append("원/달러 상승은 외국인 현물 수급과 수입물가 부담 측면에서 한국장에 불리하다")
            else:
                notes.append("원/달러 하락은 외국인 위험선호 회복에 우호적이다")
        gold_delta = common.get("fx_commodities", {}).get("gold_snapshot", {}).get("delta")
        if gold_delta is not None:
            if gold_delta > 0:
                notes.append("금 가격 상승은 안전자산 선호가 남아 있다는 뜻이라 공격적 추격을 경계해야 한다")
            else:
                notes.append("금 가격 하락은 위험선호 회복 가능성을 같이 점검할 수 있다")
        if disclosures.get("recent") != DATA_MISSING:
            notes.append("최근 공시는 개별주 이벤트 리스크를 키울 수 있어 지수 판단과 별도로 봐야 한다")
        if notes:
            return " | ".join(notes[:3])
        return ANALYSIS_PENDING

    def _overseas_major_news(self, sectors: dict[str, dict[str, str]]) -> str:
        items: list[tuple[str, str]] = []
        for sector, data in sectors.items():
            headline = data.get("headline_original", DATA_MISSING)
            source = data.get("source", DATA_MISSING)
            published = data.get("published_at", DATA_MISSING)
            if headline == DATA_MISSING:
                continue
            items.append((published, f"{sector}: {headline} | {source} | {published}"))
        if not items:
            return "해외 주요 뉴스는 데이터 미수집 (섹터 뉴스 API 응답 부족 또는 관련 기사 필터링 실패)"
        items.sort(key=lambda item: item[0], reverse=True)
        return " || ".join(item[1] for item in items[:3])

    def _overseas_major_news_view(self, sectors: dict[str, dict[str, str]]) -> str:
        notes: list[str] = []
        for sector in ("반도체", "AI", "자동차/현대차", "바이오/헬스케어", "로봇", "ETF: SCHD, QQQM, SPYG"):
            data = sectors.get(sector, {})
            headline = data.get("headline_original", DATA_MISSING)
            description = data.get("headline_description", DATA_MISSING)
            if headline == DATA_MISSING:
                continue
            if description != DATA_MISSING:
                notes.append(f"{sector}: {description}")
            else:
                notes.append(f"{sector}: {headline}")
            if len(notes) == 3:
                break
        if notes:
            return " | ".join(notes)
        return ANALYSIS_PENDING

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

    def _industry_major_issues_view(self, sectors: dict[str, dict[str, str]]) -> str:
        notes: list[str] = []
        priority = ("반도체", "AI", "자동차/현대차", "바이오/헬스케어", "로봇")
        for sector in priority:
            data = sectors.get(sector, {})
            headline = data.get("headline", DATA_MISSING)
            description = data.get("headline_description", DATA_MISSING)
            if headline == DATA_MISSING:
                continue
            if description != DATA_MISSING:
                notes.append(f"{sector}: {description}")
            else:
                notes.append(f"{sector}: headline은 확인됐지만 국내 가격 반응은 별도 확인 필요")
            if len(notes) == 3:
                break
        if notes:
            return " | ".join(notes)
        return ANALYSIS_PENDING

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

    def _expected_sector_reason(self, common: dict[str, Any], sectors: dict[str, dict[str, str]]) -> str:
        market_score = self._market_score(common)
        reasons: list[str] = []
        if sectors.get("반도체", {}).get("headline") != DATA_MISSING:
            reasons.append("반도체는 관련 해외 뉴스가 있고 금리 안정 시 가장 먼저 반응하기 쉬운 축이다")
        if sectors.get("AI", {}).get("headline") != DATA_MISSING and market_score is not None and market_score >= 3:
            reasons.append("AI는 뉴스 흐름이 유지되고 매크로 점수가 중립 이상이라 심리 반등 후보가 된다")
        if sectors.get("자동차/현대차", {}).get("headline") != DATA_MISSING:
            reasons.append("자동차는 개별 이슈가 있더라도 환율과 업종 수급 변화가 붙을 때 후보가 된다")
        if sectors.get("바이오/헬스케어", {}).get("headline") != DATA_MISSING and market_score is not None and market_score <= 3:
            reasons.append("바이오는 시장이 공격 일변도가 아닐 때 개별 이벤트 중심으로 선별 대응하기 좋다")
        if reasons:
            return " | ".join(reasons[:3])
        return ANALYSIS_PENDING

    def _market_tradeability(self, stance: str, evidence_score: str) -> str:
        if stance == DATA_MISSING or evidence_score == DATA_MISSING:
            return "오늘 매매 가능 여부는 데이터 미수집 (매크로·가격 근거 부족)"
        score = int(evidence_score.split("/")[0])
        if stance == "공격" and score >= 4:
            return "매매 가능한 날이다. 다만 시초가 추격 대신 확인 후 분할 진입이 전제다."
        if stance == "중립" and score >= 2:
            return "선별적으로 매매 가능한 날이다. 섹터와 종목의 동시 확인이 필요하다."
        return "보수적으로 접근해야 하는 날이다. 신규 진입보다 관망 또는 축소가 우선이다."

    def _extract_rate_from_market_text(self, text: str) -> float | None:
        if text == DATA_MISSING:
            return None
        match = re.search(r"등락률 ([+-]?\d+(?:\.\d+)?)%", text)
        if not match:
            return None
        return _safe_float(match.group(1))

    def _leading_sectors_text(self, sectors: dict[str, dict[str, str]]) -> str:
        items: list[str] = []
        for sector in ("반도체", "AI", "자동차/현대차", "바이오/헬스케어", "로봇"):
            if sectors.get(sector, {}).get("headline") != DATA_MISSING:
                items.append(sector)
        return ", ".join(items[:3]) if items else DATA_MISSING

    def _hyundai_day_return(self, hyundai: dict[str, str]) -> float | None:
        current = _safe_float(str(hyundai.get("current_close", DATA_MISSING)).replace(",", ""))
        prev_close = _safe_float(str(hyundai.get("previous_close", DATA_MISSING)).replace(",", ""))
        if current is None or prev_close in (None, 0):
            return None
        return ((current - prev_close) / prev_close) * 100

    def _closing_market_day_summary(self, common: dict[str, Any], hyundai: dict[str, str]) -> str:
        kospi = common.get("korea_market", {}).get("kospi", DATA_MISSING)
        kosdaq = common.get("korea_market", {}).get("kosdaq", DATA_MISSING)
        hyundai_return = self._hyundai_day_return(hyundai)
        hyundai_text = _fmt_pct(hyundai_return) if hyundai_return is not None else DATA_MISSING
        if kospi == DATA_MISSING and kosdaq == DATA_MISSING:
            return ANALYSIS_PENDING
        return f"KOSPI {kospi} | KOSDAQ {kosdaq} | 현대차 등락률 {hyundai_text}"

    def _closing_market_move_reason(self, common: dict[str, Any], sectors: dict[str, dict[str, str]], hyundai: dict[str, str]) -> str:
        kospi_rate = self._extract_rate_from_market_text(common.get("korea_market", {}).get("kospi", DATA_MISSING))
        leaders = self._leading_sectors_text(sectors)
        hyundai_return = self._hyundai_day_return(hyundai)
        notes: list[str] = []
        if kospi_rate is not None:
            if kospi_rate > 0:
                notes.append("지수 상승의 직접 배경은 위험선호 회복과 대형주 반등 시도다")
            elif kospi_rate < 0:
                notes.append("지수 하락의 직접 배경은 위험회피 확대와 대형주 차익실현이다")
        if leaders != DATA_MISSING:
            notes.append(f"오늘 주도 흐름은 {leaders} 쪽에서 형성됐다")
        if hyundai_return is not None:
            if hyundai_return < 0:
                notes.append("현대차가 지수보다 약하면 자동차는 시장 주도보다 후행 또는 소외로 해석해야 한다")
            elif hyundai_return > 0:
                notes.append("현대차가 동반 강세면 자동차도 지수 확산에 기여했을 가능성이 있다")
        return " | ".join(notes) if notes else ANALYSIS_PENDING

    def _closing_market_problem(self, common: dict[str, Any], sectors: dict[str, dict[str, str]], hyundai: dict[str, str]) -> str:
        problems: list[str] = []
        if common.get("flow", {}).get("foreign") == DATA_MISSING:
            problems.append("외국인·기관 실시간 수급이 비어 있어 상승/하락의 질을 정량 확인하기 어렵다")
        if self._leading_sectors_text(sectors) != DATA_MISSING:
            problems.append("시장이 소수 주도 섹터에 집중되면 지수와 체감 수익률이 쉽게 분리된다")
        hyundai_return = self._hyundai_day_return(hyundai)
        if hyundai_return is not None and hyundai_return < 0:
            problems.append("현대차 약세는 경기민감주 확산이 아직 부족하다는 신호일 수 있다")
        usdkrw_delta = common.get("fred", {}).get("usdkrw", {}).get("delta")
        if usdkrw_delta is not None and usdkrw_delta > 0:
            problems.append("원/달러 상승은 외국인 수급과 수입물가 측면에서 한국장 리스크를 남긴다")
        return " | ".join(problems) if problems else ANALYSIS_PENDING

    def _closing_market_sentiment_view(self, common: dict[str, Any], hyundai: dict[str, str], sectors: dict[str, dict[str, str]]) -> str:
        stance = self._stance_from_score(self._market_score(common))
        if stance == DATA_MISSING:
            return ANALYSIS_PENDING
        leader_text = self._leading_sectors_text(sectors)
        hyundai_return = self._hyundai_day_return(hyundai)
        if stance == "중립":
            if hyundai_return is not None and hyundai_return < 0:
                return f"심리는 중립이지만 확산형 강세가 아니라 선택형 반등에 가깝다. 주도 섹터는 {leader_text}이고 자동차는 아직 확인이 더 필요하다."
            return f"심리는 중립이며 주도 섹터는 {leader_text}다. 내일은 지수보다 업종 확산 여부가 더 중요하다."
        if stance == "공격":
            return f"심리는 공격 우위지만 최근 변동성이 커서 {leader_text} 추격보다 눌림 확인이 우선이다."
        return f"심리는 방어 우위다. {leader_text}가 살아 있어도 개별 종목 추격은 제한해야 한다."

    def _closing_hyundai_day_view(self, hyundai: dict[str, str]) -> str:
        day_return = self._hyundai_day_return(hyundai)
        current = hyundai.get("current_close", DATA_MISSING)
        high_low = hyundai.get("intraday_high_low", DATA_MISSING)
        if day_return is None:
            return ANALYSIS_PENDING
        if day_return < 0:
            return f"현대차는 종가 {current}, 장중 범위 {high_low} 기준 약세 마감이다. 지수와 비동행이면 자동차 업종 수급 복원이 아직 부족하다는 뜻으로 읽는다."
        return f"현대차는 종가 {current}, 장중 범위 {high_low} 기준 반등 마감이다. 다만 업종 동행과 다음날 지속성이 확인돼야 추세 전환 해석이 가능하다."

    def _closing_horizon_outlook(self, horizon: str, common: dict[str, Any], hyundai: dict[str, str], sectors: dict[str, dict[str, str]]) -> str:
        stance = self._stance_from_score(self._market_score(common))
        leaders = self._leading_sectors_text(sectors)
        hyundai_return = self._hyundai_day_return(hyundai)
        usdkrw_delta = common.get("fred", {}).get("usdkrw", {}).get("delta")
        if horizon == "tomorrow":
            return f"내일은 {leaders} 지속 여부와 현대차 후행 동참 여부를 함께 봐야 한다. 기본 태도는 {stance}이며, 원/달러가 {'상승 중이라 부담이 남아 있다' if usdkrw_delta is not None and usdkrw_delta > 0 else '안정이면 대형주 심리 완충이 가능하다'}."
        if horizon == "next_week":
            return f"다음주는 최근 급등락이 기술적 반등인지 추세 복원인지 판별하는 구간이다. {leaders}가 계속 주도하면 지수는 버틸 수 있지만, 자동차와 다른 경기민감주 확산이 없으면 체감 강도는 약할 수 있다."
        if horizon == "one_month":
            if hyundai_return is not None and hyundai_return < 0:
                return "1개월 시계열은 반도체/AI 주도와 자동차 소외가 계속 분리될 가능성을 열어둬야 한다. 현대차는 실적·환율·수요 확인 전까지 지수 대비 후행할 수 있다."
            return "1개월 시계열은 변동성은 크더라도 실적 시즌과 환율 흐름이 뒷받침되면 대형주 중심 복원 가능성을 본다."
        return "6개월 시계열은 결국 실적과 금리 방향이 결정한다. 단기 뉴스보다 AI 투자 지속성, 한국 수출 경기, 현대차 실적 회복 여부가 중기 방향성을 좌우할 가능성이 높다."

    def _closing_bull_case(self, common: dict[str, Any], hyundai: dict[str, str], sectors: dict[str, dict[str, str]]) -> str:
        leaders = self._leading_sectors_text(sectors)
        return f"{leaders} 주도력이 유지되고 원/달러 부담이 완화되며 현대차가 업종 동행 강세로 돌아오면 단기 반등이 추세 복원으로 진화할 수 있다."

    def _closing_bear_case(self, common: dict[str, Any], hyundai: dict[str, str], sectors: dict[str, dict[str, str]]) -> str:
        return "반도체 급등분이 되돌려지고 원/달러가 다시 상승하며 현대차까지 저점 재이탈하면 최근 반등은 단순 숏커버에 그쳤다고 봐야 한다."

    def _closing_invalidation_case(self, common: dict[str, Any], hyundai: dict[str, str], sectors: dict[str, dict[str, str]]) -> str:
        return "지수는 강한데 현대차·자동차가 계속 비동행하거나, 주도 섹터가 하루 만에 급반전하면 낙관 시나리오를 즉시 낮춰야 한다."

    def _closing_must_watch(self, common: dict[str, Any], hyundai: dict[str, str], sectors: dict[str, dict[str, str]]) -> str:
        points = [
            "원/달러 추가 방향",
            "반도체 주도력 지속 여부",
            "현대차와 기아 동행 여부",
        ]
        return " | ".join(points)

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
            payload[f"{prefix}_chart"] = slot["chart"] if slot else "자동 선별 후보 없음"
            payload[f"{prefix}_shakeout"] = slot["shakeout"] if slot else "자동 선별 후보 없음"
            payload[f"{prefix}_down_reason"] = slot["down_reason"] if slot else "자동 선별 후보 없음"
            payload[f"{prefix}_up_reason"] = slot["up_reason"] if slot else "자동 선별 후보 없음"
            payload[f"{prefix}_forecast"] = slot["forecast"] if slot else "자동 선별 후보 없음"
            payload[f"{prefix}_target_price"] = slot["target_price"] if slot else DATA_MISSING
            payload[f"{prefix}_target_price_view"] = slot["target_price_view"] if slot else "자동 선별 후보 없음"
            payload[f"{prefix}_target_price_basis"] = slot["target_price_basis"] if slot else "자동 선별 후보 없음"
        return payload

    def _sector_stock_recent_disclosures(self, stock_frame: dict[str, str], disclosures: dict[str, Any]) -> str:
        items_by_company = disclosures.get("items_by_company", {})
        parts: list[str] = []
        for index in range(1, 4):
            name = stock_frame.get(f"stock_{index}_name", DATA_MISSING)
            if name == DATA_MISSING:
                continue
            items = items_by_company.get(name, [])
            if items:
                latest = items[0]
                parts.append(f"{name}: {latest.report_name} ({latest.filed_at})")
            else:
                parts.append(f"{name}: {DATA_MISSING}")
        return " | ".join(parts) if parts else DATA_MISSING

    def _sector_stock_disclosure_summary(self, stock_frame: dict[str, str], disclosures: dict[str, Any]) -> str:
        items_by_company = disclosures.get("items_by_company", {})
        parts: list[str] = []
        for index in range(1, 4):
            name = stock_frame.get(f"stock_{index}_name", DATA_MISSING)
            if name == DATA_MISSING:
                continue
            items = items_by_company.get(name, [])
            if items:
                latest = items[0]
                parts.append(f"{name} 공시 확인: {latest.report_name}")
            else:
                parts.append(f"{name} 공시 확인: {DATA_MISSING}")
        return " | ".join(parts) if parts else DATA_MISSING

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
        target_snapshot = self._stock_target_snapshot(name)
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
            "chart": self._generic_stock_chart_view(name, sector, headline, disclosure),
            "shakeout": self._generic_stock_shakeout_view(name, headline, disclosure),
            "down_reason": self._generic_stock_down_reason(name, sector, headline, disclosure),
            "up_reason": self._generic_stock_up_reason(name, sector, headline, disclosure),
            "forecast": self._generic_stock_forecast(name, sector, headline, disclosure),
            "target_price": target_snapshot["target_price"],
            "target_price_view": target_snapshot["target_price_view"],
            "target_price_basis": target_snapshot["target_price_basis"],
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

    def _generic_stock_chart_view(self, name: str, sector: str, headline: str, disclosure: str) -> str:
        if headline != DATA_MISSING and disclosure != DATA_MISSING:
            return f"{name} 차트 데이터는 미수집이지만, 현재는 {sector} 뉴스와 공시가 동시에 있는 이벤트 구간이라 캔들 모양보다 거래대금 확대 여부 확인이 우선."
        if headline != DATA_MISSING:
            return f"{name} 차트 데이터는 미수집. 현재는 {sector} 뉴스 모멘텀이 선행하고 있어 눌림 후 재확산인지 확인이 필요."
        if disclosure != DATA_MISSING:
            return f"{name} 차트 데이터는 미수집. 최근 공시가 가격 변동의 직접 계기일 수 있어 공시 해석 후 대응이 우선."
        return f"{name} 차트 구조는 데이터 미수집 (개별 가격·거래량 API 미연동)"

    def _generic_stock_shakeout_view(self, name: str, headline: str, disclosure: str) -> str:
        if headline != DATA_MISSING or disclosure != DATA_MISSING:
            return f"{name} 개미 털기 여부는 데이터 미수집. 분봉·호가 없이 단정하지 말고, 장중 급락 후 거래대금이 유지되는지만 확인 필요."
        return f"{name} 개미 털기 판단은 데이터 미수집 (분봉/체결강도 미연동)"

    def _generic_stock_down_reason(self, name: str, sector: str, headline: str, disclosure: str) -> str:
        if disclosure != DATA_MISSING:
            return f"{name} 하락 시 해석 우선순위는 공시 실망, 공시 오해, 차익실현 가능성 순이다."
        if headline != DATA_MISSING:
            return f"{name} 하락 시 해석 우선순위는 {sector} 뉴스 약화, 후속 기사 부재, 테마 과열 해소 가능성 순이다."
        return f"{name} 하락 이유 분석은 데이터 미수집 (개별 시세와 뉴스 근거 부족)"

    def _generic_stock_up_reason(self, name: str, sector: str, headline: str, disclosure: str) -> str:
        if disclosure != DATA_MISSING:
            return f"{name} 상승 시 해석 우선순위는 공시 재평가, IR 기대, 섹터 동반 강세 여부다."
        if headline != DATA_MISSING:
            return f"{name} 상승 시 해석 우선순위는 {sector} 뉴스 확산, 관련주 순환매, 거래대금 집중 여부다."
        return f"{name} 상승 이유 분석은 데이터 미수집 (개별 시세와 뉴스 근거 부족)"

    def _generic_stock_forecast(self, name: str, sector: str, headline: str, disclosure: str) -> str:
        if headline != DATA_MISSING and disclosure != DATA_MISSING:
            return f"{name} 예측: 뉴스와 공시가 같은 방향이면 하루 더 연장 시도 가능, 엇갈리면 변동성만 남고 추세는 약해질 수 있다."
        if headline != DATA_MISSING:
            return f"{name} 예측: {sector} 뉴스 후속 보도가 이어지면 단기 재시도 가능, 후속 부재면 하루 이틀 내 힘이 빠질 수 있다."
        if disclosure != DATA_MISSING:
            return f"{name} 예측: 공시 해석이 우호적이면 재료 소화 후 재반등 가능, 숫자 확인 전까지는 장중 흔들림이 클 수 있다."
        return f"{name} 예측은 데이터 미수집 (차트·수급·뉴스 근거 부족)"

    def _combine_values(self, high: float | None, low: float | None) -> str:
        if high is None or low is None:
            return DATA_MISSING
        return f"{_fmt_number(high)} / {_fmt_number(low)}"

    def _krx_row_value(self, row: dict[str, Any], *keys: str) -> Any:
        lowered = {str(key).lower(): value for key, value in row.items()}
        for key in keys:
            if key in row:
                return row[key]
            if key.lower() in lowered:
                return lowered[key.lower()]
        return None

    def _krx_previous_close_text(self, row: dict[str, Any]) -> str:
        previous_close = self._krx_row_value(row, "PREV_CLSPRC", "TDD_OPNPRC", "OPNPRC")
        if previous_close not in (None, ""):
            return self._fmt_krx_number(previous_close)
        close_value = _safe_float(str(self._krx_row_value(row, "TDD_CLSPRC", "CLSPRC", "CLSPRC_IDX") or "").replace(",", ""))
        diff_value = _safe_float(str(self._krx_row_value(row, "CMPPREVDD_PRC", "CMPPREVDD_IDX", "CMPPREVDD") or "").replace(",", ""))
        if close_value is None or diff_value is None:
            return DATA_MISSING
        return _fmt_number(close_value - diff_value)

    def _select_krx_index_row(self, rows: list[dict[str, Any]], market: str) -> dict[str, Any] | None:
        for row in rows:
            idx_name = str(row.get("IDX_NM", "")).strip().lower()
            if market == "kospi" and idx_name in {"코스피", "kospi"}:
                return row
            if market == "kosdaq" and idx_name in {"코스닥", "kosdaq"}:
                return row
        for row in rows:
            idx_class = str(row.get("IDX_CLSS", "")).strip().lower()
            if market == "kospi" and idx_class == "kospi":
                return row
            if market == "kosdaq" and idx_class == "kosdaq":
                return row
        return rows[0] if rows else None

    def _select_krx_stock_row(self, rows: list[dict[str, Any]], stock_code: str, stock_name: str) -> dict[str, Any] | None:
        for row in rows:
            if str(row.get("ISU_CD", "")).strip() == stock_code:
                return row
        for row in rows:
            if str(row.get("ISU_NM", "")).strip() == stock_name:
                return row
        return None

    def _format_krx_index_row(self, row: dict[str, Any]) -> str:
        close_value = self._fmt_krx_number(self._krx_row_value(row, "CLSPRC_IDX", "TDD_CLSPRC"))
        diff_value = self._fmt_signed_krx_value(self._krx_row_value(row, "CMPPREVDD_IDX", "CMPPREVDD_PRC"))
        rate_value = self._fmt_percent_krx_value(self._krx_row_value(row, "FLUC_RT"))
        high_low = self._fmt_krx_high_low(
            self._krx_row_value(row, "HGPRC_IDX", "TDD_HGPRC"),
            self._krx_row_value(row, "LWPRC_IDX", "TDD_LWPRC"),
        )
        trade_value = self._fmt_krx_int(self._krx_row_value(row, "ACC_TRDVAL", "TDD_TRDVAL"))
        pieces = [close_value]
        if diff_value != DATA_MISSING:
            pieces.append(f"전일대비 {diff_value}")
        if rate_value != DATA_MISSING:
            pieces.append(f"등락률 {rate_value}")
        if high_low != DATA_MISSING:
            pieces.append(f"고가/저가 {high_low}")
        if trade_value != DATA_MISSING:
            pieces.append(f"거래대금 {trade_value}")
        return " | ".join(pieces)

    def _compose_korea_index_reason(self, kospi_value: str, kosdaq_value: str, kospi_reason: str, kosdaq_reason: str) -> str:
        reasons: list[str] = []
        if kospi_value == DATA_MISSING:
            reasons.append(f"KOSPI: {kospi_reason}")
        if kosdaq_value == DATA_MISSING:
            reasons.append(f"KOSDAQ: {kosdaq_reason}")
        return " / ".join(reasons) if reasons else DATA_MISSING

    def _fmt_krx_number(self, value: Any) -> str:
        return _fmt_number(_safe_float(str(value).replace(",", "")) if value not in (None, "") else None)

    def _fmt_krx_int(self, value: Any) -> str:
        parsed = _safe_float(str(value).replace(",", "")) if value not in (None, "") else None
        return _fmt_int(int(parsed) if parsed is not None else None)

    def _fmt_signed_krx_value(self, value: Any) -> str:
        parsed = _safe_float(str(value).replace(",", "")) if value not in (None, "") else None
        if parsed is None:
            return DATA_MISSING
        sign = "+" if parsed > 0 else ""
        return f"{sign}{_fmt_number(parsed)}"

    def _fmt_percent_krx_value(self, value: Any) -> str:
        parsed = _safe_float(str(value).replace(",", "")) if value not in (None, "") else None
        if parsed is None:
            return DATA_MISSING
        sign = "+" if parsed > 0 else ""
        return f"{sign}{_fmt_number(parsed)}%"

    def _fmt_krx_high_low(self, high: Any, low: Any) -> str:
        high_value = _safe_float(str(high).replace(",", "")) if high not in (None, "") else None
        low_value = _safe_float(str(low).replace(",", "")) if low not in (None, "") else None
        return self._combine_values(high_value, low_value)

    def _prefer_values(self, *values: str) -> str:
        for value in values:
            if value != DATA_MISSING:
                return value
        return DATA_MISSING

    def _favorite_chart_structure(self, current: float | None, ma20: float | None, ma60: float | None, name: str) -> str:
        if current is None or ma20 is None or ma60 is None:
            return f"{name} 차트 구조는 데이터 미수집 (종가 또는 이동평균 이력 부족)"
        if current > ma20 > ma60:
            return f"{name}는 단기·중기 이동평균 위에 있어 우상향 구조다. 눌림이 와도 추세 훼손 전까지는 상승 추세 해석이 우선."
        if current < ma20 < ma60:
            return f"{name}는 20일선과 60일선 아래라 약세 구조다. 반등이 나와도 추세 반전보다 기술적 되돌림 가능성을 먼저 봐야 한다."
        return f"{name}는 이동평균이 엇갈려 방향성이 약하다. 추세 추종보다 지지/저항 확인이 우선이다."

    def _shakeout_view(self, current: float | None, ma20: float | None, ma60: float | None, name: str) -> str:
        if current is None or ma20 is None:
            return f"{name} 개미 털기 판단은 데이터 미수집 (분봉·거래량·이동평균 부족)"
        if current > ma20:
            return f"{name}는 최소한 20일선 위에 있어 흔들림이 나와도 즉시 개미 털기로 단정하기보다 상승 추세 내 조정 가능성을 먼저 점검."
        return f"{name}는 20일선 아래라 단순 개미 털기보다 추세 약화 가능성을 더 경계해야 한다."

    def _favorite_down_reason(self, current: float | None, ma20: float | None, ma60: float | None, disclosure: str, name: str) -> str:
        if disclosure != DATA_MISSING:
            return f"{name} 하락 시 우선 해석은 공시 재료 소멸, 공시 내용 실망, 이벤트 선반영 후 차익실현 여부다."
        if current is None or ma20 is None:
            return f"{name} 하락 이유 분석은 데이터 미수집 (가격·이동평균 또는 공시 근거 부족)"
        if current < ma20:
            return f"{name} 하락은 단기 추세 이탈에 따른 매물 압박으로 해석 가능하다. 20일선 회복 실패 시 추가 약세를 경계."
        return f"{name} 하락은 추세 훼손보다 단기 과열 해소 가능성을 먼저 점검할 구간이다."

    def _favorite_up_reason(self, current: float | None, ma20: float | None, ma60: float | None, disclosure: str, name: str) -> str:
        if disclosure != DATA_MISSING:
            return f"{name} 상승 시 우선 해석은 IR/공시 재평가, 숫자 기대, 이벤트 드리븐 수급 유입 여부다."
        if current is None or ma20 is None:
            return f"{name} 상승 이유 분석은 데이터 미수집 (가격·이동평균 또는 공시 근거 부족)"
        if current > ma20:
            return f"{name} 상승은 20일선 상방 유지에 따른 추세 추종 수급 유입으로 해석 가능하다."
        return f"{name} 상승은 추세 반전 시도일 수 있으나 20일선 회복 전까지는 기술적 반등으로 보는 편이 안전하다."

    def _favorite_forecast(self, current: float | None, ma20: float | None, ma60: float | None, name: str) -> str:
        if current is None or ma20 is None:
            return f"{name} 예측은 데이터 미수집 (종가·이동평균 부족). 숫자 없이 방향성 단정 금지."
        if current > ma20:
            return f"{name} 예측: 20일선 위 안착이 이어지면 재상승 시도 가능. 다만 거래량 확인 없이 추세 연장으로 단정하지 말 것."
        return f"{name} 예측: 20일선 회복 전까지는 반등보다 저항 확인 구간이다. 반등 실패 시 재차 눌림 가능성을 열어둬야 한다."

    def _favorite_add_rule(self, current: float | None, ma20: float | None, name: str) -> str:
        if current is None or ma20 is None:
            return f"{name} 추가매수 기준은 데이터 미수집 (종가·20일선 부족)"
        if current >= ma20:
            return f"{name}는 20일선({_fmt_number(ma20)}) 지지 확인 후 분할 추가."
        return f"{name}는 20일선({_fmt_number(ma20)}) 회복 전 추가매수 보류."

    def _favorite_exit_rule(self, current: float | None, ma20: float | None, name: str) -> str:
        if current is None or ma20 is None:
            return f"{name} 매도 기준은 데이터 미수집 (종가·20일선 부족)"
        if current < ma20:
            return f"{name}는 20일선({_fmt_number(ma20)}) 이탈 지속 시 비중 축소."
        return f"{name}는 20일선({_fmt_number(ma20)}) 종가 이탈 전까지 추세 유지 관점."

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

    def _dnd_today_analysis(self, bio: dict[str, str], disclosure: str) -> str:
        if disclosure != DATA_MISSING:
            return f"디앤디파마텍은 최근 공시({disclosure})가 직접 재료다. 차트보다 공시 내용 해석과 시장 반응 확인이 우선이다."
        if bio.get("headline") != DATA_MISSING:
            return "디앤디파마텍은 바이오 섹터 뉴스 영향권에 있다. 섹터 강세가 붙는 날만 동반 탄력 기대가 가능하다."
        return "디앤디파마텍 분석은 데이터 미수집 (개별 시세·거래량·직접 공시 근거 부족)"

    def _dnd_tomorrow_scenario(self, bio: dict[str, str], disclosure: str) -> str:
        if disclosure != DATA_MISSING:
            return "공시 재해석이 긍정적으로 이어지면 단기 재상승 시도 가능. 후속 설명이 약하면 변동성만 커지고 방향은 흐려질 수 있다."
        if bio.get("headline") != DATA_MISSING:
            return "바이오 섹터 강세가 이어지면 동반 반등 시도 가능. 섹터 식으면 개별주 지속성은 급격히 약해질 수 있다."
        return "내일 시나리오는 데이터 미수집 (직접 재료 부족)"

    def _dnd_add_rule(self, disclosure: str) -> str:
        if disclosure != DATA_MISSING:
            return "추가매수 기준은 데이터 미수집. 공시만 보고 추격하지 말고 장중 거래대금 확대와 눌림 지지 확인 후 판단."
        return "추가매수 기준은 데이터 미수집 (개별 시세 API 미연동)"

    def _dnd_exit_rule(self, disclosure: str) -> str:
        if disclosure != DATA_MISSING:
            return "매도/탈출 기준은 데이터 미수집. 공시 기대가 약해지거나 후속 재료 부재 시 보수적으로 대응."
        return "매도/탈출 기준은 데이터 미수집 (개별 시세 API 미연동)"
