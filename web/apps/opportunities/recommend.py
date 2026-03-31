"""
추천 로직 모듈.

Phase A: 키워드 매칭  — embedding 미계산 시 자동 사용
Phase B: 하이브리드 (임베딩 유사도 + BM25 + 키워드 부스팅 + 카테고리 다양성)

views.py는 recommend() 하나만 호출하면 됨.
내부적으로 embedding 존재 여부에 따라 Phase를 자동 선택.
"""

import io
import logging
import os

import numpy as np

from .models import Opportunity

logger = logging.getLogger(__name__)

# OpenAI 임베딩 모델
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIM = 3072

_openai_client = None


# ── OpenAI 클라이언트 ──────────────────────────────────────────

def get_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


# ── PDF 텍스트 추출 ────────────────────────────────────────────

def extract_text_from_pdf(file_obj) -> str:
    try:
        from pdfminer.high_level import extract_text as _extract
        return _extract(io.BytesIO(file_obj.read()))
    except Exception as exc:
        logger.warning("PDF 텍스트 추출 실패: %s", exc)
        return ""


# ── 임베딩 유틸 ───────────────────────────────────────────────

def build_opportunity_text(opp: Opportunity) -> str:
    """공고 → 임베딩용 텍스트 변환."""
    parts = [opp.title]
    if opp.organization:
        parts.append(opp.organization)
    if opp.keywords:
        parts.append(" ".join(opp.keywords))
    if opp.description:
        parts.append(opp.description)
    return " ".join(parts)


def compute_embedding(text: str) -> list[float]:
    """단일 텍스트 → OpenAI 임베딩 벡터."""
    text = text.replace("\n", " ").strip()
    response = get_client().embeddings.create(
        input=[text],
        model=EMBEDDING_MODEL,
    )
    vec = np.array(response.data[0].embedding, dtype=np.float32)
    vec /= np.linalg.norm(vec)  # L2 정규화
    return vec.tolist()


def compute_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """여러 텍스트를 한 번의 API 호출로 임베딩 (최대 2048개).
    text-embedding-3-large 최대 8192 토큰 → 안전하게 6000자로 자름.
    """
    texts = [t.replace("\n", " ").strip()[:6000] for t in texts]
    response = get_client().embeddings.create(
        input=texts,
        model=EMBEDDING_MODEL,
    )
    results = []
    for item in sorted(response.data, key=lambda x: x.index):
        vec = np.array(item.embedding, dtype=np.float32)
        vec /= np.linalg.norm(vec)
        results.append(vec.tolist())
    return results


# ── BM25 인덱스 캐시 ──────────────────────────────────────────
# DB 변경 시 invalidate 필요 — 현재는 프로세스 단위 캐시 (dev/prod 단일 워커 기준)
_bm25_index = None   # BM25Okapi 인스턴스
_bm25_opps: list = []  # BM25 인덱스와 1:1 대응하는 Opportunity 리스트


def _tokenize(text: str) -> list[str]:
    """간단한 공백/구분자 기반 토크나이징 (한국어 포함)."""
    import re
    return re.findall(r"[가-힣A-Za-z0-9]+", text.lower())


def _get_bm25():
    """BM25 인덱스 반환 (lazy 초기화, 메모리 캐시)."""
    global _bm25_index, _bm25_opps
    if _bm25_index is not None:
        return _bm25_index, _bm25_opps

    from rank_bm25 import BM25Okapi

    _bm25_opps = list(Opportunity.objects.only("id", "title", "organization", "keywords", "description"))
    corpus = []
    for opp in _bm25_opps:
        text = " ".join(filter(None, [
            opp.title,
            opp.organization,
            " ".join(opp.keywords or []),
            (opp.description or "")[:500],  # description 앞 500자만 사용
        ]))
        corpus.append(_tokenize(text))

    _bm25_index = BM25Okapi(corpus)
    logger.info("BM25 인덱스 초기화 완료 (%d건)", len(_bm25_opps))
    return _bm25_index, _bm25_opps


def invalidate_bm25_cache():
    """DB 변경 후 BM25 인덱스 재초기화 트리거."""
    global _bm25_index, _bm25_opps
    _bm25_index = None
    _bm25_opps = []


# ── 통합 진입점 ───────────────────────────────────────────────

def recommend(resume_text: str, top_n: int = 5) -> tuple[list[dict], str]:
    """
    이력서 텍스트 → 상위 top_n 추천 반환.

    Returns:
        (results, phase_label)
        phase_label: "A" 또는 "B"
    """
    if Opportunity.objects.filter(embedding__isnull=False).exists():
        return hybrid_match(resume_text, top_n), "B"
    return keyword_match(resume_text, top_n), "A"


