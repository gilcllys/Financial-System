import calendar
from datetime import date
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Abs, ExtractDay, ExtractMonth

from expenses import models
from catalog.constants import _MONTH_NAMES


def _apply_payment_method_filter(qs, params, model):
    payment_method = params.get('payment_method')
    if payment_method is not None:
        valid_choices = {choice[0] for choice in model.PAYMENT_METHOD_CHOICES}
        if payment_method in valid_choices:
            qs = qs.filter(payment_method=payment_method)
    return qs


class ExpenseAnalyticsBehavior:
    """
    Behavior para calcular os endpoints de analytics de despesas.

    Recebe parametros ja extraidos da request e retorna dados serializaveis,
    mantendo o ViewSet responsavel apenas pelo contrato HTTP.
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def _parse_month(self, params, default_month: int) -> int:
        try:
            month = int(params.get('month', default_month))
            if not (1 <= month <= 12):
                raise ValueError
        except (ValueError, TypeError):
            month = default_month
        return month

    def _parse_year(self, params, default_year: int) -> int:
        try:
            year = int(params.get('year', default_year))
            if year <= 0:
                raise ValueError
        except (ValueError, TypeError):
            year = default_year
        return year

    def analytics_monthly(self, params):
        """Retorna totais mensais de receitas, despesas, saldo e quantidade."""
        from debts.models import SharedDebtMember, SharedEntry

        today = date.today()
        year = self._parse_year(params, today.year)
        tenant = self.tenant_id

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

        return result

    def analytics_by_category(self, params):
        """Retorna despesas agrupadas por categoria."""
        qs = models.Expense.objects.filter(
            tenant_id=self.tenant_id,
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

        return result

    def analytics_by_card(self, params):
        """Retorna despesas agrupadas por cartao de credito."""
        qs = models.Expense.objects.filter(
            tenant_id=self.tenant_id,
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

        return result

    def analytics_daily(self, params):
        """Retorna o movimento diario do mes, incluindo receitas em abs(amount)."""
        today = date.today()
        month = self._parse_month(params, today.month)
        year = self._parse_year(params, today.year)

        qs = models.Expense.objects.filter(
            tenant_id=self.tenant_id,
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

        return result

    def consolidated_summary(self, params):
        """Retorna resumo consolidado de receitas, dinheiro, cartoes e dividas."""
        from cards.behaviors import _compute_invoice_period, _current_invoice_month
        from cards.models import CreditCard
        from debts.models import SharedDebtMember, SharedEntry

        today = date.today()
        tenant = self.tenant_id
        month = self._parse_month(params, today.month)
        year = self._parse_year(params, today.year)

        base_qs = models.Expense.objects.filter(
            tenant_id=tenant,
            date__year=year,
            date__month=month,
        )

        income_agg = base_qs.aggregate(
            income=Sum('amount', filter=Q(amount__gt=0)),
            income_count=Count('id', filter=Q(amount__gt=0)),
        )
        income = round(float(income_agg['income'] or 0), 2)

        cash_agg = (
            base_qs
            .filter(payment_method='dinheiro', amount__lt=0)
            .aggregate(total=Sum(Abs('amount')), count=Count('id'))
        )
        cash_expenses = round(float(cash_agg['total'] or 0), 2)
        cash_count    = cash_agg['count'] or 0

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

        total_expenses = round(cash_expenses + card_invoices_total + shared_my_portion, 2)
        balance        = round(income - total_expenses, 2)

        return {
            'month': month,
            'year':  year,
            'income':       income,
            'cash_expenses': cash_expenses,
            'cash_count':    cash_count,
            'card_invoices':        card_invoices_total,
            'card_invoices_count':  card_invoices_count,
            'card_invoices_detail': card_invoices_detail,
            'shared_my_portion': shared_my_portion,
            'shared_count':      shared_count,
            'total_expenses': total_expenses,
            'balance':        balance,
        }

    def home_charts(self, params):
        """Retorna os dados consolidados dos graficos da Home/Gastos."""
        today = date.today()
        month = self._parse_month(params, today.month)
        year = self._parse_year(params, today.year)
        tenant = self.tenant_id

        base_qs = models.Expense.objects.filter(
            tenant_id=tenant,
            date__year=year,
            date__month=month,
        )
        base_qs = _apply_payment_method_filter(base_qs, params, models.Expense)

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

        day_rows = (
            base_qs
            .filter(amount__lt=0)
            .annotate(day_num=ExtractDay('date'))
            .values('day_num')
            .annotate(total=Sum(Abs('amount')), count=Count('id'))
            .order_by('day_num')
        )
        day_map = {r['day_num']: r for r in day_rows}

        _, days_in_month = calendar.monthrange(year, month)

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

        agg = base_qs.aggregate(
            income=Sum('amount', filter=Q(amount__gt=0)),
            expenses=Sum(Abs('amount'), filter=Q(amount__lt=0)),
            count=Count('id'),
        )
        income   = round(float(agg['income']   or 0), 2)
        expenses = round(float(agg['expenses'] or 0), 2)

        return {
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
        }
