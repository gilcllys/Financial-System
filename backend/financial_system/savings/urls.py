from rest_framework.routers import SimpleRouter
from savings.viewsets import SavingsGoalViewSet, SavingsDepositViewSet

router = SimpleRouter()
router.register(r'goals', SavingsGoalViewSet, basename='savings-goal')
router.register(r'deposits', SavingsDepositViewSet, basename='savings-deposit')
urlpatterns = router.urls