# ── Phase A: 키워드 매칭 ──────────────────────────────────────

def keyword_match(resume_text: str, top_n: int = 5) -> list[dict]:
    if not resume_text.strip():
        return []

    resume_lower = resume_text.lower()
    scored = []

    for opp in Opportunity.objects.exclude(keywords=[]):
        matched = [kw for kw in opp.keywords if kw.lower() in resume_lower]
        if not matched:
            continue

        score = int(len(matched) / max(len(opp.keywords), 1) * 100)
        scored.append({
            "opportunity": opp,
            "score": score,
            "matched_keywords": matched,
            "reason": f"이력서와 {len(matched)}개 키워드가 일치합니다: {', '.join(matched)}",
        })

    scored.sort(key=lambda x: (-x["score"], -len(x["matched_keywords"])))
    return scored[:top_n]


# ── Phase B: 임베딩 유사도 ────────────────────────────────────

# 임베딩 유사도 최소 임계값 (0~1). 이 값 미만은 결과에서 제외.
SIMILARITY_THRESHOLD = 0.40

# 키워드 매칭 시 점수에 더하는 보너스 (키워드 1개당)
KEYWORD_BONUS_PER_MATCH = 0.02

# 다양성 보장: 동일 직군 그룹에서 최대 허용 건수
MAX_PER_GROUP = 3

# 직군 카테고리 분류 맵 (키워드 → 그룹명)
_CATEGORY_MAP = {
    # AI/ML
    "AI(인공지능)": "AI/ML", "머신러닝": "AI/ML", "딥러닝": "AI/ML",
    "Pytorch": "AI/ML", "TensorFlow": "AI/ML", "LLM": "AI/ML",
    # 데이터
    "데이터엔지니어": "데이터", "데이터분석가": "데이터", "데이터 사이언티스트": "데이터",
    "빅데이터": "데이터", "데이터마이닝": "데이터",
    # 백엔드/풀스택
    "백엔드/서버개발": "백엔드", "풀스택": "백엔드", "Java": "백엔드",
    "Spring": "백엔드", "Django": "백엔드",
    # 프론트엔드
    "프론트엔드": "프론트엔드", "React": "프론트엔드", "Vue.js": "프론트엔드",
    # 클라우드/DevOps
    "클라우드": "클라우드/DevOps", "AWS": "클라우드/DevOps", "DevOps": "클라우드/DevOps",
    "인프라": "클라우드/DevOps", "Kubernetes": "클라우드/DevOps",
    # 교육
    "학원강사": "교육", "교직원": "교육", "교육기획": "교육",
    "대학강사": "교육", "파트강사": "교육",
    # PM/기획
    "PM(프로젝트매니저)": "PM/기획", "사업기획": "PM/기획", "개발PM": "PM/기획",
}


def _primary_group(opp: Opportunity) -> str:
    """공고의 대표 직군 그룹 — 카테고리 맵 우선, 없으면 첫 번째 키워드."""
    for kw in (opp.keywords or []):
        if kw in _CATEGORY_MAP:
            return _CATEGORY_MAP[kw]
    if opp.keywords:
        return opp.keywords[0]
    return "etc"


def embedding_match(resume_text: str, top_n: int = 5) -> list[dict]:
    if not resume_text.strip():
        return []

    resume_lower = resume_text.lower()
    resume_vec = np.array(compute_embedding(resume_text), dtype=np.float32)

    opps = list(Opportunity.objects.exclude(embedding=None))
    if not opps:
        return keyword_match(resume_text, top_n)

    # 벡터 행렬 구성 → 일괄 cosine similarity (내적, 정규화 완료)
    opp_matrix = np.array([opp.embedding for opp in opps])  # (N, D)
    base_scores = opp_matrix @ resume_vec                    # (N,)

    # ── 1. 키워드 부스팅: 이력서와 키워드 일치 시 보너스 가산 ──
    boosted = []
    for idx, opp in enumerate(opps):
        sim = float(base_scores[idx])
        if sim < SIMILARITY_THRESHOLD:
            continue
        matched = [kw for kw in (opp.keywords or []) if kw.lower() in resume_lower]
        bonus = len(matched) * KEYWORD_BONUS_PER_MATCH
        boosted.append((sim + bonus, sim, idx, matched))

    # 최종 점수 내림차순 정렬
    boosted.sort(key=lambda x: -x[0])

    # ── 2. 카테고리 다양성: 같은 그룹 최대 MAX_PER_GROUP건 ──
    group_counts: dict[str, int] = {}
    results = []
    for final_score, base_sim, idx, matched in boosted:
        if len(results) >= top_n:
            break
        opp = opps[idx]
        group = _primary_group(opp)
        if group_counts.get(group, 0) >= MAX_PER_GROUP:
            continue
        group_counts[group] = group_counts.get(group, 0) + 1

        if matched:
            reason = f"이력서와 의미적으로 유사합니다. 관련 키워드: {', '.join(matched)}"
        else:
            reason = "이력서 전체 내용과 의미적으로 유사한 공고입니다."

        results.append({
            "opportunity": opp,
            "score": round(final_score * 100, 1),
            "base_score": round(base_sim * 100, 1),
            "matched_keywords": matched,
            "reason": reason,
        })

    return results


