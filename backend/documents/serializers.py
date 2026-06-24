from rest_framework import serializers

from .models import Document
from . import extraction


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id", "filename", "doc_type", "status", "raw_text", "extracted",
            "flags", "confidence", "journal_entry", "created_at",
        ]
        read_only_fields = [
            "status", "extracted", "flags", "confidence", "journal_entry",
            "created_at",
        ]

    def to_internal_value(self, data):
        # Sanitize OCR text BEFORE field validation — NUL bytes and control
        # chars otherwise 400 a valid document at the DRF/Postgres boundary
        # (ComplianceAI PR #6). Mutate a copy so we don't touch request data.
        if hasattr(data, "copy"):
            data = data.copy()
        if data.get("raw_text"):
            data["raw_text"] = extraction.sanitize_text(data["raw_text"])
        return super().to_internal_value(data)

    def create(self, validated_data):
        organization = self.context["organization"]
        raw_text = validated_data.get("raw_text", "")
        doc_type = validated_data.get("doc_type", Document.DocType.INVOICE)

        fields = extraction.parse_document(raw_text, doc_type)
        flags = extraction.validate_extraction(fields)
        confidence = extraction.extraction_confidence(fields, flags)

        return Document.objects.create(
            organization=organization,
            filename=validated_data.get("filename", "document"),
            doc_type=doc_type,
            raw_text=raw_text,
            extracted=fields,
            flags=flags,
            confidence=confidence,
            status=(
                Document.Status.NEEDS_REVIEW if flags else Document.Status.EXTRACTED
            ),
        )


class DocumentConfirmSerializer(serializers.Serializer):
    """Optional field corrections applied before posting to the ledger."""

    extracted = serializers.JSONField(required=False)
    expense_account = serializers.IntegerField(required=False)
