from rest_framework import serializers

from decimal import Decimal


class CreateSharedDebtInputSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, allow_blank=False, max_length=120)
    member_names = serializers.ListField(
        child=serializers.CharField(allow_blank=False, max_length=120),
        required=False,
        default=list,
        help_text='Nomes de membros extras adicionados na criação (tenant_id=None).',
    )


class CreateSharedEntryInputSerializer(serializers.Serializer):
    description = serializers.CharField(required=True, allow_blank=False, max_length=255)
    amount = serializers.DecimalField(
        required=True,
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0.01'),
    )
    date = serializers.DateField(required=True)
    paid_by = serializers.IntegerField(required=True, help_text='ID do membro que pagou.')
    participant_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        help_text='IDs dos membros que dividem; se vazio, divide entre TODOS.',
    )
    payment_method = serializers.ChoiceField(
        choices=['dinheiro', 'cartao'],
        required=False,
        default='dinheiro',
    )
    credit_card_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        default=None,
    )


class JoinSharedDebtInputSerializer(serializers.Serializer):
    token = serializers.UUIDField(required=True)
    display_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
        help_text='Se ausente, usa o nome/email do usuário autenticado.',
    )


class InviteInputSerializer(serializers.Serializer):
    expires_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        default=None,
    )
