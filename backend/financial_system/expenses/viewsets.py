import re
from datetime import date

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from expenses import models, serializer
from expenses.behaviors import CreateExpenseBehavior, RecurringExpenseBehavior
from expenses.analytics_behaviors import ExpenseAnalyticsBehavior
from expenses.bulk_import_behaviors import BulkImportExpenseBehavior


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

        # --- month ---------------------------------------------------
        raw_month = params.get('month')
        if raw_month is not None:
            try:
                month = int(raw_month)
                if 1 <= month <= 12:
                    qs = qs.filter(date__month=month)
            except (ValueError, TypeError):
                pass  # parâmetro inválido ignorado silenciosamente

        # --- year ----------------------------------------------------
        raw_year = params.get('year')
        if raw_year is not None:
            try:
                year = int(raw_year)
                if year > 0:
                    qs = qs.filter(date__year=year)
            except (ValueError, TypeError):
                pass

        # --- category_id ---------------------------------------------
        raw_category = params.get('category_id')
        if raw_category is not None:
            try:
                category_id = int(raw_category)
                qs = qs.filter(category_id=category_id)
            except (ValueError, TypeError):
                pass

        # --- payment_method ------------------------------------------
        payment_method = params.get('payment_method')
        if payment_method is not None:
            valid_choices = {choice[0] for choice in models.Expense.PAYMENT_METHOD_CHOICES}
            if payment_method in valid_choices:
                qs = qs.filter(payment_method=payment_method)

        # --- credit_card_id ------------------------------------------
        raw_credit_card = params.get('credit_card_id')
        if raw_credit_card is not None:
            try:
                qs = qs.filter(credit_card_id=int(raw_credit_card))
            except (ValueError, TypeError):
                pass

        # --- start_date / end_date -----------------------------------
        raw_start_date = params.get('start_date')
        if raw_start_date:
            try:
                qs = qs.filter(date__gte=date.fromisoformat(raw_start_date))
            except (ValueError, TypeError):
                pass

        raw_end_date = params.get('end_date')
        if raw_end_date:
            try:
                qs = qs.filter(date__lte=date.fromisoformat(raw_end_date))
            except (ValueError, TypeError):
                pass

        # --- search (description icontains) --------------------------
        # [SEC-A03] Limita o tamanho da query para prevenir DoS via queries longas
        # (icontains é parameterizado pelo ORM — seguro contra SQL injection)
        search = params.get('search')
        if search:
            search = search.strip()[:200]
            if search:
                qs = qs.filter(description__icontains=search)

        return qs

    def perform_update(self, serializer):
        """[SEC-A01] Defense-in-depth: garante que tenant_id não muda em updates."""
        serializer.save(tenant_id=self.request.user.tenant_id)

    # ------------------------------------------------------------------
    # Custom actions — CRUD helpers
    # ------------------------------------------------------------------

    def perform_create(self, serializer):
        """Injeta tenant_id do usuário autenticado ao criar via POST padrão."""
        serializer.save(tenant_id=self.request.user.tenant_id)

    def perform_destroy(self, instance):
        if instance.tenant_id != self.request.user.tenant_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Você não tem permissão para excluir este recurso.")
        instance.delete()

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
        return BulkImportExpenseBehavior(request.user.tenant_id).bulk_create(
            s.validated_data['items']
        )

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """GET import-template: retorna o modelo .xlsx de importa??o."""
        return BulkImportExpenseBehavior(request.user.tenant_id).import_template()

    @action(detail=False, methods=['post'], url_path='import-excel')
    def import_excel(self, request):
        """POST import-excel: delega a importa??o do arquivo enviado."""
        return BulkImportExpenseBehavior(request.user.tenant_id).import_excel(
            request.FILES.get('file')
        )

    @action(detail=False, methods=['post'], url_path='delete-installments')
    def delete_installments(self, request):
        """POST delete-installments: valida e remove as parcelas do grupo."""
        s = serializer.DeleteInstallmentsInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return BulkImportExpenseBehavior(request.user.tenant_id).delete_installments(
            s.validated_data['description_prefix'],
            s.validated_data['total_installments'],
        )

    @action(detail=False, methods=['get'], url_path='per-credit-card/(?P<card_id>[0-9]+)')
    def expenses_per_credit_card(self, request, card_id=None):
        """
        Retorna todas as despesas de um cartão de crédito sem paginação
        (lista simples — necessária para cálculos de fatura completa).
        """
        qs = (
            models.Expense.objects
            .filter(
                tenant_id=request.user.tenant_id,
                credit_card_id=card_id,
            )
            # Evita N+1 ao serializar category e credit_card
            .select_related('category', 'credit_card')
            .order_by('-date', '-id')
        )
        s = serializer.ExpenseSerializer(qs, many=True)
        return Response(s.data, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # Analytics actions
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='analytics/monthly')
    def analytics_monthly(self, request):
        """GET analytics/monthly."""
        data = ExpenseAnalyticsBehavior(request.user.tenant_id).analytics_monthly(
            request.query_params
        )
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='analytics/by-category')
    def analytics_by_category(self, request):
        """GET analytics/by-category."""
        data = ExpenseAnalyticsBehavior(request.user.tenant_id).analytics_by_category(
            request.query_params
        )
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='analytics/by-card')
    def analytics_by_card(self, request):
        """GET analytics/by-card."""
        data = ExpenseAnalyticsBehavior(request.user.tenant_id).analytics_by_card(
            request.query_params
        )
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='analytics/daily')
    def analytics_daily(self, request):
        """GET analytics/daily."""
        data = ExpenseAnalyticsBehavior(request.user.tenant_id).analytics_daily(
            request.query_params
        )
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='consolidated-summary')
    def consolidated_summary(self, request):
        """GET consolidated-summary."""
        data = ExpenseAnalyticsBehavior(request.user.tenant_id).consolidated_summary(
            request.query_params
        )
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='home-charts')
    def home_charts(self, request):
        """GET home-charts."""
        data = ExpenseAnalyticsBehavior(request.user.tenant_id).home_charts(
            request.query_params
        )
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get', 'post'], url_path='recurring-templates')
    def recurring_templates(self, request):
        """GET: listar templates, POST: criar template"""
        behavior = RecurringExpenseBehavior(request.user.tenant_id)
        if request.method == 'GET':
            return behavior.list()
        s = serializer.CreateRecurringExpenseInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return behavior.create({**dict(s.validated_data), 'tenant_id': request.user.tenant_id})

    @action(detail=False, methods=['delete', 'patch', 'put'],
            url_path=r'recurring-templates/(?P<tpl_id>[0-9]+)')
    def recurring_template_detail(self, request, tpl_id=None):
        """DELETE: excluir, PATCH: toggle is_active, PUT: editar"""
        behavior = RecurringExpenseBehavior(request.user.tenant_id)
        if request.method == 'DELETE':
            return behavior.delete(int(tpl_id))
        if request.method == 'PUT':
            s = serializer.CreateRecurringExpenseInputSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            return behavior.update(int(tpl_id), dict(s.validated_data))
        return behavior.toggle_active(int(tpl_id))

    @action(detail=False, methods=['post'], url_path='recurring-templates/generate-month')
    def generate_month_recurring(self, request):
        """POST {month, year} → materializa todos os templates ativos"""
        s = serializer.GenerateMonthInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return RecurringExpenseBehavior(request.user.tenant_id).generate_month(
            s.validated_data['month'], s.validated_data['year']
        )

