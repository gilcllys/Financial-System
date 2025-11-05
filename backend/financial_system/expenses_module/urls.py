from rest_framework import routers
from expenses_module import viewsets


router = routers.SimpleRouter()
router.register(r'expense', viewsets.ExpenseViewSet)
router.register(r'expense_category', viewsets.ExpenseCategoryViewSet)
router.register(r'supermach_expense', viewsets.SupermachExpenseViewSet)
router.register(r'supermach_expense_item',
                viewsets.SupermachExpenseItemViewSet)


urlpatterns = router.urls
