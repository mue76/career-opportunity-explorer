"""
사람인 상세 공고 페이지에서 주요업무/자격요건 + 상세 키워드를 수집해 DB 업데이트.

사용:
    python manage.py enrich_descriptions
    python manage.py enrich_descriptions --limit 50
    python manage.py enrich_descriptions --delay 2.0
    python manage.py enrich_descriptions --force   # 이미 설명이 있는 항목도 재수집
"""

import re
import time
import logging

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

from apps.opportunities.models import Opportunity

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 릴레이 URL에서 rec_idx 추출
_RE_REC_IDX = re.compile(r"rec_idx=(\d+)")

# jobCategoryNm = 'Python,AI(인공지능),...'
_RE_CATEGORY = re.compile(r"jobCategoryNm\s*=\s*'([^']+)'")


def _rec_idx_from_link(link: str) -> str | None:
    """저장된 사람인 URL에서 rec_idx 추출."""
    m = _RE_REC_IDX.search(link)
    return m.group(1) if m else None


def _fetch_html(rec_idx: str) -> str:
    """rec_idx → 직접 공고 URL로 HTML 가져오기."""
    url = f"https://www.saramin.co.kr/zf_user/jobs/view?rec_idx={rec_idx}"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.warning("fetch 실패 [rec_idx=%s]: %s", rec_idx, exc)
        return ""


def _extract_category_keywords(html: str) -> list[str]:
    """jobCategoryNm JS 변수 → 키워드 리스트."""
    m = _RE_CATEGORY.search(html)
    if not m:
        return []
    return [kw.strip() for kw in m.group(1).split(",") if kw.strip()]


def _extract_detail_text(html: str) -> str:
    """
    jv_detail 섹션에서 공고 본문 추출.
    1차: info-block 구조 (주요업무/자격요건 등 섹션별 파싱)
    2차: user_content 구조 (자유형 HTML — 텍스트만 추출)
    """
    soup = BeautifulSoup(html, "html.parser")
    detail = soup.find(class_="jv_detail")
    if not detail:
        return ""

    # 1차: 구조형 (info-block)
    parts = []
    for block in detail.find_all(class_="info-block"):
        title_el = block.find(class_="info-block__title")
        list_el  = block.find(class_="info-block__list")
        if not title_el or not list_el:
            continue

        title = title_el.get_text(strip=True)
        title = re.sub(r"^[^\w가-힣]+", "", title).strip()

        content = list_el.get_text(" ", strip=True)
        content = re.sub(r"\s+", " ", content).strip()

        if content:
            parts.append(f"[{title}] {content}")

    if parts:
        return "\n".join(parts)

    # 2차: 자유형 (user_content div)
    user_content = detail.find(class_="user_content")
    if user_content:
        # img alt 텍스트 제거, 불필요한 공백 정리
        for img in user_content.find_all("img"):
            img.decompose()
        text = user_content.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    return ""


class Command(BaseCommand):
    help = "사람인 상세 페이지에서 주요업무/자격요건/키워드를 수집해 DB를 업데이트합니다"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=0,
            help="처리할 최대 항목 수 (0 = 전체)",
        )
        parser.add_argument(
            "--delay", type=float, default=1.5,
            help="요청 간 대기 시간(초), 기본 1.5",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="description이 이미 있는 항목도 재수집",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        delay = options["delay"]
        force = options["force"]

        qs = Opportunity.objects.filter(source="saramin")
        if not force:
            # 아직 실제 직무 내용이 없는 항목만 대상
            # (비어있거나 keywords join과 동일한 경우 = 이전 수집 방식)
            trivial_ids = [
                opp.pk for opp in qs
                if not opp.description or opp.description == ", ".join(opp.keywords)
            ]
            qs = qs.filter(pk__in=trivial_ids)

        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(f"대상 공고: {total}건 (force={force}, delay={delay}s)")

        updated = 0
        failed  = 0

        for i, opp in enumerate(qs, 1):
            title_safe = opp.title[:50].encode("cp949", errors="replace").decode("cp949")
            self.stdout.write(f"[{i}/{total}] {title_safe} ...", ending=" ")

            rec_idx = _rec_idx_from_link(opp.link)
            if not rec_idx:
                self.stdout.write(self.style.WARNING("SKIP (rec_idx 없음)"))
                failed += 1
                continue

            html = _fetch_html(rec_idx)
            if not html:
                self.stdout.write(self.style.WARNING("SKIP (fetch 실패)"))
                failed += 1
                time.sleep(delay)
                continue

            new_keywords = _extract_category_keywords(html)
            new_desc     = _extract_detail_text(html)

            changed = False

            if new_keywords and set(new_keywords) != set(opp.keywords):
                opp.keywords = new_keywords
                changed = True

            # 새 내용이 있으면 교체, 없으면 기존 잘못된 내용을 빈 값으로 초기화
            if new_desc != opp.description:
                opp.description = new_desc
                changed = True

            if changed:
                opp.save(update_fields=["keywords", "description"])
                updated += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"OK  (kw={len(opp.keywords)}, desc={len(new_desc)}자)"
                    )
                )
            else:
                self.stdout.write("변경 없음")

            time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f"\n완료 - 업데이트: {updated}건 / 실패: {failed}건 / 전체: {total}건"
            )
        )
        if updated:
            self.stdout.write(
                "\n다음 명령으로 임베딩을 재계산하세요:\n"
                "  python manage.py build_embeddings --force"
            )
