from django.db import models
from pgvector.django import VectorField


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
    # Phase B: pgvector 임베딩 (3072차원, text-embedding-3-large)
    embedding    = VectorField(dimensions=3072, null=True, blank=True)

    class Meta:
        ordering = ["-collected_at"]

    def __str__(self):
        return f"[{self.source}] {self.title}"
