from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from organizations.utils import get_current_org

from .models import Account, JournalEntry, Transaction
from .serializers import (
    AccountSerializer,
    JournalEntrySerializer,
    TransactionSerializer,
)
from . import services


class OrgScopedModelViewSet(viewsets.ModelViewSet):
    """Base viewset: every queryset is filtered to the request's organization."""

    def get_organization(self):
        return get_current_org(self.request)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["organization"] = self.get_organization()
        return ctx


class AccountViewSet(OrgScopedModelViewSet):
    serializer_class = AccountSerializer

    def get_queryset(self):
        return Account.objects.filter(organization=self.get_organization())

    def perform_create(self, serializer):
        serializer.save(organization=self.get_organization())


class JournalEntryViewSet(OrgScopedModelViewSet):
    serializer_class = JournalEntrySerializer
    http_method_names = ["get", "post", "head", "options"]  # entries are immutable

    def get_queryset(self):
        return (
            JournalEntry.objects.filter(organization=self.get_organization())
            .prefetch_related("lines")
        )


class TransactionViewSet(OrgScopedModelViewSet):
    serializer_class = TransactionSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return Transaction.objects.filter(organization=self.get_organization())


class DashboardView(APIView):
    """Real aggregates computed from the ledger for the current org."""

    def get(self, request):
        org = get_current_org(request)
        summary = services.dashboard_summary(org)

        def money(d):
            return str(d)

        kpis = {k: money(v) for k, v in summary["kpis"].items()}
        chart = [
            {"month": c["month"], "revenue": money(c["revenue"]),
             "expenses": money(c["expenses"])}
            for c in summary["chart"]
        ]
        recent = TransactionSerializer(
            summary["recent_transactions"], many=True
        ).data

        return Response({
            "organization": org.name,
            "period": summary["period"],
            "base_currency": summary["base_currency"],
            "kpis": kpis,
            "health": summary["health"],
            "recommendations": summary["recommendations"],
            "chart": chart,
            "recent_transactions": recent,
        })
