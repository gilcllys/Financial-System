from decimal import Decimal

from rest_framework import serializers
from expenses.models import Expense


class HistoryQuerySerializer(serializers.Serializer):
    month = serializers.IntegerField(required=False, min_value=1, max_value=12)
    year = serializers.IntegerField(required=False, min_value=1)
    category_id = serializers.IntegerField(required=False, min_value=1)
    category_key = serializers.CharField(required=False, max_length=40)
    payment_method = serializers.ChoiceField(
        required=False, choices=['dinheiro', 'cartao'],
    )
    credit_card_id = serializers.IntegerField(required=False, min_value=1)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)
    type = serializers.ChoiceField(required=False, choices=['individual', 'shared'])
    include_future = serializers.BooleanField(required=False, default=False)
    min_amount = serializers.DecimalField(
        required=False, max_digits=12, decimal_places=2, min_value=Decimal('0.00'),
    )
    max_amount = serializers.DecimalField(
        required=False, max_digits=12, decimal_places=2, min_value=Decimal('0.00'),
    )
    amount = serializers.DecimalField(
        required=False, max_digits=12, decimal_places=2, min_value=Decimal('0.00'),
    )
    export = serializers.ChoiceField(required=False, choices=['csv'])
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)

    def validate(self, attrs):
        minimum = attrs.get('min_amount')
        maximum = attrs.get('max_amount')
        if minimum is not None and maximum is not None and minimum > maximum:
            raise serializers.ValidationError({'max_amount': 'Deve ser maior ou igual a min_amount.'})
        return attrs


class HistoryBulkCategoryInputSerializer(serializers.Serializer):
    expense_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=100,
    )
    category_id = serializers.IntegerField(min_value=1)

    def validate_expense_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError('IDs de lançamentos duplicados.')
        return value


class ExpenseAnalyticsQuerySerializer(serializers.Serializer):
    month = serializers.IntegerField(required=False, min_value=1, max_value=12)
    year = serializers.IntegerField(required=False, min_value=1)
    closing_month = serializers.IntegerField(required=False, min_value=1, max_value=12)
    closing_year = serializers.IntegerField(required=False, min_value=1)
    payment_method = serializers.ChoiceField(required=False, choices=['dinheiro', 'cartao'])
    period = serializers.ChoiceField(
        required=False, choices=['purchase_month', 'cycle'], default='purchase_month',
    )
    include_obligations = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if ('closing_month' in attrs) != ('closing_year' in attrs):
            raise serializers.ValidationError(
                'closing_month e closing_year devem ser enviados juntos.'
            )
        return attrs


class ImportExcelInputSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)


class ExpenseSerializer(serializers.ModelSerializer):
    # Expõe category_id explicitamente para leitura e escrita
    category_id = serializers.IntegerField(source='category.id', read_only=True)
    # Nome da categoria para exibição, espelhando o contrato de shared_entries.
    # Sem isso o front só recebe o id e não consegue renderizar a categoria.
    category_name = serializers.CharField(source='category.name', read_only=True)
    # Origem da despesa: permite ao front distinguir gasto fixo de lancamento
    # manual sem inferir pela descricao (que o usuario pode editar).
    recurring_template_id = serializers.IntegerField(read_only=True)
    is_recurrent = serializers.BooleanField(read_only=True)
    is_recurring = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = '__all__'
        read_only_fields = ['tenant_id', 'recurring_template']

    def get_is_recurring(self, obj) -> bool:
        return obj.is_recurrent

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
    expense_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False,
        allow_empty=False, max_length=60,
    )

    def validate_expense_ids(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError('IDs de parcelas duplicados.')
        return value


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
