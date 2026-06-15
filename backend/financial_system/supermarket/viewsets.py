from rest_framework import viewsets
from supermarket import models, serializer


class SupermarketExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.SupermarketExpenseSerializer
    queryset = models.SupermarketExpense.objects.all()

    def get_queryset(self):
        return models.SupermarketExpense.objects.filter(
            tenant_id=self.request.user.tenant_id
        ).prefetch_related('items')


class SupermarketExpenseItemViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.SupermarketExpenseItemSerializer
    queryset = models.SupermarketExpenseItem.objects.all()

    def get_queryset(self):
        return models.SupermarketExpenseItem.objects.filter(tenant_id=self.request.user.tenant_id)
