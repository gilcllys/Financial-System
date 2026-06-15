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
    Se need_pay_vitoria=True, cria um VitoriaDebt para cada despesa.
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
        self.need_pay_vitoria = data.get('need_pay_vitoria', False)

    def _create_vitoria_debt(self, expense: Expense):
        from debts.models import VitoriaDebt
        VitoriaDebt.objects.create(
            tenant_id=self.tenant_id,
            expense=expense,
            is_paid=False,
        )

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
        if self.need_pay_vitoria:
            self._create_vitoria_debt(expense)
        return expense

    @transaction.atomic
    def _create_single(self) -> Expense:
        return self._build_expense(self.description, self.amount, self.date)

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
