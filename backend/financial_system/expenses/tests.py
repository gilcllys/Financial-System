from unittest.mock import MagicMock, patch
from datetime import date as real_date
from django.test import SimpleTestCase, RequestFactory, TestCase
from rest_framework.request import Request
from expenses.viewsets import ExpensePagination, ExpenseViewSet
from expenses.serializer import DeleteInstallmentsInputSerializer
from decimal import Decimal
from expenses.behaviors import (
    CreateExpenseBehavior,
    _split_installments,
    _strip_installment_suffix,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(query_params: dict, tenant_id: str = 'tenant-abc') -> Request:
    """Builds a DRF Request wrapping a Django GET request."""
    factory = RequestFactory()
    path = '/api/expenses/expenses/'
    django_request = factory.get(path, query_params)
    drf_request = Request(django_request)
    # Inject a minimal user object that carries tenant_id
    user = MagicMock()
    user.tenant_id = tenant_id
    drf_request._user = user  # bypass authentication
    return drf_request


class _FakeQS:
    """Minimal queryset double that records chained filter/order_by calls."""

    def __init__(self, items=None, _filters=None, _order=None):
        self._items = items or []
        self._filters = _filters or []
        self._order = _order

    # DRF / Django queryset interface used by viewset ----------------------

    def filter(self, **kwargs):
        return _FakeQS(self._items, self._filters + [kwargs], self._order)

    def select_related(self, *args):
        # No-op in tests: relationships are not traversed in unit tests.
        return self

    def order_by(self, *args):
        return _FakeQS(self._items, self._filters, args)

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)

    # Introspection helpers ------------------------------------------------

    def has_filter(self, **kwargs):
        return any(
            all(f.get(k) == v for k, v in kwargs.items())
            for f in self._filters
        )


# ---------------------------------------------------------------------------
# ExpensePagination
# ---------------------------------------------------------------------------

class ExpensePaginationConfigTest(SimpleTestCase):

    def test_default_page_size_is_20(self):
        self.assertEqual(ExpensePagination.page_size, 20)

    def test_max_page_size_is_100(self):
        self.assertEqual(ExpensePagination.max_page_size, 100)

    def test_page_size_query_param(self):
        self.assertEqual(ExpensePagination.page_size_query_param, 'page_size')

    def test_page_query_param(self):
        self.assertEqual(ExpensePagination.page_query_param, 'page')


# ---------------------------------------------------------------------------
# ExpenseViewSet.get_queryset — filter logic
# ---------------------------------------------------------------------------

class ExpenseViewSetFilterTest(SimpleTestCase):
    """
    Tests for the server-side filtering in get_queryset().
    Uses a fake queryset so no database is required.
    """

    def _build_viewset(self, query_params: dict) -> ExpenseViewSet:
        vs = ExpenseViewSet()
        vs.request = _make_request(query_params)
        vs.format_kwarg = None
        vs.kwargs = {}
        return vs

    def _get_qs(self, query_params: dict) -> _FakeQS:
        """Runs get_queryset() with a patched ORM base queryset."""
        vs = self._build_viewset(query_params)
        base_qs = _FakeQS()
        with patch('expenses.models.Expense.objects') as mock_objects:
            mock_objects.filter.return_value = base_qs
            result = vs.get_queryset()
        return result

    # --- ordering --------------------------------------------------------

    def test_default_ordering_applied(self):
        qs = self._get_qs({})
        self.assertEqual(qs._order, ('-date', '-id'))

    # --- month -----------------------------------------------------------

    def test_filter_by_valid_month(self):
        qs = self._get_qs({'month': '6'})
        self.assertTrue(qs.has_filter(date__month=6))

    def test_filter_month_boundary_1(self):
        qs = self._get_qs({'month': '1'})
        self.assertTrue(qs.has_filter(date__month=1))

    def test_filter_month_boundary_12(self):
        qs = self._get_qs({'month': '12'})
        self.assertTrue(qs.has_filter(date__month=12))

    def test_invalid_month_0_ignored(self):
        qs = self._get_qs({'month': '0'})
        self.assertFalse(qs.has_filter(date__month=0))

    def test_invalid_month_13_ignored(self):
        qs = self._get_qs({'month': '13'})
        self.assertFalse(qs.has_filter(date__month=13))

    def test_non_numeric_month_ignored(self):
        qs = self._get_qs({'month': 'abc'})
        self.assertFalse(any('date__month' in f for f in qs._filters))

    # --- year ------------------------------------------------------------

    def test_filter_by_valid_year(self):
        qs = self._get_qs({'year': '2025'})
        self.assertTrue(qs.has_filter(date__year=2025))

    def test_invalid_year_zero_ignored(self):
        qs = self._get_qs({'year': '0'})
        self.assertFalse(any('date__year' in f for f in qs._filters))

    def test_non_numeric_year_ignored(self):
        qs = self._get_qs({'year': 'abc'})
        self.assertFalse(any('date__year' in f for f in qs._filters))

    # --- month + year together -------------------------------------------

    def test_filter_month_and_year_together(self):
        qs = self._get_qs({'month': '3', 'year': '2024'})
        self.assertTrue(qs.has_filter(date__month=3))
        self.assertTrue(qs.has_filter(date__year=2024))

    # --- no date filter when neither month nor year provided -------------

    def test_no_date_filter_when_params_absent(self):
        qs = self._get_qs({})
        self.assertFalse(any('date__month' in f or 'date__year' in f for f in qs._filters))

    # --- category_id -----------------------------------------------------

    def test_filter_by_category_id(self):
        qs = self._get_qs({'category_id': '7'})
        self.assertTrue(qs.has_filter(category_id=7))

    def test_non_numeric_category_id_ignored(self):
        qs = self._get_qs({'category_id': 'food'})
        self.assertFalse(any('category_id' in f for f in qs._filters))

    # --- payment_method --------------------------------------------------

    def test_filter_by_payment_method_dinheiro(self):
        qs = self._get_qs({'payment_method': 'dinheiro'})
        self.assertTrue(qs.has_filter(payment_method='dinheiro'))

    def test_filter_by_payment_method_cartao(self):
        qs = self._get_qs({'payment_method': 'cartao'})
        self.assertTrue(qs.has_filter(payment_method='cartao'))

    def test_invalid_payment_method_ignored(self):
        qs = self._get_qs({'payment_method': 'boleto'})
        self.assertFalse(any('payment_method' in f for f in qs._filters))

    # --- search ----------------------------------------------------------

    def test_filter_by_search_term(self):
        qs = self._get_qs({'search': 'mercado'})
        self.assertTrue(qs.has_filter(description__icontains='mercado'))

    def test_search_strips_whitespace(self):
        qs = self._get_qs({'search': '  café  '})
        self.assertTrue(qs.has_filter(description__icontains='café'))

    def test_empty_search_not_applied(self):
        qs = self._get_qs({'search': ''})
        self.assertFalse(any('description__icontains' in f for f in qs._filters))

    # --- combined filters ------------------------------------------------

    def test_combined_filters_all_applied(self):
        qs = self._get_qs({
            'month': '11',
            'year': '2023',
            'category_id': '3',
            'payment_method': 'cartao',
            'search': 'uber',
        })
        self.assertTrue(qs.has_filter(date__month=11))
        self.assertTrue(qs.has_filter(date__year=2023))
        self.assertTrue(qs.has_filter(category_id=3))
        self.assertTrue(qs.has_filter(payment_method='cartao'))
        self.assertTrue(qs.has_filter(description__icontains='uber'))


# ---------------------------------------------------------------------------
# DeleteInstallmentsInputSerializer — validation
# ---------------------------------------------------------------------------

