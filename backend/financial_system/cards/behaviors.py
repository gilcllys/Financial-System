import calendar
from datetime import date, timedelta

from django.db.models import Count, Sum
from django.db.models.functions import Abs
from rest_framework import status
from rest_framework.response import Response
from catalog.constants import _MONTH_NAMES

def _effective_closing_date(year, month, closing_day):
    """Return the effective closing date, moving weekends back to Friday."""
    _, days_in_month = calendar.monthrange(year, month)
    closing = date(year, month, min(closing_day, days_in_month))

    if closing.weekday() == 5:
        return closing - timedelta(days=1)
    if closing.weekday() == 6:
        return closing - timedelta(days=2)
    return closing


def _current_invoice_month(card):
    """
    Determina (invoice_month, invoice_year) da fatura corrente (aberta hoje).

    Usa o fechamento efetivo do mes atual: quando o dia cadastrado cai no
    fim de semana, a fatura fecha na sexta-feira anterior.
    """
    today = date.today()
    effective_closing = _effective_closing_date(
        today.year, today.month, card.closing_day
    )

    if today <= effective_closing:
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

    O fechamento nominal vem de card.closing_day, mas o fechamento efetivo
    do mes antecipa sabado/domingo para a sexta-feira anterior. O inicio da
    fatura e o dia seguinte ao fechamento efetivo anterior.
    """
    closing_day = card.closing_day

    if invoice_month == 1:
        closing_month, closing_year = 12, invoice_year - 1
    else:
        closing_month, closing_year = invoice_month - 1, invoice_year

    period_end = _effective_closing_date(closing_year, closing_month, closing_day)

    if closing_month == 1:
        start_month, start_year = 12, closing_year - 1
    else:
        start_month, start_year = closing_month - 1, closing_year

    previous_closing = _effective_closing_date(start_year, start_month, closing_day)
    period_start = previous_closing + timedelta(days=1)

    _, days_in_due = calendar.monthrange(invoice_year, invoice_month)
    due = date(invoice_year, invoice_month, min(card.due_day, days_in_due))

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
                 category_id: int | None = None, page: int = 1, page_size: int = 20,
                 search: str | None = None):
        self.card = card
        self.invoice_month = invoice_month
        self.invoice_year = invoice_year
        self.category_id = category_id
        self.page = max(1, page)
        self.page_size = max(1, min(page_size, 200))
        self.search = search.strip()[:200] if search else None

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
        if self.search:
            qs = qs.filter(description__icontains=self.search)

        agg = qs.aggregate(total=Sum('amount'), count=Count('id'))
        # amount e negativo para despesa e positivo para credito/estorno.
        # Somar com sinal faz o credito ABATER a fatura, como no extrato
        # do banco. Com Abs() um estorno era somado como se fosse gasto.
        grand_total = round(-float(agg['total'] or 0), 2)

        # Breakdown sempre do período completo (sem filtro de categoria)
        base_qs = Expense.objects.filter(**base_filter)
        # Creditos nao pertencem a nenhuma categoria de gasto: incluir
        # um estorno aqui inflaria a categoria e quebraria os percentuais.
        debit_qs = base_qs.filter(amount__lt=0)
        period_total = round(
            float(debit_qs.aggregate(t=Sum(Abs('amount')))['t'] or 0), 2
        )
        cat_rows = (
            debit_qs
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


        # Shared debts paid on this card in the invoice period.
        from debts.models import SharedEntry as _SharedEntry
        _shared_entries = _SharedEntry.objects.filter(
            credit_card_id=self.card.id,
            date__gte=period_start,
            date__lte=period_end,
            paid_by__tenant_id=self.card.tenant_id,
        ).prefetch_related('participants__member', 'shared_debt__members')
        _shared_my_total = 0.0
        _shared_gross_total = 0.0
        _shared_participants = {}
        _shared_groups = {}
        for _e in _shared_entries:
            _amount = abs(float(_e.amount))
            _members = [p.member for p in _e.participants.all()]
            if not _members:
                _members = list(_e.shared_debt.members.all())
            _p = len(_members) or 1
            _portion = _amount / _p
            _shared_gross_total += _amount
            _shared_my_total += _portion

            _group_row = _shared_groups.setdefault(
                _e.shared_debt_id,
                {
                    'group_id': _e.shared_debt_id,
                    'group_name': _e.shared_debt.name,
                    'total': 0.0,
                    'participants': {},
                },
            )
            _group_row['total'] += _amount

            for _member in _members:
                _row = _shared_participants.setdefault(
                    _member.id,
                    {
                        'member_id': _member.id,
                        'name': _member.display_name,
                        'amount': 0.0,
                        'is_current_user': _member.tenant_id == self.card.tenant_id,
                    },
                )
                _row['amount'] += _portion

                _group_participant_row = _group_row['participants'].setdefault(
                    _member.id,
                    {
                        'member_id': _member.id,
                        'name': _member.display_name,
                        'amount': 0.0,
                        'is_current_user': _member.tenant_id == self.card.tenant_id,
                    },
                )
                _group_participant_row['amount'] += _portion
        _shared_my_total = round(_shared_my_total, 2)
        _shared_breakdown = {
            'total': round(_shared_gross_total, 2),
            'participants': [
                {**row, 'amount': round(row['amount'], 2)}
                for row in sorted(
                    _shared_participants.values(),
                    key=lambda item: (not item['is_current_user'], item['name'].lower()),
                )
            ],
            'groups': [
                {
                    'group_id': group['group_id'],
                    'group_name': group['group_name'],
                    'total': round(group['total'], 2),
                    'participants': [
                        {**p, 'amount': round(p['amount'], 2)}
                        for p in sorted(
                            group['participants'].values(),
                            key=lambda item: (not item['is_current_user'], item['name'].lower()),
                        )
                    ],
                }
                for group in sorted(_shared_groups.values(), key=lambda g: g['group_name'].lower())
            ],
        }
        _expenses_total = grand_total
        _composite_total = round(_expenses_total + _shared_my_total, 2)
        return Response(
            {
                'invoice_month': self.invoice_month,
                'invoice_year': self.invoice_year,
                'invoice_name': f'{_MONTH_NAMES[self.invoice_month]} {self.invoice_year}',
                'period_start': period_start.isoformat(),
                'period_end': period_end.isoformat(),
                'due_date': due.isoformat(),
                'summary': {
                    'total': _composite_total,
                    'expenses_total': _expenses_total,
                    'shared_total': _shared_my_total,
                    'shared_breakdown': _shared_breakdown,
                    'count': agg['count'] or 0,
                },
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


class OpenInvoicesBehavior:
    """
    Retorna a fatura corrente (aberta) de cada cartão do tenant,
    com o total de gastos do período e a data de fechamento/vencimento.

    Endpoint: GET /api/cards/credit-cards/open-invoices/
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def run(self) -> Response:
        from cards.models import CreditCard
        from expenses.models import Expense

        cards = CreditCard.objects.filter(tenant_id=self.tenant_id)
        result = []

        for card in cards:
            invoice_month, invoice_year = _current_invoice_month(card)
            period_start, period_end, due = _compute_invoice_period(
                card, invoice_month, invoice_year
            )

            agg = (
                Expense.objects
                .filter(
                    tenant_id=self.tenant_id,
                    credit_card_id=card.id,
                    date__gte=period_start,
                    date__lte=period_end,
                )
                .aggregate(total=Sum('amount'), count=Count('id'))
            )

            days_to_close = (period_end - date.today()).days

            result.append({
                'card_id': card.id,
                'card_name': card.name,
                'last_four_digits': card.last_four_digits,
                'invoice_month': invoice_month,
                'invoice_year': invoice_year,
                'invoice_name': f'{_MONTH_NAMES[invoice_month]} {invoice_year}',
                'period_start': period_start.isoformat(),
                'period_end': period_end.isoformat(),
                'due_date': due.isoformat(),
                'days_to_close': days_to_close,
                'total': round(-float(agg['total'] or 0), 2),
                'count': agg['count'] or 0,
            })

        result.sort(key=lambda x: x['days_to_close'])
        return Response(result, status=status.HTTP_200_OK)
