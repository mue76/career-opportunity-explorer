import json
import os
from collections import Counter

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from .models import Opportunity
from .recommend import extract_text_from_pdf, recommend, build_opportunity_text

_PDF_MIME = {"application/pdf", "application/x-pdf"}
_MAX_PDF_MB = 10


def home(request):
    """이력서 입력 폼 (텍스트 입력 + PDF 업로드)."""
    if request.method != "POST":
        return render(request, "opportunities/home.html")

    error = None
    resume_text = request.POST.get("resume_text", "").strip()
    pdf_file = request.FILES.get("resume_pdf")

    if pdf_file:
        if pdf_file.size > _MAX_PDF_MB * 1024 * 1024:
            error = f"PDF 파일 크기는 {_MAX_PDF_MB}MB 이하여야 합니다."
        elif pdf_file.content_type not in _PDF_MIME:
            error = "PDF 파일만 업로드할 수 있습니다."
        else:
            resume_text = extract_text_from_pdf(pdf_file)
            if not resume_text.strip():
                error = "PDF에서 텍스트를 추출하지 못했습니다. 텍스트 직접 입력을 이용해주세요."

    if error:
        return render(request, "opportunities/home.html", {"error": error})

    if not resume_text:
        return render(request, "opportunities/home.html", {"error": "이력서 내용을 입력하거나 PDF를 업로드해주세요."})

    # 스킬 갭 분석에서 사용하기 위해 세션에 저장
    request.session["resume_text"] = resume_text[:5000]

    results, phase = recommend(resume_text, top_n=10)

    return render(request, "opportunities/recommend.html", {
        "results": results,
        "phase": phase,
        "resume_preview": resume_text[:300].strip(),
        "total_candidates": Opportunity.objects.count(),
    })


def opportunity_list(request):
    """전체 공고 목록 (키워드 검색 포함)."""
    opportunities = Opportunity.objects.all()

    q = request.GET.get("q", "").strip()
    if q:
        opportunities = (
            opportunities.filter(title__icontains=q)
            | opportunities.filter(organization__icontains=q)
            | opportunities.filter(description__icontains=q)
        )

    return render(request, "opportunities/list.html", {
        "opportunities": opportunities[:200],
        "query": q,
        "total": Opportunity.objects.count(),
    })


@staff_member_required
def analytics(request):
    """관리자 전용 데이터 분석 대시보드."""
    opps = Opportunity.objects.all()
    total = opps.count()
    embedded = opps.filter(embedding__isnull=False).count()

    # 키워드 빈도
    all_kw = []
    for kw_list in opps.values_list("keywords", flat=True):
        all_kw.extend(kw_list or [])
    kw_counter = Counter(all_kw)
    top_keywords = kw_counter.most_common(20)

    # 고용형태 분포
    type_counter = Counter(
        t for t in opps.values_list("type", flat=True) if t
    )
    top_types = type_counter.most_common(10)

    # 기업별 공고 수 Top 15
    org_counter = Counter(
        o for o in opps.values_list("organization", flat=True) if o
    )
    top_orgs = org_counter.most_common(15)

    # 날짜별 수집 추이 (최근 30일)
    from django.db.models import Count
    from django.db.models.functions import TruncDate
    daily = (
        opps.annotate(date=TruncDate("collected_at"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )
    daily_labels = [str(d["date"]) for d in daily]
    daily_counts = [d["count"] for d in daily]

    # AI/교육 직군 상세
    ai_keywords = ["AI(인공지능)", "머신러닝", "딥러닝", "LLM", "Pytorch", "TensorFlow"]
    edu_keywords = ["학원강사", "파트강사", "교육기획", "인공지능 강사", "K-Digital Training 강사", "AI 캠퍼스 강사"]

    ai_counts = {kw: kw_counter.get(kw, 0) for kw in ai_keywords}
    edu_counts = {kw: kw_counter.get(kw, 0) for kw in edu_keywords}

    return render(request, "opportunities/analytics.html", {
        "total": total,
        "embedded": embedded,
        "top_keywords": top_keywords,
        "top_types": top_types,
        "top_orgs": top_orgs,
        "daily_labels": json.dumps(daily_labels),
        "daily_counts": json.dumps(daily_counts),
        "ai_counts": ai_counts,
        "edu_counts": edu_counts,
    })


@require_POST
def analyze_skill_gap(request, pk):
    """이력서 vs 공고 스킬 갭 분석 (OpenAI GPT-4o-mini)."""
    opp = get_object_or_404(Opportunity, pk=pk)
    resume_text = request.session.get("resume_text", "")

    if not resume_text:
        return JsonResponse({"error": "이력서 정보가 없습니다. 다시 검색해주세요."}, status=400)

    if len(resume_text.strip()) < 100:
        return JsonResponse({
            "error": "이력서 내용이 너무 짧습니다. 경력, 보유 기술, 프로젝트 경험 등을 구체적으로 입력해주세요. (최소 100자 이상)"
        }, status=400)

    job_text = build_opportunity_text(opp)

    prompt = f"""다음 이력서와 채용공고를 비교하여 스킬 갭을 분석해주세요.

[채용공고]
제목: {opp.title}
회사: {opp.organization}
내용: {job_text[:1500]}

[이력서]
{resume_text[:2000]}

분석 원칙:
- 반드시 이력서에 실제로 기재된 내용만 근거로 사용하세요.
- 이력서에 명시되지 않은 내용은 추측하거나 지어내지 마세요.
- 이력서 정보가 부족하여 판단하기 어려운 항목은 "이력서에 관련 정보 없음"으로 표기하세요.

아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "strengths": ["강점1", "강점2", "강점3"],
  "gaps": ["부족한점1", "부족한점2", "부족한점3"],
  "readiness": 75,
  "summary": "한줄 총평"
}}

- strengths: 이력서에 기재된 내용 중 이 공고와 잘 맞는 강점 (최대 3가지, 근거가 없으면 항목 수를 줄이세요)
- gaps: 이 공고에서 요구하지만 이력서에 없거나 부족한 스킬/경험 (최대 3가지)
- readiness: 이력서 정보 기준 지원 준비도 0~100 (정보가 부족할수록 낮게, 정수)
- summary: 이력서 충실도와 공고 적합성을 포함한 한 문장 총평"""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"error": f"분석 중 오류가 발생했습니다: {str(e)}"}, status=500)
