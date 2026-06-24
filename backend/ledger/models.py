"""
Double-entry ledger data model.

Design notes:
- Every record is scoped to an Organization (tenant boundary).
- A JournalEntry is a balanced voucher: the sum of its line debits must equal
  the sum of its line credits, in the entry's transaction currency. Balance is
  enforced in `ledger.services.post_journal_entry` (and re-checked by the
  serializer) — unbalanced entries are rejected, never persisted as posted.
- Multi-currency: each entry carries a `currency` and an `fx_rate` back to the
  org's base currency. Reports reconcile in base currency = amount * fx_rate.
- Money is stored as Decimal (never float) to keep accounting math exact.
"""

from decimal import Decimal

from django.db import models

from organizations.models import Organization

TWO_PLACES = Decimal("0.01")


class Account(models.Model):
    class Type(models.TextChoices):
        ASSET = "asset", "Asset"
        LIABILITY = "liability", "Liability"
        EQUITY = "equity", "Equity"
        REVENUE = "revenue", "Revenue"
        EXPENSE = "expense", "Expense"

    class Role(models.TextChoices):
        GENERIC = "generic", "Generic"
        CASH = "cash", "Cash / Bank"
        ACCOUNTS_RECEIVABLE = "accounts_receivable", "Accounts Receivable"
        ACCOUNTS_PAYABLE = "accounts_payable", "Accounts Payable"
        VAT_OUTPUT = "vat_output", "VAT Output (collected)"
        VAT_INPUT = "vat_input", "VAT Input (paid)"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="accounts"
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=Type.choices)
    # Optional semantic role used by dashboard/report aggregates (AR, VAT, etc.).
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.GENERIC)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("organization", "code")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} · {self.name}"

    @property
    def normal_balance(self):
        """Side that increases this account: assets/expenses are debit-normal."""
        return "debit" if self.type in (self.Type.ASSET, self.Type.EXPENSE) else "credit"


class JournalEntry(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="journal_entries"
    )
    date = models.DateField()
    description = models.CharField(max_length=300, blank=True)
    currency = models.CharField(max_length=3, default="SAR")
    # Rate to convert the entry currency into the org base currency.
    fx_rate = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("1"))
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.POSTED
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name_plural = "journal entries"

    def __str__(self):
        return f"JE#{self.pk} {self.date} {self.description}".strip()

    def total_debits(self):
        return sum((line.debit for line in self.lines.all()), Decimal("0"))

    def total_credits(self):
        return sum((line.credit for line in self.lines.all()), Decimal("0"))

    def is_balanced(self):
        return self.total_debits().quantize(TWO_PLACES) == self.total_credits().quantize(
            TWO_PLACES
        )


class JournalLine(models.Model):
    """One debit-or-credit posting against an account, in the entry currency."""

    entry = models.ForeignKey(
        JournalEntry, on_delete=models.CASCADE, related_name="lines"
    )
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="lines"
    )
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

    def __str__(self):
        side = f"Dr {self.debit}" if self.debit else f"Cr {self.credit}"
        return f"{self.account.code} {side}"


class Transaction(models.Model):
    """
    A raw bank/feed transaction awaiting AI bookkeeping: auto-categorization,
    duplicate/suspicious detection, and (once confirmed) posting to the ledger.
    Distinct from JournalEntry, which is the confirmed accounting record.
    """

    class Status(models.TextChoices):
        UNCATEGORIZED = "uncategorized", "Uncategorized"
        CATEGORIZED = "categorized", "AI-categorized"
        APPROVED = "approved", "Approved"
        FLAGGED = "flagged", "Flagged"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="transactions"
    )
    date = models.DateField()
    description = models.CharField(max_length=300)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3, default="SAR")

    category = models.CharField(max_length=100, blank=True)
    confidence = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("0")
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.UNCATEGORIZED
    )

    # Duplicate/suspicious detection.
    is_duplicate = models.BooleanField(default=False)
    duplicate_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="duplicates"
    )
    # Stable fingerprint (org+date+amount+normalized desc) used to spot repeats.
    fingerprint = models.CharField(max_length=64, db_index=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.date} {self.description} {self.amount}"
