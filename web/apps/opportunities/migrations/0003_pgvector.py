"""
JSONField embedding → pgvector VectorField 마이그레이션.
기존 데이터를 vector 타입으로 변환하며 코사인 유사도 인덱스를 추가합니다.
"""
from django.db import migrations
import pgvector.django


def copy_json_to_vector(apps, schema_editor):
    """JSON 임베딩 → vector 필드 복사."""
    schema_editor.execute("""
        UPDATE opportunities_opportunity
        SET embedding_vec = embedding_json::text::vector
        WHERE embedding_json IS NOT NULL
    """)


class Migration(migrations.Migration):

    dependencies = [
        ('opportunities', '0002_opportunity_embedding'),
    ]

    operations = [
        # pgvector 확장 활성화
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS vector",
            reverse_sql="DROP EXTENSION IF EXISTS vector",
        ),

        # 기존 JSON 필드 이름 변경
        migrations.RenameField(
            model_name='opportunity',
            old_name='embedding',
            new_name='embedding_json',
        ),

        # 새 vector 필드 추가
        migrations.AddField(
            model_name='opportunity',
            name='embedding_vec',
            field=pgvector.django.VectorField(dimensions=3072, null=True, blank=True),
        ),

        # 기존 JSON 데이터 → vector 복사
        migrations.RunPython(copy_json_to_vector, migrations.RunPython.noop),

        # 기존 JSON 필드 제거
        migrations.RemoveField(
            model_name='opportunity',
            name='embedding_json',
        ),

        # vector 필드 이름을 embedding으로 변경
        migrations.RenameField(
            model_name='opportunity',
            old_name='embedding_vec',
            new_name='embedding',
        ),

        # 코사인 유사도 검색 인덱스 추가 (hnsw: ivfflat 2000차원 제한 없음)
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS opp_embedding_cosine_idx "
            "ON opportunities_opportunity USING hnsw (embedding vector_cosine_ops)",
            reverse_sql="DROP INDEX IF EXISTS opp_embedding_cosine_idx",
        ),
    ]
