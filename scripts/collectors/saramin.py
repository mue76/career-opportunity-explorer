"""사람인 수집기 (Playwright 기반).

현재: SaraminCollector — headless=False Chromium으로 검색 결과 수집
  · 사람인이 headless=True 연결을 차단하므로 headless=False 고정
  · 수집 중 브라우저 창이 잠시 열림 (MVP 허용 범위)
추후: SaraminAPICollector — Open API 키 승인 후 추가 예정
  → collect() 인터페이스가 동일하므로 run_collect.py 수정 불필요
"""

import time
import logging
from urllib.parse import urlencode, urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from .base import BaseCollector

logger = logging.getLogger(__name__)

BASE_URL = "https://www.saramin.co.kr"
SEARCH_PATH = "/zf_user/search/recruit"

# 고용형태 키워드 — job_condition span 중 해당 텍스트가 포함된 것을 type으로 추출
_EMPLOYMENT_KEYWORDS = {"정규직", "계약직", "인턴", "아르바이트", "파견직", "프리랜서", "위촉직"}


class SaraminCollector(BaseCollector):
    """Playwright headless browser 기반 사람인 수집기."""

    source_name = "saramin"

    def collect(self, query: str = "python", pages: int = 1) -> list[dict]:
        """하위 호환용 — collect_pages()를 모아서 반환."""
        results = []
        for _, page_items in self.collect_pages(query=query, pages=pages):
            results.extend(page_items)
        return results

    def collect_pages(self, query: str = "python", pages: int = 1):
        """
        페이지 단위 제너레이터. (page_num, items) 튜플을 yield.
        브라우저를 닫은 후 yield해야 Django ORM과 충돌하지 않음.
        """
        collected = []  # [(page_num, items), ...]

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()

            for page_num in range(1, pages + 1):
                url = f"{BASE_URL}{SEARCH_PATH}?{urlencode({'searchword': query, 'recruitPage': page_num})}"
                logger.info("[saramin] page %d → %s", page_num, url)

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    page.wait_for_selector("div.item_recruit", timeout=15_000)
                except PlaywrightTimeoutError:
                    logger.info("[saramin] no more results at page %d, stopping", page_num)
                    break

                items = page.query_selector_all("div.item_recruit")
                logger.info("[saramin] %d items found on page %d", len(items), page_num)

                if not items:
                    logger.info("[saramin] empty page %d, stopping", page_num)
                    break

                parsed = [self._parse_item(item) for item in items]
                collected.append((page_num, [p for p in parsed if p]))

                if page_num < pages:
                    time.sleep(1.5)

            browser.close()

        # Playwright 컨텍스트 종료 후 yield → Django ORM 안전
        yield from collected

    def _parse_item(self, item) -> dict | None:
        try:
            # ── 제목 & 링크 ──────────────────────────────────────
            title_el = item.query_selector("h2.job_tit a")
            if not title_el:
                return None
            title = title_el.inner_text().strip()
            link = title_el.get_attribute("href") or ""
            if link and not link.startswith("http"):
                link = urljoin(BASE_URL, link)

            # ── 회사명 ────────────────────────────────────────────
            org_el = item.query_selector("strong.corp_name a") or item.query_selector("strong.corp_name")
            organization = org_el.inner_text().strip() if org_el else ""

            # ── 고용형태 (job_condition span 중 키워드 매칭) ──────
            cond_els = item.query_selector_all("div.job_condition span")
            cond_texts = [el.inner_text().strip() for el in cond_els]
            kind = next(
                (t for t in cond_texts if any(k in t for k in _EMPLOYMENT_KEYWORDS)),
                cond_texts[-1] if cond_texts else "",
            )

            # ── 키워드 (직무 분야 태그) ───────────────────────────
            kw_els = item.query_selector_all("div.job_sector a")
            keywords = [el.inner_text().strip() for el in kw_els if el.inner_text().strip()]

            # ── description: 직무 분야 텍스트 (목록 페이지엔 상세 설명 없음)
            # .job_day span(등록일/수정일)을 제외하고 키워드 텍스트만 추출
            description = ", ".join(keywords)

            # ── note: 마감일 ──────────────────────────────────────
            date_el = item.query_selector("div.job_date span.date") or item.query_selector("div.job_date span")
            note = date_el.inner_text().strip() if date_el else ""

            return self._item(
                title=title,
                organization=organization,
                kind=kind,
                description=description,
                keywords=keywords,
                link=link,
                note=note,
            )

        except Exception as exc:
            logger.warning("[saramin] parse error: %s", exc)
            return None


# ──────────────────────────────────────────────────────────────
# TODO: SaraminAPICollector
# ──────────────────────────────────────────────────────────────
# Open API 키 승인 후 아래 클래스를 구현한다.
# run_collect.py에서 "saramin-api"로 등록하면 전환 가능.
#
# class SaraminAPICollector(BaseCollector):
#     source_name = "saramin-api"
#
#     def collect(self, query: str = "python", pages: int = 1) -> list[dict]:
#         # GET https://oapi.saramin.co.kr/job-search
#         # params: access-key, keywords, start, count
#         # response JSON → _item() 매핑
#         raise NotImplementedError
