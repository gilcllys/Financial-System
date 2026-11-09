from datetime import date as real_date
from types import SimpleNamespace
from unittest.mock import patch

from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from cards.behaviors import (
    CreditCardInvoiceViewBehavior,
    InvoiceExpensesBehavior,
    OpenInvoicesBehavior,
    compute_invoice_period,
    current_invoice_month,
)
from cards.models import CreditCard
from catalog.models import ExpenseCategory
from debts.models import (
    SharedDebt, SharedDebtMember, SharedEntry, SharedEntryParticipant,
    SharedRecurringTemplate,
)
from expenses.models import Expense


class InvoicePeriodTests(SimpleTestCase):
    def test_uses_previous_friday_when_closing_day_is_saturday(self):
        card = SimpleNamespace(closing_day=26, due_day=10)

        period_start, period_end, due = compute_invoice_period(card, 10, 2026)

        self.assertEqual(period_start, real_date(2026, 8, 27))
        self.assertEqual(period_end, real_date(2026, 9, 25))
        self.assertEqual(due, real_date(2026, 10, 10))

    def test_uses_previous_friday_when_closing_day_is_sunday(self):
        card = SimpleNamespace(closing_day=26, due_day=10)

        period_start, period_end, due = compute_invoice_period(card, 5, 2026)

        self.assertEqual(period_start, real_date(2026, 3, 27))
        self.assertEqual(period_end, real_date(2026, 4, 24))
        self.assertEqual(due, real_date(2026, 5, 10))

    def test_clamps_invalid_month_days_before_adjusting_weekends(self):
        card = SimpleNamespace(closing_day=31, due_day=31)

        period_start, period_end, due = compute_invoice_period(card, 3, 2026)

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
            self.assertEqual(current_invoice_month(card), (11, 2026))

    def test_current_invoice_accepts_reference_date_for_historical_calculations(self):
        card = SimpleNamespace(closing_day=21)
        self.assertEqual(current_invoice_month(card, real_date(2026, 9, 28)), (11, 2026))


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


class SharedCategoryBreakdownTests(TestCase):
    TENANT = 'tenant-shared-category'

    def setUp(self):
        self.card = CreditCard.objects.create(
            tenant_id=self.TENANT, name='Azul', due_day=3,
            closing_day=25, last_four_digits='9225',
        )
        self.individual_category = ExpenseCategory.objects.create(
            tenant_id=self.TENANT, name='Gastos com carro',
        )
        self.clothes_category = ExpenseCategory.objects.create(
            tenant_id=self.TENANT, name='Roupas',
        )
        self.shared_category = ExpenseCategory.objects.create(
            tenant_id=self.TENANT, name='Compras para casa',
        )
        self.transport_category = ExpenseCategory.objects.create(
            tenant_id=self.TENANT, name='Transporte',
        )
        self.group = SharedDebt.objects.create(
            name='Casa', owner_tenant_id=self.TENANT,
        )
        self.payer = SharedDebtMember.objects.create(
            shared_debt=self.group, tenant_id=self.TENANT, display_name='Eu',
        )
        self.other = SharedDebtMember.objects.create(
            shared_debt=self.group, tenant_id='other-tenant', display_name='Outra pessoa',
        )

    def _shared(self, amount, date, paid_by, category):
        return SharedEntry.objects.create(
            shared_debt=self.group, paid_by=paid_by, description='Compra compartilhada',
            amount=Decimal(amount), date=date, payment_method='cartao',
            credit_card=self.card, category=category,
            created_by_tenant_id=self.TENANT,
        )

    def test_category_chart_sums_individual_and_full_shared_invoice_amounts(self):
        Expense.objects.create(
            tenant_id=self.TENANT, category=self.individual_category,
            credit_card=self.card, description='Compra individual', quantity=1,
            amount=Decimal('-617.66'), date=real_date(2026, 11, 10),
            payment_method='cartao',
        )
        Expense.objects.create(
            tenant_id=self.TENANT, category=self.clothes_category,
            credit_card=self.card, description='Roupa individual', quantity=1,
            amount=Decimal('-449.58'), date=real_date(2026, 11, 10),
            payment_method='cartao',
        )
        self._shared('243.72', real_date(2026, 11, 14), self.payer, self.individual_category)
        self._shared('206.39', real_date(2026, 11, 14), self.payer, self.shared_category)
        self._shared('122.69', real_date(2026, 11, 14), self.payer, self.transport_category)
        self._shared('1000.00', real_date(2026, 11, 14), self.other, self.shared_category)
        self._shared('500.00', real_date(2026, 11, 26), self.payer, self.shared_category)

        data = InvoiceExpensesBehavior(
            card=self.card, invoice_month=12, invoice_year=2026,
        ).run().data
        by_name = {row['category_name']: row for row in data['by_category']}

        self.assertEqual(by_name['Gastos com carro']['total'], 861.38)
        self.assertEqual(by_name['Compras para casa']['total'], 206.39)
        self.assertEqual(by_name['Transporte']['total'], 122.69)
        self.assertEqual(by_name['Roupas']['total'], 449.58)
        self.assertEqual(sum(row['total'] for row in data['by_category']), 1640.04)
        self.assertAlmostEqual(sum(row['percentage'] for row in data['by_category']), 100.0, places=1)


