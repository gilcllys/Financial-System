import calendar
import csv
import io
import re
from datetime import date, datetime
from datetime import date as date_cls
from dateutil.relativedelta import relativedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import List

from django.db.models import Count, Q, Sum
from django.db.models.functions import Abs, ExtractDay, ExtractMonth
from rest_framework.pagination import PageNumberPagination
from django.db import transaction
from django.utils import timezone
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework import status

from catalog.constants import _MONTH_NAMES
from catalog.models import ExpenseCategory
from debts.models import SharedDebtMember, SharedEntry
from financial_system.money import to_float
from financial_system.params import apply_common_filters, choice_param, int_param
from expenses import models
from expenses.models import Expense, RecurringExpenseTemplate
from expenses.serializer import ExpenseSerializer, RecurringExpenseTemplateSerializer
from financial_system.api import get_or_404

from financial_system.money import split_installments as _split_installments, strip_suffix  # _split_installments: usado por test_installment_split

# Sufixo de parcela gerado por _create_installments (um ou mais, no fim da string).
_INSTALLMENT_SUFFIX_RE = re.compile(r'(?:\s*-\s*Parcela\s+\d+\s*/\s*\d+)+\s*$', re.IGNORECASE)


def _strip_installment_suffix(description: str) -> str:
    """Remove ' - Parcela X/Y' do fim; evita acumular sufixos ao reparcelar uma parcela."""
    return strip_suffix(description, _INSTALLMENT_SUFFIX_RE)