class DeleteInstallmentsInputSerializerTest(SimpleTestCase):
    """Unit tests for DeleteInstallmentsInputSerializer field validation."""

    # --- happy path -------------------------------------------------------

    def test_valid_input_passes(self):
        s = DeleteInstallmentsInputSerializer(data={
            'description_prefix': 'Celular novo',
            'total_installments': 10,
        })
        self.assertTrue(s.is_valid(), s.errors)

    def test_minimum_valid_total_installments(self):
        s = DeleteInstallmentsInputSerializer(data={
            'description_prefix': 'TV nova',
            'total_installments': 2,
        })
        self.assertTrue(s.is_valid(), s.errors)

    def test_description_prefix_max_length_exactly_255_passes(self):
        s = DeleteInstallmentsInputSerializer(data={
            'description_prefix': 'a' * 255,
            'total_installments': 3,
        })
        self.assertTrue(s.is_valid(), s.errors)

    # --- description_prefix errors ----------------------------------------

    def test_missing_description_prefix_fails(self):
        s = DeleteInstallmentsInputSerializer(data={'total_installments': 10})
        self.assertFalse(s.is_valid())
        self.assertIn('description_prefix', s.errors)

    def test_empty_description_prefix_fails(self):
        s = DeleteInstallmentsInputSerializer(data={
            'description_prefix': '',
            'total_installments': 10,
        })
        self.assertFalse(s.is_valid())
        self.assertIn('description_prefix', s.errors)

    def test_description_prefix_256_chars_fails(self):
        s = DeleteInstallmentsInputSerializer(data={
            'description_prefix': 'a' * 256,
            'total_installments': 10,
        })
        self.assertFalse(s.is_valid())
        self.assertIn('description_prefix', s.errors)

    # --- total_installments errors ----------------------------------------

    def test_missing_total_installments_fails(self):
        s = DeleteInstallmentsInputSerializer(data={'description_prefix': 'Celular novo'})
        self.assertFalse(s.is_valid())
        self.assertIn('total_installments', s.errors)

    def test_total_installments_one_fails(self):
        s = DeleteInstallmentsInputSerializer(data={
            'description_prefix': 'Celular novo',
            'total_installments': 1,
        })
        self.assertFalse(s.is_valid())
        self.assertIn('total_installments', s.errors)

    def test_total_installments_zero_fails(self):
        s = DeleteInstallmentsInputSerializer(data={
            'description_prefix': 'Celular novo',
            'total_installments': 0,
        })
        self.assertFalse(s.is_valid())
        self.assertIn('total_installments', s.errors)

    def test_total_installments_negative_fails(self):
        s = DeleteInstallmentsInputSerializer(data={
            'description_prefix': 'Celular novo',
            'total_installments': -5,
        })
        self.assertFalse(s.is_valid())
        self.assertIn('total_installments', s.errors)

    def test_total_installments_non_integer_fails(self):
        s = DeleteInstallmentsInputSerializer(data={
            'description_prefix': 'Celular novo',
            'total_installments': 'dez',
        })
        self.assertFalse(s.is_valid())
        self.assertIn('total_installments', s.errors)


# ---------------------------------------------------------------------------
# ExpenseViewSet.delete_installments — action logic
# ---------------------------------------------------------------------------

def _make_action_request(data: dict, tenant_id: str = 'tenant-abc') -> MagicMock:
    """Builds a minimal mock request suitable for the delete_installments action."""
    request = MagicMock()
    request.data = data
    request.user.tenant_id = tenant_id
    return request


class DeleteInstallmentsActionTest(SimpleTestCase):
    """
    Unit tests for delete_installments action.

    ORM calls are mocked so no database is required.
    transaction.atomic is patched to a no-op context manager.
    """

    def _call_action(
        self,
        data: dict,
        tenant_id: str = 'tenant-abc',
        delete_return: tuple = (5, {'expenses.Expense': 5}),
    ):
        """
        Runs delete_installments with mocked DB calls.

        Returns (response, mock_objects, mock_qs).
        """
        vs = ExpenseViewSet()
        vs.request = _make_action_request(data, tenant_id)
        vs.format_kwarg = None
        vs.kwargs = {}

        mock_qs = MagicMock()
        mock_qs.delete.return_value = delete_return
        mock_qs.count.return_value = len(data.get('expense_ids', []))
        mock_qs.filter.return_value = mock_qs

        with patch('expenses.models.Expense.objects') as mock_objects, \
             patch('django.db.transaction.atomic'):
            mock_objects.filter.return_value = mock_qs
            response = vs.delete_installments(vs.request)

        return response, mock_objects, mock_qs

    # --- success path -----------------------------------------------------

    def test_returns_200_when_expenses_are_deleted(self):
        response, _, _ = self._call_action(
            data={'description_prefix': 'Celular novo', 'total_installments': 10},
            delete_return=(10, {'expenses.Expense': 10}),
        )
        self.assertEqual(response.status_code, 200)

    def test_response_body_contains_deleted_count(self):
        response, _, _ = self._call_action(
            data={'description_prefix': 'Celular novo', 'total_installments': 10},
            delete_return=(10, {'expenses.Expense': 10}),
        )
        self.assertEqual(response.data['deleted'], 10)

    def test_response_body_echoes_description_prefix(self):
        response, _, _ = self._call_action(
            data={'description_prefix': 'Celular novo', 'total_installments': 10},
            delete_return=(10, {'expenses.Expense': 10}),
        )
        self.assertEqual(response.data['description_prefix'], 'Celular novo')

    def test_response_body_echoes_total_installments(self):
        response, _, _ = self._call_action(
            data={'description_prefix': 'Celular novo', 'total_installments': 10},
            delete_return=(10, {'expenses.Expense': 10}),
        )
        self.assertEqual(response.data['total_installments'], 10)

    # --- not found --------------------------------------------------------

    def test_returns_404_when_no_expenses_found(self):
        response, _, _ = self._call_action(
            data={'description_prefix': 'Celular novo', 'total_installments': 10},
            delete_return=(0, {}),
        )
        self.assertEqual(response.status_code, 404)

    def test_404_response_contains_detail_key(self):
        response, _, _ = self._call_action(
            data={'description_prefix': 'Celular novo', 'total_installments': 10},
            delete_return=(0, {}),
        )
        self.assertIn('detail', response.data)

    # --- validation errors ------------------------------------------------

    def test_invalid_input_raises_validation_error(self):
        from rest_framework.exceptions import ValidationError
        vs = ExpenseViewSet()
        vs.request = _make_action_request({
            'description_prefix': '',
            'total_installments': 1,
        })
        vs.format_kwarg = None
        vs.kwargs = {}
        with self.assertRaises(ValidationError):
            vs.delete_installments(vs.request)

    def test_missing_fields_raises_validation_error(self):
        from rest_framework.exceptions import ValidationError
        vs = ExpenseViewSet()
        vs.request = _make_action_request({})
        vs.format_kwarg = None
        vs.kwargs = {}
        with self.assertRaises(ValidationError):
            vs.delete_installments(vs.request)

    # --- tenant isolation -------------------------------------------------

    def test_filter_always_includes_tenant_id(self):
        TENANT = 'specific-tenant-xyz'
        _, mock_objects, _ = self._call_action(
            data={'description_prefix': 'Notebook', 'total_installments': 5},
            tenant_id=TENANT,
            delete_return=(5, {'expenses.Expense': 5}),
        )
        call_kwargs = mock_objects.filter.call_args.kwargs
        self.assertEqual(call_kwargs['tenant_id'], TENANT)

    def test_filter_does_not_see_other_tenant_data(self):
        """Verify that tenant_id is the ONLY tenant scoping and is set correctly."""
        _, mock_objects, _ = self._call_action(
            data={'description_prefix': 'Viagem', 'total_installments': 4},
            tenant_id='tenant-A',
            delete_return=(4, {'expenses.Expense': 4}),
        )
        call_kwargs = mock_objects.filter.call_args.kwargs
        # Must be scoped to tenant-A, not any other value
        self.assertNotEqual(call_kwargs.get('tenant_id'), 'tenant-B')

    # --- iregex pattern correctness ---------------------------------------

    def test_filter_uses_iregex_with_correct_pattern(self):
        import re
        PREFIX = 'TV nova'
        TOTAL = 6
        _, mock_objects, _ = self._call_action(
            data={'description_prefix': PREFIX, 'total_installments': TOTAL},
            delete_return=(6, {'expenses.Expense': 6}),
        )
        call_kwargs = mock_objects.filter.call_args.kwargs
        expected = rf'^{re.escape(PREFIX)} - Parcela \d+/{TOTAL}$'
        self.assertEqual(call_kwargs['description__iregex'], expected)

    def test_iregex_pattern_escapes_special_chars_in_prefix(self):
        """Prefixes with regex-special chars must be escaped to prevent injection."""
        import re
        PREFIX = 'Curso (React) 2.0'   # contains ( ) .
        TOTAL = 3
        _, mock_objects, _ = self._call_action(
            data={'description_prefix': PREFIX, 'total_installments': TOTAL},
            delete_return=(3, {'expenses.Expense': 3}),
        )
        call_kwargs = mock_objects.filter.call_args.kwargs
        expected = rf'^{re.escape(PREFIX)} - Parcela \d+/{TOTAL}$'
        self.assertEqual(call_kwargs['description__iregex'], expected)
        # Double-check the escaped prefix does NOT contain unescaped special chars
        self.assertIn(r'\(', call_kwargs['description__iregex'])

    # --- ORM call verification --------------------------------------------

    def test_delete_is_called_once(self):
        _, _, mock_qs = self._call_action(
            data={'description_prefix': 'Celular', 'total_installments': 3},
            delete_return=(3, {'expenses.Expense': 3}),
        )
        mock_qs.delete.assert_called_once()

    def test_filter_is_called_once(self):
        _, mock_objects, _ = self._call_action(
            data={'description_prefix': 'Celular', 'total_installments': 3},
            delete_return=(3, {'expenses.Expense': 3}),
        )
        mock_objects.filter.assert_called_once()

    def test_specific_ids_limit_delete_to_one_installment_group(self):
        ids = [101, 102]
        response, mock_objects, mock_qs = self._call_action(
            data={'description_prefix': 'Celular', 'total_installments': 3, 'expense_ids': ids},
            delete_return=(2, {'expenses.Expense': 2}),
        )
        self.assertEqual(response.status_code, 200)
        mock_qs.filter.assert_called_once_with(id__in=ids)