# ---------------------------------------------------------------------------
# Faturas abertas (Home): compartilhado entra no MESMO range da fatura
# ---------------------------------------------------------------------------


class _FixedToday(real_date):
    """2026-08-10: fatura corrente do cartão (fecha dia 21) é Setembro/2026,
    período 22/07 → 21/08."""

    @classmethod
    def today(cls):
        return cls(2026, 8, 10)


class OpenInvoicesSharedTests(TestCase):
    TENANT = 'tenant-open-inv'
    OTHER = 'tenant-other'

    def setUp(self):
        self.card = CreditCard.objects.create(
            tenant_id=self.TENANT, name='Nubank',
            due_day=1, closing_day=21, last_four_digits='1234',
        )
        self.category = ExpenseCategory.objects.create(
            tenant_id=self.TENANT, name='Diversos'
        )
        self.group = SharedDebt.objects.create(name='Casa', owner_tenant_id=self.TENANT)
        self.me = SharedDebtMember.objects.create(
            shared_debt=self.group, tenant_id=self.TENANT, display_name='Eu'
        )
        self.other = SharedDebtMember.objects.create(
            shared_debt=self.group, tenant_id=self.OTHER, display_name='Ana'
        )

    def _expense(self, amount, day):
        return Expense.objects.create(
            tenant_id=self.TENANT, category=self.category, credit_card=self.card,
            description='Gasto', quantity=1, amount=Decimal(amount),
            date=real_date(2026, 8, day), payment_method='cartao',
        )

    def _shared(self, amount, entry_date, paid_by=None, card=True):
        entry = SharedEntry.objects.create(
            shared_debt=self.group, paid_by=paid_by or self.me,
            description='Compartilhado', amount=Decimal(amount), date=entry_date,
            payment_method='cartao', credit_card=self.card if card else None,
            created_by_tenant_id=self.TENANT,
        )
        for m in (self.me, self.other):
            SharedEntryParticipant.objects.create(entry=entry, member=m)
        return entry

    def _run(self, closing_month=None, closing_year=None):
        with patch('cards.behaviors.date', _FixedToday):
            rows = OpenInvoicesBehavior(
                self.TENANT, closing_month, closing_year,
            ).run().data
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_period_matches_invoice_window(self):
        row = self._run()
        self.assertEqual(row['invoice_month'], 9)
        self.assertEqual(row['period_start'], '2026-07-22')
        self.assertEqual(row['period_end'], '2026-08-21')

    def test_selected_closing_month_maps_to_invoice_due_next_month(self):
        Expense.objects.create(
            tenant_id=self.TENANT, category=self.category, credit_card=self.card,
            description='Dentro do ciclo', quantity=1, amount=Decimal('-22.00'),
            date=real_date(2026, 7, 10), payment_method='cartao',
        )
        Expense.objects.create(
            tenant_id=self.TENANT, category=self.category, credit_card=self.card,
            description='Após fechamento', quantity=1, amount=Decimal('-99.00'),
            date=real_date(2026, 7, 22), payment_method='cartao',
        )

        row = self._run(closing_month=7, closing_year=2026)

        self.assertEqual(row['invoice_month'], 8)
        self.assertEqual(row['period_start'], '2026-06-20')
        self.assertEqual(row['period_end'], '2026-07-21')
        self.assertEqual(row['due_date'], '2026-08-01')
        self.assertEqual(row['expenses_total'], 22.00)

    def test_total_is_gross_individual_plus_full_shared(self):
        self._expense('-100.00', 10)
        self._shared('200.00', real_date(2026, 8, 10))

        row = self._run()

        self.assertEqual(row['expenses_total'], 100.00)
        self.assertEqual(row['shared_gross_total'], 200.00)
        self.assertEqual(row['shared_total'], 100.00)   # minha metade
        self.assertEqual(row['total'], 300.00)          # o que o banco cobra
        self.assertEqual(row['shared_groups'], [{
            'group_id': self.group.id, 'group_name': 'Casa',
            'total': 200.00, 'my_portion': 100.00,
        }])

    def test_shared_outside_invoice_window_is_excluded(self):
        self._shared('999.00', real_date(2026, 7, 21))   # fechamento anterior
        self._shared('999.00', real_date(2026, 8, 22))   # já é da próxima fatura
        self._shared('50.00', real_date(2026, 7, 22))    # primeiro dia do período

        row = self._run()

        self.assertEqual(row['shared_gross_total'], 50.00)
        self.assertEqual(row['total'], 50.00)

    def test_shared_paid_by_someone_else_or_in_cash_is_excluded(self):
        self._shared('80.00', real_date(2026, 8, 5), paid_by=self.other)
        self._shared('70.00', real_date(2026, 8, 5), card=False)

        row = self._run()

        self.assertEqual(row['shared_gross_total'], 0.0)
        self.assertEqual(row['shared_groups'], [])
        self.assertEqual(row['total'], 0.0)


