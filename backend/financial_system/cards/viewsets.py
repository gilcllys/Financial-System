from rest_framework import viewsets
from cards import models, serializer


class CreditCardViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.CreditCardSerializer
    queryset = models.CreditCard.objects.all()

    def get_queryset(self):
        return models.CreditCard.objects.filter(tenant_id=self.request.user.tenant_id)

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.user.tenant_id)

    def perform_update(self, serializer):
        """[SEC-A01] Defense-in-depth: garante que tenant_id não muda em updates."""
        serializer.save(tenant_id=self.request.user.tenant_id)
