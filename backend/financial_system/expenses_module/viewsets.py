from rest_framework import viewsets
from rest_framework.decorators import action
from expenses_module import serializer, models, custom_serializer
from expenses_module.behaviors import CreateExpenseBehavior


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.ExpenseSerializer
    queryset = models.Expense.objects.all()

    @action(detail=False, methods=['post'], url_path='create-expense')
    def create_expense(self, request):
        data = request.data
        serializer = custom_serializer.CreateExpenseCustomSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        data_serializer = serializer.validated_data
        response = CreateExpenseBehavior(data=data_serializer).run()
        return response


class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.ExpenseCategorySerializer
    queryset = models.ExpenseCategory.objects.all()


class CreditCardViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.CreditCardSerializer
    queryset = models.CreditCard.objects.all()


class SupermachExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.SupermachExpenseSerializer
    queryset = models.SupermachExepense.objects.all()


class SupermachExpenseItemViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.SupermachExpenseItemSerializer
    queryset = models.SupermachExpenseItem.objects.all()
