from cards.models import CreditCard


class CreditCardBehavior:
    @staticmethod
    def list_for_tenant(tenant_id: str):
        return CreditCard.objects.filter(tenant_id=tenant_id)

    @staticmethod
    def create(tenant_id: str, **kwargs) -> CreditCard:
        return CreditCard.objects.create(tenant_id=tenant_id, **kwargs)
