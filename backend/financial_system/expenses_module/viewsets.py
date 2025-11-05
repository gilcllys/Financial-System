from rest_framework import viewsets
from expenses_module import serializer, models


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.ExpenseSerializer
    queryset = models.Expense.objects.all()


class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.ExpenseCategorySerializer
    queryset = models.ExpenseCategory.objects.all()


class SupermachExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.SupermachExpenseSerializer
    queryset = models.SupermachExepense.objects.all()


class SupermachExpenseItemViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.SupermachExpenseItemSerializer
    queryset = models.SupermachExpenseItem.objects.all()
