"""
Document ingestion: an uploaded financial document (invoice, receipt, PO, bank
statement) whose text is OCR-extracted client-side, parsed into structured
fields server-side, validated for inconsistencies, and — once the user confirms
— posted to the ledger as a balanced journal entry.

The original binary is not stored (no object-storage credential in this phase);
we keep the extracted text, the parsed fields, and the validation flags.
"""

from decimal import Decimal

from django.db import models

from organizations.models import Organization


class Document(models.Model):
    class DocType(models.TextChoices):
        INVOICE = "invoice", "Invoice"
        RECEIPT = "receipt", "Receipt"
        PURCHASE_ORDER = "purchase_order", "Purchase Order"
        BANK_STATEMENT = "bank_statement", "Bank Statement"

    class Status(models.TextChoices):
        EXTRACTED = "extracted", "Extracted"
        NEEDS_REVIEW = "needs_review", "Needs Review"  # has inconsistency flags
        CONFIRMED = "confirmed", "Confirmed"
        POSTED = "posted", "Posted to ledger"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="documents"
    )
    filename = models.CharField(max_length=255)
    doc_type = models.CharField(
        max_length=20, choices=DocType.choices, default=DocType.INVOICE
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.EXTRACTED
    )

    raw_text = models.TextField(blank=True)
    # Parsed fields: vendor, invoice_number, date, subtotal, vat_amount, total,
    # currency, vat_number (kept as JSON so the schema can evolve per doc type).
    extracted = models.JSONField(default=dict, blank=True)
    # List of {field, message, severity} inconsistency flags.
    flags = models.JSONField(default=list, blank=True)
    confidence = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("0")
    )

    journal_entry = models.ForeignKey(
        "ledger.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_documents",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.get_doc_type_display()} · {self.filename}"