# ---------------------------------------------------------------------------
# Regressao: parcelamento e sufixo de descricao
# ---------------------------------------------------------------------------

class SplitInstallmentsTests(SimpleTestCase):
    """Parcelas devem somar exatamente o total, sem perder centavos."""

    def test_sum_always_equals_total(self):
        for total, n in [('100.00', 3), ('0.05', 3), ('485.92', 2), ('999.99', 7)]:
            parts = _split_installments(Decimal(total), n)
            self.assertEqual(len(parts), n)
            self.assertEqual(sum(parts), Decimal(total), f'{total} em {n}x')

    def test_residual_cents_go_to_first_installments(self):
        self.assertEqual(
            _split_installments(Decimal('100.00'), 3),
            [Decimal('33.34'), Decimal('33.33'), Decimal('33.33')],
        )

    def test_single_installment(self):
        self.assertEqual(_split_installments(Decimal('242.96'), 1), [Decimal('242.96')])


class StripInstallmentSuffixTests(SimpleTestCase):
    """Regressao: reparcelar uma parcela acumulava " - Parcela X/Y"."""

    def test_removes_single_suffix(self):
        self.assertEqual(
            _strip_installment_suffix('Aspirador para a mamae - Parcela 1/2'),
            'Aspirador para a mamae',
        )

    def test_removes_duplicated_suffix(self):
        self.assertEqual(
            _strip_installment_suffix('Aspirador para a mamae - Parcela 1/2 - Parcela 1/2'),
            'Aspirador para a mamae',
        )

    def test_keeps_plain_description(self):
        self.assertEqual(_strip_installment_suffix('Celular novo'), 'Celular novo')

    def test_does_not_touch_fraction_in_the_middle(self):
        self.assertEqual(_strip_installment_suffix('Curso 2/3 aulas'), 'Curso 2/3 aulas')


class CreateExpenseCardValidationTests(SimpleTestCase):
    """payment_method='cartao' sem cartao deixa o gasto fora de qualquer fatura."""

    def test_cartao_without_card_raises(self):
        behavior = CreateExpenseBehavior(data={
            'description': 'Netflix', 'amount': -44.90, 'date': '2026-08-01',
            'payment_method': 'cartao', 'credit_card_id': None,
        })
        with self.assertRaises(ValueError):
            behavior._validate_payment()

    def test_cartao_with_card_is_ok(self):
        behavior = CreateExpenseBehavior(data={
            'description': 'Netflix', 'amount': -44.90, 'date': '2026-08-01',
            'payment_method': 'cartao', 'credit_card_id': 6,
        })
        behavior._validate_payment()
        self.assertEqual(behavior.credit_card_id, 6)

    def test_dinheiro_clears_card(self):
        behavior = CreateExpenseBehavior(data={
            'description': 'Feira', 'amount': -30.00, 'date': '2026-08-01',
            'payment_method': 'dinheiro', 'credit_card_id': 6,
        })
        behavior._validate_payment()
        self.assertIsNone(behavior.credit_card_id)


class ExpenseDeleteEndpointTests(TestCase):
    """
    Trava do comportamento de delete antes de remover o perform_destroy.

    O get_queryset ja filtra por tenant, entao a despesa alheia nunca chega ao
    perform_destroy: o get_object() levanta 404 antes. Estes testes provam que
    o 404 vem do queryset, nao da guarda.
    """

    TENANT = 'tenant-exp-del-1'
    OTHER_TENANT = 'tenant-exp-del-2'
    URL = '/api/expenses/expenses/'

    def setUp(self):
        from rest_framework.test import APIClient
        from financial_system.authentication import KeycloakPrincipal

        self.client = APIClient()
        self.client.force_authenticate(user=KeycloakPrincipal({
            'sub': self.TENANT, 'email': 'e@example.com',
            'given_name': 'E', 'family_name': 'D',
        }))

    def _expense(self, description='Compra', tenant=None):
        from catalog.models import ExpenseCategory
        from expenses.models import Expense as ExpenseModel
        category, _ = ExpenseCategory.objects.get_or_create(
            tenant_id=tenant or self.TENANT, name='Geral')
        return ExpenseModel.objects.create(
            tenant_id=tenant or self.TENANT,
            description=description,
            amount=Decimal('-50.00'),
            date=real_date(2026, 3, 10),
            payment_method='dinheiro',
            category=category,
            quantity=1,
        )

    def test_delete_da_propria_despesa_funciona(self):
        from expenses.models import Expense as ExpenseModel
        exp = self._expense()
        resp = self.client.delete(f'{self.URL}{exp.id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ExpenseModel.objects.filter(id=exp.id).exists())

    def test_delete_de_despesa_de_outro_tenant_retorna_404(self):
        from expenses.models import Expense as ExpenseModel
        alheia = self._expense('Alheia', tenant=self.OTHER_TENANT)
        resp = self.client.delete(f'{self.URL}{alheia.id}/')
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(ExpenseModel.objects.filter(id=alheia.id).exists())


from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from catalog.models import ExpenseCategory
from expenses import models as expense_models


class AnalyticsCharacterizationBase(TestCase):
    """Base com um tenant autenticado e helpers de criacao."""

    TENANT = 'tenant-caracterizacao'

    def _principal(self, sub):
        from financial_system.authentication import KeycloakPrincipal
        return KeycloakPrincipal({
            'sub': sub, 'email': f'{sub}@example.com',
            'given_name': 'Teste', 'family_name': 'Caracterizacao',
        })

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self._principal(self.TENANT))

        self.cat_lazer = ExpenseCategory.objects.create(tenant_id='system', name='Lazer')
        self.cat_mercado = ExpenseCategory.objects.create(tenant_id='system', name='Supermercado')

        self.card = self._make_card('Bradesco', closing_day=21, due_day=5)

    def _make_card(self, name, closing_day=21, due_day=5):
        from cards.models import CreditCard
        return CreditCard.objects.create(
            tenant_id=self.TENANT, name=name,
            closing_day=closing_day, due_day=due_day, last_four_digits='1234',
        )

    def _expense(self, description, amount, on_date, category=None,
                 payment_method='dinheiro', credit_card=None):
        return expense_models.Expense.objects.create(
            tenant_id=self.TENANT,
            description=description,
            amount=amount,
            date=on_date,
            category=category or self.cat_lazer,
            payment_method=payment_method,
            credit_card=credit_card,
            quantity=1,
        )


