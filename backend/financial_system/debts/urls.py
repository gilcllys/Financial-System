from django.urls import path
from rest_framework.routers import SimpleRouter

from debts.viewsets import (
    PersonalSummaryView,
    SharedDebtViewSet,
    SharedEntryViewSet,
)

router = SimpleRouter()
router.register(r'shared-debts', SharedDebtViewSet, basename='shared-debt')
router.register(r'shared-entries', SharedEntryViewSet, basename='shared-entry')

urlpatterns = [
    path('personal-summary/', PersonalSummaryView.as_view(), name='personal-summary'),
] + router.urls
