from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, RequestFactory
from rest_framework.request import Request
from expenses.viewsets import ExpensePagination, ExpenseViewSet


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