class AnalyticsMonthlyCharacterizationTests(AnalyticsCharacterizationBase):

    def test_retorna_sempre_os_12_meses_mesmo_sem_lancamentos(self):
        resp = self.client.get('/api/expenses/expenses/analytics/monthly/?year=2026')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 12)
        self.assertEqual([m['month'] for m in resp.data], list(range(1, 13)))

    def test_separa_receita_de_despesa_e_calcula_saldo(self):
        self._expense('Salario', '5000.00', date(2026, 3, 1))
        self._expense('Cinema', '-100.00', date(2026, 3, 10))

        resp = self.client.get('/api/expenses/expenses/analytics/monthly/?year=2026')
        marco = resp.data[2]

        self.assertEqual(marco['month_name'], 'Mar\u00e7o')
        self.assertEqual(marco['income'], 5000.0)
        self.assertEqual(marco['expenses'], 100.0)
        self.assertEqual(marco['balance'], 4900.0)
        self.assertEqual(marco['count'], 2)

    def test_separa_gasto_em_dinheiro_de_gasto_no_cartao(self):
        self._expense('Feira', '-200.00', date(2026, 5, 4), payment_method='dinheiro')
        self._expense('Streaming', '-50.00', date(2026, 5, 6),
                      payment_method='cartao', credit_card=self.card)

        resp = self.client.get('/api/expenses/expenses/analytics/monthly/?year=2026')
        maio = resp.data[4]

        self.assertEqual(maio['cash_expenses'], 200.0)
        self.assertEqual(maio['card_expenses'], 50.0)
        self.assertEqual(maio['expenses'], 250.0)

    def test_ano_invalido_cai_para_o_ano_corrente_sem_erro(self):
        resp = self.client.get('/api/expenses/expenses/analytics/monthly/?year=abc')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 12)

    def test_nao_vaza_dados_de_outro_tenant(self):
        expense_models.Expense.objects.create(
            tenant_id='outro-tenant', description='Nao e meu', amount='-999.00',
            date=date(2026, 3, 5), category=self.cat_lazer,
            payment_method='dinheiro', quantity=1,
        )
        resp = self.client.get('/api/expenses/expenses/analytics/monthly/?year=2026')
        self.assertEqual(resp.data[2]['expenses'], 0.0)


class AnalyticsByCategoryCharacterizationTests(AnalyticsCharacterizationBase):

    def test_agrupa_apenas_despesas_e_ignora_receitas(self):
        self._expense('Salario', '5000.00', date(2026, 3, 1))
        self._expense('Cinema', '-100.00', date(2026, 3, 10), category=self.cat_lazer)

        resp = self.client.get('/api/expenses/expenses/analytics/by-category/?year=2026&month=3')

        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['category_name'], 'Lazer')
        self.assertEqual(resp.data[0]['total'], 100.0)
        self.assertEqual(resp.data[0]['percentage'], 100.0)

    def test_ordena_por_total_decrescente_e_calcula_percentual(self):
        self._expense('Feira', '-300.00', date(2026, 3, 2), category=self.cat_mercado)
        self._expense('Cinema', '-100.00', date(2026, 3, 3), category=self.cat_lazer)

        resp = self.client.get('/api/expenses/expenses/analytics/by-category/?year=2026&month=3')

        self.assertEqual([c['category_name'] for c in resp.data], ['Supermercado', 'Lazer'])
        self.assertEqual(resp.data[0]['percentage'], 75.0)
        self.assertEqual(resp.data[1]['percentage'], 25.0)

    def test_mes_fora_do_intervalo_e_ignorado_em_vez_de_dar_erro(self):
        self._expense('Cinema', '-100.00', date(2026, 3, 10))
        resp = self.client.get('/api/expenses/expenses/analytics/by-category/?year=2026&month=99')
        self.assertEqual(resp.status_code, 200)


class AnalyticsDailyCharacterizationTests(AnalyticsCharacterizationBase):

    def test_retorna_todos_os_dias_do_mes(self):
        resp = self.client.get('/api/expenses/expenses/analytics/daily/?year=2026&month=3')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 31)
        self.assertEqual(resp.data[0]['date'], '2026-03-01')

    def test_daily_exclui_receita_do_total(self):
        """
        A receita nao entra no grafico de gastos diarios.

        Antes este teste era
        `test_COMPORTAMENTO_ATUAL_daily_soma_receita_junto_com_despesa` e
        gravava a receita virando pico de gasto. Agora bate com o criterio da
        chave `daily` de /home-charts/ -- ver
        HomeChartsCharacterizationTests.test_daily_do_home_exclui_receita.
        """
        self._expense('Salario', '5000.00', date(2026, 3, 1))
        self._expense('Cinema', '-100.00', date(2026, 3, 2))

        resp = self.client.get('/api/expenses/expenses/analytics/daily/?year=2026&month=3')

        self.assertEqual(resp.data[0]['total'], 0.0)
        self.assertEqual(resp.data[0]['count'], 0)
        self.assertEqual(resp.data[1]['total'], 100.0)

    def test_daily_bate_com_o_daily_do_home_charts(self):
        """Trava de regressao: as duas telas nao podem divergir de novo."""
        self._expense('Salario', '5000.00', date(2026, 3, 1))
        self._expense('Cinema', '-100.00', date(2026, 3, 2))
        self._expense('Mercado', '-250.00', date(2026, 3, 5))

        daily = self.client.get(
            '/api/expenses/expenses/analytics/daily/?year=2026&month=3').data
        home = self.client.get(
            '/api/expenses/expenses/home-charts/?year=2026&month=3').data['daily']

        self.assertEqual(
            [d['total'] for d in daily],
            [h['total'] for h in home],
        )


class AnalyticsByCardCharacterizationTests(AnalyticsCharacterizationBase):

    def test_lista_vazia_quando_nao_ha_gasto_no_cartao(self):
        self._expense('Feira', '-200.00', date(2026, 3, 4), payment_method='dinheiro')
        resp = self.client.get('/api/expenses/expenses/analytics/by-card/?year=2026&month=3')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(resp.data), [])

    def test_agrupa_gastos_por_cartao(self):
        self._expense('Streaming', '-50.00', date(2026, 3, 6),
                      payment_method='cartao', credit_card=self.card)
        resp = self.client.get('/api/expenses/expenses/analytics/by-card/?year=2026&month=3')
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['total'], 50.0)

    def test_periodo_ciclo_usa_data_de_fechamento_em_vez_do_mes_da_compra(self):
        self._expense('Compra depois do fechamento', '-80.00', date(2026, 3, 22),
                      payment_method='cartao', credit_card=self.card)
        cycle = self.client.get(
            '/api/expenses/expenses/analytics/by-card/?year=2026&month=5&period=cycle')
        purchase_month = self.client.get(
            '/api/expenses/expenses/analytics/by-card/?year=2026&month=5&period=purchase_month')

        self.assertEqual(cycle.data[0]['total'], 80.0)
        self.assertEqual(cycle.data[0]['period'], 'cycle')
        self.assertEqual(list(purchase_month.data), [])


class HistoryCharacterizationTests(AnalyticsCharacterizationBase):

    def test_historico_busca_por_faixa_de_valor_e_csv_exporta_os_filtros(self):
        self._expense('Supermercado', '-82.50', date(2026, 3, 6))
        self._expense('Salário', '250.00', date(2026, 3, 1))

        response = self.client.get('/api/expenses/expenses/history/?min_amount=80&max_amount=90')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['totals']['count'], 1)
        self.assertEqual(response.data['results'][0]['description'], 'Supermercado')

        csv_response = self.client.get(
            '/api/expenses/expenses/history/?min_amount=80&max_amount=90&export=csv')
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn('Supermercado', csv_response.content.decode('utf-8'))
        self.assertNotIn('Salário', csv_response.content.decode('utf-8'))

    def test_historico_compartilhado_mostra_valor_bruto_e_rateio_do_usuario(self):
        from debts.models import SharedDebt, SharedDebtMember, SharedEntry

        group = SharedDebt.objects.create(name='Casa', owner_tenant_id=self.TENANT)
        me = SharedDebtMember.objects.create(
            shared_debt=group, tenant_id=self.TENANT, display_name='Teste')
        SharedDebtMember.objects.create(
            shared_debt=group, tenant_id='tenant-outro', display_name='Outro')
        SharedEntry.objects.create(
            shared_debt=group, paid_by=me, description='Aluguel dividido',
            amount='1200.00', date=date(2026, 3, 1), payment_method='dinheiro',
            created_by_tenant_id=self.TENANT,
        )

        response = self.client.get('/api/expenses/expenses/history/?type=shared')
        self.assertEqual(response.status_code, 200)
        row = response.data['results'][0]
        self.assertEqual(row['amount'], -1200.0)
        self.assertEqual(row['own_portion'], 600.0)
        self.assertEqual(response.data['totals']['expenses'], 600.0)


