from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from organizations.utils import get_current_org
from ledger.models import Account

from .models import Document
from .serializers import DocumentSerializer, DocumentConfirmSerializer
from . import extraction


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_organization(self):
        return get_current_org(self.request)

    def get_queryset(self):
        return Document.objects.filter(organization=self.get_organization())

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["organization"] = self.get_organization()
        return ctx

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        """Apply optional corrections, then post the document to the ledger."""
        document = self.get_object()
        if document.status == Document.Status.POSTED:
            return Response(
                {"detail": "Document already posted."},
                status=status.HTTP_409_CONFLICT,
            )

        payload = DocumentConfirmSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        corrections = payload.validated_data.get("extracted")
        if corrections:
            document.extracted = {**document.extracted, **corrections}
            # Re-validate after the user's corrections.
            document.flags = extraction.validate_extraction(document.extracted)
            document.save(update_fields=["extracted", "flags"])

        expense_account = None
        acc_id = payload.validated_data.get("expense_account")
        if acc_id:
            expense_account = Account.objects.filter(
                organization=document.organization, pk=acc_id
            ).first()

        try:
            entry = extraction.post_document_to_ledger(
                document, expense_account=expense_account
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {
                "document": DocumentSerializer(document).data,
                "journal_entry": entry.id,
            },
            status=status.HTTP_201_CREATED,
        )
