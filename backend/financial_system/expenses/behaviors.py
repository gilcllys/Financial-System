from datetime import date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from typing import List
from django.db import transaction
from rest_framework.response import Response
from rest_framework import status

from expenses.models import Expense


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

    def _build_expense(self, description: str, amount: Decimal, expense_date) -> Expense:
        expense = Expense.objects.create(
            tenant_id=self.tenant_id,
            category_id=self.category_id,
            description=description,
            quantity=self.quantity,
            amount=amount,
            date=expense_date,
            payment_method=self.payment_method,
            credit_card_id=self.credit_card_id,
        )
        return expense

    @transaction.atomic
    def _create_single(self) -> Expense:
        return self._build_expense(self.description, self.amount, self.date)

    @transaction.atomic
    def _create_multiple(self) -> List[Expense]:
        """Cria self.quantity registros independentes com o mesmo valor e data."""
        return [
            self._build_expense(self.description, self.amount, self.date)
            for _ in range(self.quantity)
        ]

    @transaction.atomic
    def _create_installments(self) -> List[Expense]:
        expenses = []
        installment_amount = self.amount / self.installments
        current_date = (
            self.date
            if isinstance(self.date, date)
            else date.fromisoformat(str(self.date))
        )
        for i in range(1, self.installments + 1):
            desc = f"{self.description} - Parcela {i}/{self.installments}"
            expenses.append(self._build_expense(desc, installment_amount, current_date))
            current_date = current_date + relativedelta(months=1)
        return expenses

    def run(self) -> Response:
        try:
            if self.is_installment and self.installments > 1:
                # Parcelado: ignora quantity, cria N parcelas
                expenses = self._create_installments()
                return Response(
                    {
                        'success': True,
                        'message': f'{len(expenses)} parcelas criadas com sucesso',
                        'is_installment': True,
                        'installments': self.installments,
                        'total_amount': float(self.amount),
                        'installment_amount': float(self.amount / self.installments),
                        'expenses': [
                            {
                                'id': e.id,
                                'description': e.description,
                                'amount': float(e.amount),
                                'date': e.date.isoformat(),
                            }
                            for e in expenses
                        ],
                    },
                    status=status.HTTP_201_CREATED,
                )
            elif self.quantity > 1:
                # Quantidade > 1: cria N registros independentes
                expenses = self._create_multiple()
                return Response(
                    {
                        'success': True,
                        'message': f'{len(expenses)} gastos criados com sucesso',
                        'is_installment': False,
                        'quantity': self.quantity,
                        'total_amount': float(self.amount * self.quantity),
                        'expenses': [
                            {
                                'id': e.id,
                                'description': e.description,
                                'amount': float(e.amount),
                                'date': e.date.isoformat(),
                            }
                            for e in expenses
                        ],
                    },
                    status=status.HTTP_201_CREATED,
                )
            else:
                expense = self._create_single()
                return Response(
                    {
                        'success': True,
                        'message': 'Despesa criada com sucesso',
                        'is_installment': False,
                        'installments': 1,
                        'total_amount': float(self.amount),
                        'expense': {
                            'id': expense.id,
                            'description': expense.description,
                            'amount': float(expense.amount),
                            'date': expense.date.isoformat(),
                        },
                    },
                    status=status.HTTP_201_CREATED,
                )
        except Exception as e:
            return Response(
                {'success': False, 'message': f'Erro ao criar despesa(s): {str(e)}', 'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class RecurringExpenseBehavior:
    """Cria, lista e materializa templates recorrentes individuais."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def list(self) -> Response:
        from expenses.models import RecurringExpenseTemplate
        from expenses.serializer import RecurringExpenseTemplateSerializer
        qs = RecurringExpenseTemplate.objects.filter(
            tenant_id=self.tenant_id
        ).select_related('category', 'credit_card').order_by('id')
        return Response(RecurringExpenseTemplateSerializer(qs, many=True).data)

    def create(self, data: dict) -> Response:
        from expenses.models import RecurringExpenseTemplate
        from expenses.serializer import RecurringExpenseTemplateSerializer
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

    def toggle_active(self, template_id: int) -> Response:
        from expenses.models import RecurringExpenseTemplate
        from expenses.serializer import RecurringExpenseTemplateSerializer
        try:
            tpl = RecurringExpenseTemplate.objects.get(id=template_id, tenant_id=self.tenant_id)
        except RecurringExpenseTemplate.DoesNotExist:
            return Response({'detail': 'Template não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        tpl.is_active = not tpl.is_active
        tpl.save(update_fields=['is_active', 'updated_at'])
        return Response(RecurringExpenseTemplateSerializer(tpl).data)

    def delete(self, template_id: int) -> Response:
        from expenses.models import RecurringExpenseTemplate
        try:
            tpl = RecurringExpenseTemplate.objects.get(id=template_id, tenant_id=self.tenant_id)
        except RecurringExpenseTemplate.DoesNotExist:
            return Response({'detail': 'Template não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        tpl.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def generate_month(self, month: int, year: int) -> Response:
        import calendar as cal_mod
        from datetime import date as date_cls
        from expenses.models import RecurringExpenseTemplate, Expense
        templates = RecurringExpenseTemplate.objects.filter(tenant_id=self.tenant_id, is_active=True)
        created, skipped = [], []
        for tpl in templates:
            last_day = cal_mod.monthrange(year, month)[1]
            day = min(tpl.day_of_month, last_day)
            entry_date = date_cls(year, month, day)
            already = Expense.objects.filter(
                tenant_id=self.tenant_id,
                description=tpl.description,
                date__year=year,
                date__month=month,
            ).exists()
            if already:
                skipped.append(tpl.description)
                continue
            Expense.objects.create(
                tenant_id=self.tenant_id,
                category_id=tpl.category_id,
                description=tpl.description,
                quantity=1,
                amount=tpl.amount,
                date=entry_date,
                payment_method=tpl.payment_method,
                credit_card_id=tpl.credit_card_id,
            )
            created.append(tpl.description)
        return Response({'created': created, 'skipped': skipped})
