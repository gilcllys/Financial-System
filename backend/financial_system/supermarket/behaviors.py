from supermarket.models import SupermarketExpense, SupermarketExpenseItem


class SupermarketExpenseBehavior:
    @staticmethod
    def list_for_tenant(tenant_id: str):
        return SupermarketExpense.objects.filter(tenant_id=tenant_id).prefetch_related('items')

    @staticmethod
    def create(tenant_id: str, store_name: str, date, address: str = None) -> SupermarketExpense:
        return SupermarketExpense.objects.create(
            tenant_id=tenant_id,
            store_name=store_name,
            date=date,
            address=address,
        )


class SupermarketExpenseItemBehavior:
    @staticmethod
    def list_for_tenant(tenant_id: str):
        return SupermarketExpenseItem.objects.filter(tenant_id=tenant_id)
