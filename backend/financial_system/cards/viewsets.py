from rest_framework import viewsets
from cards import models, serializer


class CreditCardViewSet(viewsets.ModelViewSet):
    serializer_class = serializer.CreditCardSerializer
    queryset = models.CreditCard.objects.all()

    def get_queryset(self):
        return models.CreditCard.objects.filter(tenant_id=self.request.user.tenant_id)