# ── Phase B-2: 하이브리드 (임베딩 + BM25 RRF) ────────────────

# RRF 상수 (k=60이 표준값; 클수록 하위 순위 영향력 감소)
_RRF_K = 60
# BM25 비중 (0~1). 높을수록 정확한 단어 일치 우선
_BM25_WEIGHT = 0.4
# 임베딩 비중
_EMB_WEIGHT = 0.6


def hybrid_match(resume_text: str, top_n: int = 5) -> list[dict]:
    """임베딩 유사도 + BM25를 RRF로 합산한 하이브리드 검색."""
    if not resume_text.strip():
        return []

    resume_lower = resume_text.lower()
    resume_vec = np.array(compute_embedding(resume_text), dtype=np.float32)

    # ── 임베딩 점수 계산 ──
    emb_opps = list(Opportunity.objects.exclude(embedding=None))
    if not emb_opps:
        return keyword_match(resume_text, top_n)

    opp_matrix = np.array([opp.embedding for opp in emb_opps])
    emb_scores = opp_matrix @ resume_vec  # (N,)

    # id → 임베딩 순위 매핑
    emb_rank_map: dict[int, int] = {}
    for rank, idx in enumerate(np.argsort(emb_scores)[::-1]):
        opp = emb_opps[idx]
        emb_rank_map[opp.id] = rank

    # ── BM25 점수 계산 ──
    bm25, bm25_opps = _get_bm25()
    query_tokens = _tokenize(resume_text)
    bm25_raw = bm25.get_scores(query_tokens)

    # id → BM25 순위 매핑
    bm25_rank_map: dict[int, int] = {}
    for rank, idx in enumerate(np.argsort(bm25_raw)[::-1]):
        opp = bm25_opps[idx]
        bm25_rank_map[opp.id] = rank

    # ── 임베딩 임계값 필터 + RRF 합산 ──
    # 임계값 미달 공고는 임베딩 점수 기준으로 제외
    emb_id_to_idx = {opp.id: i for i, opp in enumerate(emb_opps)}
    candidates = []
    for opp in emb_opps:
        sim = float(emb_scores[emb_id_to_idx[opp.id]])
        if sim < SIMILARITY_THRESHOLD:
            continue
        e_rank = emb_rank_map[opp.id]
        b_rank = bm25_rank_map.get(opp.id, len(bm25_opps))  # BM25에 없으면 최하위
        rrf = _EMB_WEIGHT / (_RRF_K + e_rank) + _BM25_WEIGHT / (_RRF_K + b_rank)
        matched = [kw for kw in (opp.keywords or []) if kw.lower() in resume_lower]
        keyword_bonus = len(matched) * KEYWORD_BONUS_PER_MATCH * 0.001  # RRF 스케일에 맞게 축소
        candidates.append((rrf + keyword_bonus, sim, opp, matched))

    candidates.sort(key=lambda x: -x[0])

    # ── 카테고리 다양성 적용 ──
    group_counts: dict[str, int] = {}
    results = []
    for rrf_score, base_sim, opp, matched in candidates:
        if len(results) >= top_n:
            break
        group = _primary_group(opp)
        if group_counts.get(group, 0) >= MAX_PER_GROUP:
            continue
        group_counts[group] = group_counts.get(group, 0) + 1

        if matched:
            reason = f"이력서와 의미적으로 유사합니다. 관련 키워드: {', '.join(matched)}"
        else:
            reason = "이력서 전체 내용과 의미적으로 유사한 공고입니다."

        results.append({
            "opportunity": opp,
            "score": round(base_sim * 100, 1),
            "matched_keywords": matched,
            "reason": reason,
        })

    return results
