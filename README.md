# 커리어 기회 탐색기 (Career Opportunity Explorer)

이력서를 붙여넣으면 AI가 맞춤 채용공고를 추천해주는 서비스.
**Claude Code**를 활용해 기획부터 배포까지 진행한 프로젝트입니다.

🔗 **라이브 데모**: https://career-opportunity-explorer-production.up.railway.app

---

## 서비스 개요

| 단계 | 입력 | 출력 |
|------|------|------|
| 1. 데이터 수집 | 사람인 검색 키워드 | 채용공고 JSON |
| 2. 임베딩 계산 | 공고 텍스트 | 3072차원 벡터 (OpenAI) |
| 3. 추천 | 이력서 텍스트/PDF | 상위 5개 공고 + 추천 이유 |
| 4. 스킬갭 분석 | 이력서 + 선택한 공고 | 강점/부족역량/합격가능성 (GPT-4o-mini) |

---

## 기술 스택

```
Frontend  : Django Templates + Tailwind CSS
Backend   : Django 6 + Python 3.12
DB        : PostgreSQL + pgvector (Railway)
AI/검색   : OpenAI text-embedding-3-large + BM25 + RRF 하이브리드
LLM       : GPT-4o-mini (스킬갭 분석)
배포      : Railway (웹 + DB 통합)
```

---

## 프로젝트 구조

```
career-opportunity-explorer/
├── web/                          # Django 애플리케이션
│   ├── apps/opportunities/
│   │   ├── models.py             # Opportunity 모델 (VectorField 포함)
│   │   ├── recommend.py          # 하이브리드 검색 엔진
│   │   ├── views.py              # 추천 + 스킬갭 분석 뷰
│   │   └── management/commands/
│   │       ├── collect_opportunities.py  # 수집 커맨드
│   │       ├── build_embeddings.py       # 임베딩 일괄 계산
│   │       └── enrich_descriptions.py   # 공고 상세 크롤링
│   ├── config/                   # Django 설정
│   ├── templates/                # HTML 템플릿
│   ├── requirements.txt
│   └── Procfile                  # Railway 배포 설정
├── scripts/                      # 독립 수집 스크립트
│   └── collectors/               # 사람인 / 위시켓 크롤러
└── data/raw/                     # 수집 원본 JSON
```

---

## 추천 엔진 구조

### Phase A — 키워드 매칭 (임베딩 없을 때 자동 사용)
이력서 텍스트에서 공고 키워드가 몇 개 일치하는지 스코어링.

### Phase B — 하이브리드 검색 (임베딩 있을 때 자동 사용)

```
pgvector 코사인 유사도 (가중치 60%)
    +
BM25 텍스트 검색 (가중치 40%)
    +
키워드 매칭 보너스 (+0.02/개)
    +
카테고리 다양성 (직군별 최대 3개)
──────────────────────────────────
RRF (Reciprocal Rank Fusion) 최종 점수
```

**왜 하이브리드인가?**
- 임베딩만 쓰면 특정 기술명(React, Kubernetes 등) 정확 매칭에 약함
- BM25만 쓰면 "Python 백엔드" ↔ "서버 개발" 같은 의미 연결 못함
- 둘을 합치면 서로의 약점을 보완

---

## AI 역할 분담

| 역할 | 모델 | 용도 |
|------|------|------|
| 텍스트 임베딩 | `text-embedding-3-large` | 공고/이력서 벡터화 (3072차원) |
| 스킬갭 분석 | `gpt-4o-mini` | 강점·부족역량·합격가능성 분석 |

**왜 text-embedding-3-large?**
로컬 모델(KR-SBERT 등) 대비 한국어 이해도가 높고, 3072차원으로 미묘한 의미 차이까지 포착.
단, Railway free tier에서 임베딩 전체를 Python 메모리에 올리면 OOM → pgvector로 DB 레벨 검색으로 해결.

---

## 로컬 실행

