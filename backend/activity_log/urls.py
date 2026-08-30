from django.urls import path

from .views import ActivityEventListView, ActivityStatsView, ActivityTrackingToggleView

urlpatterns = [
    path("events/", ActivityEventListView.as_view(), name="activity-event-list"),
    path("stats/", ActivityStatsView.as_view(), name="activity-stats"),
    path("toggle/", ActivityTrackingToggleView.as_view(), name="activity-tracking-toggle"),
]
