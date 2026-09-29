import re
from datetime import date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from typing import List
from django.db import transaction
from rest_framework.response import Response
from rest_framework import status

from expenses.models import Expense, RecurringExpenseTemplate
from expenses.serializer import RecurringExpenseTemplateSerializer
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
    def create(self) -> List[Expense]:
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
            expenses = self.create()
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


class RecurringExpenseBehavior:
    """Cria, lista e materializa templates recorrentes individuais."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def _get(self, template_id: int):
        return get_or_404(RecurringExpenseTemplate.objects, 'Template não encontrado.', id=template_id, tenant_id=self.tenant_id)

    def list(self) -> Response:
        qs = RecurringExpenseTemplate.objects.filter(
            tenant_id=self.tenant_id
        ).select_related('category', 'credit_card').order_by('id')
        return Response(RecurringExpenseTemplateSerializer(qs, many=True).data)

    def create(self, data: dict) -> Response:
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
        return Response(RecurringExpenseTemplateSerializer(tpl).data, status=status.HTTP_201_CREATED)

    def update(self, template_id: int, data: dict) -> Response:
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

    def toggle_active(self, template_id: int) -> Response:
        tpl, err = self._get(template_id)
        if err:
            return err
        tpl.is_active = not tpl.is_active
        tpl.save(update_fields=['is_active', 'updated_at'])
        return Response(RecurringExpenseTemplateSerializer(tpl).data)

    def delete(self, template_id: int) -> Response:
        tpl, err = self._get(template_id)
        if err:
            return err
        tpl.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def generate_month(self, month: int, year: int) -> Response:
        import calendar as cal_mod
        from datetime import date as date_cls
        from django.db import IntegrityError, transaction
        from expenses.models import RecurringExpenseTemplate, Expense
        templates = RecurringExpenseTemplate.objects.filter(tenant_id=self.tenant_id, is_active=True)
        created, skipped, skipped_invalid = [], [], []
        for tpl in templates:
            # cartao sem cartao gera despesa orfa, invisivel em qualquer fatura
            if tpl.payment_method == 'cartao' and tpl.credit_card_id is None:
                skipped_invalid.append(tpl.description)
                continue
            last_day = cal_mod.monthrange(year, month)[1]
            day = min(tpl.day_of_month, last_day)
            entry_date = date_cls(year, month, day)
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
                    Expense.objects.create(
                        tenant_id=self.tenant_id,
                        category_id=tpl.category_id,
                        description=tpl.description,
                        quantity=1,
                        amount=-abs(tpl.amount),  # gasto fixo e sempre despesa
                        date=entry_date,
                        payment_method=tpl.payment_method,
                        credit_card_id=tpl.credit_card_id,
                        recurring_template=tpl,
                    )
            except IntegrityError:
                # Corrida entre dois cliques simultaneos: a constraint do banco
                # e a autoridade final. Perder a corrida e sucesso, nao erro.
                skipped.append(tpl.description)
                continue
            created.append(tpl.description)
        return Response({
            'created': created,
            'skipped': skipped,
            'skipped_invalid': skipped_invalid,
        })
