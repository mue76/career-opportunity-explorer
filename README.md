# 커리어 기회 탐색기 (Career Opportunity Explorer)

이력서/경력/관심사를 기반으로 맞춤형 기회를 추천하는 서비스입니다.

## MVP 기능

- 이력서 업로드 (PDF/텍스트)
- 강의 / 프로젝트 / 협업 기회 대상 추천
- 상위 5개 추천 결과 + 추천 이유 제공

## 기술 스택

- Backend: Python, Django
- 데이터: JSON / CSV (초기 샘플 데이터)

## 프로젝트 구조

```
career-opportunity-explorer/
├── web/            # Django 웹 애플리케이션
│   ├── config/     # Django 설정 (settings, urls, wsgi)
│   ├── apps/       # Django 앱 모음
│   └── manage.py
├── scripts/        # 데이터 수집 / 전처리 스크립트
├── data/
│   ├── raw/        # 원본 수집 데이터
│   └── processed/  # 전처리된 데이터
└── docs/           # 기획 문서, API 명세 등
```

## 로컬 실행

```bash
cd web
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## 개발 로드맵

- [x] 초기 repo 구조 설정
- [ ] 샘플 데이터 수집 스크립트
- [ ] 이력서 업로드 및 파싱
- [ ] 추천 로직 구현
- [ ] 추천 결과 UI
- [ ] (확장) 로그인 / 사용자 저장
- [ ] (확장) 추천 알고리즘 고도화
- [ ] (확장) 배포 자동화
