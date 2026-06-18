from rest_framework.routers import SimpleRouter
from debts.viewsets import VitoriaDebtViewSet

router = SimpleRouter()
router.register(r'vitoria-debts', VitoriaDebtViewSet, basename='vitoria-debt')

urlpatterns = router.urls
