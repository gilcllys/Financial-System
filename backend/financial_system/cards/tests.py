from datetime import date as real_date
from types import SimpleNamespace
from unittest.mock import patch

from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from cards.behaviors import (
    InvoiceExpensesBehavior,
    _compute_invoice_period,
    _current_invoice_month,
)
from cards.models import CreditCard
from catalog.models import ExpenseCategory
from expenses.models import Expense


class InvoicePeriodTests(SimpleTestCase):
    def test_uses_previous_friday_when_closing_day_is_saturday(self):
        card = SimpleNamespace(closing_day=26, due_day=10)

        period_start, period_end, due = _compute_invoice_period(card, 10, 2026)

        self.assertEqual(period_start, real_date(2026, 8, 27))
        self.assertEqual(period_end, real_date(2026, 9, 25))
        self.assertEqual(due, real_date(2026, 10, 10))

    def test_uses_previous_friday_when_closing_day_is_sunday(self):
        card = SimpleNamespace(closing_day=26, due_day=10)

        period_start, period_end, due = _compute_invoice_period(card, 5, 2026)

        self.assertEqual(period_start, real_date(2026, 3, 27))
        self.assertEqual(period_end, real_date(2026, 4, 24))
        self.assertEqual(due, real_date(2026, 5, 10))

    def test_clamps_invalid_month_days_before_adjusting_weekends(self):
        card = SimpleNamespace(closing_day=31, due_day=31)

        period_start, period_end, due = _compute_invoice_period(card, 3, 2026)

        self.assertEqual(period_start, real_date(2026, 1, 31))
        self.assertEqual(period_end, real_date(2026, 2, 27))
        self.assertEqual(due, real_date(2026, 3, 31))

    def test_current_invoice_advances_after_effective_closing_date(self):
        card = SimpleNamespace(closing_day=26)

        class FixedDate(real_date):
            @classmethod
            def today(cls):
                return cls(2026, 9, 26)

        with patch('cards.behaviors.date', FixedDate):
            self.assertEqual(_current_invoice_month(card), (11, 2026))


# ---------------------------------------------------------------------------
# Regressao: credito na fatura deve ABATER, nao somar
# ---------------------------------------------------------------------------


class InvoiceCreditSignTests(TestCase):
    """
    O extrato do banco desconta creditos/estornos do total da fatura.

    Antes desta regressao o total usava Sum(Abs('amount')), entao um credito
    (amount > 0) era somado como se fosse mais um gasto: lancar um estorno de
    R$ 41,61 aumentava a fatura em vez de reduzi-la.
    """

    TENANT = 'tenant-credit-test'

    def setUp(self):
        self.category = ExpenseCategory.objects.create(
            tenant_id=self.TENANT, name='Diversos'
        )
        self.card = CreditCard.objects.create(
            tenant_id=self.TENANT, name='Bradesco',
            due_day=1, closing_day=21, last_four_digits='0000',
        )

    def _expense(self, amount, description='Gasto'):
        return Expense.objects.create(
            tenant_id=self.TENANT, category=self.category, credit_card=self.card,
            description=description, quantity=1,
            amount=Decimal(amount), date=real_date(2026, 8, 10),
            payment_method='cartao',
        )

    def _summary(self):
        behavior = InvoiceExpensesBehavior(
            card=self.card, invoice_month=9, invoice_year=2026,
        )
        return behavior.run().data['summary']

    def test_credit_reduces_invoice_total(self):
        self._expense('-100.00')
        self._expense('40.00', description='[CREDITO] - Estorno')
        self.assertEqual(self._summary()['expenses_total'], 60.00)

    def test_only_debits_keeps_total_positive(self):
        self._expense('-100.00')
        self._expense('-50.00')
        self.assertEqual(self._summary()['expenses_total'], 150.00)

    def test_credit_is_excluded_from_category_breakdown(self):
        self._expense('-100.00')
        self._expense('40.00', description='[CREDITO] - Estorno')
        behavior = InvoiceExpensesBehavior(
            card=self.card, invoice_month=9, invoice_year=2026,
        )
        by_category = behavior.run().data['by_category']
        self.assertEqual(len(by_category), 1)
        self.assertEqual(by_category[0]['total'], 100.00)
        self.assertEqual(by_category[0]['percentage'], 100.00)
