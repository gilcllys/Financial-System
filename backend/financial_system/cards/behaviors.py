import calendar
from datetime import date

from django.db.models import Count, Sum
from django.db.models.functions import Abs
from rest_framework import status
from rest_framework.response import Response

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

      O mês da fatura é sempre M + 1 (leva o nome do mês de vencimento,
      que é um mês após o fechamento).
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

    if closing_month < 12:
        return closing_month + 1, closing_year
    return 1, closing_year + 1


def _compute_invoice_period(card, invoice_month, invoice_year):
    """
    Calcula (period_start, period_end, due_date) para a fatura identificada
    por (invoice_month, invoice_year).

    Contrato (verificado contra faturas reais Itaú):
      closing_day   = best_purchase_date - 1
      closing_month = invoice_month - 1   (com wraparound de ano)

      period_end   = date(closing_year, closing_month, closing_day)
      period_start = date(start_year,   start_month,   best_purchase_date)
                     onde start_month = closing_month - 1 (com wraparound)
      due_date     = date(invoice_year, invoice_month, card.due_date)

    Dias são limitados (clamped) ao número real de dias do mês para evitar
    datas inválidas (ex.: 31 de fevereiro).
    """
    closing_day = card.best_purchase_date - 1

    if invoice_month == 1:
        closing_month, closing_year = 12, invoice_year - 1
    else:
        closing_month, closing_year = invoice_month - 1, invoice_year

    _, days_in_closing = calendar.monthrange(closing_year, closing_month)
    period_end = date(closing_year, closing_month, min(closing_day, days_in_closing))

    if closing_month == 1:
        start_month, start_year = 12, closing_year - 1
    else:
        start_month, start_year = closing_month - 1, closing_year

    _, days_in_start = calendar.monthrange(start_year, start_month)
    period_start = date(start_year, start_month, min(card.best_purchase_date, days_in_start))

    _, days_in_due = calendar.monthrange(invoice_year, invoice_month)
    due = date(invoice_year, invoice_month, min(card.due_date, days_in_due))

    return period_start, period_end, due


class InvoicesBehavior:
    """
    Lista as faturas de um cartão de crédito.

    Retorna 2 faturas futuras + a corrente (is_current=True) + 12 anteriores
    (15 no total), ordenadas da mais recente para a mais antiga.
    """

    FUTURE_COUNT = 2
    PAST_COUNT = 12

    def __init__(self, card):
        self.card = card

    def _advance_month(self, month, year, steps=1):
        for _ in range(steps):
            if month == 12:
                month, year = 1, year + 1
            else:
                month += 1
        return month, year

    def run(self) -> Response:
        curr_month, curr_year = _current_invoice_month(self.card)

        # Começa 2 meses à frente da fatura corrente
        inv_month, inv_year = self._advance_month(curr_month, curr_year, self.FUTURE_COUNT)

        result = []
        total = self.FUTURE_COUNT + 1 + self.PAST_COUNT  # 15

        for i in range(total):
            period_start, period_end, due = _compute_invoice_period(
                self.card, inv_month, inv_year
            )
            result.append({
                'invoice_month': inv_month,
                'invoice_year': inv_year,
                'invoice_name': f'{_MONTH_NAMES[inv_month]} {inv_year}',
                'period_start': period_start.isoformat(),
                'period_end': period_end.isoformat(),
                'due_date': due.isoformat(),
                'is_current': i == self.FUTURE_COUNT,
                'is_future': i < self.FUTURE_COUNT,
            })

            if inv_month == 1:
                inv_month, inv_year = 12, inv_year - 1
            else:
                inv_month -= 1

        return Response(result, status=status.HTTP_200_OK)


class InvoiceExpensesBehavior:
    """
    Retorna as despesas de uma fatura específica de um cartão.

    Inclui:
      - Resumo geral (total e contagem)
      - Breakdown por categoria (sempre do período completo da fatura)
      - Lista de despesas (filtrada por category_id se informado)
    """

    PAGE_SIZE = 20

    def __init__(self, card, invoice_month: int, invoice_year: int,
                 category_id: int | None = None, page: int = 1, page_size: int = 20):
        self.card = card
        self.invoice_month = invoice_month
        self.invoice_year = invoice_year
        self.category_id = category_id
        self.page = max(1, page)
        self.page_size = max(1, min(page_size, 100))

    def run(self) -> Response:
        from expenses.models import Expense
        from expenses.serializer import ExpenseSerializer

        period_start, period_end, due = _compute_invoice_period(
            self.card, self.invoice_month, self.invoice_year
        )

        base_filter = dict(
            tenant_id=self.card.tenant_id,
            credit_card_id=self.card.id,
            date__gte=period_start,
            date__lte=period_end,
        )

        # QuerySet para a lista de expenses (com filtro de categoria opcional)
        qs = (
            Expense.objects
            .filter(**base_filter)
            .select_related('category', 'credit_card')
            .order_by('-date', '-id')
        )
        if self.category_id is not None:
            qs = qs.filter(category_id=self.category_id)

        agg = qs.aggregate(total=Sum(Abs('amount')), count=Count('id'))
        grand_total = round(float(agg['total'] or 0), 2)

        # Breakdown sempre do período completo (sem filtro de categoria)
        base_qs = Expense.objects.filter(**base_filter)
        period_total = round(
            float(base_qs.aggregate(t=Sum(Abs('amount')))['t'] or 0), 2
        )
        cat_rows = (
            base_qs
            .values('category_id', 'category__name')
            .annotate(cat_total=Sum(Abs('amount')), cat_count=Count('id'))
            .order_by('-cat_total')
        )
        by_category = [
            {
                'category_id': row['category_id'],
                'category_name': row['category__name'],
                'total': round(float(row['cat_total'] or 0), 2),
                'count': row['cat_count'],
                'percentage': round(
                    float(row['cat_total'] or 0) / period_total * 100
                    if period_total else 0,
                    2,
                ),
            }
            for row in cat_rows
        ]

        # Pagination
        total_count = qs.count()
        total_pages = max(1, -(-total_count // self.page_size))  # ceil division
        offset = (self.page - 1) * self.page_size
        page_qs = qs[offset: offset + self.page_size]

        return Response(
            {
                'invoice_month': self.invoice_month,
                'invoice_year': self.invoice_year,
                'invoice_name': f'{_MONTH_NAMES[self.invoice_month]} {self.invoice_year}',
                'period_start': period_start.isoformat(),
                'period_end': period_end.isoformat(),
                'due_date': due.isoformat(),
                'summary': {'total': grand_total, 'count': agg['count'] or 0},
                'by_category': by_category,
                'pagination': {
                    'page': self.page,
                    'page_size': self.page_size,
                    'total_count': total_count,
                    'total_pages': total_pages,
                },
                'expenses': ExpenseSerializer(page_qs, many=True).data,
            },
            status=status.HTTP_200_OK,
        )