class ConsolidatedSummaryCharacterizationTests(AnalyticsCharacterizationBase):

    EXPECTED_KEYS = {
        'month', 'year', 'income', 'cash_expenses', 'cash_count',
        'card_invoices', 'card_invoices_count', 'card_invoices_detail',
        'shared_my_portion', 'shared_count', 'total_expenses', 'balance',
    }

    def test_contrato_de_chaves_da_resposta(self):
        resp = self.client.get('/api/expenses/expenses/consolidated-summary/?year=2026&month=3')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.data.keys()), self.EXPECTED_KEYS)

    def test_balanco_e_receita_menos_despesa_total(self):
        self._expense('Salario', '5000.00', date(2026, 3, 1))
        self._expense('Cinema', '-100.00', date(2026, 3, 10))

        resp = self.client.get('/api/expenses/expenses/consolidated-summary/?year=2026&month=3')

        self.assertEqual(resp.data['income'], 5000.0)
        self.assertEqual(resp.data['cash_expenses'], 100.0)
        self.assertEqual(resp.data['total_expenses'], 100.0)
        self.assertEqual(resp.data['balance'], 4900.0)

    def test_gasto_no_cartao_nao_entra_como_dinheiro(self):
        self._expense('Streaming', '-50.00', date(2026, 3, 6),
                      payment_method='cartao', credit_card=self.card)
        resp = self.client.get('/api/expenses/expenses/consolidated-summary/?year=2026&month=3')
        self.assertEqual(resp.data['cash_expenses'], 0.0)
        self.assertEqual(resp.data['cash_count'], 0)

    def test_resumo_da_home_usa_o_ciclo_que_fecha_no_mes_selecionado(self):
        self._expense('Compra antes do fechamento', '-120.00', date(2026, 3, 10),
                      payment_method='cartao', credit_card=self.card)
        self._expense('Compra do ciclo seguinte', '-45.00', date(2026, 3, 22),
                      payment_method='cartao', credit_card=self.card)

        response = self.client.get(
            '/api/expenses/expenses/consolidated-summary/?month=3&year=2026'
            '&closing_month=3&closing_year=2026&include_obligations=1')

        self.assertEqual(response.data['card_invoices'], 120.0)
        self.assertEqual(response.data['card_invoices_detail'][0]['invoice_month'], 4)

    def test_resumo_separa_compartilhado_em_dinheiro_por_mes_e_cartao_por_ciclo(self):
        from debts.models import SharedDebt, SharedDebtMember, SharedEntry, SharedEntryParticipant
        group = SharedDebt.objects.create(name='Casa', owner_tenant_id=self.TENANT)
        me = SharedDebtMember.objects.create(shared_debt=group, tenant_id=self.TENANT, display_name='Eu')
        partner = SharedDebtMember.objects.create(shared_debt=group, tenant_id='partner', display_name='Parceiro')

        def shared(description, amount, day, method, card=None):
            entry = SharedEntry.objects.create(
                shared_debt=group, paid_by=me, description=description, amount=amount,
                date=date(2026, 3, day), payment_method=method, credit_card=card,
                created_by_tenant_id=self.TENANT,
            )
            SharedEntryParticipant.objects.create(entry=entry, member=me)
            SharedEntryParticipant.objects.create(entry=entry, member=partner)

        shared('Cartão no ciclo', '120.00', 10, 'cartao', self.card)
        shared('Cartão após fechamento', '90.00', 22, 'cartao', self.card)
        shared('Dinheiro do mês', '20.00', 22, 'dinheiro')

        response = self.client.get(
            '/api/expenses/expenses/consolidated-summary/?month=3&year=2026'
            '&closing_month=3&closing_year=2026')

        self.assertEqual(response.data['shared_my_portion'], 70.0)
        self.assertEqual(response.data['total_expenses'], 70.0)


class StableCategoryKeyTests(AnalyticsCharacterizationBase):

    def test_list_filter_uses_stable_uncategorized_key(self):
        uncategorized = ExpenseCategory.objects.create(
            tenant_id='system', name='Sem categoria', key='uncategorized')
        self._expense('Sem rótulo', '-15.00', date(2026, 3, 2), category=uncategorized)

        response = self.client.get('/api/expenses/expenses/?category_key=uncategorized')

        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['description'], 'Sem rótulo')

    def test_livre_para_gastar_desconta_gastos_fixos_ainda_nao_gerados(self):
        from expenses.models import RecurringExpenseTemplate

        self._expense('Salário', '5000.00', date(2026, 3, 1))
        RecurringExpenseTemplate.objects.create(
            tenant_id=self.TENANT, description='Internet', amount='120.00',
            day_of_month=10, payment_method='dinheiro', is_active=True,
        )
        response = self.client.get(
            '/api/expenses/expenses/consolidated-summary/?year=2026&month=3&include_obligations=1')

        self.assertEqual(response.data['upcoming_fixed'], 120.0)
        self.assertEqual(response.data['personal_cost'], 0.0)
        self.assertEqual(response.data['free_to_spend'], 4880.0)


class HomeChartsCharacterizationTests(AnalyticsCharacterizationBase):

    EXPECTED_KEYS = {'month', 'year', 'summary', 'by_category', 'daily', 'weekly'}

    def test_contrato_de_chaves_da_resposta(self):
        resp = self.client.get('/api/expenses/expenses/home-charts/?year=2026&month=3')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.data.keys()), self.EXPECTED_KEYS)
        self.assertEqual(set(resp.data['summary'].keys()),
                         {'income', 'expenses', 'balance', 'count'})

    def test_daily_do_home_exclui_receita(self):
        """Mesmo criterio de /analytics/daily/ desde a correcao da divergencia."""
        self._expense('Salario', '5000.00', date(2026, 3, 1))
        self._expense('Cinema', '-100.00', date(2026, 3, 2))

        resp = self.client.get('/api/expenses/expenses/home-charts/?year=2026&month=3')

        self.assertEqual(resp.data['daily'][0]['total'], 0.0)
        self.assertEqual(resp.data['daily'][1]['total'], 100.0)
        self.assertEqual(resp.data['summary']['income'], 5000.0)
        self.assertEqual(resp.data['summary']['expenses'], 100.0)

    def test_weekly_divide_o_mes_em_semanas(self):
        self._expense('Cinema', '-100.00', date(2026, 3, 10))
        resp = self.client.get('/api/expenses/expenses/home-charts/?year=2026&month=3')
        weekly = resp.data['weekly']
        self.assertTrue(len(weekly) >= 4)
        self.assertEqual(sum(w['total'] for w in weekly), 100.0)


from datetime import date, timedelta
from decimal import Decimal
from importlib import import_module

from django.apps import apps as global_apps
from django.test import TestCase
from django.utils import timezone

from cards.models import CreditCard
from catalog.models import ExpenseCategory
from expenses.models import Expense, RecurringExpenseTemplate

# O nome do modulo comeca com digito, entao nao da para usar "import" normal.
backfill = import_module('expenses.migrations.0005_backfill_recurring_template')


