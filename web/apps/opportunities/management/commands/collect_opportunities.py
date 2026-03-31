"""
사람인 수집 후 DB 저장 management command.

사용:
    python manage.py collect_opportunities
    python manage.py collect_opportunities --query "AI 개발자" --pages 2
    python manage.py collect_opportunities --query python --pages 3 --source saramin
"""

import re
import sys
from pathlib import Path

from django.core.management.base import BaseCommand

_RE_REC_IDX = re.compile(r"rec_idx=(\d+)")

# scripts/ 디렉터리를 sys.path에 추가 (collectors 패키지 임포트용)
SCRIPTS_DIR = Path(__file__).resolve().parents[5] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from collectors.saramin import SaraminCollector  # noqa: E402
from apps.opportunities.models import Opportunity  # noqa: E402
from apps.opportunities.recommend import build_opportunity_text, compute_embedding  # noqa: E402

COLLECTORS = {
    "saramin": SaraminCollector,
}


class Command(BaseCommand):
    help = "채용 공고를 수집하여 DB에 저장합니다 (link 기준 중복 스킵)"

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=list(COLLECTORS), default="saramin")
        parser.add_argument("--query", default="python", help="검색 키워드")
        parser.add_argument("--pages", type=int, default=1, help="수집 페이지 수")
        parser.add_argument("--embed", action="store_true", help="신규 항목 임베딩 즉시 계산")

    def handle(self, *args, **options):
        source = options["source"]
        query  = options["query"]
        pages  = options["pages"]

        self.stdout.write(f"수집 시작 | source={source} | query={query} | pages={pages}")

        collector = COLLECTORS[source]()

        created_count = 0
        skipped_count = 0

        # 페이지 단위로 즉시 저장 (중간 실패해도 수집된 것은 보존)
        for page_num, items in collector.collect_pages(query=query, pages=pages):
            self.stdout.write(f"  page {page_num}: {len(items)}건 수집")

            for item in items:
                link = item.get("link", "")
                if not link:
                    skipped_count += 1
                    continue

                # rec_idx 기반 중복 체크 (relay URL이 달라도 같은 공고 스킵)
                m = _RE_REC_IDX.search(link)
                if m:
                    rec_idx = m.group(1)
                    if Opportunity.objects.filter(link__contains=f"rec_idx={rec_idx}").exists():
                        skipped_count += 1
                        continue

                opp, created = Opportunity.objects.get_or_create(
                    link=link,
                    defaults={
                        "title":        item.get("title", ""),
                        "organization": item.get("organization", ""),
                        "type":         item.get("type", ""),
                        "description":  item.get("description", ""),
                        "keywords":     item.get("keywords", []),
                        "note":         item.get("note", ""),
                        "source":       source,
                    },
                )
                if created:
                    created_count += 1
                    if options["embed"]:
                        opp.embedding = compute_embedding(build_opportunity_text(opp))
                        opp.save(update_fields=["embedding"])
                else:
                    skipped_count += 1

            self.stdout.write(
                f"  누적 저장: 신규 {created_count}건 / 중복 {skipped_count}건"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"DB 저장 완료 - 신규: {created_count}건 / 중복 스킵: {skipped_count}건"
            )
        )
