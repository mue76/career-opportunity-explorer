"""
로컬 SQLite → Railway PostgreSQL 데이터 이전 스크립트.
실행: python migrate_to_railway.py
"""
import os
import sys
import json
import django
import psycopg2

# Django 설정 로드 (SQLite)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.opportunities.models import Opportunity

RAILWAY_URL = "postgresql://postgres:zbRyRFrPWdAnGgENKmoNxMPhSeXdkNNL@hopper.proxy.rlwy.net:34941/railway"

print("Railway PostgreSQL 연결 중...")
conn = psycopg2.connect(RAILWAY_URL)
cur = conn.cursor()

# 기존 데이터 확인
cur.execute("SELECT COUNT(*) FROM opportunities_opportunity")
existing = cur.fetchone()[0]
print(f"Railway DB 현재: {existing}건")

total = Opportunity.objects.count()
print(f"로컬 SQLite: {total}건 이전 시작...\n")

batch_size = 50
done = 0

for start in range(0, total, batch_size):
    batch = Opportunity.objects.all()[start:start + batch_size]
    for opp in batch:
        cur.execute("""
            INSERT INTO opportunities_opportunity
                (title, organization, type, description, keywords, link, note, source, collected_at, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (link) DO NOTHING
        """, (
            opp.title,
            opp.organization,
            opp.type,
            opp.description,
            json.dumps(opp.keywords or []),
            opp.link,
            opp.note,
            opp.source,
            opp.collected_at,
            json.dumps(opp.embedding) if opp.embedding else None,
        ))
    conn.commit()
    done += len(batch)
    print(f"  {done}/{total} 완료", end="\r")

cur.execute("SELECT COUNT(*) FROM opportunities_opportunity")
final = cur.fetchone()[0]
print(f"\n\n이전 완료: Railway DB {final}건")

cur.close()
conn.close()
