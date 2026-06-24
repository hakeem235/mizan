from datetime import date
from decimal import Decimal

from django.test import TestCase

from organizations.models import Organization
from ledger.models import Account, JournalEntry
from documents.models import Document
from documents import extraction


CLEAN_INVOICE = """
Vendor: Gulf Office Supplies
Invoice Number: INV-2026-0042
Date: 2026-05-12
VAT Number: 300000000000003
Subtotal: 1,000.00
VAT: 150.00
Total: 1150.00
"""

# Subtotal + VAT != Total, and VAT is not 15%.
INCONSISTENT_INVOICE = """
Vendor: Dodgy Traders
Invoice Number: X-1
Date: 2026-05-12
Subtotal: 1000.00
VAT: 90.00
Total: 1300.00
"""


def org_with_accounts():
    org = Organization.objects.create(name="Acme", base_currency="SAR")
    A, R = Account.Type, Account.Role
    Account.objects.create(organization=org, code="5200", name="Office Expense", type=A.EXPENSE)
    Account.objects.create(organization=org, code="1300", name="VAT Input", type=A.ASSET, role=R.VAT_INPUT)
    Account.objects.create(organization=org, code="2000", name="AP", type=A.LIABILITY, role=R.ACCOUNTS_PAYABLE)
    return org


class SanitizeTests(TestCase):
    def test_strips_nul_and_control_chars(self):
        dirty = "Total:\x00 1150\x07.00\x1f"
        clean = extraction.sanitize_text(dirty)
        self.assertNotIn("\x00", clean)
        self.assertNotIn("\x07", clean)
        self.assertEqual(clean, "Total: 1150.00")

    def test_preserves_newlines_and_tabs(self):
        self.assertEqual(extraction.sanitize_text("a\tb\nc"), "a\tb\nc")


class ParseTests(TestCase):
    def test_parses_core_fields(self):
        f = extraction.parse_document(CLEAN_INVOICE)
        self.assertEqual(f["invoice_number"], "INV-2026-0042")
        self.assertEqual(f["date"], "2026-05-12")
        self.assertEqual(f["vat_number"], "300000000000003")
        self.assertEqual(f["subtotal"], "1000.00")
        self.assertEqual(f["vat_amount"], "150.00")
        self.assertEqual(f["total"], "1150.00")


class ValidationTests(TestCase):
    def test_clean_invoice_has_no_flags(self):
        f = extraction.parse_document(CLEAN_INVOICE)
        self.assertEqual(extraction.validate_extraction(f), [])

    def test_totals_mismatch_flagged(self):
        f = extraction.parse_document(INCONSISTENT_INVOICE)
        msgs = [fl["message"] for fl in extraction.validate_extraction(f)]
        self.assertTrue(any("don't add up" in m for m in msgs))

    def test_vat_not_15_percent_flagged(self):
        f = extraction.parse_document(INCONSISTENT_INVOICE)
        fields = [fl["field"] for fl in extraction.validate_extraction(f)]
        self.assertIn("vat_amount", fields)

    def test_missing_vat_number_flagged(self):
        f = extraction.parse_document(INCONSISTENT_INVOICE)
        fields = [fl["field"] for fl in extraction.validate_extraction(f)]
        self.assertIn("vat_number", fields)

    def test_future_date_flagged(self):
        future = date.today().replace(year=date.today().year + 1).isoformat()
        flags = extraction.validate_extraction({
            "subtotal": "100.00", "vat_amount": "15.00", "total": "115.00",
            "vat_number": "300000000000003", "date": future,
        })
        self.assertTrue(any(f["field"] == "date" and f["severity"] == "danger"
                            for f in flags))


class IngestAndPostTests(TestCase):
    def setUp(self):
        self.org = org_with_accounts()

    def _create(self, text, **ctx):
        from documents.serializers import DocumentSerializer
        s = DocumentSerializer(
            data={"filename": "inv.png", "doc_type": "invoice", "raw_text": text},
            context={"organization": self.org},
        )
        s.is_valid(raise_exception=True)
        return s.save()

    def test_clean_invoice_extracted_status(self):
        doc = self._create(CLEAN_INVOICE)
        self.assertEqual(doc.status, Document.Status.EXTRACTED)
        self.assertEqual(doc.flags, [])

    def test_inconsistent_doc_is_flagged_not_silently_accepted(self):
        doc = self._create(INCONSISTENT_INVOICE)
        self.assertEqual(doc.status, Document.Status.NEEDS_REVIEW)
        self.assertTrue(len(doc.flags) > 0)

    def test_confirm_posts_balanced_entry_to_ledger(self):
        doc = self._create(CLEAN_INVOICE)
        entry = extraction.post_document_to_ledger(doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.POSTED)
        self.assertEqual(doc.journal_entry_id, entry.id)
        self.assertTrue(entry.is_balanced())
        # Dr expense 1000 + Dr VAT 150 = Cr AP 1150.
        self.assertEqual(entry.total_debits(), Decimal("1150.00"))
        self.assertEqual(JournalEntry.objects.filter(organization=self.org).count(), 1)

    def test_nul_bytes_in_payload_do_not_break_creation(self):
        doc = self._create(CLEAN_INVOICE.replace("Total", "T\x00otal"))
        self.assertNotIn("\x00", doc.raw_text)
        self.assertEqual(doc.status, Document.Status.EXTRACTED)
