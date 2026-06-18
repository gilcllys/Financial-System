from django.contrib import admin
from supermarket.models import SupermarketExpense, SupermarketExpenseItem

admin.site.register(SupermarketExpense)
admin.site.register(SupermarketExpenseItem)
