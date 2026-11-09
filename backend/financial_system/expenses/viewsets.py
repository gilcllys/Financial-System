from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from expenses import models, serializer
from expenses.behaviors import (
    BulkImportExpenseBehavior,
    CardExpensesBehavior,
    CreateExpenseBehavior,
    ExpenseAnalyticsBehavior,
    ExpenseHistoryBehavior,
    BulkExpenseCategoryBehavior,
    RecurringExpenseBehavior,
)
from financial_system.params import apply_common_filters


class ExpensePagination(PageNumberPagination):
    """
    Paginação padrão para o endpoint de expenses.
    Query params disponíveis:
      - page       : número da página (começa em 1)
      - page_size  : tamanho da página (padrão 20, máximo 100)
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    page_query_param = 'page'


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.ExpenseSerializer
    queryset = models.Expense.objects.all()
    pagination_class = ExpensePagination
    # ------------------------------------------------------------------
    # Query params suportados pelo endpoint de listagem (GET /expenses/):
    #   month          (int 1-12)  – filtra por mês da data
    #   year           (int)       – filtra por ano da data
    #   category_id    (int)       – filtra por categoria
    #   payment_method (str)       – "dinheiro" | "cartao"
    #   search         (str)       – busca case-insensitive em description
    #
    # month e year são independentes: podem ser usados individualmente ou
    # em conjunto. Quando nenhum dos dois for informado, nenhum filtro de
    # data é aplicado (suporte a buscas históricas).
    # ------------------------------------------------------------------

    def get_queryset(self):
        qs = (
            models.Expense.objects
            .filter(tenant_id=self.request.user.tenant_id)
            # Evita N+1 ao serializar category e credit_card em cada registro
            .select_related('category', 'credit_card')
            .order_by('-date', '-id')
        )
        params = self.request.query_params
        qs = apply_common_filters(qs, params, models.Expense)
        category_key = params.get('category_key')
        if category_key:
            qs = qs.filter(category__key=category_key[:40])
        # --- search (description icontains) --------------------------
        # [SEC-A03] Limita o tamanho da query para prevenir DoS via queries longas
        # (icontains é parameterizado pelo ORM — seguro contra SQL injection)
        search = params.get('search')
        if search:
            search = search.strip()[:200]
            if search:
                qs = qs.filter(description__icontains=search)
        return qs

    @action(detail=False, methods=['get'], url_path='history')
    def history(self, request):
        query = serializer.HistoryQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return ExpenseHistoryBehavior(
            request.user.tenant_id, query.validated_data, request,
        ).run()

    @action(detail=False, methods=['post'], url_path='history/bulk-category')
    def history_bulk_category(self, request):
        payload = serializer.HistoryBulkCategoryInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return BulkExpenseCategoryBehavior(
            request.user.tenant_id, payload.validated_data,
        ).run()

    def perform_update(self, serializer):
        """[SEC-A01] Defense-in-depth: garante que tenant_id não muda em updates."""
        serializer.save(tenant_id=self.request.user.tenant_id)
    # ------------------------------------------------------------------
    # Custom actions — CRUD helpers
    # ------------------------------------------------------------------

    def perform_create(self, serializer):
        """Injeta tenant_id do usuário autenticado ao criar via POST padrão."""
        serializer.save(tenant_id=self.request.user.tenant_id)

    @action(detail=False, methods=['post'], url_path='create-expense')
    def create_expense(self, request):
        s = serializer.CreateExpenseInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        payload = dict(s.validated_data)
        payload['tenant_id'] = request.user.tenant_id
        return CreateExpenseBehavior(data=payload).run()

    @action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request):
        """POST bulk-create: valida o payload e delega a cria??o at?mica."""
        s = serializer.BulkCreateExpenseInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return BulkImportExpenseBehavior(
            request.user.tenant_id, 'bulk_create', items=s.validated_data['items'],
        ).run()

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """GET import-template: retorna o modelo .xlsx de importa??o."""
        return BulkImportExpenseBehavior(
            request.user.tenant_id, 'import_template',
        ).run()

    @action(detail=False, methods=['post'], url_path='import-excel')
    def import_excel(self, request):
        """POST import-excel: delega a importa??o do arquivo enviado."""
        payload = serializer.ImportExcelInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return BulkImportExpenseBehavior(
            request.user.tenant_id, 'import_excel', upload=payload.validated_data['file'],
        ).run()

    @action(detail=False, methods=['post'], url_path='delete-installments')
    def delete_installments(self, request):
        """POST delete-installments: valida e remove as parcelas do grupo."""
        payload = serializer.DeleteInstallmentsInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return BulkImportExpenseBehavior(
            request.user.tenant_id, 'delete_installments', **payload.validated_data,
        ).run()

    @action(detail=False, methods=['get'], url_path='per-credit-card/(?P<card_id>[0-9]+)')
    def expenses_per_credit_card(self, request, card_id=None):
        return CardExpensesBehavior(request.user.tenant_id, int(card_id)).run()
    # ------------------------------------------------------------------
    # Analytics actions
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='analytics/monthly')
    def analytics_monthly(self, request):
        query = serializer.ExpenseAnalyticsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(ExpenseAnalyticsBehavior(
            request.user.tenant_id, 'monthly', query.validated_data,
        ).run())

    @action(detail=False, methods=['get'], url_path='analytics/by-category')
    def analytics_by_category(self, request):
        query = serializer.ExpenseAnalyticsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(ExpenseAnalyticsBehavior(
            request.user.tenant_id, 'by_category', query.validated_data,
        ).run())

    @action(detail=False, methods=['get'], url_path='analytics/by-card')
    def analytics_by_card(self, request):
        query = serializer.ExpenseAnalyticsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(ExpenseAnalyticsBehavior(
            request.user.tenant_id, 'by_card', query.validated_data,
        ).run())

    @action(detail=False, methods=['get'], url_path='analytics/daily')
    def analytics_daily(self, request):
        query = serializer.ExpenseAnalyticsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(ExpenseAnalyticsBehavior(
            request.user.tenant_id, 'daily', query.validated_data,
        ).run())

    @action(detail=False, methods=['get'], url_path='consolidated-summary')
    def consolidated_summary(self, request):
        query = serializer.ExpenseAnalyticsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(ExpenseAnalyticsBehavior(
            request.user.tenant_id, 'consolidated_summary', query.validated_data,
        ).run())

    @action(detail=False, methods=['get'], url_path='home-charts')
    def home_charts(self, request):
        query = serializer.ExpenseAnalyticsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(ExpenseAnalyticsBehavior(
            request.user.tenant_id, 'home_charts', query.validated_data,
        ).run())

    @action(detail=False, methods=['get', 'post'], url_path='recurring-templates')
    def recurring_templates(self, request):
        """GET: listar templates, POST: criar template"""
        if request.method == 'GET':
            return RecurringExpenseBehavior(request.user.tenant_id, 'list').run()
        payload = serializer.CreateRecurringExpenseInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return RecurringExpenseBehavior(
            request.user.tenant_id, 'create', data=payload.validated_data,
        ).run()

    @action(detail=False, methods=['delete', 'patch', 'put'],
            url_path=r'recurring-templates/(?P<tpl_id>[0-9]+)')

    def recurring_template_detail(self, request, tpl_id=None):
        """DELETE: excluir, PATCH: toggle is_active, PUT: editar"""
        if request.method == 'DELETE':
            return RecurringExpenseBehavior(
                request.user.tenant_id, 'delete', template_id=int(tpl_id),
            ).run()
        if request.method == 'PUT':
            payload = serializer.CreateRecurringExpenseInputSerializer(data=request.data)
            payload.is_valid(raise_exception=True)
            return RecurringExpenseBehavior(
                request.user.tenant_id, 'update', template_id=int(tpl_id),
                data=payload.validated_data,
            ).run()
        return RecurringExpenseBehavior(
            request.user.tenant_id, 'toggle_active', template_id=int(tpl_id),
        ).run()

    @action(detail=False, methods=['post'], url_path='recurring-templates/generate-month')
    def generate_month_recurring(self, request):
        """POST {month, year} → materializa todos os templates ativos"""
        s = serializer.GenerateMonthInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return RecurringExpenseBehavior(
            request.user.tenant_id, 'generate_month', **s.validated_data,
        ).run()
