---
title: "{title}"
slug: "{slug}"
date: "{date}"
session: "{session}"
session_title: "{session_title}"
generated_at: "{generated_at}"
author: "{author}"
language: "ko"
tags: [{tag_csv}]
watchlist: [{watchlist_csv}]
links:
  wiki_index: "{wiki_index}"
  asset_pages: [{asset_page_csv}]
---

# {title}

<!-- TODO: 뉴스/시세/수급 API 연동 후 afternoon 템플릿 자동 채움 -->

## 리포트 작성 원칙

- 데이터가 없으면 `데이터 미수집`으로 기록한다.
- 추정 수치와 임의 숫자는 입력하지 않는다.
- 오전장 해석과 오후 전략을 분리해 기록한다.

{session_specific_sections}

{common_sections}

{hyundai_section}

## 섹터별 뉴스 및 투자 판단

{sector_news_sections}
