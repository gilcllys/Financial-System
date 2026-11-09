import calendar
from datetime import date, timedelta

from django.db.models import Count, Sum
from django.db.models.functions import Abs
from rest_framework import status
from rest_framework.response import Response
from catalog.constants import _MONTH_NAMES
from financial_system.money import to_float

def _effective_closing_date(year, month, closing_day):
    """Return the effective closing date, moving weekends back to Friday."""
    _, days_in_month = calendar.monthrange(year, month)
    closing = date(year, month, min(closing_day, days_in_month))

    if closing.weekday() == 5:
        return closing - timedelta(days=1)
    if closing.weekday() == 6:
        return closing - timedelta(days=2)
    return closing


def shift_month(month, year, delta):
    """(month, year) deslocado `delta` meses (negativo volta no tempo)."""
    idx = year * 12 + (month - 1) + delta
    return idx % 12 + 1, idx // 12


def current_invoice_month(card, today=None):
    """
    (invoice_month, invoice_year) da fatura corrente (aberta hoje).

    Usa o fechamento efetivo do mes atual: quando o dia cadastrado cai no
    fim de semana, a fatura fecha na sexta-feira anterior. A fatura e
    nomeada pelo mes SEGUINTE ao do fechamento.
    """
    today = today or date.today()
    effective_closing = _effective_closing_date(today.year, today.month, card.closing_day)
    closing_month, closing_year = (today.month, today.year) if today <= effective_closing else shift_month(today.month, today.year, 1)
    return shift_month(closing_month, closing_year, 1)


def compute_invoice_period(card, invoice_month, invoice_year):
    """
    (period_start, period_end, due_date) da fatura (invoice_month, invoice_year).

    Fechamento efetivo antecipa sabado/domingo para a sexta anterior; o
    inicio da fatura e o dia seguinte ao fechamento efetivo anterior.
    """
    closing_month, closing_year = shift_month(invoice_month, invoice_year, -1)
    period_end = _effective_closing_date(closing_year, closing_month, card.closing_day)
    start_month, start_year = shift_month(closing_month, closing_year, -1)
    period_start = _effective_closing_date(start_year, start_month, card.closing_day) + timedelta(days=1)
    _, days_in_due = calendar.monthrange(invoice_year, invoice_month)
    due = date(invoice_year, invoice_month, min(card.due_day, days_in_due))
    return period_start, period_end, due


def invoice_meta(invoice_month, invoice_year, period_start, period_end, due):
    """Bloco de identificacao de fatura repetido nas respostas de cards."""
    return {
        'invoice_month': invoice_month,
        'invoice_year': invoice_year,
        'invoice_name': f'{_MONTH_NAMES[invoice_month]} {invoice_year}',
        'period_start': period_start.isoformat(),
        'period_end': period_end.isoformat(),
        'due_date': due.isoformat(),
    }


# Compatibilidade: nomes antigos importados por cards/tests.py e debts/by_person.py.
_current_invoice_month = current_invoice_month
_compute_invoice_period = compute_invoice_period


def _sorted_participants(rows):
    return [
        {**row, 'amount': round(row['amount'], 2)}
        for row in sorted(
            rows.values(),
            key=lambda item: (not item['is_current_user'], item['name'].lower()),
        )
    ]


