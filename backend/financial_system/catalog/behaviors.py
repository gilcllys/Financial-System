from catalog.models import ExpenseCategory


class ExpenseCategoryBehavior:
    @staticmethod
    def list_for_tenant(tenant_id: str):
        return ExpenseCategory.objects.filter(tenant_id=tenant_id)

    @staticmethod
    def create(tenant_id: str, name: str, description: str = None) -> ExpenseCategory:
        return ExpenseCategory.objects.create(
            tenant_id=tenant_id,
            name=name,
            description=description,
        )