class BackfillRecurringTemplateTest(TestCase):
    TENANT = "tenant-backfill"

    def setUp(self):
        self.category = ExpenseCategory.objects.create(
            tenant_id=self.TENANT, name="Assinaturas"
        )
        self.card = CreditCard.objects.create(
            tenant_id=self.TENANT, name="Itau Azul", closing_day=25, due_day=3
        )
        self.agora = timezone.now()

    def _template(self, description, amount, day, criado_em=None, tenant=None):
        tpl = RecurringExpenseTemplate.objects.create(
            tenant_id=tenant or self.TENANT,
            description=description,
            amount=Decimal(amount),
            day_of_month=day,
            payment_method="cartao",
            credit_card=self.card,
            category=self.category,
        )
        if criado_em is not None:
            RecurringExpenseTemplate.objects.filter(id=tpl.id).update(created_at=criado_em)
            tpl.refresh_from_db()
        return tpl

    def _expense(self, description, amount, quando, criado_em=None, tenant=None):
        exp = Expense.objects.create(
            tenant_id=tenant or self.TENANT,
            category=self.category,
            description=description,
            quantity=1,
            amount=Decimal(amount),
            date=quando,
            payment_method="cartao",
            credit_card=self.card,
        )
        if criado_em is not None:
            Expense.objects.filter(id=exp.id).update(created_at=criado_em)
            exp.refresh_from_db()
        return exp

    def _rodar(self):
        backfill.ligar_historico(global_apps, None)

    # -- caso simples -----------------------------------------------------
    def test_liga_uma_despesa_por_mes(self):
        tpl = self._template("Spotify", "23.90", 18, criado_em=self.agora - timedelta(days=90))
        e1 = self._expense("Spotify", "-23.90", date(2026, 8, 18))
        e2 = self._expense("Spotify", "-23.90", date(2026, 9, 18))

        self._rodar()

        e1.refresh_from_db(); e2.refresh_from_db()
        self.assertEqual(e1.recurring_template_id, tpl.id)
        self.assertEqual(e2.recurring_template_id, tpl.id)

    # -- conta variavel: o valor mudou, mas continua sendo o mesmo gasto --
    def test_liga_mesmo_quando_o_valor_diverge_do_template(self):
        """Producao: 'Conta da Vivo' template R$41,00 x despesa real R$41,90."""
        tpl = self._template("Conta da Vivo", "41.00", 1, criado_em=self.agora - timedelta(days=90))
        exp = self._expense("Conta da Vivo", "-41.90", date(2026, 8, 17))

        self._rodar()

        exp.refresh_from_db()
        self.assertEqual(exp.recurring_template_id, tpl.id)

    # -- despesa anterior ao template e manual ----------------------------
    def test_nao_liga_despesa_criada_antes_do_template_existir(self):
        """Producao: Netflix de 07/07 e anterior ao template criado em 28/08."""
        criacao_tpl = self.agora - timedelta(days=30)
        tpl = self._template("Netflix", "20.90", 3, criado_em=criacao_tpl)
        antiga = self._expense(
            "Netflix", "-20.90", date(2026, 7, 7), criado_em=criacao_tpl - timedelta(days=50)
        )
        nova = self._expense("Netflix", "-20.90", date(2026, 8, 3), criado_em=criacao_tpl)

        self._rodar()

        antiga.refresh_from_db(); nova.refresh_from_db()
        self.assertIsNone(antiga.recurring_template_id)
        self.assertEqual(nova.recurring_template_id, tpl.id)

    def test_tolera_despesa_criada_milissegundos_antes_do_template(self):
        """Ao criar um template o sistema ja materializa o mes na mesma transacao."""
        criacao_tpl = self.agora - timedelta(days=10)
        tpl = self._template("TIM", "71.00", 5, criado_em=criacao_tpl)
        exp = self._expense(
            "TIM", "-71.00", date(2026, 8, 5),
            criado_em=criacao_tpl - timedelta(milliseconds=40),
        )

        self._rodar()

        exp.refresh_from_db()
        self.assertEqual(exp.recurring_template_id, tpl.id)

    # -- a garantia que protege a constraint da 0006 ----------------------
    def test_nunca_liga_duas_despesas_ao_mesmo_template_no_mesmo_mes(self):
        tpl = self._template("Aluguel", "1800.00", 25, criado_em=self.agora - timedelta(days=90))
        certa = self._expense("Aluguel", "-1800.00", date(2026, 8, 25))
        outra = self._expense("Aluguel", "-1800.00", date(2026, 8, 3))

        self._rodar()

        certa.refresh_from_db(); outra.refresh_from_db()
        # o dia mais proximo do day_of_month vence; a outra fica manual
        self.assertEqual(certa.recurring_template_id, tpl.id)
        self.assertIsNone(outra.recurring_template_id)

    def test_desempate_prefere_valor_identico_ao_do_template(self):
        tpl = self._template("Aluguel", "1800.00", 25, criado_em=self.agora - timedelta(days=90))
        valor_certo = self._expense("Aluguel", "-1800.00", date(2026, 8, 20))
        valor_errado = self._expense("Aluguel", "-999.00", date(2026, 8, 25))

        self._rodar()

        valor_certo.refresh_from_db(); valor_errado.refresh_from_db()
        self.assertEqual(valor_certo.recurring_template_id, tpl.id)
        self.assertIsNone(valor_errado.recurring_template_id)

    # -- isolamento entre tenants ----------------------------------------
    def test_nao_liga_despesa_de_outro_tenant(self):
        outro = "tenant-backfill-2"
        ExpenseCategory.objects.create(tenant_id=outro, name="Assinaturas")
        self._template("Netflix", "20.90", 3, criado_em=self.agora - timedelta(days=90))
        alheia = self._expense("Netflix", "-20.90", date(2026, 9, 3), tenant=outro)

        self._rodar()

        alheia.refresh_from_db()
        self.assertIsNone(alheia.recurring_template_id)

    # -- idempotencia e reversao ------------------------------------------
    def test_rodar_duas_vezes_nao_muda_nada(self):
        tpl = self._template("Spotify", "23.90", 18, criado_em=self.agora - timedelta(days=90))
        exp = self._expense("Spotify", "-23.90", date(2026, 9, 18))

        self._rodar()
        self._rodar()

        exp.refresh_from_db()
        self.assertEqual(exp.recurring_template_id, tpl.id)
        self.assertEqual(Expense.objects.filter(recurring_template=tpl).count(), 1)

    def test_reversao_desfaz_todos_os_vinculos(self):
        self._template("Spotify", "23.90", 18, criado_em=self.agora - timedelta(days=90))
        exp = self._expense("Spotify", "-23.90", date(2026, 9, 18))
        self._rodar()

        backfill.desligar_historico(global_apps, None)

        exp.refresh_from_db()
        self.assertIsNone(exp.recurring_template_id)

    # -- o backfill nao pode mexer em dinheiro ----------------------------
    def test_backfill_nao_altera_valores_nem_datas(self):
        self._template("Conta da Vivo", "41.00", 1, criado_em=self.agora - timedelta(days=90))
        exp = self._expense("Conta da Vivo", "-41.90", date(2026, 8, 17))
        antes = (exp.amount, exp.date, exp.credit_card_id, exp.category_id, exp.quantity)

        self._rodar()

        exp.refresh_from_db()
        depois = (exp.amount, exp.date, exp.credit_card_id, exp.category_id, exp.quantity)
        self.assertEqual(antes, depois)

    def test_soma_do_saldo_permanece_identica(self):
        self._template("Spotify", "23.90", 18, criado_em=self.agora - timedelta(days=90))
        self._expense("Spotify", "-23.90", date(2026, 9, 18))
        self._expense("Mercado", "-150.00", date(2026, 9, 10))
        total_antes = sum(e.amount for e in Expense.objects.all())

        self._rodar()

        total_depois = sum(e.amount for e in Expense.objects.all())
        self.assertEqual(total_antes, total_depois)
        self.assertEqual(Expense.objects.count(), 2)


from decimal import Decimal

from django.test import TestCase

from expenses.behaviors import _split_installments