def _shared_invoice_breakdown(card, period_start, period_end):
    """
    Dívidas compartilhadas pagas pelo dono do cartão, NESTE cartão, dentro do
    período da fatura (mesmo range usado para as despesas individuais).

    O banco cobra o valor cheio (`total`); `my_total` é apenas a parte do
    usuário no rateio. `groups` traz o mesmo recorte por grupo.
    """
    from debts.models import SharedEntry

    entries = SharedEntry.objects.filter(
        credit_card_id=card.id,
        date__gte=period_start,
        date__lte=period_end,
        paid_by__tenant_id=card.tenant_id,
    ).prefetch_related('participants__member', 'shared_debt__members')

    my_total = 0.0
    gross_total = 0.0
    participants = {}
    groups = {}
    for entry in entries:
        amount = abs(float(entry.amount))
        members_by_id = {m.id: m for m in entry.shared_debt.members.all()}
        members = [members_by_id[mid] for mid in entry.participant_ids() if mid in members_by_id]
        portion = abs(float(entry.share_per_participant()))
        gross_total += amount
        my_total += portion

        group = groups.setdefault(
            entry.shared_debt_id,
            {
                'group_id': entry.shared_debt_id,
                'group_name': entry.shared_debt.name,
                'total': 0.0,
                'my_portion': 0.0,
                'participants': {},
            },
        )
        group['total'] += amount
        group['my_portion'] += portion

        for member in members:
            for bucket in (participants, group['participants']):
                row = bucket.setdefault(
                    member.id,
                    {
                        'member_id': member.id,
                        'name': member.display_name,
                        'amount': 0.0,
                        'is_current_user': member.tenant_id == card.tenant_id,
                    },
                )
                row['amount'] += portion

    return {
        'total': round(gross_total, 2),
        'my_total': round(my_total, 2),
        'participants': _sorted_participants(participants),
        'groups': [
            {
                'group_id': g['group_id'],
                'group_name': g['group_name'],
                'total': round(g['total'], 2),
                'my_portion': round(g['my_portion'], 2),
                'participants': _sorted_participants(g['participants']),
            }
            for g in sorted(groups.values(), key=lambda g: g['group_name'].lower())
        ],
    }


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

    def run(self) -> Response:
        curr_month, curr_year = current_invoice_month(self.card)

        # Começa 2 meses à frente da fatura corrente
        inv_month, inv_year = shift_month(curr_month, curr_year, self.FUTURE_COUNT)

        result = []
        total = self.FUTURE_COUNT + 1 + self.PAST_COUNT  # 15

        for i in range(total):
            period_start, period_end, due = compute_invoice_period(
                self.card, inv_month, inv_year
            )
            result.append({
                **invoice_meta(inv_month, inv_year, period_start, period_end, due),
                'is_current': i == self.FUTURE_COUNT,
                'is_future': i < self.FUTURE_COUNT,
            })

            inv_month, inv_year = shift_month(inv_month, inv_year, -1)

        return Response(result, status=status.HTTP_200_OK)