class CreateExpenseBehavior:
    """
    Behavior para criar despesas com suporte a parcelamento.

    O tenant_id é extraído automaticamente do token autenticado.
    """

    def __init__(self, data: dict):
        self.tenant_id = data.get('tenant_id')
        self.category_id = data.get('category_id')
        self.description = data.get('description')
        self.amount = Decimal(str(data.get('amount', 0)))
        self.date = data.get('date')
        self.quantity = data.get('quantity', 1)
        self.payment_method = data.get('payment_method', 'dinheiro')
        self.credit_card_id = data.get('credit_card_id')
        self.installments = data.get('installments', 1)
        self.is_installment = data.get('is_installment', False)

    def _validate_payment(self):
        """cartao sem credit_card_id gera lançamento invisível em qualquer fatura."""
        if self.payment_method == 'cartao' and self.credit_card_id is None:
            raise ValueError(
                'credit_card_id é obrigatório quando payment_method é "cartao".'
            )
        if self.payment_method == 'dinheiro':
            self.credit_card_id = None

    def _build_expense(self, description: str, amount: Decimal, expense_date) -> Expense:
        return Expense.objects.create(
            tenant_id=self.tenant_id,
            category_id=self.category_id,
            description=description,
            quantity=self.quantity,
            amount=amount,
            date=expense_date,
            payment_method=self.payment_method,
            credit_card_id=self.credit_card_id,
        )

    def _create_installments(self) -> List[Expense]:
        base_description = _strip_installment_suffix(self.description)
        installment_amounts = _split_installments(self.amount, self.installments)
        current_date = (
            self.date
            if isinstance(self.date, date)
            else date.fromisoformat(str(self.date))
        )
        expenses = []
        for i in range(1, self.installments + 1):
            desc = f"{base_description} - Parcela {i}/{self.installments}"
            expenses.append(self._build_expense(desc, installment_amounts[i - 1], current_date))
            current_date = current_date + relativedelta(months=1)
        return expenses

    @transaction.atomic
    def _create(self) -> List[Expense]:
        """
        Cria a(s) despesa(s) e devolve a lista. Unico ponto de decisao entre
        parcelado / quantidade / simples — usado por run() e pelo bulk import.
        """
        self._validate_payment()
        if self.is_installment and self.installments > 1:
            return self._create_installments()          # parcelado ignora quantity
        if self.quantity > 1:
            return [self._build_expense(self.description, self.amount, self.date) for _ in range(self.quantity)]
        return [self._build_expense(self.description, self.amount, self.date)]

    @staticmethod
    def _expense_dict(e: Expense) -> dict:
        return {'id': e.id, 'description': e.description, 'amount': float(e.amount), 'date': e.date.isoformat()}

    def run(self) -> Response:
        try:
            expenses = self._create()
        except Exception as e:
            return Response(
                {'detail': f'Erro ao criar despesa(s): {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        is_installment = self.is_installment and self.installments > 1
        if is_installment:
            payload = {
                'message': f'{len(expenses)} parcelas criadas com sucesso',
                'is_installment': True,
                'installments': self.installments,
                'total_amount': float(self.amount),
                'installment_amount': float(expenses[0].amount),
                'expenses': [self._expense_dict(e) for e in expenses],
            }
        elif len(expenses) > 1:
            payload = {
                'message': f'{len(expenses)} gastos criados com sucesso',
                'is_installment': False,
                'quantity': self.quantity,
                'total_amount': float(self.amount * self.quantity),
                'expenses': [self._expense_dict(e) for e in expenses],
            }
        else:
            payload = {
                'message': 'Despesa criada com sucesso',
                'is_installment': False,
                'installments': 1,
                'total_amount': float(self.amount),
                'expense': self._expense_dict(expenses[0]),
            }
        return Response(payload, status=status.HTTP_201_CREATED)


class CardExpensesBehavior:
    """Returns a tenant's complete expense ledger for one credit card."""

    def __init__(self, tenant_id: str, card_id: int):
        self.tenant_id = tenant_id
        self.card_id = card_id

    def run(self) -> Response:
        expenses = (
            Expense.objects
            .filter(tenant_id=self.tenant_id, credit_card_id=self.card_id)
            .select_related('category', 'credit_card')
            .order_by('-date', '-id')
        )
        return Response(ExpenseSerializer(expenses, many=True).data, status=status.HTTP_200_OK)


class RecurringExpenseBehavior:
    """Cria, lista e materializa templates recorrentes individuais."""

    def __init__(self, tenant_id: str, operation: str, **params):
        self.tenant_id = tenant_id
        self.operation = operation
        self.params = params

    def run(self) -> Response:
        operations = {
            'list': self._list,
            'create': self._create_template,
            'update': self._update_template,
            'toggle_active': self._toggle_active,
            'delete': self._delete_template,
            'generate_month': self._generate_month,
        }
        operation = operations.get(self.operation)
        if operation is None:
            raise ValueError(f'Operação recorrente desconhecida: {self.operation}')
        return operation(**self.params)

    def _get(self, template_id: int):
        return get_or_404(RecurringExpenseTemplate.objects, 'Template não encontrado.', id=template_id, tenant_id=self.tenant_id)

    def _list(self) -> Response:
        qs = RecurringExpenseTemplate.objects.filter(
            tenant_id=self.tenant_id
        ).select_related('category', 'credit_card').order_by('id')
        return Response(RecurringExpenseTemplateSerializer(qs, many=True).data)

    @transaction.atomic
    def _create_template(self, data: dict) -> Response:
        day = int(data.get('day_of_month', 1))
        if not (1 <= day <= 28):
            return Response({'detail': 'day_of_month deve ser entre 1 e 28.'}, status=status.HTTP_400_BAD_REQUEST)
        tpl = RecurringExpenseTemplate.objects.create(
            tenant_id=self.tenant_id,
            description=data['description'],
            amount=data['amount'],
            day_of_month=day,
            payment_method=data.get('payment_method', 'dinheiro'),
            credit_card_id=data.get('credit_card_id'),
            category_id=data.get('category_id'),
        )
        today = timezone.localdate()
        self._materialize_template(tpl, today.month, today.year)
        return Response(RecurringExpenseTemplateSerializer(tpl).data, status=status.HTTP_201_CREATED)

    def _materialize_template(self, tpl, month: int, year: int) -> bool:
        """Create the template's real ledger entry once for the requested month."""
        import calendar as cal_mod
        from datetime import date as date_cls

        if tpl.payment_method == 'cartao' and tpl.credit_card_id is None:
            return False
        if Expense.objects.filter(
            recurring_template=tpl, date__year=year, date__month=month,
        ).exists():
            return False

        category_id = tpl.category_id
        if category_id is None:
            category_id = ExpenseCategory.objects.filter(
                Q(tenant_id='system') | Q(tenant_id=self.tenant_id),
                name='Sem categoria',
            ).order_by('tenant_id').values_list('id', flat=True).first()
            if category_id is None:
                raise ValueError('Não foi encontrada a categoria “Sem categoria”.')

        day = min(tpl.day_of_month, cal_mod.monthrange(year, month)[1])
        Expense.objects.create(
            tenant_id=self.tenant_id,
            category_id=category_id,
            description=tpl.description,
            quantity=1,
            amount=-abs(tpl.amount),
            date=date_cls(year, month, day),
            payment_method=tpl.payment_method,
            credit_card_id=tpl.credit_card_id,
            recurring_template=tpl,
            is_recurrent=True,
        )
        return True

    def _update_template(self, template_id: int, data: dict) -> Response:
        tpl, err = self._get(template_id)
        if err:
            return err
        day = int(data.get('day_of_month', tpl.day_of_month))
        if not (1 <= day <= 28):
            return Response({'detail': 'day_of_month deve ser entre 1 e 28.'}, status=status.HTTP_400_BAD_REQUEST)
        tpl.description = data['description']
        tpl.amount = data['amount']
        tpl.day_of_month = day
        tpl.payment_method = data.get('payment_method', 'dinheiro')
        tpl.credit_card_id = data.get('credit_card_id')
        tpl.category_id = data.get('category_id')
        tpl.save(update_fields=[
            'description', 'amount', 'day_of_month', 'payment_method',
            'credit_card', 'category', 'updated_at',
        ])
        return Response(RecurringExpenseTemplateSerializer(tpl).data)

    def _toggle_active(self, template_id: int) -> Response:
        tpl, err = self._get(template_id)
        if err:
            return err
        tpl.is_active = not tpl.is_active
        tpl.save(update_fields=['is_active', 'updated_at'])
        return Response(RecurringExpenseTemplateSerializer(tpl).data)

    def _delete_template(self, template_id: int) -> Response:
        tpl, err = self._get(template_id)
        if err:
            return err
        tpl.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _generate_month(self, month: int, year: int) -> Response:
        from django.db import IntegrityError, transaction
        templates = RecurringExpenseTemplate.objects.filter(tenant_id=self.tenant_id, is_active=True)
        created, skipped, skipped_invalid = [], [], []
        for tpl in templates:
            # cartao sem cartao gera despesa orfa, invisivel em qualquer fatura
            if tpl.payment_method == 'cartao' and tpl.credit_card_id is None:
                skipped_invalid.append(tpl.description)
                continue
            # A trava e pela FK, nao pela descricao: renomear o template ou a
            # despesa nao duplica mais, e um gasto manual homonimo nao impede
            # mais o gasto fixo de ser gerado.
            already = Expense.objects.filter(
                recurring_template=tpl,
                date__year=year,
                date__month=month,
            ).exists()
            if already:
                skipped.append(tpl.description)
                continue
            try:
                # savepoint proprio: sem ele um IntegrityError aborta a
                # transacao inteira e os templates seguintes nao seriam gerados.
                with transaction.atomic():
                    materialized = self._materialize_template(tpl, month, year)
            except IntegrityError:
                # Corrida entre dois cliques simultaneos: a constraint do banco
                # e a autoridade final. Perder a corrida e sucesso, nao erro.
                skipped.append(tpl.description)
                continue
            if not materialized:
                skipped.append(tpl.description)
                continue
            created.append(tpl.description)
        return Response({
            'created': created,
            'skipped': skipped,
            'skipped_invalid': skipped_invalid,
        })


def _apply_payment_method_filter(qs, params, model):
    pm = choice_param(params, 'payment_method', model.PAYMENT_METHOD_CHOICES)
    return qs.filter(payment_method=pm) if pm is not None else qs


class ExpenseAnalyticsBehavior:
    """
    Behavior para calcular os endpoints de analytics de despesas.

    Recebe parametros ja extraidos da request e retorna dados serializaveis,
    mantendo o ViewSet responsavel apenas pelo contrato HTTP.
    """

    def __init__(self, tenant_id: str, operation: str, params: dict):
        self.tenant_id = tenant_id
        self.operation = operation
        self.params = params

    def run(self):
        operations = {
            'monthly': self._analytics_monthly,
            'by_category': self._analytics_by_category,
            'by_card': self._analytics_by_card,
            'daily': self._analytics_daily,
            'consolidated_summary': self._consolidated_summary,
            'home_charts': self._home_charts,
        }
        operation = operations.get(self.operation)
        if operation is None:
            raise ValueError(f'Operação de analytics desconhecida: {self.operation}')
        return operation(self.params)

    @staticmethod
    def _parse_month(params, default_month: int) -> int:
        return int_param(params, 'month', 1, 12, default=default_month)

    @staticmethod
    def _parse_year(params, default_year: int) -> int:
        return int_param(params, 'year', 1, default=default_year)

    def _analytics_monthly(self, params):
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
            m = entry.date.month
            shared_by_month[m] = shared_by_month.get(m, 0.0) + float(entry.share_per_participant())

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

    def _analytics_by_category(self, params):
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

    def _analytics_by_card(self, params):
        """Agrupa despesas por cartão no ciclo da fatura (ou mês da compra)."""
        from cards.behaviors import compute_invoice_period
        from cards.models import CreditCard

        today = date.today()
        month = self._parse_month(params, today.month)
        year = self._parse_year(params, today.year)
        # Compatibilidade do endpoint antigo: consumidores legados que não
        # enviam `period` continuam vendo mês da compra. A UI nova envia cycle.
        period = params.get('period', 'purchase_month')
        cards = CreditCard.objects.filter(tenant_id=self.tenant_id).order_by('id')
        rows = []

        for card in cards:
            qs = models.Expense.objects.filter(
                tenant_id=self.tenant_id,
                payment_method='cartao',
                credit_card_id=card.id,
                amount__lt=0,
            )
            if period == 'purchase_month':
                qs = qs.filter(date__month=month, date__year=year)
            else:
                start, end, _ = compute_invoice_period(card, month, year)
                qs = qs.filter(date__gte=start, date__lte=end)
            aggregate = qs.aggregate(total=Sum(Abs('amount')), count=Count('id'))
            total = float(aggregate['total'] or 0)
            if total:
                rows.append({
                    'card_id': card.id,
                    'card_name': card.name,
                    'last_four_digits': card.last_four_digits,
                    'total': total,
                    'count': aggregate['count'] or 0,
                })

        rows.sort(key=lambda row: row['total'], reverse=True)

        grand_total = sum(float(row['total'] or 0) for row in rows)

        result = []
        for row in rows:
            total = float(row['total'] or 0)
            result.append({
                'card_id': row['card_id'],
                'card_name': row['card_name'],
                'last_four_digits': row['last_four_digits'],
                'total': round(total, 2),
                'count': row['count'],
                'percentage': round((total / grand_total * 100) if grand_total else 0, 2),
                'period': 'purchase_month' if period == 'purchase_month' else 'cycle',
            })

        return result

    def _analytics_daily(self, params):
        """
        Retorna o gasto diario do mes.

        Receita (amount > 0) fica de fora: o consumidor deste endpoint e o
        grafico de "gastos diarios" da tela de Analytics, onde um salario
        entrando como abs(amount) virava um pico de gasto. Mesmo criterio ja
        usado pela chave `daily` de home_charts.
        """
        today = date.today()
        month = self._parse_month(params, today.month)
        year = self._parse_year(params, today.year)

        qs = models.Expense.objects.filter(
            tenant_id=self.tenant_id,
            date__year=year,
            date__month=month,
            amount__lt=0,
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
                'total': to_float(row.get('total')),
                'count': row.get('count', 0),
            })

        return result

    def _consolidated_summary(self, params):
        """Retorna resumo consolidado de receitas, dinheiro, cartoes e dividas."""
        from cards.behaviors import compute_invoice_period, current_invoice_month, shift_month
        from cards.models import CreditCard
        from debts.models import SharedDebtMember, SharedEntry

        today = date.today()
        tenant = self.tenant_id
        month = self._parse_month(params, today.month)
        year = self._parse_year(params, today.year)
        closing_month = int_param(params, 'closing_month', 1, 12)
        closing_year = int_param(params, 'closing_year', 1)

        base_qs = models.Expense.objects.filter(
            tenant_id=tenant,
            date__year=year,
            date__month=month,
        )

        income_agg = base_qs.aggregate(
            income=Sum('amount', filter=Q(amount__gt=0)),
            income_count=Count('id', filter=Q(amount__gt=0)),
        )
        income = to_float(income_agg['income'])

        cash_agg = (
            base_qs
            .filter(payment_method='dinheiro', amount__lt=0)
            .aggregate(total=Sum(Abs('amount')), count=Count('id'))
        )
        cash_expenses = to_float(cash_agg['total'])
        cash_count    = cash_agg['count'] or 0

        cards = CreditCard.objects.filter(tenant_id=tenant)
        card_invoices_total = 0.0
        card_invoices_count = 0
        card_invoices_detail = []

        for card in cards:
            if closing_month is not None and closing_year is not None:
                inv_month, inv_year = shift_month(closing_month, closing_year, 1)
            else:
                inv_month, inv_year = current_invoice_month(card)
            period_start, period_end, due = compute_invoice_period(
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
            total = to_float(agg['total'])
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
            shared_my_portion += entry.share_per_participant()
            shared_count += 1

        shared_my_portion = to_float(shared_my_portion)

        total_expenses = round(cash_expenses + card_invoices_total + shared_my_portion, 2)
        balance        = round(income - total_expenses, 2)

        result = {
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
        if params.get('include_obligations') in ('1', True):
            from expenses.models import RecurringExpenseTemplate
            templates = RecurringExpenseTemplate.objects.filter(
                tenant_id=tenant, is_active=True,
            )
            ungenerated_fixed = Decimal('0')
            for template in templates:
                exists = models.Expense.objects.filter(
                    tenant_id=tenant,
                    recurring_template_id=template.id,
                    date__year=year,
                    date__month=month,
                ).exists()
                if not exists:
                    ungenerated_fixed += abs(Decimal(template.amount))
            result.update({
                'personal_cost': total_expenses,
                'upcoming_fixed': to_float(ungenerated_fixed),
                'free_to_spend': round(balance - to_float(ungenerated_fixed), 2),
            })
        return result

    def _home_charts(self, params):
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
                'total': to_float(r['total']),
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
            total = to_float(row.get('total'))
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
        income   = to_float(agg['income']  )
        expenses = to_float(agg['expenses'])

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


class BulkImportExpenseBehavior:
    """Executa criacao em lote, importacao e exclusao de parcelas de despesas."""

    MAX_ROWS = 1000

    def __init__(self, tenant_id, operation: str, **params):
        self.tenant_id = tenant_id
        self.operation = operation
        self.params = params

    def run(self) -> Response:
        operations = {
            'bulk_create': self._bulk_create,
            'import_template': self._import_template,
            'import_excel': self._import_excel,
            'delete_installments': self._delete_installments,
        }
        operation = operations.get(self.operation)
        if operation is None:
            raise ValueError(f'Operação de importação desconhecida: {self.operation}')
        return operation(**self.params)

    def _create_from_item(self, item: dict):
        """Cria despesa(s) a partir de um item validado, respeitando quantidade/parcelamento."""
        payload = dict(item)
        payload['tenant_id'] = self.tenant_id
        result = CreateExpenseBehavior(data=payload).run()
        if result.status_code >= 400:
            raise ValueError(result.data.get('detail', 'Não foi possível criar a despesa.'))

        created_rows = result.data.get('expenses')
        if created_rows is None:
            created_rows = [result.data['expense']]
        created_by_id = {
            expense.id: expense
            for expense in models.Expense.objects.filter(
                tenant_id=self.tenant_id,
                id__in=[row['id'] for row in created_rows],
            )
        }
        return [created_by_id[row['id']] for row in created_rows]

    def _bulk_create(self, items) -> Response:
        """Cria multiplos gastos de forma atomica apos validar suas categorias."""
        requested_ids = {item['category_id'] for item in items}
        allowed_ids = set(ExpenseCategory.objects.filter(tenant_id__in=['system', self.tenant_id], id__in=requested_ids).values_list('id', flat=True))
        invalid_ids = sorted(requested_ids - allowed_ids)
        if invalid_ids:
            return Response({'detail': f'Categoria(s) inv?lida(s): {invalid_ids}', 'invalid_category_ids': invalid_ids}, status=status.HTTP_400_BAD_REQUEST)
        created = []
        try:
            with transaction.atomic():
                for item in items:
                    created.extend(self._create_from_item(item))
        except Exception as e:
            return Response({'detail': f'Erro ao criar gastos em lote: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'created': len(created), 'message': f'{len(created)} gasto(s) criado(s) com sucesso'}, status=status.HTTP_201_CREATED)

    def _import_template(self):
        """Gera o arquivo .xlsx modelo para importacao de gastos."""
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.datavalidation import DataValidation
        from cards.models import CreditCard
        categories = list(ExpenseCategory.objects.filter(tenant_id__in=['system', self.tenant_id]).order_by('name').values_list('name', flat=True))
        card_names = list(CreditCard.objects.filter(tenant_id=self.tenant_id).order_by('name').values_list('name', flat=True))
        headers = ['descricao', 'tipo', 'valor', 'data', 'categoria', 'metodo_pagamento', 'quantidade', 'parcelado', 'parcelas', 'cartao']
        wb = Workbook()
        ws = wb.active
        ws.title = 'Gastos'
        bold = Font(bold=True)
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = bold
        sample_category = categories[0] if categories else 'Alimenta??o'
        ws.append(['Mercado do m?s', 'despesa', 150.00, '2026-08-01', sample_category, 'dinheiro', 1, 'nao', 1, ''])
        widths = [28, 12, 12, 14, 22, 18, 12, 12, 10, 22]
        for col_idx, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width
        ws.freeze_panes = 'A2'
        cat_ws = wb.create_sheet('Categorias')
        cat_ws.cell(row=1, column=1, value='Categorias dispon?veis').font = bold
        for i, name in enumerate(categories, start=2):
            cat_ws.cell(row=i, column=1, value=name)
        tipo_dv = DataValidation(type='list', formula1='"despesa,receita"', allow_blank=False)
        ws.add_data_validation(tipo_dv)
        tipo_dv.add('B2:B1000')
        if categories:
            last = len(categories) + 1
            cat_dv = DataValidation(type='list', formula1=f'=Categorias!$A$2:$A${last}', allow_blank=True)
            ws.add_data_validation(cat_dv)
            cat_dv.add('E2:E1000')
        pm_dv = DataValidation(type='list', formula1='"dinheiro,cartao"', allow_blank=True)
        ws.add_data_validation(pm_dv)
        pm_dv.add('F2:F1000')
        parc_dv = DataValidation(type='list', formula1='"sim,nao"', allow_blank=True)
        ws.add_data_validation(parc_dv)
        parc_dv.add('H2:H1000')
        if card_names:
            card_ws = wb.create_sheet('Cartoes')
            card_ws.cell(row=1, column=1, value='Cart?es dispon?veis').font = bold
            for i, name in enumerate(card_names, start=2):
                card_ws.cell(row=i, column=1, value=name)
            card_dv = DataValidation(type='list', formula1=f'=Cartoes!$A$2:$A${len(card_names) + 1}', allow_blank=True)
            ws.add_data_validation(card_dv)
            card_dv.add('J2:J1000')
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        resp = HttpResponse(bio.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = 'attachment; filename="template_gastos.xlsx"'
        return resp

    @staticmethod
    def _get_cell(row, header_map, name):
        idx = header_map.get(name)
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    @staticmethod
    def _parse_date(value):
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

    def _import_excel(self, upload) -> Response:
        """Importa gastos de uma planilha .xlsx com semantica tudo-ou-nada."""
        if upload is None:
            return Response({'detail': 'Arquivo n?o enviado'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from openpyxl import load_workbook
            wb = load_workbook(upload, data_only=True)
        except Exception:
            return Response({'detail': 'Arquivo inv?lido ou corrompido'}, status=status.HTTP_400_BAD_REQUEST)
        ws = wb['Gastos'] if 'Gastos' in wb.sheetnames else wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return Response({'detail': 'Planilha vazia'}, status=status.HTTP_400_BAD_REQUEST)
        header_map = {str(val).strip().lower(): idx for idx, val in enumerate(rows[0]) if val is not None}
        missing = {'descricao', 'valor', 'data', 'categoria'} - set(header_map.keys())
        if missing:
            return Response({'detail': f'Colunas obrigat?rias ausentes: {sorted(missing)}'}, status=status.HTTP_400_BAD_REQUEST)
        data_rows = rows[1:]
        if len(data_rows) > self.MAX_ROWS:
            return Response({'detail': f'N?mero de linhas excede o m?ximo de {self.MAX_ROWS}'}, status=status.HTTP_400_BAD_REQUEST)
        category_map = {c.name.strip(): c.id for c in ExpenseCategory.objects.filter(tenant_id__in=['system', self.tenant_id])}
        from cards.models import CreditCard
        card_map = {c.name.strip().lower(): c.id for c in CreditCard.objects.filter(tenant_id=self.tenant_id)}
        errors, parsed_items = [], []
        for offset, row in enumerate(data_rows):
            excel_row = offset + 2
            if all(cell is None or str(cell).strip() == '' for cell in row):
                continue
            row_errors = []
            get_cell = lambda name: self._get_cell(row, header_map, name)
            descricao = get_cell('descricao')
            descricao = str(descricao).strip() if descricao is not None else ''
            if not descricao:
                row_errors.append('descricao vazia')
            elif len(descricao) > 255:
                row_errors.append('descricao excede 255 caracteres')
            valor_raw = get_cell('valor')
            amount = None
            try:
                amount = Decimal(str(valor_raw).strip().replace(',', '.'))
            except (InvalidOperation, AttributeError, TypeError):
                row_errors.append('valor inv?lido')
            tipo_raw = get_cell('tipo')
            tipo = str(tipo_raw).strip().lower() if tipo_raw not in (None, '') else 'despesa'
            if tipo not in ('despesa', 'receita'):
                row_errors.append('tipo deve ser despesa/receita')
            if amount is not None and tipo in ('despesa', 'receita'):
                amount = abs(amount) if tipo == 'receita' else -abs(amount)
            data_val = self._parse_date(get_cell('data'))
            if data_val is None:
                row_errors.append('data inv?lida')
            cat_name = get_cell('categoria')
            cat_name = str(cat_name).strip() if cat_name is not None else ''
            category_id = category_map.get(cat_name)
            if category_id is None:
                row_errors.append(f'categoria "{cat_name}" n?o encontrada')
            pm_raw = get_cell('metodo_pagamento')
            payment_method = str(pm_raw).strip().lower() if pm_raw not in (None, '') else 'dinheiro'
            if payment_method not in ('dinheiro', 'cartao'):
                row_errors.append('metodo_pagamento inv?lido')
            card_raw = get_cell('cartao')
            card_name = str(card_raw).strip() if card_raw not in (None, '') else ''
            credit_card_id = None
            if payment_method == 'cartao':
                if not card_name:
                    row_errors.append('cartao ? obrigat?rio quando metodo_pagamento = "cartao"')
                else:
                    credit_card_id = card_map.get(card_name.lower())
                    if credit_card_id is None:
                        row_errors.append(f'cartao "{card_name}" n?o encontrado')
            elif card_name:
                row_errors.append('cartao s? pode ser informado quando metodo_pagamento = "cartao"')
            qty_raw = get_cell('quantidade')
            quantity = 1
            if qty_raw not in (None, ''):
                try:
                    quantity = int(qty_raw)
                except (ValueError, TypeError):
                    row_errors.append('quantidade inv?lida')
            if quantity < 1:
                row_errors.append('quantidade deve ser >= 1')
            parc_raw = get_cell('parcelado')
            parcelado = str(parc_raw).strip().lower() if parc_raw not in (None, '') else 'nao'
            if parcelado not in ('sim', 'nao'):
                row_errors.append('parcelado deve ser sim/nao')
            parcelas_raw = get_cell('parcelas')
            parcelas = 1
            if parcelas_raw not in (None, ''):
                try:
                    parcelas = int(parcelas_raw)
                except (ValueError, TypeError):
                    row_errors.append('parcelas inv?lida')
            if parcelas < 1:
                row_errors.append('parcelas deve ser >= 1')
            if row_errors:
                errors.append({'row': excel_row, 'error': '; '.join(row_errors)})
                continue
            parsed_items.append({'category_id': category_id, 'description': descricao, 'amount': amount, 'date': data_val, 'quantity': quantity, 'payment_method': payment_method, 'credit_card_id': credit_card_id, 'is_installment': parcelado == 'sim', 'installments': parcelas})
        if errors:
            return Response({'errors': errors, 'detail': f'{len(errors)} linha(s) com erro; nada foi importado'}, status=status.HTTP_400_BAD_REQUEST)
        if not parsed_items:
            return Response({'detail': 'Nenhuma linha de dados encontrada'}, status=status.HTTP_400_BAD_REQUEST)
        created = []
        try:
            with transaction.atomic():
                for item in parsed_items:
                    created.extend(self._create_from_item(item))
        except Exception as e:
            return Response({'detail': f'Erro ao importar gastos: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'created': len(created), 'message': f'{len(created)} gasto(s) importado(s) com sucesso'}, status=status.HTTP_201_CREATED)

    def _delete_installments(self, description_prefix, total_installments, expense_ids=None) -> Response:
        """Remove parcelas selecionadas do próprio tenant; IDs evitam atingir grupos homônimos."""
        pattern = rf'^{re.escape(description_prefix)} - Parcela \d+/{total_installments}$'
        qs = models.Expense.objects.filter(tenant_id=self.tenant_id, description__iregex=pattern)
        if expense_ids is not None:
            qs = qs.filter(id__in=expense_ids)
            if qs.count() != len(expense_ids):
                return Response({'detail': 'Uma ou mais parcelas não pertencem a este grupo.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            deleted_count, _ = qs.delete()
        if deleted_count == 0:
            return Response({'detail': 'Nenhuma parcela encontrada para os crit?rios informados.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'deleted': deleted_count, 'description_prefix': description_prefix, 'total_installments': total_installments}, status=status.HTTP_200_OK)


class ExpenseHistoryPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    page_query_param = 'page'


class ExpenseHistoryBehavior:
    """Combines personal and shared entries for the history screen."""

    def __init__(self, tenant_id: str, filters: dict, request):
        self.tenant_id = tenant_id
        self.filters = filters
        self.request = request

    def run(self):
        expenses, shared, member_ids = self._base_querysets()
        expenses, shared = self._apply_filters(expenses, shared)
        expenses, shared = self._apply_amount_filters(expenses, shared)
        rows = self._build_history_rows(expenses, shared, member_ids)
        return self._build_response(rows)

    def _base_querysets(self):
        member_ids = set(SharedDebtMember.objects.filter(
            tenant_id=self.tenant_id,
        ).values_list('id', flat=True))
        expenses = models.Expense.objects.filter(
            tenant_id=self.tenant_id,
        ).select_related('category', 'credit_card').order_by('-date', '-id')
        shared = (
            SharedEntry.objects
            .filter(shared_debt__members__tenant_id=self.tenant_id)
            .select_related('category', 'credit_card', 'paid_by', 'shared_debt')
            .prefetch_related('participants', 'shared_debt__members')
            .distinct()
        )
        return expenses, shared, member_ids

    def _apply_filters(self, expenses, shared):
        filters = self.filters
        today = date.today()
        expenses = self._filter_personal(expenses, filters)
        shared = self._filter_shared(shared, filters)
        if filters.get('type') == 'individual':
            shared = shared.none()
        elif filters.get('type') == 'shared':
            expenses = expenses.none()
        if not filters.get('include_future', False):
            expenses = expenses.filter(date__lte=today)
            shared = shared.filter(date__lte=today)
        return expenses, shared

    def _apply_amount_filters(self, expenses, shared):
        filters = self.filters
        for key, lookup in (
            ('min_amount', 'gte'), ('max_amount', 'lte'), ('amount', 'exact'),
        ):
            value = filters.get(key)
            if value is not None:
                expenses = expenses.annotate(abs_amount=Abs('amount')).filter(**{f'abs_amount__{lookup}': value})
                shared = shared.annotate(abs_amount=Abs('amount')).filter(**{f'abs_amount__{lookup}': value})
        return expenses, shared

    def _build_history_rows(self, expenses, shared, member_ids):
        rows = self._personal_rows(expenses) + self._shared_rows(shared, member_ids)
        rows.sort(key=lambda row: (row['date'], row['id'], row['type']), reverse=True)
        return rows

    def _build_response(self, rows):
        if self.filters.get('export') == 'csv':
            return self._csv_response(rows)

        totals = self._totals(rows)
        paginator = ExpenseHistoryPagination()
        page = paginator.paginate_queryset(rows, self.request)
        response = paginator.get_paginated_response(page)
        response.data['totals'] = totals
        return response

    def _filter_personal(self, queryset, filters):
        queryset = apply_common_filters(queryset, filters, models.Expense)
        category_key = filters.get('category_key')
        if category_key:
            queryset = queryset.filter(category__key=category_key[:40])
        search = (filters.get('search') or '').strip()
        if search:
            queryset = queryset.filter(description__icontains=search)
        return queryset

    @staticmethod
    def _filter_shared(queryset, filters):
        queryset = apply_common_filters(queryset, filters, SharedEntry)
        search = (filters.get('search') or '').strip()
        if search:
            queryset = queryset.filter(description__icontains=search)
        return queryset

    @staticmethod
    def _personal_rows(expenses):
        return [{
            'id': expense.id,
            'type': 'individual',
            'description': expense.description,
            'date': expense.date.isoformat(),
            'amount': float(expense.amount),
            'category_id': expense.category_id,
            'category_name': expense.category.name if expense.category else 'Sem categoria',
            'payment_method': expense.payment_method,
            'credit_card_id': expense.credit_card_id,
            'card_name': expense.credit_card.name if expense.credit_card else None,
            'group_id': None,
            'group_name': None,
            'paid_by_name': None,
            'installment_number': None,
            'total_installments': None,
            'is_recurrent': expense.is_recurrent,
            'is_recurring': expense.is_recurrent,
        } for expense in expenses]

    def _shared_rows(self, entries, member_ids):
        rows = []
        for entry in entries:
            participant_ids = entry.participant_ids()
            if not member_ids.intersection(participant_ids):
                continue
            own_portion = float(Decimal(entry.share_per_participant()).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP,
            ))
            card_name = None
            if entry.credit_card_id:
                card_name = (
                    entry.credit_card.name
                    if entry.paid_by.tenant_id == self.tenant_id
                    else f'Cartão de {entry.paid_by.display_name}'
                )
            rows.append({
                'id': entry.id,
                'type': 'shared',
                'description': entry.description,
                'date': entry.date.isoformat(),
                'amount': -abs(float(entry.amount)),
                'category_id': entry.category_id,
                'category_name': entry.category.name if entry.category else 'Sem categoria',
                'payment_method': entry.payment_method,
                'credit_card_id': entry.credit_card_id,
                'card_name': card_name,
                'group_id': entry.shared_debt_id,
                'group_name': entry.shared_debt.name,
                'paid_by_name': entry.paid_by.display_name,
                'installment_number': entry.installment_number,
                'total_installments': entry.total_installments,
                'participant_count': len(participant_ids) or 1,
                'is_recurrent': entry.is_recurrent,
                'is_recurring': entry.is_recurrent,
                'own_portion': own_portion,
            })
        return rows

    @staticmethod
    def _totals(rows):
        money = lambda value: Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        income = sum((money(row['amount']) for row in rows if row['amount'] > 0), Decimal('0'))
        expenses = sum((money(row.get('own_portion', abs(row['amount'])))
                        for row in rows if row['amount'] < 0), Decimal('0'))
        return {
            'count': len(rows),
            'income': float(income),
            'expenses': float(expenses),
            'net': float(income - expenses),
        }

    @staticmethod
    def _csv_response(rows):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Tipo', 'Fixo', 'Data', 'Descrição', 'Categoria', 'Pagamento', 'Cartão',
            'Grupo', 'Pago por', 'Valor total', 'Minha parte',
        ])
        for row in rows:
            writer.writerow([
                'Compartilhado' if row['type'] == 'shared' else 'Individual',
                'Sim' if row.get('is_recurrent', False) else '',
                row['date'],
                _safe_csv_cell(row['description']),
                _safe_csv_cell(row['category_name']),
                _safe_csv_cell(row['payment_method']),
                _safe_csv_cell(row['card_name'] or ''),
                _safe_csv_cell(row['group_name'] or ''),
                _safe_csv_cell(row['paid_by_name'] or ''),
                f"{row['amount']:.2f}",
                f"{-row.get('own_portion', abs(row['amount'])):.2f}"
                if row['amount'] < 0 else f"{row['amount']:.2f}",
            ])
        response = HttpResponse(
            '\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8',
        )
        response['Content-Disposition'] = 'attachment; filename="historico.csv"'
        return response


def _safe_csv_cell(value):
    if isinstance(value, str) and value[:1] in ('=', '+', '-', '@'):
        return "'" + value
    return value


class BulkExpenseCategoryBehavior:
    """Validates ownership and category kind before updating history entries."""

    def __init__(self, tenant_id: str, data: dict):
        self.tenant_id = tenant_id
        self.data = data

    def run(self) -> Response:
        data = self.data
        ids = data['expense_ids']
        expenses = models.Expense.objects.filter(tenant_id=self.tenant_id, id__in=ids)
        if expenses.count() != len(ids):
            return Response(
                {'detail': 'Um ou mais lançamentos não pertencem a esta conta.'}, status=400,
            )

        category = ExpenseCategory.objects.filter(
            Q(tenant_id='system') | Q(tenant_id=self.tenant_id),
            id=data['category_id'],
        ).first()
        if category is None:
            return Response({'detail': 'Categoria não encontrada.'}, status=404)
        invalid_kind = expenses.filter(
            (Q(amount__gte=0) & ~Q(category__kind='receita')) |
            Q(amount__lt=0, category__kind='receita')
        ).exists()
        if invalid_kind:
            return Response(
                {'detail': 'A categoria deve corresponder ao tipo de receita ou despesa.'},
                status=400,
            )

        with transaction.atomic():
            updated = expenses.update(category=category)
        return Response({'updated': updated}, status=200)
