from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, RequestFactory
from rest_framework.request import Request
from expenses.viewsets import ExpensePagination, ExpenseViewSet
from expenses.serializer import DeleteInstallmentsInputSerializer


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

    def test_404_response_contains_error_key(self):
        response, _, _ = self._call_action(
            data={'description_prefix': 'Celular novo', 'total_installments': 10},
            delete_return=(0, {}),
        )
        self.assertIn('error', response.data)

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