```bash
# 1. 저장소 클론 및 환경 설정
git clone https://github.com/mue76/career-opportunity-explorer.git
cd career-opportunity-explorer/web

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. .env 파일 생성 (web/ 디렉터리)
OPENAI_API_KEY=sk-...
# DATABASE_URL 미설정 시 SQLite 자동 사용

# 3. DB 초기화 및 실행
python manage.py migrate
python manage.py runserver
```

```bash
# 4. 데이터 수집 (사람인)
python manage.py collect_opportunities --query "python" --pages 3 --embed
python manage.py collect_opportunities --query "AI 개발" --pages 3 --embed
```

---

## Railway 배포 가이드

### 1. 저장소 준비
```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/<username>/<repo>.git
git push -u origin main
```

### 2. Railway 프로젝트 생성
1. [railway.app](https://railway.app) → 로그인 → **New Project**
2. **Deploy from GitHub repo** → 저장소 선택
3. 앱 서비스 → **Settings** → **Root Directory** = `web`

### 3. PostgreSQL 추가
1. Railway 프로젝트 → **+ New** → **Database** → **PostgreSQL**
2. 앱 서비스 → **Variables** → `DATABASE_URL` 참조 연결

### 4. 환경변수 설정 (앱 서비스 Variables)
```
OPENAI_API_KEY       = sk-...
DJANGO_SECRET_KEY    = 랜덤 50자 문자열
ALLOWED_HOSTS        = .railway.app
CSRF_TRUSTED_ORIGINS = https://<your-app>.railway.app
```

### 5. Procfile (자동 마이그레이션 포함)
```
web: python manage.py migrate && gunicorn config.wsgi --workers 1 --timeout 120 --bind 0.0.0.0:8000
```

### 6. 로컬 데이터 → Railway 이전
```bash
# migrate_to_railway.py의 RAILWAY_URL을 PostgreSQL Public URL로 수정 후 실행
python migrate_to_railway.py
```

---

## 트러블슈팅 요약

| 문제 | 원인 | 해결 |
|------|------|------|
| Build failed | Railway Root Directory 미설정 | Settings → Root Directory = `web` |
| DisallowedHost | ALLOWED_HOSTS 형식 오류 | `.railway.app` (앞에 점) |
| CSRF 403 | CSRF_TRUSTED_ORIGINS 누락 | `https://` 포함 전체 URL 등록 |
| Worker SIGKILL (OOM) | 임베딩 전체를 Python 메모리에 로드 | pgvector로 DB 레벨 검색 전환 |
| ivfflat/hnsw 인덱스 오류 | pgvector 3072차원 초과 제한 | 인덱스 제거 (3천건 규모에서 sequential scan으로 충분) |
| No space left on device | JSON + vector 동시 저장으로 용량 초과 | PostgreSQL 재생성 후 vector 포맷으로만 이전 |

---

## 향후 계획

- [ ] **다중 키워드 자동 수집** — 직군별 키워드 목록으로 주기적 크롤링
- [ ] **위시켓 수집 활성화** — 프리랜서 프로젝트 공고 포함
- [ ] **사용자 이력서 저장** — 로그인 후 재사용
- [ ] **추천 피드백 루프** — 좋아요/싫어요로 개인화
- [ ] **pgvector HNSW 인덱스** — Railway pgvector 버전 업 후 적용 (현재 3072차원 제한으로 미적용)
- [ ] **공고 만료 처리** — 마감된 공고 자동 필터링

---

## Claude Code로 개발하기

이 프로젝트는 **Claude Code CLI** 로 개발했습니다.

```bash
# 설치 (Node.js 필요)
npm install -g @anthropic/claude-code

# 프로젝트 디렉터리에서 실행
claude
```

**활용 방식:**
- 수집 스크립트 → Django 모델 → 추천 로직 → UI 순서로 단계별 구현
- 배포 에러 로그를 그대로 붙여넣으면 원인 분석 + 수정까지 처리
- 마이그레이션 충돌, OOM 등 복잡한 문제도 대화로 해결
- 코드 한 줄 직접 작성 없이 기획 의도만 설명해도 동작하는 코드 생성
