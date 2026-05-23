from rest_framework import viewsets
from rest_framework.decorators import action
from expenses_module import serializer, models, custom_serializer
from expenses_module.behaviors import CreateExpenseBehavior


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.ExpenseSerializer
    queryset = models.Expense.objects.all()

    def get_queryset(self):
        return models.Expense.objects.filter(
            tenant_id=self.request.user.tenant_id
        )

    @action(detail=False, methods=['post'], url_path='create-expense')
    def create_expense(self, request):
        data = request.data.copy()
        s = custom_serializer.CreateExpenseCustomSerializer(data=data)
        s.is_valid(raise_exception=True)
        payload = dict(s.validated_data)
        payload['tenant_id'] = request.user.tenant_id
        response = CreateExpenseBehavior(data=payload).run()
        return response


class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.ExpenseCategorySerializer
    queryset = models.ExpenseCategory.objects.all()


class CreditCardViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.CreditCardSerializer
    queryset = models.CreditCard.objects.all()

    def get_queryset(self):
        return models.CreditCard.objects.filter(
            tenant_id=self.request.user.tenant_id
        )

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.user.tenant_id)


class SupermachExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.SupermachExpenseSerializer
    queryset = models.SupermachExepense.objects.all()


class SupermachExpenseItemViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.SupermachExpenseItemSerializer
    queryset = models.SupermachExpenseItem.objects.all()
