from datetime import date as real_date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from cards.behaviors import _compute_invoice_period, _current_invoice_month


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
