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

    def perform_update(self, serializer):
        """
        [SEC-A01] Impede o sequestro de categoria global.

        Categorias 'system' aparecem no get_queryset de TODOS os tenants. Sem
        esta guarda o save() abaixo gravaria o tenant do autenticado na
        categoria global, que passaria a pertencer a ele e sumiria para todos
        os outros. O perform_destroy ja barrava o delete; faltava o update.
        """
        if serializer.instance.tenant_id != self.request.user.tenant_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Você não tem permissão para editar este recurso.")
        serializer.save(tenant_id=self.request.user.tenant_id)

    def perform_destroy(self, instance):
        if instance.tenant_id != self.request.user.tenant_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Você não tem permissão para excluir este recurso.")
        instance.delete()
