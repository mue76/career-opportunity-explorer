from django.db import models


class Opportunity(models.Model):
    title        = models.CharField(max_length=500)
    organization = models.CharField(max_length=200, blank=True)
    type         = models.CharField(max_length=100, blank=True)   # 고용형태
    description  = models.TextField(blank=True)
    keywords     = models.JSONField(default=list)
    link         = models.URLField(max_length=1000, unique=True)  # dedup 기준
    note         = models.CharField(max_length=200, blank=True)   # 마감일
    source       = models.CharField(max_length=50, default="saramin")
    collected_at = models.DateTimeField(auto_now_add=True)
    # Phase B: 임베딩 벡터 (float 리스트). None이면 아직 미계산.
    embedding    = models.JSONField(null=True, blank=True, default=None)

    class Meta:
        ordering = ["-collected_at"]

    def __str__(self):
        return f"[{self.source}] {self.title}"
