from rest_framework import serializers
from cards.models import CreditCard


class InvoiceExpensesQuerySerializer(serializers.Serializer):
    invoice_month = serializers.IntegerField(min_value=1, max_value=12)
    invoice_year = serializers.IntegerField(min_value=1)
    category_id = serializers.IntegerField(required=False, min_value=1)
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=200, default=20)
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)


class InvoiceViewQuerySerializer(serializers.Serializer):
    invoice_month = serializers.IntegerField(required=False, min_value=1, max_value=12)
    invoice_year = serializers.IntegerField(required=False, min_value=1)
    category_id = serializers.IntegerField(required=False, min_value=1)
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=200, default=20)
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)

    def validate(self, attrs):
        if ('invoice_month' in attrs) != ('invoice_year' in attrs):
            raise serializers.ValidationError(
                'invoice_month e invoice_year devem ser enviados juntos.'
            )
        return attrs


class OpenInvoicesQuerySerializer(serializers.Serializer):
    closing_month = serializers.IntegerField(required=False, min_value=1, max_value=12)
    closing_year = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        if ('closing_month' in attrs) != ('closing_year' in attrs):
            raise serializers.ValidationError(
                'closing_month e closing_year devem ser enviados juntos.'
            )
        return attrs


class CreditCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditCard
        fields = '__all__'
        read_only_fields = ['tenant_id']
