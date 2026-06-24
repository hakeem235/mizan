from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from organizations.models import Organization
from ledger.models import Account, JournalEntry, Transaction
from ledger import services


def make_org(name="Acme", currency="SAR"):
    return Organization.objects.create(name=name, base_currency=currency)


def accounts(org):
    A = Account.Type
    return {
        "cash": Account.objects.create(organization=org, code="1000", name="Cash", type=A.ASSET, role=Account.Role.CASH),
        "ar": Account.objects.create(organization=org, code="1100", name="AR", type=A.ASSET, role=Account.Role.ACCOUNTS_RECEIVABLE),
        "vat_out": Account.objects.create(organization=org, code="2100", name="VAT Output", type=A.LIABILITY, role=Account.Role.VAT_OUTPUT),
        "sales": Account.objects.create(organization=org, code="4000", name="Sales", type=A.REVENUE),
        "rent": Account.objects.create(organization=org, code="5100", name="Rent", type=A.EXPENSE),
    }


class DoubleEntryTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.acc = accounts(self.org)

    def test_balanced_entry_posts(self):
        entry = services.post_journal_entry(
            organization=self.org, date=date(2026, 1, 5), description="Sale",
            lines=[
                {"account": self.acc["cash"], "debit": Decimal("100"), "credit": 0},
                {"account": self.acc["sales"], "debit": 0, "credit": Decimal("100")},
            ],
        )
        self.assertTrue(entry.is_balanced())
        self.assertEqual(JournalEntry.objects.count(), 1)

    def test_unbalanced_entry_rejected_and_not_persisted(self):
        with self.assertRaises(ValidationError):
            services.post_journal_entry(
                organization=self.org, date=date(2026, 1, 5),
                lines=[
                    {"account": self.acc["cash"], "debit": Decimal("100"), "credit": 0},
                    {"account": self.acc["sales"], "debit": 0, "credit": Decimal("90")},
                ],
            )
        # Nothing written on failure.
        self.assertEqual(JournalEntry.objects.count(), 0)
        self.assertEqual(self.acc["cash"].lines.count(), 0)

    def test_line_must_be_one_sided(self):
        with self.assertRaises(ValidationError):
            services.post_journal_entry(
                organization=self.org, date=date(2026, 1, 5),
                lines=[
                    {"account": self.acc["cash"], "debit": Decimal("100"), "credit": Decimal("100")},
                    {"account": self.acc["sales"], "debit": 0, "credit": Decimal("100")},
                ],
            )

    def test_cross_org_account_rejected(self):
        other = make_org(name="Other")
        other_acc = accounts(other)
        with self.assertRaises(ValidationError):
            services.post_journal_entry(
                organization=self.org, date=date(2026, 1, 5),
                lines=[
                    {"account": self.acc["cash"], "debit": Decimal("100"), "credit": 0},
                    {"account": other_acc["sales"], "debit": 0, "credit": Decimal("100")},
                ],
            )


class BalanceTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.acc = accounts(self.org)

    def test_normal_balance_signs(self):
        self.assertEqual(self.acc["cash"].normal_balance, "debit")
        self.assertEqual(self.acc["sales"].normal_balance, "credit")

    def test_account_balance_positive_on_normal_side(self):
        services.post_journal_entry(
            organization=self.org, date=date(2026, 1, 5),
            lines=[
                {"account": self.acc["cash"], "debit": Decimal("250"), "credit": 0},
                {"account": self.acc["sales"], "debit": 0, "credit": Decimal("250")},
            ],
        )
        self.assertEqual(services.account_balance(self.acc["cash"]), Decimal("250.00"))
        self.assertEqual(services.account_balance(self.acc["sales"]), Decimal("250.00"))

    def test_multicurrency_entry_converts_via_fx_rate(self):
        # 1,000 USD purchase at 3.75 → 3,750 SAR in base currency.
        cogs = Account.objects.create(
            organization=self.org, code="5200", name="COGS", type=Account.Type.EXPENSE
        )
        ap = Account.objects.create(
            organization=self.org, code="2000", name="AP", type=Account.Type.LIABILITY,
            role=Account.Role.ACCOUNTS_PAYABLE,
        )
        entry = services.post_journal_entry(
            organization=self.org, date=date(2026, 1, 5), currency="USD",
            fx_rate=Decimal("3.75"),
            lines=[
                {"account": cogs, "debit": Decimal("1000"), "credit": 0},
                {"account": ap, "debit": 0, "credit": Decimal("1000")},
            ],
        )
        # Balanced in transaction currency.
        self.assertTrue(entry.is_balanced())
        # Reported in base currency.
        self.assertEqual(services.account_balance(cogs), Decimal("3750.00"))
        self.assertEqual(services.account_balance(ap), Decimal("3750.00"))


