# A century-long plan

실제 데이터 기반 투자 리서치 시스템입니다. Python 3.11 기준으로 오전, 오후, 마감 리포트를 자동 생성하며, `FRED`, `NewsAPI`, `MarketAux`, `Massive`, `Alpha Vantage`, `DART` 데이터를 사용합니다.

## 구조

- `research/`: 생성된 리서치 파일
- `companies/`, `etf/`, `industries/`: 자산별 위키형 문서
- `templates/`: Markdown 템플릿
- `scripts/`: 생성 스크립트와 데이터 수집 로직
- `config/`: 자산, API, 스케줄 설정
- `logs/`: 생성 로그

## API 발급 방법

- `FRED`: [FRED API](https://fred.stlouisfed.org/docs/api/api_key.html)에서 API 키 발급
- `NewsAPI`: [NewsAPI](https://newsapi.org/register)에서 계정 생성 후 키 발급
- `MarketAux`: [MarketAux](https://www.marketaux.com/)에서 API 키 발급
- `Massive`: [Massive](https://massive.com/)에서 API 키 발급
- `Alpha Vantage`: [Alpha Vantage](https://www.alphavantage.co/support/#api-key)에서 무료 키 발급
- `DART`: [OPEN DART](https://opendart.fss.or.kr/)에서 인증키 발급

## .env 설정 방법

프로젝트 루트에 `.env` 파일을 두고 아래처럼 입력합니다.

```bash
FRED_API_KEY=...
NEWS_API_KEY=...
MARKETAUX_API_KEY=...
MASSIVE_API_KEY=...
ALPHA_VANTAGE_API_KEY=...
DART_API_KEY=...
```

현대차 Alpha Vantage 심볼을 강제로 지정하려면 아래를 추가할 수 있습니다.

```bash
HYUNDAI_ALPHA_SYMBOL=HYMTF
```

`.env`는 `.gitignore`에 포함되어 있어 커밋되지 않습니다.

## 설치

```bash
python3 -m pip install -r requirements.txt
```

## 실행 방법

간단 리포트 생성:

```bash
python3 scripts/generate_report.py morning
python3 scripts/generate_report.py afternoon
python3 scripts/generate_report.py closing
```

확장 리포트 생성:

```bash
python3 scripts/generate_research.py daily --session morning
python3 scripts/generate_research.py daily --session afternoon
python3 scripts/generate_research.py daily --session closing
```

특정 날짜 지정:

```bash
python3 scripts/generate_report.py morning --date 2026-06-18 --overwrite
python3 scripts/generate_research.py daily --session morning --date 2026-06-18 --overwrite
```

하루 3개 리포트 동시 생성:

```bash
python3 scripts/generate_research.py all-daily --overwrite
```

## 현재 자동 수집 범위

- `FRED`: 미국 10년물 금리, CPI, PPI, 실업률, 연방기금금리
- `Alpha Vantage`: 현대차 현재가, 전일 종가, 거래량, 52주 고가, 52주 저가
- `NewsAPI` + `MarketAux`: 기본 섹터 뉴스 수집
- `Massive`: `MarketAux` 한도 초과 시 `/v2/reference/news` fallback 뉴스 수집
- `DART`: 현대차, 삼성전자, 디앤디파마텍 최근 공시

## 데이터 미수집으로 남는 항목

- 외국인/기관/개인 수급
- 한국장 실시간 KOSPI/KOSDAQ
- 현대차 투자주체별 순매수/순매도

이 항목들은 한국 브로커 API 또는 거래소 API를 추가로 연결해야 합니다.

## 리포트 완성도를 위해 추가로 필요한 것

- `KIS` 또는 다른 한국 브로커 API
  - KOSPI, KOSDAQ
  - 외국인/기관/개인 수급
  - 현대차 투자주체 매매
- 국내 종목 시세 히스토리 API
  - 현대차 20일/60일 이동평균
  - 지지선/저항선
  - 뉴스 이후 실제 가격 반응
- 번역 계층
  - 해외 뉴스 제목과 요약의 자동 한글화
  - 현재는 일부 리포트만 수동 보정

준비된 환경변수 예시:

```bash
KIS_APP_KEY=...
KIS_APP_SECRET=...
```

## 현재 리포트의 트레이딩 보조 구조

리포트는 단순 뉴스 요약이 아니라 아래 항목을 기준으로 매매 판단을 돕도록 구성됩니다.

- `근거 점수`: 현재 리포트가 몇 개의 핵심 데이터 축을 확보했는지 표시
- `근거 품질 코멘트`: 공격/중립/방어 판단의 신뢰도 설명
- `신규 진입 금지 조건`: 어떤 상황에서는 매매를 하지 말아야 하는지 명시
- `허용 포지션 크기`: 근거 품질에 따라 허용할 비중 가이드
- `진입 트리거`: 실제로 주문을 고려할 조건
- `시나리오 무효화 조건`: 아이디어가 틀렸다고 판단할 조건
- `반대 신호`: 원래 가설과 반대로 해석해야 하는 신호

이 구조는 데이터가 비어 있어도 왜 판단을 보류해야 하는지 같이 보여주도록 설계되어 있습니다.

## 자동화 방법

`cron` 예시:

```cron
30 8 * * 1-5 cd /Users/htkim/Project/Stock/devkim_research && python3 scripts/generate_report.py morning
20 12 * * 1-5 cd /Users/htkim/Project/Stock/devkim_research && python3 scripts/generate_report.py afternoon
40 15 * * 1-5 cd /Users/htkim/Project/Stock/devkim_research && python3 scripts/generate_report.py closing
```

Codex 앱 자동화를 쓸 때도 같은 명령을 그대로 넣으면 됩니다.
