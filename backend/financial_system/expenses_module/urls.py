from rest_framework import routers
from expenses_module import viewsets


router = routers.SimpleRouter()
router.register(r'expense', viewsets.ExpenseViewSet, basename='expense')
router.register(r'expense_category',
                viewsets.ExpenseCategoryViewSet, basename='expense_category')
router.register(r'supermach_expense',
                viewsets.SupermachExpenseViewSet, basename='supermach_expense')
router.register(r'supermach_expense_item',
                viewsets.SupermachExpenseItemViewSet, basename='supermach_expense_item')

urlpatterns = router.urls
