from rest_framework import viewsets
from catalog import models, serializer


class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.ExpenseCategorySerializer
    queryset = models.ExpenseCategory.objects.all()

    def get_queryset(self):
        return models.ExpenseCategory.objects.filter(
            tenant_id__in=['system', self.request.user.tenant_id]
        )

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.user.tenant_id)
