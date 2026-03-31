"""
DB의 모든 공고에 임베딩 벡터를 사전 계산하여 저장.

사용:
    python manage.py build_embeddings           # 미계산 항목만
    python manage.py build_embeddings --force   # 전체 재계산
    python manage.py build_embeddings --batch 256
"""

from django.core.management.base import BaseCommand
from apps.opportunities.models import Opportunity
from apps.opportunities.recommend import build_opportunity_text, compute_embeddings_batch


class Command(BaseCommand):
    help = "공고 임베딩 벡터를 사전 계산하여 DB에 저장합니다 (OpenAI text-embedding-3-large)"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="이미 계산된 것도 재계산")
        parser.add_argument("--batch", type=int, default=256, help="배치 크기 (OpenAI 최대 2048)")

    def handle(self, *args, **options):
        qs = Opportunity.objects.all()
        if not options["force"]:
            qs = qs.filter(embedding__isnull=True)

        total = qs.count()
        if total == 0:
            self.stdout.write("계산할 항목이 없습니다. (--force 옵션으로 재계산 가능)")
            return

        self.stdout.write(f"임베딩 계산 시작: {total}건 (model=text-embedding-3-large)")

        batch_size = options["batch"]
        done = 0

        ids = list(qs.values_list("id", flat=True))
        for start in range(0, len(ids), batch_size):
            batch_ids = ids[start:start + batch_size]
            batch = list(Opportunity.objects.filter(id__in=batch_ids))

            texts = [build_opportunity_text(opp) for opp in batch]
            embeddings = compute_embeddings_batch(texts)

            for opp, emb in zip(batch, embeddings):
                opp.embedding = emb

            Opportunity.objects.bulk_update(batch, ["embedding"])
            done += len(batch)
            self.stdout.write(f"  {done}/{total} 완료", ending="\r")
            self.stdout.flush()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"임베딩 계산 완료: {done}건 저장"))
