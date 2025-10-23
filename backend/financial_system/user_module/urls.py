from rest_framework import routers
from user_module import viewsets
from django.urls import path, include


router = routers.SimpleRouter()
router.register(r'user', viewsets.UserViewSet)


urlpatterns = router.urls
