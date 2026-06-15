from rest_framework import viewsets
from rest_framework.decorators import action
from expenses import models, serializer
from expenses.behaviors import CreateExpenseBehavior


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.ExpenseSerializer
    queryset = models.Expense.objects.all()

    def get_queryset(self):
        return models.Expense.objects.filter(tenant_id=self.request.user.tenant_id)

    @action(detail=False, methods=['post'], url_path='create-expense')
    def create_expense(self, request):
        s = serializer.CreateExpenseInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        payload = dict(s.validated_data)
        payload['tenant_id'] = request.user.tenant_id
        return CreateExpenseBehavior(data=payload).run()