class SplitInstallmentsTest(TestCase):
    def test_soma_das_parcelas_bate_com_o_total_negativo(self):
        """Despesa parcelada: 1853,00 em 3x nao pode perder centavos."""
        parcelas = _split_installments(Decimal("-1853.00"), 3)

        self.assertEqual(sum(parcelas), Decimal("-1853.00"))

    def test_residual_negativo_vai_para_as_primeiras_parcelas(self):
        parcelas = _split_installments(Decimal("-1853.00"), 3)

        self.assertEqual(
            parcelas, [Decimal("-617.67"), Decimal("-617.67"), Decimal("-617.66")]
        )

    def test_duas_parcelas_com_residual_negativo(self):
        parcelas = _split_installments(Decimal("-192.31"), 2)

        self.assertEqual(parcelas, [Decimal("-96.16"), Decimal("-96.15")])
        self.assertEqual(sum(parcelas), Decimal("-192.31"))

    def test_divisao_exata_negativa_nao_muda(self):
        parcelas = _split_installments(Decimal("-488.08"), 2)

        self.assertEqual(parcelas, [Decimal("-244.04"), Decimal("-244.04")])

    def test_cem_reais_em_tres_vezes_negativo(self):
        """Caso classico: 100,00 em 3x = 33,34 + 33,33 + 33,33."""
        parcelas = _split_installments(Decimal("-100.00"), 3)

        self.assertEqual(
            parcelas, [Decimal("-33.34"), Decimal("-33.33"), Decimal("-33.33")]
        )
        self.assertEqual(sum(parcelas), Decimal("-100.00"))

    # -- comportamento positivo preservado --------------------------------
    def test_positivo_continua_igual(self):
        self.assertEqual(
            _split_installments(Decimal("1853.00"), 3),
            [Decimal("617.67"), Decimal("617.67"), Decimal("617.66")],
        )
        self.assertEqual(
            _split_installments(Decimal("100.00"), 3),
            [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")],
        )

    def test_parcela_unica_devolve_o_total(self):
        self.assertEqual(_split_installments(Decimal("-50.00"), 1), [Decimal("-50.00")])

    def test_aceita_float_e_string(self):
        self.assertEqual(sum(_split_installments(-100.00, 3)), Decimal("-100.00"))
        self.assertEqual(sum(_split_installments("-100.00", 3)), Decimal("-100.00"))


from datetime import date
from decimal import Decimal

from django.test import TestCase

from cards.models import CreditCard
from catalog.models import ExpenseCategory
from expenses.behaviors import RecurringExpenseBehavior
from expenses.models import Expense, RecurringExpenseTemplate


class RecurringExpenseCharacterizationTest(TestCase):
    TENANT = "tenant-recurring-1"
    OTHER_TENANT = "tenant-recurring-2"

    def setUp(self):
        self.category = ExpenseCategory.objects.create(
            tenant_id=self.TENANT, name="Assinaturas"
        )
        self.card = CreditCard.objects.create(
            tenant_id=self.TENANT, name="Itau Azul", closing_day=25, due_day=3
        )

    def _template(self, **overrides):
        data = dict(
            tenant_id=self.TENANT,
            description="Netflix",
            amount=Decimal("20.90"),
            day_of_month=3,
            payment_method="cartao",
            credit_card=self.card,
            category=self.category,
        )
        data.update(overrides)
        return RecurringExpenseTemplate.objects.create(**data)

    # -- bug 1: sinal -----------------------------------------------------
    def test_generate_month_materializa_gasto_fixo_como_despesa(self):
        """Template positivo deve virar Expense NEGATIVA (despesa)."""
        self._template()

        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        expense = Expense.objects.get(tenant_id=self.TENANT, description="Netflix")
        self.assertEqual(expense.amount, Decimal("-20.90"))

    def test_template_ja_negativo_nao_inverte_para_receita(self):
        """amount negativo no template continua despesa (nao vira receita)."""
        self._template(amount=Decimal("-20.90"))

        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        expense = Expense.objects.get(tenant_id=self.TENANT, description="Netflix")
        self.assertEqual(expense.amount, Decimal("-20.90"))

    # -- bug 2: cartao orfao ----------------------------------------------
    def test_template_cartao_sem_cartao_nao_gera_despesa_orfa(self):
        """Template legado cartao/NULL nao pode virar Expense invisivel."""
        self._template(payment_method="cartao", credit_card=None)

        response = RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        self.assertFalse(
            Expense.objects.filter(
                tenant_id=self.TENANT, payment_method="cartao", credit_card__isnull=True
            ).exists(),
            "gerou despesa de cartao sem cartao: invisivel em qualquer fatura",
        )
        self.assertIn("Netflix", response.data.get("skipped_invalid", []))
        self.assertNotIn("Netflix", response.data["created"])

    def test_template_dinheiro_sem_cartao_e_valido(self):
        """dinheiro sem cartao e o caso normal, nao pode ser bloqueado."""
        self._template(payment_method="dinheiro", credit_card=None)

        response = RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        expense = Expense.objects.get(tenant_id=self.TENANT, description="Netflix")
        self.assertEqual(expense.amount, Decimal("-20.90"))
        self.assertIsNone(expense.credit_card_id)
        self.assertIn("Netflix", response.data["created"])

    # -- comportamento preservado -----------------------------------------
    def test_preserva_cartao_categoria_e_data(self):
        self._template(day_of_month=5)

        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        expense = Expense.objects.get(tenant_id=self.TENANT, description="Netflix")
        self.assertEqual(expense.credit_card_id, self.card.id)
        self.assertEqual(expense.category_id, self.category.id)
        self.assertEqual(expense.date, date(2026, 9, 5))
        self.assertEqual(expense.payment_method, "cartao")
        self.assertEqual(expense.quantity, 1)

    def test_nao_duplica_quando_ja_existe_no_mes(self):
        self._template()
        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        response = RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        self.assertEqual(
            Expense.objects.filter(tenant_id=self.TENANT, description="Netflix").count(), 1
        )
        self.assertIn("Netflix", response.data["skipped"])

    def test_template_inativo_nao_gera(self):
        self._template(is_active=False)

        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        self.assertFalse(Expense.objects.filter(tenant_id=self.TENANT).exists())

    def test_dia_29_a_31_cai_no_ultimo_dia_do_mes(self):
        self._template(day_of_month=28)
        RecurringExpenseTemplate.objects.filter(tenant_id=self.TENANT).update(day_of_month=31)

        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=2, year=2026).run()

        expense = Expense.objects.get(tenant_id=self.TENANT, description="Netflix")
        self.assertEqual(expense.date, date(2026, 2, 28))

    def test_nao_vaza_template_de_outro_tenant(self):
        self._template()

        RecurringExpenseBehavior(self.OTHER_TENANT, 'generate_month', month=9, year=2026).run()

        self.assertFalse(Expense.objects.filter(tenant_id=self.OTHER_TENANT).exists())


class RecurringExpenseUpdateTest(TestCase):
    """Edicao de template, usada pela tela de gerenciamento de gastos fixos."""

    TENANT = "tenant-recurring-upd"
    OTHER_TENANT = "tenant-recurring-other"

    def setUp(self):
        self.category = ExpenseCategory.objects.create(
            tenant_id=self.TENANT, name="Assinaturas"
        )
        self.card = CreditCard.objects.create(
            tenant_id=self.TENANT, name="Itau Azul", closing_day=25, due_day=3
        )
        self.tpl = RecurringExpenseTemplate.objects.create(
            tenant_id=self.TENANT,
            description="Netflix",
            amount=Decimal("20.90"),
            day_of_month=3,
            payment_method="cartao",
            credit_card=self.card,
            category=self.category,
        )

    def _payload(self, **overrides):
        data = dict(
            description="Netflix",
            amount=Decimal("29.90"),
            day_of_month=10,
            payment_method="cartao",
            credit_card_id=self.card.id,
            category_id=self.category.id,
        )
        data.update(overrides)
        return data

    def test_atualiza_campos_do_template(self):
        response = RecurringExpenseBehavior(self.TENANT, 'update', template_id=self.tpl.id, data=self._payload()).run()

        self.assertEqual(response.status_code, 200)
        self.tpl.refresh_from_db()
        self.assertEqual(self.tpl.amount, Decimal("29.90"))
        self.assertEqual(self.tpl.day_of_month, 10)

    def test_preserva_is_active_ao_editar(self):
        """Editar nao pode reativar um template pausado."""
        self.tpl.is_active = False
        self.tpl.save(update_fields=["is_active"])

        RecurringExpenseBehavior(self.TENANT, 'update', template_id=self.tpl.id, data=self._payload()).run()

        self.tpl.refresh_from_db()
        self.assertFalse(self.tpl.is_active)

    def test_permite_trocar_de_cartao_para_dinheiro(self):
        RecurringExpenseBehavior(
            self.TENANT, 'update', template_id=self.tpl.id,
            data=self._payload(payment_method="dinheiro", credit_card_id=None),
        ).run()

        self.tpl.refresh_from_db()
        self.assertEqual(self.tpl.payment_method, "dinheiro")
        self.assertIsNone(self.tpl.credit_card_id)

    def test_rejeita_dia_fora_do_intervalo(self):
        response = RecurringExpenseBehavior(
            self.TENANT, 'update', template_id=self.tpl.id,
            data=self._payload(day_of_month=31),
        ).run()

        self.assertEqual(response.status_code, 400)
        self.tpl.refresh_from_db()
        self.assertEqual(self.tpl.day_of_month, 3)

    def test_nao_edita_template_de_outro_tenant(self):
        response = RecurringExpenseBehavior(
            self.OTHER_TENANT, 'update', template_id=self.tpl.id, data=self._payload(),
        ).run()

        self.assertEqual(response.status_code, 404)
        self.tpl.refresh_from_db()
        self.assertEqual(self.tpl.amount, Decimal("20.90"))

    def test_template_inexistente_retorna_404(self):
        response = RecurringExpenseBehavior(
            self.TENANT, 'update', template_id=999999, data=self._payload(),
        ).run()

        self.assertEqual(response.status_code, 404)


