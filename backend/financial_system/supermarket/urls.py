from rest_framework.routers import SimpleRouter
from supermarket.viewsets import SupermarketExpenseViewSet, SupermarketExpenseItemViewSet

router = SimpleRouter()
router.register(r'supermarket-expenses', SupermarketExpenseViewSet, basename='supermarket-expense')
router.register(r'supermarket-expense-items', SupermarketExpenseItemViewSet, basename='supermarket-expense-item')

urlpatterns = router.urls
