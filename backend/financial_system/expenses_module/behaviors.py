from datetime import date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from typing import List
from rest_framework.response import Response
from rest_framework import status
from expenses_module.models import Expense


class CreateExpenseBehavior:
    """
    Behavior para criar despesas (expenses) com suporte a parcelamento.

    O keycloak_user_id é extraído automaticamente do token autenticado
    e não precisa ser enviado no corpo da requisição.
    """

    def __init__(self, data):
        self.data = data
        self.keycloak_user_id = data.get('keycloak_user_id')
        self.category_id = data.get('category_id')
        self.description = data.get('description')
        self.amount = Decimal(str(data.get('amount', 0)))
        self.date = data.get('date')
        self.quantity = data.get('quantity', 1)
        self.installments = data.get('installments', 1)
        self.is_installment = data.get('is_installment', False)

    def is_incoming(self) -> bool:
        return self.amount > 0

    def is_outgoing(self) -> bool:
        return self.amount < 0

    def create_single_expense(self) -> Expense:
        return Expense.objects.create(
            keycloak_user_id=self.keycloak_user_id,
            category_id_id=self.category_id,
            description=self.description,
            quantity=self.quantity,
            amount=self.amount,
            date=self.date
        )

    def create_installment_expenses(self) -> List[Expense]:
        expenses = []
        installment_amount = self.amount / self.installments
        current_date = (
            self.date
            if isinstance(self.date, date)
            else date.fromisoformat(str(self.date))
        )

        for installment_number in range(1, self.installments + 1):
            description_with_installment = (
                f"{self.description} - Parcela {installment_number}/{self.installments}"
            )
            expense = Expense.objects.create(
                keycloak_user_id=self.keycloak_user_id,
                category_id_id=self.category_id,
                description=description_with_installment,
                quantity=self.quantity,
                amount=installment_amount,
                date=current_date
            )
            expenses.append(expense)
            current_date = current_date + relativedelta(months=1)

        return expenses

    def run(self):
        try:
            if self.is_installment and self.installments > 1:
                expenses = self.create_installment_expenses()
                return Response(
                    {
                        'success': True,
                        'message': f'{len(expenses)} parcelas criadas com sucesso',
                        'type': 'incoming' if self.is_incoming() else 'outgoing',
                        'is_installment': True,
                        'installments': self.installments,
                        'total_amount': float(self.amount),
                        'installment_amount': float(self.amount / self.installments),
                        'expenses': [
                            {
                                'id': expense.id,
                                'description': expense.description,
                                'amount': float(expense.amount),
                                'date': expense.date.isoformat()
                            }
                            for expense in expenses
                        ]
                    },
                    status=status.HTTP_201_CREATED
                )
            else:
                expense = self.create_single_expense()
                return Response(
                    {
                        'success': True,
                        'message': 'Despesa criada com sucesso',
                        'type': 'incoming' if self.is_incoming() else 'outgoing',
                        'is_installment': False,
                        'installments': 1,
                        'total_amount': float(self.amount),
                        'expense': {
                            'id': expense.id,
                            'description': expense.description,
                            'amount': float(expense.amount),
                            'date': expense.date.isoformat()
                        }
                    },
                    status=status.HTTP_201_CREATED
                )
        except Exception as e:
            return Response(
                {
                    'success': False,
                    'message': f'Erro ao criar despesa(s): {str(e)}',
                    'error': str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
