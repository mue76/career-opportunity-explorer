from django.contrib import admin
from .models import Opportunity


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display  = ("title", "organization", "type", "source", "note", "collected_at")
    list_filter   = ("source", "type")
    search_fields = ("title", "organization", "keywords")
    ordering      = ("-collected_at",)
