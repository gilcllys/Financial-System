from rest_framework import viewsets
from debts import models, serializer


class VitoriaDebtViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.VitoriaDebtSerializer
    queryset = models.VitoriaDebt.objects.all()

    def get_queryset(self):
        return models.VitoriaDebt.objects.filter(tenant_id=self.request.user.tenant_id)
