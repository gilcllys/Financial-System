"""Aggregated read models and thin API views for complex screens."""

from datetime import date

from rest_framework.response import Response
from rest_framework.views import APIView

from financial_system.screen_serializers import HomeDashboardQuerySerializer


class HomeDashboardBehavior:
    """Compose existing domain read models for the Home screen."""

    def __init__(self, user, month: int, year: int):
        self.user = user
        self.tenant_id = user.tenant_id
        self.month = month
        self.year = year

    def run(self) -> Response:
        analytics = self._load_analytics()
        sources = self._load_screen_sources()
        return self._build_response(analytics, sources)

    def _load_analytics(self):
        from expenses.behaviors import ExpenseAnalyticsBehavior

        selected_period = {
            'month': self.month,
            'year': self.year,
            'closing_month': self.month,
            'closing_year': self.year,
        }
        return {
            'consolidated': ExpenseAnalyticsBehavior(
                self.tenant_id, 'consolidated_summary', selected_period,
            ).run(),
            'home_charts': ExpenseAnalyticsBehavior(
                self.tenant_id, 'home_charts', selected_period,
            ).run(),
            'evolution': ExpenseAnalyticsBehavior(
                self.tenant_id, 'monthly', {'year': self.year},
            ).run(),
        }

    def _load_screen_sources(self):
        from cards.models import CreditCard
        from catalog.models import ExpenseCategory
        from expenses.models import Expense, RecurringExpenseTemplate

        return {
            'expenses': Expense.objects.filter(
            tenant_id=self.tenant_id, date__year=self.year, date__month=self.month,
            ).select_related('category', 'credit_card').order_by('-date', '-id'),
            'installments': Expense.objects.filter(
                tenant_id=self.tenant_id, description__iregex=r'parcela\s+\d+/\d+',
            ).select_related('category', 'credit_card').order_by('-date', '-id'),
            'categories': ExpenseCategory.objects.filter(
                tenant_id__in=['system', self.tenant_id],
            ).order_by('name'),
            'templates': RecurringExpenseTemplate.objects.filter(
                tenant_id=self.tenant_id,
            ).select_related('category', 'credit_card').order_by('description'),
            'cards': CreditCard.objects.filter(tenant_id=self.tenant_id).order_by('id').values(
                'id', 'name', 'last_four_digits', 'closing_day', 'due_day',
            ),
        }

    def _build_response(self, analytics, sources):
        from cards.behaviors import OpenInvoicesBehavior
        from catalog.serializer import ExpenseCategorySerializer
        from debts.behaviors import HomeSummaryBehavior
        from expenses.serializer import ExpenseSerializer, RecurringExpenseTemplateSerializer

        expenses = sources['expenses']
        return Response({
            **analytics,
            'open_invoices': OpenInvoicesBehavior(
                self.tenant_id, self.month, self.year,
            ).run().data,
            'shared_debts': HomeSummaryBehavior(self.user).run().data,
            'expenses': {
                'count': expenses.count(),
                'results': ExpenseSerializer(expenses[:20], many=True).data,
            },
            'installment_expenses': ExpenseSerializer(sources['installments'], many=True).data,
            'cards': list(sources['cards']),
            'categories': ExpenseCategorySerializer(sources['categories'], many=True).data,
            'recurring_templates': RecurringExpenseTemplateSerializer(
                sources['templates'], many=True,
            ).data,
        })


class InstallmentsOverviewBehavior:
    """Compose personal and shared installment ledgers for the screen."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def run(self) -> Response:
        from cards.models import CreditCard
        from cards.serializer import CreditCardSerializer
        from debts.models import SharedEntry
        from debts.serializer import SharedEntrySerializer
        from expenses.models import Expense
        from expenses.serializer import ExpenseSerializer

        expense_rows = Expense.objects.filter(
            tenant_id=self.tenant_id, description__iregex=r'parcela\s+\d+/\d+',
        ).select_related('credit_card', 'category').order_by('-date', '-id')
        shared_rows = (
            SharedEntry.objects.filter(
                shared_debt__members__tenant_id=self.tenant_id,
                installment_group_id__isnull=False,
            ).select_related('shared_debt', 'paid_by', 'credit_card', 'category')
            .prefetch_related('participants', 'shared_debt__members')
            .distinct().order_by('-date', '-id')
        )
        cards = CreditCard.objects.filter(tenant_id=self.tenant_id).order_by('id')
        return Response({
            'expenses': ExpenseSerializer(expense_rows, many=True).data,
            'shared_entries': SharedEntrySerializer(shared_rows, many=True).data,
            'cards': CreditCardSerializer(cards, many=True).data,
        })


class HomeDashboardView(APIView):
    """GET /api/dashboard/home/?month=&year= — one read for the Home screen."""

    def get(self, request):
        query = HomeDashboardQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        today = date.today()
        params = query.validated_data
        return HomeDashboardBehavior(
            request.user,
            params.get('month', today.month),
            params.get('year', today.year),
        ).run()


class InstallmentsOverviewView(APIView):
    """GET /api/dashboard/installments/ — card metadata and both ledgers."""

    def get(self, request):
        return InstallmentsOverviewBehavior(request.user.tenant_id).run()