class CategorizationTests(TestCase):
    def test_keyword_match_high_confidence(self):
        cat, conf = services.categorize_transaction("Monthly payroll run")
        self.assertEqual(cat, "Payroll")
        self.assertEqual(conf, Decimal("0.95"))

    def test_arabic_keyword_match(self):
        cat, _ = services.categorize_transaction("إيجار المكتب")
        self.assertEqual(cat, "Rent")

    def test_unknown_low_confidence(self):
        cat, conf = services.categorize_transaction("Zxqv random memo")
        self.assertEqual(cat, "Uncategorized")
        self.assertEqual(conf, Decimal("0.30"))


class DuplicateDetectionTests(TestCase):
    def setUp(self):
        self.org = make_org()

    def test_duplicate_transaction_flagged(self):
        first = services.ingest_transaction(
            organization=self.org, date=date(2026, 1, 10),
            description="Payroll run - April", amount=Decimal("-28000.00"),
        )
        dup = services.ingest_transaction(
            organization=self.org, date=date(2026, 1, 10),
            description="Payroll run - April", amount=Decimal("-28000.00"),
        )
        self.assertFalse(first.is_duplicate)
        self.assertTrue(dup.is_duplicate)
        self.assertEqual(dup.duplicate_of_id, first.id)
        self.assertEqual(dup.status, Transaction.Status.FLAGGED)

    def test_non_duplicate_not_flagged(self):
        services.ingest_transaction(
            organization=self.org, date=date(2026, 1, 10),
            description="Payroll run - April", amount=Decimal("-28000.00"),
        )
        other = services.ingest_transaction(
            organization=self.org, date=date(2026, 1, 10),
            description="Office rent", amount=Decimal("-8000.00"),
        )
        self.assertFalse(other.is_duplicate)


class DashboardTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.acc = accounts(self.org)
        # One sale this month: 1,000 net + 150 VAT, partially collected.
        services.post_journal_entry(
            organization=self.org, date=date.today().replace(day=6),
            description="Sale",
            lines=[
                {"account": self.acc["ar"], "debit": Decimal("1150"), "credit": 0},
                {"account": self.acc["sales"], "debit": 0, "credit": Decimal("1000")},
                {"account": self.acc["vat_out"], "debit": 0, "credit": Decimal("150")},
            ],
        )
        services.post_journal_entry(
            organization=self.org, date=date.today().replace(day=7),
            description="Partial payment",
            lines=[
                {"account": self.acc["cash"], "debit": Decimal("400"), "credit": 0},
                {"account": self.acc["ar"], "debit": 0, "credit": Decimal("400")},
            ],
        )
        services.post_journal_entry(
            organization=self.org, date=date.today().replace(day=8),
            description="Rent",
            lines=[
                {"account": self.acc["rent"], "debit": Decimal("300"), "credit": 0},
                {"account": self.acc["cash"], "debit": 0, "credit": Decimal("300")},
            ],
        )

    def test_aggregates_match_ledger(self):
        s = services.dashboard_summary(self.org)
        self.assertEqual(s["kpis"]["revenue"], Decimal("1000.00"))
        self.assertEqual(s["kpis"]["expenses"], Decimal("300.00"))
        # Cash: +400 collected, -300 rent = +100 net movement.
        self.assertEqual(s["kpis"]["net_cash_flow"], Decimal("100.00"))
        # AR: 1150 billed - 400 collected = 750 outstanding.
        self.assertEqual(s["kpis"]["outstanding_invoices"], Decimal("750.00"))
        self.assertEqual(s["kpis"]["vat_payable"], Decimal("150.00"))

    def test_tenant_isolation_in_aggregates(self):
        # A second org with its own sale must not bleed into the first's figures.
        other = make_org(name="Other Co")
        oacc = accounts(other)
        services.post_journal_entry(
            organization=other, date=date.today().replace(day=6),
            lines=[
                {"account": oacc["cash"], "debit": Decimal("99999"), "credit": 0},
                {"account": oacc["sales"], "debit": 0, "credit": Decimal("99999")},
            ],
        )
        s = services.dashboard_summary(self.org)
        self.assertEqual(s["kpis"]["revenue"], Decimal("1000.00"))