class InvoiceExpensesBehavior:
    """
    Retorna as despesas de uma fatura específica de um cartão.

    Inclui:
      - Resumo geral (total e contagem)
      - Breakdown por categoria (sempre do período completo da fatura)
      - Lista de despesas (filtrada por category_id se informado)
    """


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

        period = compute_invoice_period(self.card, self.invoice_month, self.invoice_year)
        base_filter = self._period_filter(period)
        expense_page = self._get_expense_page(Expense, base_filter)
        breakdown = self._get_category_breakdown(Expense, base_filter)
        shared = _shared_invoice_breakdown(self.card, period[0], period[1])
        return self._build_response(period, expense_page, breakdown, shared, ExpenseSerializer)

    def _period_filter(self, period):
        return {
            'tenant_id': self.card.tenant_id,
            'credit_card_id': self.card.id,
            'date__gte': period[0],
            'date__lte': period[1],
        }

    def _expense_queryset(self, expense_model, base_filter):
        queryset = expense_model.objects.filter(**base_filter).select_related(
            'category', 'credit_card',
        ).order_by('-date', '-id')
        if self.category_id is not None:
            queryset = queryset.filter(category_id=self.category_id)
        if self.search:
            queryset = queryset.filter(description__icontains=self.search)
        return queryset

    def _get_expense_page(self, expense_model, base_filter):
        queryset = self._expense_queryset(expense_model, base_filter)
        aggregate = queryset.aggregate(total=Sum('amount'), count=Count('id'))
        total_count = queryset.count()
        total_pages = max(1, -(-total_count // self.page_size))
        offset = (self.page - 1) * self.page_size
        return {
            'aggregate': aggregate,
            'total_count': total_count,
            'total_pages': total_pages,
            'rows': queryset[offset:offset + self.page_size],
        }

    @staticmethod
    def _get_category_breakdown(expense_model, base_filter):
        debit_queryset = expense_model.objects.filter(**base_filter, amount__lt=0)
        period_total = round(
            float(debit_queryset.aggregate(total=Sum(Abs('amount')))['total'] or 0), 2,
        )
        category_rows = debit_queryset.values(
            'category_id', 'category__name',
        ).annotate(
            cat_total=Sum(Abs('amount')), cat_count=Count('id'),
        ).order_by('-cat_total')
        return [
            {
                'category_id': row['category_id'],
                'category_name': row['category__name'],
                'total': to_float(row['cat_total']),
                'count': row['cat_count'],
                'percentage': round(float(row['cat_total'] or 0) / period_total * 100, 2)
                if period_total else 0,
            }
            for row in category_rows
        ]

    def _build_response(self, period, expense_page, by_category, shared, expense_serializer):
        period_start, period_end, due = period
        aggregate = expense_page['aggregate']
        expenses_total = round(-float(aggregate['total'] or 0), 2)
        shared_breakdown = {
            'total': shared['total'],
            'participants': shared['participants'],
            'groups': shared['groups'],
        }
        return Response({
            **invoice_meta(self.invoice_month, self.invoice_year, period_start, period_end, due),
            'summary': {
                'total': round(expenses_total + shared['my_total'], 2),
                'expenses_total': expenses_total,
                'shared_total': shared['my_total'],
                'shared_breakdown': shared_breakdown,
                'count': aggregate['count'] or 0,
            },
            'by_category': by_category,
            'pagination': {
                'page': self.page,
                'page_size': self.page_size,
                'total_count': expense_page['total_count'],
                'total_pages': expense_page['total_pages'],
            },
            'expenses': expense_serializer(expense_page['rows'], many=True).data,
        }, status=status.HTTP_200_OK)


class OpenInvoicesBehavior:
    """
    Retorna o ciclo de fechamento selecionado para cada cartão do tenant,
    com o total de gastos do período e a data de fechamento/vencimento.

    `total` é o valor BRUTO que o banco cobra: despesas individuais +
    valor cheio das dívidas compartilhadas pagas neste cartão no período.
    `shared_total` é só a parte do usuário nesse rateio.

    Endpoint: GET /api/cards/credit-cards/open-invoices/
    """

    def __init__(self, tenant_id: str, closing_month=None, closing_year=None):
        self.tenant_id = tenant_id
        self.closing_month = closing_month
        self.closing_year = closing_year

    def run(self) -> Response:
        from cards.models import CreditCard
        rows = [
            self._build_card_invoice(card)
            for card in CreditCard.objects.filter(tenant_id=self.tenant_id)
        ]
        return Response(sorted(rows, key=lambda row: row['days_to_close']), status=status.HTTP_200_OK)

    def _invoice_period(self, card):
        if self.closing_month is not None and self.closing_year is not None:
            invoice_month, invoice_year = shift_month(
                self.closing_month, self.closing_year, 1,
            )
        else:
            invoice_month, invoice_year = current_invoice_month(card)
        return invoice_month, invoice_year, compute_invoice_period(
            card, invoice_month, invoice_year,
        )

    def _build_card_invoice(self, card):
        from expenses.models import Expense

        invoice_month, invoice_year, period = self._invoice_period(card)
        period_start, period_end, due = period
        aggregate = Expense.objects.filter(
            tenant_id=self.tenant_id,
            credit_card_id=card.id,
            date__gte=period_start,
            date__lte=period_end,
        ).aggregate(total=Sum('amount'), count=Count('id'))
        expenses_total = round(-float(aggregate['total'] or 0), 2)
        shared = _shared_invoice_breakdown(card, period_start, period_end)
        return {
            'card_id': card.id,
            'card_name': card.name,
            'last_four_digits': card.last_four_digits,
            **invoice_meta(invoice_month, invoice_year, period_start, period_end, due),
            'days_to_close': (period_end - date.today()).days,
            'total': round(expenses_total + shared['total'], 2),
            'expenses_total': expenses_total,
            'shared_total': shared['my_total'],
            'shared_gross_total': shared['total'],
            'shared_groups': [
                {
                    'group_id': group['group_id'],
                    'group_name': group['group_name'],
                    'total': group['total'],
                    'my_portion': group['my_portion'],
                }
                for group in shared['groups']
            ],
            'count': aggregate['count'] or 0,
        }


class CreditCardInvoiceViewBehavior:
    """Composes the read model used by the credit card invoice screen."""

    def __init__(self, card, request, params: dict):
        self.card = card
        self.request = request
        self.params = params

    def run(self) -> Response:
        invoices = InvoicesBehavior(self.card).run().data
        selected = self._select_invoice(invoices)
        if isinstance(selected, Response):
            return selected
        invoice_data = self._invoice_data(selected)
        chart_data = self._chart_data(selected)
        return self._build_response(invoices, selected, invoice_data, chart_data)

    def _select_invoice(self, invoices):
        selected = next((row for row in invoices if row['is_current']), invoices[0])
        if 'invoice_month' not in self.params:
            return selected
        selected = next((row for row in invoices if
                         row['invoice_month'] == self.params['invoice_month'] and
                         row['invoice_year'] == self.params['invoice_year']), None)
        if selected is None:
            return Response({'detail': 'Fatura não encontrada para este cartão.'}, status=404)
        return selected

    def _invoice_data(self, selected):
        return InvoiceExpensesBehavior(
            self.card, selected['invoice_month'], selected['invoice_year'],
            self.params.get('category_id'), page=self.params['page'],
            page_size=self.params['page_size'], search=self.params.get('search'),
        ).run().data

    def _chart_data(self, selected):
        return InvoiceExpensesBehavior(
            self.card, selected['invoice_month'], selected['invoice_year'],
            page=1, page_size=200,
        ).run().data

    def _build_response(self, invoices, selected, invoice_data, chart_data):
        from catalog.models import ExpenseCategory
        from catalog.serializer import ExpenseCategorySerializer
        from debts.models import SharedEntry
        from debts.serializer import SharedEntrySerializer
        from cards.serializer import CreditCardSerializer

        shared_entries = SharedEntry.objects.filter(
            credit_card_id=self.card.id,
            paid_by__tenant_id=self.card.tenant_id,
            date__gte=selected['period_start'], date__lte=selected['period_end'],
        ).select_related('paid_by', 'shared_debt', 'credit_card', 'category') \
         .prefetch_related('participants', 'shared_debt__members').order_by('-date', '-id')
        categories = ExpenseCategory.objects.filter(
            tenant_id__in=['system', self.card.tenant_id],
        ).order_by('name')
        return Response({
            'card': CreditCardSerializer(self.card).data,
            'invoices': invoices,
            'selected_invoice': selected,
            'invoice_data': invoice_data,
            'chart_data': chart_data,
            'shared_entries': SharedEntrySerializer(
                shared_entries, many=True, context={'request': self.request},
            ).data,
            'categories': ExpenseCategorySerializer(categories, many=True).data,
            'annual_invoice_totals': self._annual_totals(invoices, selected),
        })

    def _annual_totals(self, invoices, selected):
        from django.db.models import Sum
        from django.db.models.functions import Abs
        from debts.models import SharedEntry
        from expenses.models import Expense

        totals = [0.0] * 12
        year_invoices = [row for row in invoices if row['invoice_year'] == selected['invoice_year']]
        for invoice in year_invoices:
            total = Expense.objects.filter(
                tenant_id=self.card.tenant_id, credit_card_id=self.card.id,
                date__gte=invoice['period_start'], date__lte=invoice['period_end'], amount__lt=0,
            ).aggregate(total=Sum(Abs('amount')))['total'] or 0
            shared_total = SharedEntry.objects.filter(
                credit_card_id=self.card.id,
                paid_by__tenant_id=self.card.tenant_id,
                date__gte=invoice['period_start'], date__lte=invoice['period_end'],
            ).aggregate(total=Sum(Abs('amount')))['total'] or 0
            totals[invoice['invoice_month'] - 1] = round(
                float(total) + float(shared_total), 2,
            )
        return totals
