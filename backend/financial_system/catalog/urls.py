from rest_framework.routers import SimpleRouter
from catalog.viewsets import ExpenseCategoryViewSet

router = SimpleRouter()
router.register(r'categories', ExpenseCategoryViewSet, basename='expense-category')

urlpatterns = router.urls
