from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings

from organizations.models import Organization
from ledger.models import Account
from ledger import services
from assistant import analytics, intents
from assistant.services import answer_question


AS_OF = date(2026, 6, 15)  # last complete month = May 2026; prior = April 2026


def make_org(name="Acme"):
    org = Organization.objects.create(name=name, base_currency="SAR")
    A, R = Account.Type, Account.Role
    accs = {
        "cash": Account.objects.create(organization=org, code="1000", name="Cash", type=A.ASSET, role=R.CASH),
        "ar": Account.objects.create(organization=org, code="1100", name="Accounts Receivable", type=A.ASSET, role=R.ACCOUNTS_RECEIVABLE),
        "sales": Account.objects.create(organization=org, code="4000", name="Sales Revenue", type=A.REVENUE),
        "payroll": Account.objects.create(organization=org, code="5000", name="Payroll", type=A.EXPENSE),
        "rent": Account.objects.create(organization=org, code="5100", name="Rent", type=A.EXPENSE),
    }
    return org, accs


def post(org, accs, d, lines):
    services.post_journal_entry(organization=org, date=d, lines=[
        {"account": accs[a], "debit": Decimal(dr), "credit": Decimal(cr)} for a, dr, cr in lines
    ])


class IntentClassificationTests(TestCase):
    def test_each_sample_question_classifies(self):
        cases = {
            "What were my highest expenses last month?": "highest_expenses",
            "Show unpaid invoices older than 60 days": "unpaid_invoices",
            "Give me a cash flow forecast for next quarter": "cashflow_forecast",
            "Explain the change in revenue": "revenue_change",
        }
        for q, expected in cases.items():
            name, fn = intents.classify(q)
            self.assertEqual(name, expected, q)

    def test_unknown_question_returns_no_intent(self):
        name, fn = intents.classify("What is the meaning of life?")
        self.assertIsNone(name)


class HighestExpensesTests(TestCase):
    def test_top_expenses_last_month(self):
        org, accs = make_org()
        post(org, accs, date(2026, 5, 25), [("payroll", "28000", "0"), ("cash", "0", "28000")])
        post(org, accs, date(2026, 5, 26), [("rent", "8000", "0"), ("cash", "0", "8000")])
        res = analytics.highest_expenses(org, as_of=AS_OF)
        self.assertIn("Payroll", res["summary"])
        self.assertIn("28,000", res["summary"])
        self.assertEqual(res["citations"][0]["label"], "Payroll")
        self.assertTrue(len(res["citations"]) >= 2)


class UnpaidInvoiceAgingTests(TestCase):
    def test_fifo_aging_over_60_days(self):
        org, accs = make_org()
        # Old invoice (Feb) 1000, recent invoice (Jun) 500, payment 300 (FIFO → Feb).
        post(org, accs, date(2026, 2, 1), [("ar", "1000", "0"), ("sales", "0", "1000")])
        post(org, accs, date(2026, 6, 1), [("ar", "500", "0"), ("sales", "0", "500")])
        post(org, accs, date(2026, 6, 10), [("cash", "300", "0"), ("ar", "0", "300")])
        res = analytics.unpaid_invoices_older_than(org, days=60, as_of=AS_OF)
        # Feb invoice: 1000 - 300 = 700 remaining, older than cutoff.
        self.assertEqual(res["data"]["overdue_amount"], "700.00")
        self.assertEqual(res["data"]["total_open"], "1200.00")


class CashflowForecastTests(TestCase):
    def test_projects_from_trailing_average(self):
        org, accs = make_org()
        # +1200 net cash in May only → avg over 6 months = 200, quarter = 600.
        post(org, accs, date(2026, 5, 15), [("cash", "1200", "0"), ("sales", "0", "1200")])
        res = analytics.cashflow_forecast(org, as_of=AS_OF, lookback_months=6)
        self.assertEqual(res["data"]["avg_monthly"], "200.00")
        self.assertEqual(res["data"]["projected_quarter"], "600.00")


class RevenueChangeTests(TestCase):
    def test_explains_month_over_month(self):
        org, accs = make_org()
        post(org, accs, date(2026, 4, 10), [("ar", "1000", "0"), ("sales", "0", "1000")])
        post(org, accs, date(2026, 5, 10), [("ar", "1500", "0"), ("sales", "0", "1500")])
        res = analytics.explain_revenue_change(org, as_of=AS_OF)
        self.assertEqual(res["data"]["previous"], "1000.00")
        self.assertEqual(res["data"]["current"], "1500.00")
        self.assertEqual(res["data"]["delta"], "500.00")
        self.assertEqual(res["data"]["pct"], "50.00")
        self.assertIn("increased", res["summary"])


@override_settings(ANTHROPIC_API_KEY="")  # force the templated (grounded) fallback
class AnswerServiceTests(TestCase):
    """End-to-end: questions answered from real data, grounded, with citations."""

    def setUp(self):
        self.org, self.accs = make_org()
        # Anchor data to the last complete month relative to today.
        today = date.today()
        last_month_end = today.replace(day=1) - timedelta(days=1)
        d = last_month_end.replace(day=15)
        post(self.org, self.accs, d, [("payroll", "31000", "0"), ("cash", "0", "31000")])

    def test_answer_is_grounded_with_citations_and_disclaimer(self):
        res = answer_question(self.org, "What were my highest expenses last month?")
        self.assertTrue(res["grounded"])
        self.assertEqual(res["intent"], "highest_expenses")
        self.assertIn("Payroll", res["answer"])
        self.assertIn("31,000", res["answer"])  # real figure, not hallucinated
        self.assertTrue(len(res["citations"]) >= 1)
        self.assertIn("not financial or tax advice", res["disclaimer"])

    def test_unknown_question_offers_help_not_a_hallucination(self):
        res = answer_question(self.org, "Tell me a joke")
        self.assertFalse(res["grounded"])
        self.assertIsNone(res["intent"])
        self.assertEqual(res["citations"], [])

    def test_tenant_isolation_org_a_cannot_see_org_b(self):
        # Org B has its own (much larger) expenses; org A's answer must not cite them.
        org_b, accs_b = make_org(name="Rival Co")
        today = date.today()
        d = (today.replace(day=1) - timedelta(days=1)).replace(day=15)
        post(org_b, accs_b, d, [("payroll", "999999", "0"), ("cash", "0", "999999")])

        res = answer_question(self.org, "What were my highest expenses last month?")
        self.assertIn("31,000", res["answer"])
        self.assertNotIn("999,999", res["answer"])
        # And the reverse direction.
        res_b = answer_question(org_b, "What were my highest expenses last month?")
        self.assertIn("999,999", res_b["answer"])
        self.assertNotIn("31,000", res_b["answer"])
