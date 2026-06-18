from django.contrib import admin
from django.urls import path, include
from .api_root import api_root


urlpatterns = [
    path('', api_root),
    path('admin/', admin.site.urls),
    path('api/catalog/', include('catalog.urls')),
    path('api/cards/', include('cards.urls')),
    path('api/expenses/', include('expenses.urls')),
    path('api/debts/', include('debts.urls')),
    path('api/supermarket/', include('supermarket.urls')),
]
