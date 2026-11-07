from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health, name="ai-health"),
    path("ready/", views.ready, name="ai-ready"),
    path("capabilities/", views.capabilities, name="ai-capabilities"),
    path("predict/", views.predict, name="ai-predict"),
    path("fleet/analyze/", views.analyze_fleet_view, name="ai-fleet-analyze"),
    path("assessment/analyze/", views.assessment_analyze, name="ai-assessment-analyze"),
    path("chat/", views.chat, name="ai-chat"),
    path("knowledge/search/", views.knowledge_search, name="ai-knowledge-search"),
    path("models/", views.model_inventory, name="ai-models"),
    path("training/models/", views.training_models, name="ai-training-models"),
    path("training/train/", views.training_train, name="ai-training-train"),
    path("training/promote/", views.training_promote, name="ai-training-promote"),
    path("training/revoke/", views.training_revoke, name="ai-training-revoke"),
    # POST without the trailing slash would otherwise hit APPEND_SLASH, which cannot redirect a POST and returns 500.
    path("chat", views.chat),
    path("predict", views.predict),
    path("fleet/analyze", views.analyze_fleet_view),
    path("assessment/analyze", views.assessment_analyze),
    path("knowledge/search", views.knowledge_search),
]