class AnnualInvoiceTotalsSharedTests(TestCase):
    TENANT = 'tenant-annual-invoice'
    OTHER_TENANT = 'tenant-annual-other'

    def setUp(self):
        self.card = CreditCard.objects.create(
            tenant_id=self.TENANT, name='Cartao anual', due_day=1,
            closing_day=21, last_four_digits='4321',
        )
        self.category = ExpenseCategory.objects.create(
            tenant_id=self.TENANT, name='Casa anual'
        )
        self.group = SharedDebt.objects.create(
            name='Grupo anual', owner_tenant_id=self.TENANT,
        )
        self.me = SharedDebtMember.objects.create(
            shared_debt=self.group, tenant_id=self.TENANT, display_name='Eu'
        )
        self.other = SharedDebtMember.objects.create(
            shared_debt=self.group, tenant_id=self.OTHER_TENANT, display_name='Outra pessoa'
        )

    def test_anual_soma_compartilhados_no_periodo_da_fatura(self):
        period_start = real_date(2026, 1, 22)
        period_end = real_date(2026, 2, 20)
        Expense.objects.create(
            tenant_id=self.TENANT, category=self.category, credit_card=self.card,
            description='Individual', quantity=1, amount=Decimal('-100.00'),
            date=real_date(2026, 2, 3), payment_method='cartao',
        )
        SharedEntry.objects.create(
            shared_debt=self.group, paid_by=self.me, description='Dentro da fatura',
            amount=Decimal('200.00'), date=real_date(2026, 2, 4),
            payment_method='cartao', credit_card=self.card,
            created_by_tenant_id=self.TENANT,
        )
        SharedEntry.objects.create(
            shared_debt=self.group, paid_by=self.other, description='Pago por outra pessoa',
            amount=Decimal('500.00'), date=real_date(2026, 2, 4),
            payment_method='cartao', credit_card=self.card,
            created_by_tenant_id=self.TENANT,
        )
        SharedEntry.objects.create(
            shared_debt=self.group, paid_by=self.me, description='Fora da fatura',
            amount=Decimal('700.00'), date=real_date(2026, 2, 21),
            payment_method='cartao', credit_card=self.card,
            created_by_tenant_id=self.TENANT,
        )

        totals = CreditCardInvoiceViewBehavior(
            self.card, request=None, params={},
        )._annual_totals(
            [{
                'invoice_month': 2,
                'invoice_year': 2026,
                'period_start': period_start.isoformat(),
                'period_end': period_end.isoformat(),
            }],
            {'invoice_year': 2026},
        )

        self.assertEqual(totals[1], 300.00)
        self.assertEqual(sum(totals), 300.00)


class CreditCardDeleteEndpointTests(TestCase):
    """
    Trava do comportamento de delete antes de remover o perform_destroy.

    O get_queryset ja filtra por tenant, entao o cartao alheio nunca chega ao
    perform_destroy: o get_object() levanta 404 antes. Estes testes provam que
    o 404 vem do queryset, nao da guarda.
    """

    TENANT = 'tenant-cards-1'
    OTHER_TENANT = 'tenant-cards-2'
    URL = '/api/cards/credit-cards/'

    def setUp(self):
        from rest_framework.test import APIClient
        from financial_system.authentication import KeycloakPrincipal

        self.client = APIClient()
        self.client.force_authenticate(user=KeycloakPrincipal({
            'sub': self.TENANT, 'email': 'c@example.com',
            'given_name': 'C', 'family_name': 'D',
        }))

    def _card(self, name='Cartao', tenant=None):
        return CreditCard.objects.create(
            tenant_id=tenant or self.TENANT,
            name=name,
            due_day=10,
            closing_day=3,
            last_four_digits='1234',
        )

    def test_delete_do_proprio_cartao_funciona(self):
        card = self._card()
        resp = self.client.delete(f'{self.URL}{card.id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(CreditCard.objects.filter(id=card.id).exists())

    def test_delete_pausa_template_compartilhado_antes_de_remover_cartao(self):
        card = self._card()
        group = SharedDebt.objects.create(
            name='Grupo recorrente', owner_tenant_id=self.TENANT,
        )
        payer = SharedDebtMember.objects.create(
            shared_debt=group, tenant_id=self.TENANT, display_name='Eu'
        )
        template = SharedRecurringTemplate.objects.create(
            shared_debt=group,
            description='Aluguel',
            amount=Decimal('1000.00'),
            paid_by=payer,
            participant_ids=[payer.id],
            payment_method='cartao',
            credit_card=card,
            is_active=True,
        )

        resp = self.client.delete(f'{self.URL}{card.id}/')

        self.assertEqual(resp.status_code, 204)
        template.refresh_from_db()
        self.assertFalse(template.is_active)
        self.assertIsNone(template.credit_card_id)

    def test_delete_de_cartao_de_outro_tenant_retorna_404(self):
        alheio = self._card('Alheio', tenant=self.OTHER_TENANT)
        resp = self.client.delete(f'{self.URL}{alheio.id}/')
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(CreditCard.objects.filter(id=alheio.id).exists())
