import calendar
from datetime import date

from django.db.models import Count, Sum
from django.db.models.functions import Abs
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from cards import models, serializer

# Nomes dos meses em português (índice 0 não utilizado)
_MONTH_NAMES = [
    '',
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]


def _current_invoice_month(card):
    """
    Determina (invoice_month, invoice_year) da fatura corrente (aberta hoje).

    Lógica verificada contra 2 faturas reais Itaú:
      closing_day = best_purchase_date - 1

      Se hoje.dia <= closing_day  → estamos no período de fechamento do mês
          atual (M = today.month)
      Caso contrário              → o período já fechou; a próxima fatura é
          do mês seguinte (M = today.month + 1, com wraparound)

      O mês da fatura é sempre M + 1 (a fatura leva o nome do mês de
      vencimento, que é um mês após o fechamento).
    """
    today = date.today()
    closing_day = card.best_purchase_date - 1

    if today.day <= closing_day:
        closing_month = today.month
        closing_year = today.year
    else:
        if today.month < 12:
            closing_month = today.month + 1
            closing_year = today.year
        else:
            closing_month = 1
            closing_year = today.year + 1

    # invoice_month = closing_month + 1 (com wraparound)
    if closing_month < 12:
        invoice_month = closing_month + 1
        invoice_year = closing_year
    else:
        invoice_month = 1
        invoice_year = closing_year + 1

    return invoice_month, invoice_year


def _compute_invoice_period(card, invoice_month, invoice_year):
    """
    Calcula (period_start, period_end, due_date) para uma fatura identificada
    por (invoice_month, invoice_year).

    Contrato (verificado contra faturas reais Itaú):
      closing_day   = best_purchase_date - 1
      closing_month = invoice_month - 1   (com wraparound de ano)

      period_end   = date(closing_year, closing_month, closing_day)
      period_start = date(start_year,   start_month,   best_purchase_date)
                     onde start_month = closing_month - 1 (com wraparound)
      due_date     = date(invoice_year, invoice_month, card.due_date)

    Dias são limitados (clamped) ao número real de dias do mês via
    calendar.monthrange para evitar datas inválidas (ex: 31 de Fevereiro).
    """
    closing_day = card.best_purchase_date - 1

    # ── Mês de fechamento ──────────────────────────────────────────────────
    if invoice_month == 1:
        closing_month = 12
        closing_year = invoice_year - 1
    else:
        closing_month = invoice_month - 1
        closing_year = invoice_year

    # ── period_end ─────────────────────────────────────────────────────────
    _, days_in_closing = calendar.monthrange(closing_year, closing_month)
    period_end = date(
        closing_year,
        closing_month,
        min(closing_day, days_in_closing),
    )

    # ── period_start ───────────────────────────────────────────────────────
    if closing_month == 1:
        start_month = 12
        start_year = closing_year - 1
    else:
        start_month = closing_month - 1
        start_year = closing_year

    _, days_in_start = calendar.monthrange(start_year, start_month)
    period_start = date(
        start_year,
        start_month,
        min(card.best_purchase_date, days_in_start),
    )

    # ── due_date ───────────────────────────────────────────────────────────
    _, days_in_due = calendar.monthrange(invoice_year, invoice_month)
    due = date(
        invoice_year,
        invoice_month,
        min(card.due_date, days_in_due),
    )

    return period_start, period_end, due


class CreditCardViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.CreditCardSerializer
    queryset = models.CreditCard.objects.all()

    def get_queryset(self):
        return models.CreditCard.objects.filter(tenant_id=self.request.user.tenant_id)

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.user.tenant_id)

    def perform_update(self, serializer):
        """[SEC-A01] Defense-in-depth: garante que tenant_id não muda em updates."""
        serializer.save(tenant_id=self.request.user.tenant_id)

    def perform_destroy(self, instance):
        if instance.tenant_id != self.request.user.tenant_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Você não tem permissão para excluir este recurso.")
        instance.delete()

    # ------------------------------------------------------------------
    # Invoice actions
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='invoices')
    def invoices(self, request, pk=None):
        """
        GET /api/cards/credit-cards/{id}/invoices/

        Retorna lista de 13 faturas: a corrente (is_current=true) mais as 12
        anteriores, ordenadas da mais recente (índice 0) para a mais antiga.

        Cada objeto de fatura contém:
          - invoice_month / invoice_year : identificam a fatura
          - invoice_name                 : nome legível em português
          - period_start / period_end    : intervalo de lançamentos
          - due_date                     : data de vencimento
          - is_current                   : true apenas para a fatura aberta
        """
        try:
            card = models.CreditCard.objects.get(
                pk=pk,
                tenant_id=request.user.tenant_id,
            )
        except models.CreditCard.DoesNotExist:
            return Response(
                {'detail': 'Cartão não encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        curr_month, curr_year = _current_invoice_month(card)

        result = []
        inv_month, inv_year = curr_month, curr_year

        for i in range(13):
            period_start, period_end, due = _compute_invoice_period(
                card, inv_month, inv_year
            )
            result.append({
                'invoice_month': inv_month,
                'invoice_year': inv_year,
                'invoice_name': f'{_MONTH_NAMES[inv_month]} {inv_year}',
                'period_start': period_start.isoformat(),
                'period_end': period_end.isoformat(),
                'due_date': due.isoformat(),
                'is_current': i == 0,
            })

            # Retrocede um mês para a próxima iteração
            if inv_month == 1:
                inv_month = 12
                inv_year -= 1
            else:
                inv_month -= 1

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='invoice-expenses')
    def invoice_expenses(self, request, pk=None):
        """
        GET /api/cards/credit-cards/{id}/invoice-expenses/
            ?invoice_month=7&invoice_year=2026[&category_id=1]

        Retorna as despesas de uma fatura específica, agrupamentos por
        categoria e um resumo geral.

        Query params:
          - invoice_month (int 1-12)  — obrigatório
          - invoice_year  (int)       — obrigatório
          - category_id   (int)       — opcional; filtra por categoria

        Resposta:
          {
            invoice_month, invoice_year, invoice_name,
            period_start, period_end, due_date,
            summary: { total, count },
            by_category: [ { category_id, category_name, total, count,
                              percentage } ],
            expenses: [ <ExpenseSerializer> ]
          }
        """
        from expenses import models as expense_models
        from expenses.serializer import ExpenseSerializer

        # ── Valida ownership do cartão ─────────────────────────────────────
        try:
            card = models.CreditCard.objects.get(
                pk=pk,
                tenant_id=request.user.tenant_id,
            )
        except models.CreditCard.DoesNotExist:
            return Response(
                {'detail': 'Cartão não encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        params = request.query_params

        # ── invoice_month ──────────────────────────────────────────────────
        raw_month = params.get('invoice_month')
        if raw_month is None:
            return Response(
                {'detail': 'invoice_month é obrigatório.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            invoice_month = int(raw_month)
            if not (1 <= invoice_month <= 12):
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {'detail': 'invoice_month deve ser um inteiro entre 1 e 12.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── invoice_year ───────────────────────────────────────────────────
        raw_year = params.get('invoice_year')
        if raw_year is None:
            return Response(
                {'detail': 'invoice_year é obrigatório.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            invoice_year = int(raw_year)
            if invoice_year <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {'detail': 'invoice_year deve ser um inteiro positivo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── category_id (opcional) ─────────────────────────────────────────
        category_id = None
        raw_category = params.get('category_id')
        if raw_category is not None:
            try:
                category_id = int(raw_category)
            except (ValueError, TypeError):
                return Response(
                    {'detail': 'category_id deve ser um inteiro.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ── Período da fatura ──────────────────────────────────────────────
        period_start, period_end, due = _compute_invoice_period(
            card, invoice_month, invoice_year
        )

        # ── QuerySet base ──────────────────────────────────────────────────
        qs = (
            expense_models.Expense.objects
            .filter(
                tenant_id=request.user.tenant_id,
                credit_card_id=card.id,
                date__gte=period_start,
                date__lte=period_end,
            )
            .select_related('category', 'credit_card')
            .order_by('-date', '-id')
        )

        if category_id is not None:
            qs = qs.filter(category_id=category_id)

        # ── Summary ────────────────────────────────────────────────────────
        agg = qs.aggregate(
            total=Sum(Abs('amount')),
            count=Count('id'),
        )
        grand_total = round(float(agg['total'] or 0), 2)
        grand_count = agg['count'] or 0

        # ── By category ────────────────────────────────────────────────────
        # Realiza a agregação sem o filtro de category_id para que o breakdown
        # sempre mostre todas as categorias presentes no período da fatura,
        # mesmo quando o parâmetro category_id foi informado para filtrar a
        # lista de expenses.
        base_qs = expense_models.Expense.objects.filter(
            tenant_id=request.user.tenant_id,
            credit_card_id=card.id,
            date__gte=period_start,
            date__lte=period_end,
        )
        cat_rows = (
            base_qs
            .values('category_id', 'category__name')
            .annotate(
                cat_total=Sum(Abs('amount')),
                cat_count=Count('id'),
            )
            .order_by('-cat_total')
        )

        # Usa grand_total do período completo como base para percentuais
        period_total = round(
            float(
                base_qs.aggregate(t=Sum(Abs('amount')))['t'] or 0
            ),
            2,
        )

        by_category = []
        for row in cat_rows:
            cat_total = round(float(row['cat_total'] or 0), 2)
            by_category.append({
                'category_id': row['category_id'],
                'category_name': row['category__name'],
                'total': cat_total,
                'count': row['cat_count'],
                'percentage': round(
                    (cat_total / period_total * 100) if period_total else 0,
                    2,
                ),
            })

        # ── Serializa expenses ─────────────────────────────────────────────
        expenses_data = ExpenseSerializer(qs, many=True).data

        return Response(
            {
                'invoice_month': invoice_month,
                'invoice_year': invoice_year,
                'invoice_name': f'{_MONTH_NAMES[invoice_month]} {invoice_year}',
                'period_start': period_start.isoformat(),
                'period_end': period_end.isoformat(),
                'due_date': due.isoformat(),
                'summary': {
                    'total': grand_total,
                    'count': grand_count,
                },
                'by_category': by_category,
                'expenses': expenses_data,
            },
            status=status.HTTP_200_OK,
        )
