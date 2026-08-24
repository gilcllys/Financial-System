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
from expenses.behaviors import CreateExpenseBehavior, RecurringExpenseBehavior
from catalog.models import ExpenseCategory

# Nomes dos meses em português (índice 0 não utilizado)
_MONTH_NAMES = [
    '',
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]


def _apply_payment_method_filter(qs, params, model):
    payment_method = params.get('payment_method')
    if payment_method is not None:
        valid_choices = {choice[0] for choice in model.PAYMENT_METHOD_CHOICES}
        if payment_method in valid_choices:
            qs = qs.filter(payment_method=payment_method)
    return qs


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

    def _create_from_item(self, item: dict, tenant_id):
        """Cria despesa(s) a partir de um item validado, respeitando
        quantidade/parcelamento. Retorna a lista de objetos criados."""
        payload = dict(item)
        payload['tenant_id'] = tenant_id
        behavior = CreateExpenseBehavior(data=payload)
        if behavior.is_installment and behavior.installments > 1:
            return behavior._create_installments()
        if behavior.quantity and behavior.quantity > 1:
            return behavior._create_multiple()
        return [behavior._create_single()]

    @action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request):
        """
        POST /api/expenses/expenses/bulk-create/

        Cria múltiplos gastos de forma atômica (tudo ou nada). Cada item segue
        a mesma validação de create-expense (CreateExpenseInputSerializer).
        """
        s = serializer.BulkCreateExpenseInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        items = s.validated_data['items']
        tenant = request.user.tenant_id

        # [SEC] Valida propriedade das categorias ANTES de qualquer DML —
        # impede referenciar categoria de outro tenant.
        requested_ids = {item['category_id'] for item in items}
        allowed_ids = set(
            ExpenseCategory.objects.filter(
                tenant_id__in=['system', tenant],
                id__in=requested_ids,
            ).values_list('id', flat=True)
        )
        invalid_ids = sorted(requested_ids - allowed_ids)
        if invalid_ids:
            return Response(
                {
                    'success': False,
                    'message': f'Categoria(s) inválida(s): {invalid_ids}',
                    'invalid_category_ids': invalid_ids,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        try:
            with transaction.atomic():
                for item in items:
                    created.extend(self._create_from_item(item, tenant))
        except Exception as e:
            return Response(
                {'success': False, 'message': f'Erro ao criar gastos em lote: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'success': True,
                'created': len(created),
                'message': f'{len(created)} gasto(s) criado(s) com sucesso',
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """
        GET /api/expenses/expenses/import-template/

        Retorna um arquivo .xlsx modelo para importação de gastos, com
        dropdowns de categoria (válidas para o tenant), método de pagamento
        e parcelado.
        """
        import io
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.datavalidation import DataValidation

        tenant = request.user.tenant_id
        categories = list(
            ExpenseCategory.objects
            .filter(tenant_id__in=['system', tenant])
            .order_by('name')
            .values_list('name', flat=True)
        )

        headers = [
            'descricao', 'tipo', 'valor', 'data', 'categoria',
            'metodo_pagamento', 'quantidade', 'parcelado', 'parcelas',
        ]

        wb = Workbook()
        ws = wb.active
        ws.title = 'Gastos'

        bold = Font(bold=True)
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = bold

        # Linha de exemplo (valor POSITIVO — o sinal vem de `tipo`)
        sample_category = categories[0] if categories else 'Alimentação'
        ws.append([
            'Mercado do mês', 'despesa', 150.00, '2026-08-01', sample_category,
            'dinheiro', 1, 'nao', 1,
        ])

        # Larguras razoáveis (9 colunas)
        widths = [28, 12, 12, 14, 22, 18, 12, 12, 10]
        for col_idx, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        ws.freeze_panes = 'A2'

        # Sheet de categorias (fonte para o dropdown)
        cat_ws = wb.create_sheet('Categorias')
        cat_ws.cell(row=1, column=1, value='Categorias disponíveis').font = bold
        for i, name in enumerate(categories, start=2):
            cat_ws.cell(row=i, column=1, value=name)

        # Colunas: A descricao, B tipo, C valor, D data, E categoria,
        #          F metodo_pagamento, G quantidade, H parcelado, I parcelas.

        # Dropdown tipo (coluna B)
        tipo_dv = DataValidation(
            type='list', formula1='"despesa,receita"', allow_blank=False,
        )
        ws.add_data_validation(tipo_dv)
        tipo_dv.add('B2:B1000')

        # Dropdown de categoria (coluna E). Se não houver categorias, pula.
        if categories:
            last = len(categories) + 1
            cat_dv = DataValidation(
                type='list',
                formula1=f'=Categorias!$A$2:$A${last}',
                allow_blank=True,
            )
            ws.add_data_validation(cat_dv)
            cat_dv.add('E2:E1000')

        # Dropdown método de pagamento (coluna F)
        pm_dv = DataValidation(
            type='list', formula1='"dinheiro,cartao"', allow_blank=True,
        )
        ws.add_data_validation(pm_dv)
        pm_dv.add('F2:F1000')

        # Dropdown parcelado (coluna H)
        parc_dv = DataValidation(
            type='list', formula1='"sim,nao"', allow_blank=True,
        )
        ws.add_data_validation(parc_dv)
        parc_dv.add('H2:H1000')

        from django.http import HttpResponse
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        resp = HttpResponse(
            bio.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp['Content-Disposition'] = 'attachment; filename="template_gastos.xlsx"'
        return resp

    @action(detail=False, methods=['post'], url_path='import-excel')
    def import_excel(self, request):
        """
        POST /api/expenses/expenses/import-excel/  (multipart/form-data)

        Importa gastos a partir de um arquivo .xlsx (campo 'file').
        Semântica tudo-ou-nada: se qualquer linha tiver erro, nada é criado.
        """
        from datetime import date as date_cls, datetime
        from decimal import Decimal, InvalidOperation

        MAX_ROWS = 1000

        upload = request.FILES.get('file')
        if upload is None:
            return Response(
                {'success': False, 'message': 'Arquivo não enviado'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from openpyxl import load_workbook
            wb = load_workbook(upload, data_only=True)
        except Exception:
            return Response(
                {'success': False, 'message': 'Arquivo inválido ou corrompido'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ws = wb['Gastos'] if 'Gastos' in wb.sheetnames else wb.active

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return Response(
                {'success': False, 'message': 'Planilha vazia'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Mapa header -> índice (resiliente à ordem das colunas)
        header_row = rows[0]
        header_map = {}
        for idx, val in enumerate(header_row):
            if val is not None:
                header_map[str(val).strip().lower()] = idx

        required_headers = {'descricao', 'valor', 'data', 'categoria'}
        missing = required_headers - set(header_map.keys())
        if missing:
            return Response(
                {'success': False, 'message': f'Colunas obrigatórias ausentes: {sorted(missing)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data_rows = rows[1:]
        if len(data_rows) > MAX_ROWS:
            return Response(
                {'success': False, 'message': f'Número de linhas excede o máximo de {MAX_ROWS}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant = request.user.tenant_id
        category_map = {
            c.name.strip(): c.id
            for c in ExpenseCategory.objects.filter(tenant_id__in=['system', tenant])
        }

        def get_cell(row, name):
            idx = header_map.get(name)
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        def parse_date(value):
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, date_cls):
                return value
            s = str(value).strip()
            for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                try:
                    return datetime.strptime(s, fmt).date()
                except ValueError:
                    continue
            return None

        errors = []
        parsed_items = []

        for offset, row in enumerate(data_rows):
            excel_row = offset + 2  # header é linha 1
            # Ignora linhas totalmente vazias
            if all(cell is None or str(cell).strip() == '' for cell in row):
                continue

            row_errors = []

            descricao = get_cell(row, 'descricao')
            descricao = str(descricao).strip() if descricao is not None else ''
            if not descricao:
                row_errors.append('descricao vazia')
            elif len(descricao) > 255:
                row_errors.append('descricao excede 255 caracteres')

            valor_raw = get_cell(row, 'valor')
            amount = None
            try:
                amount = Decimal(str(valor_raw).strip().replace(',', '.'))
            except (InvalidOperation, AttributeError, TypeError):
                row_errors.append('valor inválido')

            tipo_raw = get_cell(row, 'tipo')
            tipo = str(tipo_raw).strip().lower() if tipo_raw not in (None, '') else 'despesa'
            if tipo not in ('despesa', 'receita'):
                row_errors.append('tipo deve ser despesa/receita')

            # Aplica o sinal a partir do tipo (magnitude absoluta), garantindo
            # despesa negativa e receita positiva independente do que o usuário digitou.
            if amount is not None and tipo in ('despesa', 'receita'):
                amount = abs(amount) if tipo == 'receita' else -abs(amount)

            data_val = parse_date(get_cell(row, 'data'))
            if data_val is None:
                row_errors.append('data inválida')

            cat_name = get_cell(row, 'categoria')
            cat_name = str(cat_name).strip() if cat_name is not None else ''
            category_id = category_map.get(cat_name)
            if category_id is None:
                row_errors.append(f'categoria "{cat_name}" não encontrada')

            pm_raw = get_cell(row, 'metodo_pagamento')
            payment_method = str(pm_raw).strip().lower() if pm_raw not in (None, '') else 'dinheiro'
            if payment_method not in ('dinheiro', 'cartao'):
                row_errors.append('metodo_pagamento inválido')

            qty_raw = get_cell(row, 'quantidade')
            quantity = 1
            if qty_raw not in (None, ''):
                try:
                    quantity = int(qty_raw)
                except (ValueError, TypeError):
                    row_errors.append('quantidade inválida')
            if quantity < 1:
                row_errors.append('quantidade deve ser >= 1')

            parc_raw = get_cell(row, 'parcelado')
            parcelado = str(parc_raw).strip().lower() if parc_raw not in (None, '') else 'nao'
            if parcelado not in ('sim', 'nao'):
                row_errors.append('parcelado deve ser sim/nao')

            parcelas_raw = get_cell(row, 'parcelas')
            parcelas = 1
            if parcelas_raw not in (None, ''):
                try:
                    parcelas = int(parcelas_raw)
                except (ValueError, TypeError):
                    row_errors.append('parcelas inválida')
            if parcelas < 1:
                row_errors.append('parcelas deve ser >= 1')

            if row_errors:
                errors.append({'row': excel_row, 'error': '; '.join(row_errors)})
                continue

            parsed_items.append({
                'category_id': category_id,
                'description': descricao,
                'amount': amount,
                'date': data_val,
                'quantity': quantity,
                'payment_method': payment_method,
                'is_installment': parcelado == 'sim',
                'installments': parcelas,
            })

        if errors:
            return Response(
                {
                    'success': False,
                    'errors': errors,
                    'message': f'{len(errors)} linha(s) com erro; nada foi importado',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not parsed_items:
            return Response(
                {'success': False, 'message': 'Nenhuma linha de dados encontrada'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        try:
            with transaction.atomic():
                for item in parsed_items:
                    created.extend(self._create_from_item(item, tenant))
        except Exception as e:
            return Response(
                {'success': False, 'message': f'Erro ao importar gastos: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'success': True,
                'created': len(created),
                'message': f'{len(created)} gasto(s) importado(s) com sucesso',
            },
            status=status.HTTP_201_CREATED,
        )

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
          - year           (int, default=ano atual)
          - payment_method (str, opcional) "dinheiro" | "cartao"
        """
        from decimal import Decimal
        from debts.models import SharedDebtMember, SharedEntry

        today = date.today()
        params = request.query_params
        try:
            year = int(params.get('year', today.year))
            if year <= 0:
                raise ValueError
        except (ValueError, TypeError):
            year = today.year

        tenant = request.user.tenant_id

        qs = models.Expense.objects.filter(tenant_id=tenant, date__year=year)
        qs = _apply_payment_method_filter(qs, params, models.Expense)

        rows = (
            qs
            .annotate(month_num=ExtractMonth('date'))
            .values('month_num')
            .annotate(
                income=Sum('amount', filter=Q(amount__gt=0)),
                expenses_total=Sum(Abs('amount'), filter=Q(amount__lt=0)),
                cash_total=Sum(Abs('amount'), filter=Q(amount__lt=0, payment_method='dinheiro')),
                card_total=Sum(Abs('amount'), filter=Q(amount__lt=0, payment_method='cartao')),
                count=Count('id'),
            )
            .order_by('month_num')
        )
        month_map = {row['month_num']: row for row in rows}

        # ── Shared my_portion per month ───────────────────────────────────
        my_member_ids = list(
            SharedDebtMember.objects
            .filter(tenant_id=tenant)
            .values_list('id', flat=True)
        )
        shared_entries = (
            SharedEntry.objects
            .filter(participants__member_id__in=my_member_ids, date__year=year)
            .prefetch_related('participants')
            .distinct()
        )
        shared_by_month: dict[int, float] = {}
        for entry in shared_entries:
            pc = entry.participants.count()
            if pc > 0:
                m = entry.date.month
                shared_by_month[m] = shared_by_month.get(m, 0.0) + float(entry.amount / Decimal(pc))

        result = []
        for m in range(1, 13):
            row = month_map.get(m, {})
            income        = float(row.get('income') or 0)
            cash_exp      = float(row.get('cash_total') or 0)
            card_exp      = float(row.get('card_total') or 0)
            shared_exp    = round(shared_by_month.get(m, 0.0), 2)
            total_exp     = round(cash_exp + card_exp + shared_exp, 2)
            result.append({
                'month':            m,
                'month_name':       _MONTH_NAMES[m],
                'income':           round(income, 2),
                'expenses':         total_exp,
                'cash_expenses':    round(cash_exp, 2),
                'card_expenses':    round(card_exp, 2),
                'shared_my_portion': shared_exp,
                'balance':          round(income - total_exp, 2),
                'count':            row.get('count', 0),
            })

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='analytics/by-category')
    def analytics_by_category(self, request):
        """
        GET /api/expenses/expenses/analytics/by-category/?month=6&year=2026

        Retorna despesas agrupadas por categoria (somente lançamentos com
        amount < 0), ordenadas por total decrescente.

        Query params:
          - month          (int 1-12, opcional)
          - year           (int, opcional)
          - payment_method (str, opcional) "dinheiro" | "cartao"
        """
        params = request.query_params
        qs = models.Expense.objects.filter(
            tenant_id=request.user.tenant_id,
            amount__lt=0,
        )
        qs = _apply_payment_method_filter(qs, params, models.Expense)

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
          - month          (int 1-12, default=mês atual)
          - year           (int, default=ano atual)
          - payment_method (str, opcional) "dinheiro" | "cartao"
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

        qs = models.Expense.objects.filter(
            tenant_id=request.user.tenant_id,
            date__year=year,
            date__month=month,
        )
        qs = _apply_payment_method_filter(qs, params, models.Expense)

        rows = (
            qs
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


    @action(detail=False, methods=['get'], url_path='consolidated-summary')
    def consolidated_summary(self, request):
        """
        GET /api/expenses/expenses/consolidated-summary/?month=8&year=2026

        Resumo financeiro consolidado com as 3 fontes reais de gasto:

          1. Receitas do mês (Expense, amount > 0, filtro mês/ano calendário)
          2. Gastos em dinheiro (Expense, payment_method='dinheiro', amount < 0)
          3. Faturas abertas de cartão (período real da fatura, NÃO mês calendário)
          4. Minha parte em dívidas compartilhadas (SharedEntry onde sou participante)

        total_expenses = cash_expenses + card_invoices + shared_my_portion
        balance        = income - total_expenses
        """
        from datetime import date as date_cls
        from decimal import Decimal

        from cards.behaviors import _compute_invoice_period, _current_invoice_month
        from cards.models import CreditCard
        from debts.models import SharedDebtMember, SharedEntry

        today  = date_cls.today()
        params = request.query_params
        tenant = request.user.tenant_id

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

        base_qs = models.Expense.objects.filter(
            tenant_id=tenant,
            date__year=year,
            date__month=month,
        )

        # ── 1. Receitas do mês ────────────────────────────────────────────────
        income_agg = base_qs.aggregate(
            income=Sum('amount', filter=Q(amount__gt=0)),
            income_count=Count('id', filter=Q(amount__gt=0)),
        )
        income = round(float(income_agg['income'] or 0), 2)

        # ── 2. Gastos em dinheiro (mês calendário) ────────────────────────────
        cash_agg = (
            base_qs
            .filter(payment_method='dinheiro', amount__lt=0)
            .aggregate(total=Sum(Abs('amount')), count=Count('id'))
        )
        cash_expenses = round(float(cash_agg['total'] or 0), 2)
        cash_count    = cash_agg['count'] or 0

        # ── 3. Faturas abertas de cartão (período real da fatura) ─────────────
        cards = CreditCard.objects.filter(tenant_id=tenant)
        card_invoices_total = 0.0
        card_invoices_count = 0
        card_invoices_detail = []

        for card in cards:
            inv_month, inv_year = _current_invoice_month(card)
            period_start, period_end, due = _compute_invoice_period(
                card, inv_month, inv_year
            )
            agg = (
                models.Expense.objects
                .filter(
                    tenant_id=tenant,
                    credit_card_id=card.id,
                    date__gte=period_start,
                    date__lte=period_end,
                )
                .aggregate(total=Sum(Abs('amount')), count=Count('id'))
            )
            total = round(float(agg['total'] or 0), 2)
            cnt   = agg['count'] or 0
            card_invoices_total += total
            card_invoices_count += cnt
            card_invoices_detail.append({
                'card_id':         card.id,
                'card_name':       card.name,
                'last_four_digits': card.last_four_digits,
                'invoice_month':   inv_month,
                'invoice_year':    inv_year,
                'due_date':        due.isoformat(),
                'total':           total,
                'count':           cnt,
            })

        card_invoices_total = round(card_invoices_total, 2)

        # ── 4. Minha parte em dívidas compartilhadas (mês calendário) ─────────
        my_member_ids = list(
            SharedDebtMember.objects
            .filter(tenant_id=tenant)
            .values_list('id', flat=True)
        )

        entries_qs = (
            SharedEntry.objects
            .filter(
                participants__member_id__in=my_member_ids,
                date__year=year,
                date__month=month,
            )
            .prefetch_related('participants')
            .distinct()
        )

        shared_my_portion = Decimal('0')
        shared_count = 0
        for entry in entries_qs:
            participant_count = entry.participants.count()
            if participant_count > 0:
                shared_my_portion += entry.amount / Decimal(participant_count)
                shared_count += 1

        shared_my_portion = round(float(shared_my_portion), 2)

        # ── 5. Totais consolidados ─────────────────────────────────────────────
        total_expenses = round(cash_expenses + card_invoices_total + shared_my_portion, 2)
        balance        = round(income - total_expenses, 2)

        return Response({
            'month': month,
            'year':  year,
            # Receita
            'income':       income,
            # Gastos em dinheiro
            'cash_expenses': cash_expenses,
            'cash_count':    cash_count,
            # Faturas de cartão (período real)
            'card_invoices':        card_invoices_total,
            'card_invoices_count':  card_invoices_count,
            'card_invoices_detail': card_invoices_detail,
            # Dívidas compartilhadas (minha parte)
            'shared_my_portion': shared_my_portion,
            'shared_count':      shared_count,
            # Consolidado
            'total_expenses': total_expenses,
            'balance':        balance,
        }, status=status.HTTP_200_OK)

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

        Query params:
          - month          (int 1-12, default=mês atual)
          - year           (int, default=ano atual)
          - payment_method (str, opcional) "dinheiro" | "cartao"

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
        base_qs = _apply_payment_method_filter(base_qs, params, models.Expense)

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

    @action(detail=False, methods=['get', 'post'], url_path='recurring-templates')
    def recurring_templates(self, request):
        """GET: listar templates, POST: criar template"""
        behavior = RecurringExpenseBehavior(request.user.tenant_id)
        if request.method == 'GET':
            return behavior.list()
        s = serializer.CreateRecurringExpenseInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return behavior.create({**dict(s.validated_data), 'tenant_id': request.user.tenant_id})

    @action(detail=False, methods=['delete', 'patch'],
            url_path=r'recurring-templates/(?P<tpl_id>[0-9]+)')
    def recurring_template_detail(self, request, tpl_id=None):
        """DELETE: excluir, PATCH: toggle is_active"""
        behavior = RecurringExpenseBehavior(request.user.tenant_id)
        if request.method == 'DELETE':
            return behavior.delete(int(tpl_id))
        return behavior.toggle_active(int(tpl_id))

    @action(detail=False, methods=['post'], url_path='recurring-templates/generate-month')
    def generate_month_recurring(self, request):
        """POST {month, year} → materializa todos os templates ativos"""
        s = serializer.GenerateMonthInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return RecurringExpenseBehavior(request.user.tenant_id).generate_month(
            s.validated_data['month'], s.validated_data['year']
        )

