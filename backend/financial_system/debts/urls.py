from rest_framework.routers import SimpleRouter
from debts.viewsets import SharedDebtViewSet, SharedEntryViewSet

router = SimpleRouter()
router.register(r'shared-debts', SharedDebtViewSet, basename='shared-debt')
router.register(r'shared-entries', SharedEntryViewSet, basename='shared-entry')

urlpatterns = router.urls
