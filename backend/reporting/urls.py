from django.urls import path

from .views import ReportListView, ReportView

urlpatterns = [
    path("reports/", ReportListView.as_view(), name="report-list"),
    path("reports/<str:key>/", ReportView.as_view(), name="report-detail"),
]
