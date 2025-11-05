from rest_framework import serializers
from expenses_module import models


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ExpenseCategory
        fields = '__all__'


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Expense
        fields = '__all__'


class SupermachExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SupermachExepense
        fields = '__all__'


class SupermachExpenseItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SupermachExpenseItem
        fields = '__all__'
