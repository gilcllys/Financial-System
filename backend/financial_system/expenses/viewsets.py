import calendar
import re
from datetime import date

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Abs, ExtractDay, ExtractMonth
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

    @action(detail=False, methods=['post'], url_path='delete-installments')
    def delete_installments(self, request):
        """
        POST /api/expenses/expenses/delete-installments/

        Remove todas as parcelas de uma despesa parcelada de uma só vez.

        O padrão de descrição esperado é o gerado por CreateExpenseBehavior:
          "{description_prefix} - Parcela {X}/{total_installments}"

        Request body:
          - description_prefix   (str, obrigatório, max 255 chars)
          - total_installments   (int, obrigatório, mínimo 2)

        Responses:
          200  {"deleted": N, "description_prefix": "...", "total_installments": N}
          404  {"error": "Nenhuma parcela encontrada para os critérios informados."}
          400  DRF validation errors
        """
        s = serializer.DeleteInstallmentsInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        description_prefix = s.validated_data['description_prefix']
        total_installments = s.validated_data['total_installments']

        # Build a regex that matches exactly the installment format produced by
        # CreateExpenseBehavior: "{BaseName} - Parcela {X}/{total}"
        # re.escape ensures user-supplied characters (e.g. dots, parens) are safe.
        pattern = rf'^{re.escape(description_prefix)} - Parcela \d+/{total_installments}$'

        # [SEC-A01] Always scope to the authenticated tenant before any DML.
        qs = models.Expense.objects.filter(
            tenant_id=request.user.tenant_id,
            description__iregex=pattern,
        )

        with transaction.atomic():
            deleted_count, _ = qs.delete()

        if deleted_count == 0:
            return Response(
                {'error': 'Nenhuma parcela encontrada para os critérios informados.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                'deleted': deleted_count,
                'description_prefix': description_prefix,
                'total_installments': total_installments,
            },
            status=status.HTTP_200_OK,
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

    @action(detail=False, methods=['get'], url_path='home-charts')
    def home_charts(self, request):
        """
        GET /api/expenses/expenses/home-charts/?month=6&year=2026

        Endpoint otimizado para a tela Home/Gastos.
        Retorna em UMA requisição:
          - summary: total_income, total_expenses, balance, count
          - by_category: gastos agrupados por categoria (doughnut)
          - daily: gasto por dia do mês (bar chart)
          - weekly: gasto agrupado por semana 1-4 (line chart)

        Usa apenas 2 queries ao banco (category group + daily group).
        """
        import calendar as cal_module

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

        tenant = request.user.tenant_id
        base_qs = models.Expense.objects.filter(
            tenant_id=tenant,
            date__year=year,
            date__month=month,
        )

        # ── Query 1: agrupamento por categoria (apenas despesas) ──────────
        cat_rows = (
            base_qs
            .filter(amount__lt=0)
            .values('category_id', 'category__name')
            .annotate(total=Sum(Abs('amount')), count=Count('id'))
            .order_by('-total')
        )
        cat_grand = sum(float(r['total'] or 0) for r in cat_rows)
        by_category = [
            {
                'category_id': r['category_id'],
                'category_name': r['category__name'] or 'Sem categoria',
                'total': round(float(r['total'] or 0), 2),
                'count': r['count'],
                'percentage': round(
                    float(r['total'] or 0) / cat_grand * 100 if cat_grand else 0, 2
                ),
            }
            for r in cat_rows
        ]

        # ── Query 2: agrupamento por dia ───────────────────────────────────
        day_rows = (
            base_qs
            .filter(amount__lt=0)
            .annotate(day_num=ExtractDay('date'))
            .values('day_num')
            .annotate(total=Sum(Abs('amount')), count=Count('id'))
            .order_by('day_num')
        )
        day_map = {r['day_num']: r for r in day_rows}

        _, days_in_month = cal_module.monthrange(year, month)

        daily = []
        weeks = [0.0, 0.0, 0.0, 0.0]
        for day in range(1, days_in_month + 1):
            row = day_map.get(day, {})
            total = round(float(row.get('total') or 0), 2)
            daily.append({'day': day, 'total': total, 'count': row.get('count', 0)})
            w = min((day - 1) // 7, 3)
            weeks[w] += total

        weekly = [
            {'week': i + 1, 'label': f'Semana {i + 1}', 'total': round(weeks[i], 2)}
            for i in range(4)
        ]

        # ── Summary: income / expenses / balance ───────────────────────────
        agg = base_qs.aggregate(
            income=Sum('amount', filter=Q(amount__gt=0)),
            expenses=Sum(Abs('amount'), filter=Q(amount__lt=0)),
            count=Count('id'),
        )
        income   = round(float(agg['income']   or 0), 2)
        expenses = round(float(agg['expenses'] or 0), 2)

        return Response({
            'month': month,
            'year': year,
            'summary': {
                'income':   income,
                'expenses': expenses,
                'balance':  round(income - expenses, 2),
                'count':    agg['count'] or 0,
            },
            'by_category': by_category,
            'daily':  daily,
            'weekly': weekly,
        }, status=status.HTTP_200_OK)
