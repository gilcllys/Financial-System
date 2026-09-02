from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from supermarket import models, serializer


class SupermarketExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.SupermarketExpenseSerializer
    queryset = models.SupermarketExpense.objects.all()

    def get_queryset(self):
        return models.SupermarketExpense.objects.filter(
            tenant_id=self.request.user.tenant_id
        ).prefetch_related('items')

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.user.tenant_id)

    def perform_update(self, serializer):
        """[SEC-A01] Defense-in-depth: mantém tenant_id fixo no update."""
        serializer.save(tenant_id=self.request.user.tenant_id)


class SupermarketExpenseItemViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.SupermarketExpenseItemSerializer
    queryset = models.SupermarketExpenseItem.objects.all()

    def get_queryset(self):
        return models.SupermarketExpenseItem.objects.filter(tenant_id=self.request.user.tenant_id)

    def _assert_parent_ownership(self, validated_data):
        """
        [SEC-A01] IDOR: valida que o SupermarketExpense pai pertence ao tenant
        autenticado. Sem este check, um usuário poderia criar/editar itens
        apontando para despesas de outros tenants.
        """
        parent = validated_data.get('supermarket_expense')
        if parent and parent.tenant_id != self.request.user.tenant_id:
            raise PermissionDenied(
                "A despesa de supermercado vinculada não pertence ao usuário autenticado."
            )

    def perform_create(self, serializer):
        self._assert_parent_ownership(serializer.validated_data)
        serializer.save(tenant_id=self.request.user.tenant_id)

    def perform_update(self, serializer):
        """[SEC-A01] Defense-in-depth: valida parent ownership e fixa tenant_id."""
        self._assert_parent_ownership(serializer.validated_data)
        serializer.save(tenant_id=self.request.user.tenant_id)
