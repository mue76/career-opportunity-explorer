"""
여러 키워드로 사람인 공고를 일괄 수집하는 커맨드.

사용:
    python manage.py collect_bulk               # 기본 키워드 목록, 각 2페이지
    python manage.py collect_bulk --pages 3     # 키워드당 3페이지
    python manage.py collect_bulk --embed       # 신규 공고 임베딩 즉시 계산
    python manage.py collect_bulk --pages 3 --embed
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

# 수집 대상 키워드 목록 (직군별 구성)
KEYWORDS = [
    # AI / ML
    "AI 개발자",
    "머신러닝",
    "딥러닝",
    "LLM",
    # 데이터
    "데이터 엔지니어",
    "데이터 분석가",
    "데이터 사이언티스트",
    # 백엔드 / 풀스택
    "python 백엔드",
    "java 백엔드",
    "Django",
    "Spring",
    # 프론트엔드
    "프론트엔드",
    "React",
    # 클라우드 / DevOps
    "AWS",
    "클라우드",
    "DevOps",
    # 교육
    "학원강사",
    "파트강사",
    "교육기획",
    "인공지능 강사",
    "K-Digital Training 강사",
    "AI 캠퍼스 강사",
]


class Command(BaseCommand):
    help = "다중 키워드로 사람인 공고를 일괄 수집합니다 (중복 자동 스킵)"

    def add_arguments(self, parser):
        parser.add_argument("--pages", type=int, default=2, help="키워드당 수집 페이지 수")
        parser.add_argument("--embed", action="store_true", help="신규 공고 임베딩 즉시 계산")

    def handle(self, *args, **options):
        pages = options["pages"]
        embed = options["embed"]
        total_keywords = len(KEYWORDS)

        self.stdout.write(
            f"일괄 수집 시작 | 키워드 {total_keywords}개 × {pages}페이지"
            + (" + 임베딩 계산" if embed else "")
        )
        self.stdout.write("-" * 50)

        for i, query in enumerate(KEYWORDS, 1):
            self.stdout.write(f"[{i}/{total_keywords}] '{query}' 수집 중...")
            try:
                call_command(
                    "collect_opportunities",
                    query=query,
                    pages=pages,
                    embed=embed,
                    verbosity=0,
                )
            except Exception as exc:
                self.stderr.write(f"  오류 (스킵): {exc}")

        self.stdout.write(self.style.SUCCESS("일괄 수집 완료"))
