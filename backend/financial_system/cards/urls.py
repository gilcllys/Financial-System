from rest_framework.routers import SimpleRouter
from cards.viewsets import CreditCardViewSet

router = SimpleRouter()
router.register(r'credit-cards', CreditCardViewSet, basename='credit-card')

urlpatterns = router.urls
