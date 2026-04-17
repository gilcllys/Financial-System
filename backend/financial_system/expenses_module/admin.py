from django.contrib import admin
from expenses_module import models

admin.site.register(models.ExpenseCategory)
admin.site.register(models.CreditCard)
admin.site.register(models.Expense)
admin.site.register(models.SupermachExepense)
admin.site.register(models.SupermachExpenseItem)
