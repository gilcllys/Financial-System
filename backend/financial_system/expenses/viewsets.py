import calendar
from datetime import date

from django.db.models import Count, Q, Sum
from django.db.models.functions import Abs, ExtractMonth
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from expenses import models, serializer
from expenses.behaviors import CreateExpenseBehavior

# Nomes dos meses em português (índice 0 não utilizado)
_MONTH_NAMES = [
    '',
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]


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

    @action(detail=False, methods=['post'], url_path='create-expense')
    def perform_destroy(self, instance):
        if instance.tenant_id != self.request.user.tenant_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Você não tem permissão para excluir este recurso.")
        instance.delete()

    def create_expense(self, request):
        s = serializer.CreateExpenseInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        payload = dict(s.validated_data)
        payload['tenant_id'] = request.user.tenant_id
        return CreateExpenseBehavior(data=payload).run()

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
        """
        GET /api/expenses/expenses/analytics/monthly/?year=2026

        Retorna os 12 meses do ano com totais de receitas, despesas,
        saldo e quantidade de lançamentos.

        Query params:
          - year (int, default=ano atual)
        """
        today = date.today()
        try:
            year = int(request.query_params.get('year', today.year))
            if year <= 0:
                raise ValueError
        except (ValueError, TypeError):
            year = today.year

        rows = (
            models.Expense.objects
            .filter(tenant_id=request.user.tenant_id, date__year=year)
            .annotate(month_num=ExtractMonth('date'))
            .values('month_num')
            .annotate(
                income=Sum('amount', filter=Q(amount__gt=0)),
                expenses_total=Sum(Abs('amount'), filter=Q(amount__lt=0)),
                count=Count('id'),
            )
            .order_by('month_num')
        )

        month_map = {row['month_num']: row for row in rows}

        result = []
        for m in range(1, 13):
            row = month_map.get(m, {})
            income = float(row.get('income') or 0)
            expenses = float(row.get('expenses_total') or 0)
            result.append({
                'month': m,
                'month_name': _MONTH_NAMES[m],
                'income': round(income, 2),
                'expenses': round(expenses, 2),
                'balance': round(income - expenses, 2),
                'count': row.get('count', 0),
            })

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='analytics/by-category')
    def analytics_by_category(self, request):
        """
        GET /api/expenses/expenses/analytics/by-category/?month=6&year=2026

        Retorna despesas agrupadas por categoria (somente lançamentos com
        amount < 0), ordenadas por total decrescente.

        Query params:
          - month (int 1-12, opcional)
          - year  (int, opcional)
        """
        params = request.query_params
        qs = models.Expense.objects.filter(
            tenant_id=request.user.tenant_id,
            amount__lt=0,
        )

        raw_month = params.get('month')
        if raw_month is not None:
            try:
                month = int(raw_month)
                if 1 <= month <= 12:
                    qs = qs.filter(date__month=month)
            except (ValueError, TypeError):
                pass

        raw_year = params.get('year')
        if raw_year is not None:
            try:
                year = int(raw_year)
                if year > 0:
                    qs = qs.filter(date__year=year)
            except (ValueError, TypeError):
                pass

        rows = (
            qs
            .values('category_id', 'category__name')
            .annotate(
                total=Sum(Abs('amount')),
                count=Count('id'),
            )
            .order_by('-total')
        )

        grand_total = sum(float(row['total'] or 0) for row in rows)

        result = []
        for row in rows:
            total = float(row['total'] or 0)
            result.append({
                'category_id': row['category_id'],
                'category_name': row['category__name'],
                'total': round(total, 2),
                'count': row['count'],
                'percentage': round((total / grand_total * 100) if grand_total else 0, 2),
            })

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='analytics/by-card')
    def analytics_by_card(self, request):
        """
        GET /api/expenses/expenses/analytics/by-card/?month=6&year=2026

        Retorna despesas agrupadas por cartão de crédito (payment_method='cartao'
        e credit_card_id IS NOT NULL), ordenadas por total decrescente.

        Query params:
          - month (int 1-12, opcional)
          - year  (int, opcional)
        """
        params = request.query_params
        qs = models.Expense.objects.filter(
            tenant_id=request.user.tenant_id,
            payment_method='cartao',
            credit_card_id__isnull=False,
        )

        raw_month = params.get('month')
        if raw_month is not None:
            try:
                month = int(raw_month)
                if 1 <= month <= 12:
                    qs = qs.filter(date__month=month)
            except (ValueError, TypeError):
                pass

        raw_year = params.get('year')
        if raw_year is not None:
            try:
                year = int(raw_year)
                if year > 0:
                    qs = qs.filter(date__year=year)
            except (ValueError, TypeError):
                pass

        rows = (
            qs
            .values('credit_card_id', 'credit_card__name', 'credit_card__last_four_digits')
            .annotate(
                total=Sum(Abs('amount')),
                count=Count('id'),
            )
            .order_by('-total')
        )

        grand_total = sum(float(row['total'] or 0) for row in rows)

        result = []
        for row in rows:
            total = float(row['total'] or 0)
            result.append({
                'card_id': row['credit_card_id'],
                'card_name': row['credit_card__name'],
                'last_four_digits': row['credit_card__last_four_digits'],
                'total': round(total, 2),
                'count': row['count'],
                'percentage': round((total / grand_total * 100) if grand_total else 0, 2),
            })

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='analytics/daily')
    def analytics_daily(self, request):
        """
        GET /api/expenses/expenses/analytics/daily/?month=6&year=2026

        Retorna o movimento diário do mês — todos os dias aparecem, mesmo
        sem lançamentos (total=0, count=0).

        O campo `total` é a soma de abs(amount) de todos os lançamentos do
        dia (receitas e despesas somadas em valor absoluto).

        Query params:
          - month (int 1-12, default=mês atual)
          - year  (int, default=ano atual)
        """
        today = date.today()
        params = request.query_params

        try:
            month = int(params.get('month', today.month))
            if not (1 <= month <= 12):
                raise ValueError
        except (ValueError, TypeError):
            month = today.month

        try:
            year = int(params.get('year', today.year))
            if year <= 0:
                raise ValueError
        except (ValueError, TypeError):
            year = today.year

        rows = (
            models.Expense.objects
            .filter(
                tenant_id=request.user.tenant_id,
                date__year=year,
                date__month=month,
            )
            .values('date')
            .annotate(
                total=Sum(Abs('amount')),
                count=Count('id'),
            )
        )

        # Indexa por date para lookup O(1)
        day_map = {row['date']: row for row in rows}

        _, days_in_month = calendar.monthrange(year, month)

        result = []
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            row = day_map.get(current_date, {})
            result.append({
                'day': day,
                'date': current_date.isoformat(),
                'total': round(float(row.get('total') or 0), 2),
                'count': row.get('count', 0),
            })

        return Response(result, status=status.HTTP_200_OK)
