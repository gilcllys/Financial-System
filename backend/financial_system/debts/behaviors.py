from debts.models import VitoriaDebt


class VitoriaDebtBehavior:
    @staticmethod
    def list_for_tenant(tenant_id: str):
        return VitoriaDebt.objects.filter(tenant_id=tenant_id)

    @staticmethod
    def mark_as_paid(debt_id: int, tenant_id: str) -> VitoriaDebt:
        debt = VitoriaDebt.objects.get(id=debt_id, tenant_id=tenant_id)
        debt.is_paid = True
        debt.save(update_fields=['is_paid', 'updated_at'])
        return debt
