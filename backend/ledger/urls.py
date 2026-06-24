from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AccountViewSet,
    DashboardView,
    JournalEntryViewSet,
    TransactionViewSet,
)

router = DefaultRouter()
router.register("accounts", AccountViewSet, basename="account")
router.register("journal-entries", JournalEntryViewSet, basename="journal-entry")
router.register("transactions", TransactionViewSet, basename="transaction")

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("", include(router.urls)),
]
