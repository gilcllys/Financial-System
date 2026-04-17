from rest_framework import serializers


class CreateExpenseCustomSerializer(serializers.Serializer):
    category_id = serializers.IntegerField(
        required=True,
        allow_null=False
    )
    description = serializers.CharField(
        required=True,
        allow_null=False,
        max_length=255
    )
    amount = serializers.DecimalField(
        required=True,
        allow_null=False,
        max_digits=10,
        decimal_places=2
    )
    date = serializers.DateField(
        required=True,
        allow_null=False
    )
    quantity = serializers.IntegerField(
        required=False,
        default=1
    )
    is_installment = serializers.BooleanField(
        required=False,
        default=False
    )
    installments = serializers.IntegerField(
        required=False,
        default=1
    )
