from django.urls import path
from . import views

app_name = "opportunities"

urlpatterns = [
    path("", views.home, name="home"),
    path("opportunities/", views.opportunity_list, name="list"),
    path("opportunities/<int:pk>/analyze/", views.analyze_skill_gap, name="analyze"),
]