from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from cards.models import CreditCard
from catalog.models import ExpenseCategory
from expenses.behaviors import RecurringExpenseBehavior
from expenses.models import Expense, RecurringExpenseTemplate
from expenses.serializer import ExpenseSerializer


class RecurringTemplateLinkTest(TestCase):
    TENANT = "tenant-link-1"

    def setUp(self):
        self.category = ExpenseCategory.objects.create(
            tenant_id=self.TENANT, name="Assinaturas"
        )
        self.card = CreditCard.objects.create(
            tenant_id=self.TENANT, name="Itau Azul", closing_day=25, due_day=3
        )

    def _template(self, **overrides):
        data = dict(
            tenant_id=self.TENANT,
            description="Netflix",
            amount=Decimal("20.90"),
            day_of_month=3,
            payment_method="cartao",
            credit_card=self.card,
            category=self.category,
        )
        data.update(overrides)
        return RecurringExpenseTemplate.objects.create(**data)

    def _manual(self, description="Netflix", day=15, amount=Decimal("-20.90")):
        return Expense.objects.create(
            tenant_id=self.TENANT,
            category=self.category,
            description=description,
            quantity=1,
            amount=amount,
            date=date(2026, 9, day),
            payment_method="cartao",
            credit_card=self.card,
        )

    # -- vinculo ----------------------------------------------------------
    def test_despesa_gerada_aponta_para_o_template(self):
        tpl = self._template()

        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        expense = Expense.objects.get(tenant_id=self.TENANT)
        self.assertEqual(expense.recurring_template_id, tpl.id)

    def test_despesa_manual_nao_aponta_para_template(self):
        self._manual()

        expense = Expense.objects.get(tenant_id=self.TENANT)
        self.assertIsNone(expense.recurring_template_id)

    # -- defeito 1: gasto manual homonimo bloqueava o gasto fixo ----------
    def test_gasto_manual_homonimo_nao_impede_a_geracao(self):
        self._template()
        self._manual()  # mesma descricao, lancado a mao

        response = RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        self.assertIn("Netflix", response.data["created"])
        self.assertEqual(Expense.objects.filter(tenant_id=self.TENANT).count(), 2)
        # a manual continua livre, sem vinculo
        self.assertEqual(
            Expense.objects.filter(recurring_template__isnull=True).count(), 1
        )

    # -- defeito 2: renomear o template duplicava ------------------------
    def test_renomear_template_apos_gerar_nao_duplica(self):
        tpl = self._template()
        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        tpl.description = "Netflix Premium"
        tpl.save(update_fields=["description"])
        response = RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        self.assertEqual(Expense.objects.filter(tenant_id=self.TENANT).count(), 1)
        self.assertIn("Netflix Premium", response.data["skipped"])

    # -- defeito 3: editar a descricao da despesa duplicava --------------
    def test_editar_descricao_da_despesa_gerada_nao_duplica(self):
        self._template()
        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        Expense.objects.filter(tenant_id=self.TENANT).update(description="Netflix (familia)")
        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        self.assertEqual(Expense.objects.filter(tenant_id=self.TENANT).count(), 1)

    # -- a trava do banco -------------------------------------------------
    def test_banco_recusa_duas_despesas_do_mesmo_template_no_mesmo_mes(self):
        tpl = self._template()
        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Expense.objects.create(
                    tenant_id=self.TENANT,
                    category=self.category,
                    description="qualquer outra coisa",
                    quantity=1,
                    amount=Decimal("-20.90"),
                    date=date(2026, 9, 28),
                    payment_method="cartao",
                    credit_card=self.card,
                    recurring_template=tpl,
                )

    def test_banco_aceita_o_mesmo_template_em_meses_diferentes(self):
        self._template()

        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()
        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=10, year=2026).run()

        self.assertEqual(Expense.objects.filter(tenant_id=self.TENANT).count(), 2)

    def test_constraint_nao_limita_despesas_manuais(self):
        """NULL nunca conflita: o usuario pode repetir gastos manuais a vontade."""
        self._manual(day=10)
        self._manual(day=20)

        self.assertEqual(Expense.objects.filter(tenant_id=self.TENANT).count(), 2)

    # -- historico sobrevive ao template ---------------------------------
    def test_apagar_template_preserva_a_despesa(self):
        tpl = self._template()
        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        tpl.delete()

        expense = Expense.objects.get(tenant_id=self.TENANT)
        self.assertEqual(expense.amount, Decimal("-20.90"))
        self.assertIsNone(expense.recurring_template_id)

    def test_apagar_template_libera_o_mes_para_novo_template(self):
        tpl = self._template()
        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()
        tpl.delete()

        self._template()
        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        self.assertEqual(Expense.objects.filter(tenant_id=self.TENANT).count(), 2)

    # -- contrato da API --------------------------------------------------
    def test_serializer_marca_gasto_fixo_como_recurring(self):
        tpl = self._template()
        RecurringExpenseBehavior(self.TENANT, 'generate_month', month=9, year=2026).run()

        data = ExpenseSerializer(Expense.objects.get(tenant_id=self.TENANT)).data

        self.assertTrue(data["is_recurring"])
        self.assertEqual(data["recurring_template_id"], tpl.id)

    def test_serializer_marca_gasto_manual_como_nao_recurring(self):
        self._manual()

        data = ExpenseSerializer(Expense.objects.get(tenant_id=self.TENANT)).data

        self.assertFalse(data["is_recurring"])
        self.assertIsNone(data["recurring_template_id"])

    def test_payload_do_cliente_nao_consegue_forjar_o_vinculo(self):
        """recurring_template e read-only: so o generate_month pode preencher."""
        tpl = self._template()

        serializer = ExpenseSerializer(data={
            "category_id": self.category.id,
            "description": "Tentativa",
            "quantity": 1,
            "amount": "-10.00",
            "date": "2026-09-09",
            "payment_method": "dinheiro",
            "recurring_template": tpl.id,
        })
        serializer.is_valid(raise_exception=True)

        self.assertNotIn("recurring_template", serializer.validated_data)


class RecurringTemplateTenantIsolationTest(TestCase):
    """Templates homonimos de tenants diferentes nao podem interferir."""

    A = "tenant-link-a"
    B = "tenant-link-b"

    def _setup_tenant(self, tenant, amount, day):
        category = ExpenseCategory.objects.create(tenant_id=tenant, name="Assinaturas")
        card = CreditCard.objects.create(
            tenant_id=tenant, name="Cartao", closing_day=25, due_day=3
        )
        return RecurringExpenseTemplate.objects.create(
            tenant_id=tenant,
            description="Netflix",
            amount=amount,
            day_of_month=day,
            payment_method="cartao",
            credit_card=card,
            category=category,
        )

    def test_dois_tenants_com_netflix_geram_cada_um_o_seu(self):
        tpl_a = self._setup_tenant(self.A, Decimal("44.90"), 27)
        tpl_b = self._setup_tenant(self.B, Decimal("20.90"), 3)

        RecurringExpenseBehavior(self.A, 'generate_month', month=9, year=2026).run()
        RecurringExpenseBehavior(self.B, 'generate_month', month=9, year=2026).run()

        self.assertEqual(
            Expense.objects.get(tenant_id=self.A).recurring_template_id, tpl_a.id
        )
        self.assertEqual(
            Expense.objects.get(tenant_id=self.B).recurring_template_id, tpl_b.id
        )
