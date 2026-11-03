import csv
import io
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum, Q
from django.db.models.functions import Abs
from django.http import HttpResponse
from rest_framework import status, viewsets, serializers
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from expenses import models, serializer
from expenses.behaviors import CreateExpenseBehavior, RecurringExpenseBehavior
from expenses.analytics_behaviors import ExpenseAnalyticsBehavior
from expenses.bulk_import_behaviors import BulkImportExpenseBehavior
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
        """Linha do tempo combinada, com totais do filtro e exportação CSV."""
        from datetime import date
        from debts.models import SharedEntry, SharedDebtMember
        from financial_system.params import apply_common_filters

        tenant_id = request.user.tenant_id
        member_ids = list(SharedDebtMember.objects.filter(tenant_id=tenant_id).values_list('id', flat=True))
        params = request.query_params
        include_future = params.get('include_future') in ('1', 'true', 'yes')
        today = date.today()
        expenses = self.get_queryset().select_related('category', 'credit_card')
        shared = (
            SharedEntry.objects
            .filter(shared_debt__members__tenant_id=tenant_id)
            .select_related('category', 'credit_card', 'paid_by', 'shared_debt')
            .prefetch_related('participants', 'shared_debt__members')
            .distinct()
        )
        shared = apply_common_filters(shared, params, SharedEntry)
        search = (params.get('search') or '').strip()[:200]
        if search:
            shared = shared.filter(description__icontains=search)
        entry_type = params.get('type')
        if entry_type == 'individual':
            shared = shared.none()
        elif entry_type == 'shared':
            expenses = expenses.none()
        if not include_future:
            expenses = expenses.filter(date__lte=today)
            shared = shared.filter(date__lte=today)

        try:
            min_amount = Decimal(params['min_amount']) if params.get('min_amount') else None
            max_amount = Decimal(params['max_amount']) if params.get('max_amount') else None
            exact_amount = Decimal(params['amount']) if params.get('amount') else None
        except InvalidOperation:
            min_amount = max_amount = exact_amount = None
        if min_amount is not None:
            expenses = expenses.annotate(abs_amount=Abs('amount')).filter(abs_amount__gte=min_amount)
            shared = shared.annotate(abs_amount=Abs('amount')).filter(abs_amount__gte=min_amount)
        if max_amount is not None:
            expenses = expenses.annotate(abs_amount=Abs('amount')).filter(abs_amount__lte=max_amount)
            shared = shared.annotate(abs_amount=Abs('amount')).filter(abs_amount__lte=max_amount)
        if exact_amount is not None:
            expenses = expenses.annotate(abs_amount=Abs('amount')).filter(abs_amount=exact_amount)
            shared = shared.annotate(abs_amount=Abs('amount')).filter(abs_amount=exact_amount)

        rows = []
        for expense in expenses:
            rows.append({
                'id': expense.id, 'type': 'individual', 'description': expense.description,
                'date': expense.date.isoformat(), 'amount': float(expense.amount),
                'category_id': expense.category_id,
                'category_name': expense.category.name if expense.category else 'Sem categoria',
                'payment_method': expense.payment_method,
                'credit_card_id': expense.credit_card_id,
                'card_name': expense.credit_card.name if expense.credit_card else None,
                'group_id': None, 'group_name': None, 'paid_by_name': None,
                'installment_number': None, 'total_installments': None,
                'is_recurring': expense.recurring_template_id is not None,
            })
        for entry in shared:
            participant_ids = entry.participant_ids()
            if not set(member_ids).intersection(participant_ids):
                continue
            participants = len(participant_ids) or 1
            own_portion = float(Decimal(entry.share_per_participant()).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP))
            card_name = None
            if entry.credit_card_id:
                card_name = (
                    entry.credit_card.name if entry.paid_by.tenant_id == tenant_id
                    else f'Cartão de {entry.paid_by.display_name}'
                )
            rows.append({
                'id': entry.id, 'type': 'shared', 'description': entry.description,
                'date': entry.date.isoformat(), 'amount': -abs(float(entry.amount)),
                'category_id': entry.category_id,
                'category_name': entry.category.name if entry.category else 'Sem categoria',
                'payment_method': entry.payment_method,
                'credit_card_id': entry.credit_card_id, 'card_name': card_name,
                'group_id': entry.shared_debt_id, 'group_name': entry.shared_debt.name,
                'paid_by_name': entry.paid_by.display_name,
                'installment_number': entry.installment_number,
                'total_installments': entry.total_installments,
                'participant_count': participants, 'is_recurring': False,
                'own_portion': own_portion,
            })
        rows.sort(key=lambda row: (row['date'], row['id'], row['type']), reverse=True)
        money = lambda value: Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        income_total = sum((money(row['amount']) for row in rows if row['amount'] > 0), Decimal('0'))
        expense_total = sum((money(row.get('own_portion', abs(row['amount'])))
                             for row in rows if row['amount'] < 0), Decimal('0'))
        totals = {
            'count': len(rows), 'income': float(income_total), 'expenses': float(expense_total),
            'net': float(income_total - expense_total),
        }

        if params.get('export') == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            safe_text = lambda value: ("'" + value if isinstance(value, str) and value[:1] in ('=', '+', '-', '@') else value)
            writer.writerow(['Tipo', 'Data', 'Descrição', 'Categoria', 'Pagamento', 'Cartão', 'Grupo', 'Pago por', 'Valor total', 'Minha parte'])
            for row in rows:
                writer.writerow([
                    'Compartilhado' if row['type'] == 'shared' else 'Individual', row['date'],
                    safe_text(row['description']), safe_text(row['category_name']),
                    safe_text(row['payment_method']), safe_text(row['card_name'] or ''),
                    safe_text(row['group_name'] or ''), safe_text(row['paid_by_name'] or ''),
                    f"{row['amount']:.2f}",
                    f"{-row.get('own_portion', abs(row['amount'])):.2f}" if row['amount'] < 0
                    else f"{row['amount']:.2f}",
                ])
            response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = 'attachment; filename="historico.csv"'
            return response

        page = self.paginate_queryset(rows)
        response = self.get_paginated_response(page)
        response.data['totals'] = totals
        return response

    @action(detail=False, methods=['post'], url_path='history/bulk-category')
    def history_bulk_category(self, request):
        from catalog.models import ExpenseCategory

        class BulkCategoryInput(serializers.Serializer):
            expense_ids = serializers.ListField(
                child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=100)
            category_id = serializers.IntegerField(min_value=1)

        payload = BulkCategoryInput(data=request.data)
        payload.is_valid(raise_exception=True)
        category_id = payload.validated_data['category_id']
        ids = payload.validated_data['expense_ids']
        qs = models.Expense.objects.filter(tenant_id=request.user.tenant_id, id__in=ids)
        if qs.count() != len(set(ids)):
            return Response({'detail': 'Um ou mais lançamentos não pertencem a esta conta.'}, status=400)
        category = ExpenseCategory.objects.filter(
            Q(tenant_id='system') | Q(tenant_id=request.user.tenant_id), id=category_id).first()
        if category is None:
            return Response({'detail': 'Categoria não encontrada.'}, status=404)
        if qs.filter((Q(amount__gte=0) & ~Q(category__kind='receita')) | Q(amount__lt=0, category__kind='receita')).exists():
            return Response({'detail': 'A categoria deve corresponder ao tipo de receita ou despesa.'}, status=400)
        with transaction.atomic():
            updated = qs.update(category_id=category_id)
        return Response({'updated': updated}, status=200)

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
        args = [s.validated_data['description_prefix'], s.validated_data['total_installments']]
        if 'expense_ids' in s.validated_data:
            args.append(s.validated_data['expense_ids'])
        return BulkImportExpenseBehavior(request.user.tenant_id).delete_installments(*args)

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
