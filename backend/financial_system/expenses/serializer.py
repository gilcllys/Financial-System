from rest_framework import serializers
from expenses.models import Expense


class ExpenseSerializer(serializers.ModelSerializer):
    # Expõe category_id explicitamente para leitura e escrita
    category_id = serializers.IntegerField(source='category.id', read_only=True)
    # Nome da categoria para exibição, espelhando o contrato de shared_entries.
    # Sem isso o front só recebe o id e não consegue renderizar a categoria.
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Expense
        fields = '__all__'
        read_only_fields = ['tenant_id']

    def to_internal_value(self, data):
        # Aceita category_id no payload (PUT/PATCH) mapeando para o campo category
        mutable = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'category_id' in mutable and 'category' not in mutable:
            mutable['category'] = mutable.pop('category_id')
        return super().to_internal_value(mutable)


class CreateExpenseInputSerializer(serializers.Serializer):
    category_id = serializers.IntegerField(required=True, allow_null=False)
    description = serializers.CharField(required=True, allow_null=False, max_length=255)
    amount = serializers.DecimalField(required=True, allow_null=False, max_digits=10, decimal_places=2)
    date = serializers.DateField(required=True, allow_null=False)
    quantity = serializers.IntegerField(required=False, default=1)
    payment_method = serializers.ChoiceField(choices=['dinheiro', 'cartao'], required=False, default='dinheiro')
    credit_card_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    is_installment = serializers.BooleanField(required=False, default=False)
    installments = serializers.IntegerField(required=False, default=1)

    def validate(self, attrs):
        if attrs.get('payment_method') == 'cartao' and attrs.get('credit_card_id') is None:
            raise serializers.ValidationError({
                'credit_card_id': 'Obrigatório quando payment_method é "cartao".',
            })
        return attrs


class BulkCreateExpenseInputSerializer(serializers.Serializer):
    items = CreateExpenseInputSerializer(many=True, allow_empty=False)


class DeleteInstallmentsInputSerializer(serializers.Serializer):
    description_prefix = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=255,
        help_text='Nome base da despesa parcelada (ex: "Celular novo").',
    )
    total_installments = serializers.IntegerField(
        required=True,
        min_value=2,
        help_text='Total de parcelas do grupo (ex: 10 para "Parcela X/10").',
    )


class RecurringExpenseTemplateSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)
    credit_card_name = serializers.CharField(source='credit_card.name', read_only=True, default=None)

    class Meta:
        from expenses.models import RecurringExpenseTemplate
        model = RecurringExpenseTemplate
        fields = [
            'id', 'description', 'amount', 'day_of_month',
            'payment_method', 'credit_card', 'credit_card_name',
            'category', 'category_name', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class CreateRecurringExpenseInputSerializer(serializers.Serializer):
    from decimal import Decimal
    description = serializers.CharField(required=True, max_length=255)
    amount = serializers.DecimalField(required=True, max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    day_of_month = serializers.IntegerField(required=False, default=1, min_value=1, max_value=28)
    payment_method = serializers.ChoiceField(choices=['dinheiro', 'cartao'], required=False, default='dinheiro')
    credit_card_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    category_id = serializers.IntegerField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        if attrs.get('payment_method') == 'cartao' and attrs.get('credit_card_id') is None:
            raise serializers.ValidationError({
                'credit_card_id': 'Obrigatório quando payment_method é "cartao".',
            })
        return attrs


class GenerateMonthInputSerializer(serializers.Serializer):
    month = serializers.IntegerField(min_value=1, max_value=12)
    year = serializers.IntegerField(min_value=2000)
