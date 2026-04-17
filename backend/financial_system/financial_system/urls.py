from django.contrib import admin
from django.urls import path, include
from .api_root import api_root


urlpatterns = [
    path('', api_root),
    path('admin/', admin.site.urls),
    path('api/cost/', include('expenses_module.urls')),
]
