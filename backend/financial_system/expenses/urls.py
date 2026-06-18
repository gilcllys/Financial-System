from rest_framework.routers import SimpleRouter
from expenses.viewsets import ExpenseViewSet

router = SimpleRouter()
router.register(r'expenses', ExpenseViewSet, basename='expense')

urlpatterns = router.urls
