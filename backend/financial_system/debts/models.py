import uuid

from django.db import models
from django.db.models import Q

from financial_system.base_model import BaseModel


class SharedDebt(BaseModel):
    """
    Grupo de dívida compartilhada (estilo Tricount).

    Reúne múltiplos membros (tenants distintos do Keycloak) que dividem
    despesas em comum. O acesso é baseado em participação (membership),
    não em posse — ver SharedDebtViewSet.get_queryset.
    """

    name = models.CharField(
        max_length=120,
        db_column='name',
        null=False,
    )
    owner_tenant_id = models.CharField(
        max_length=36,
        db_column='owner_tenant_id',
        db_index=True,
        null=False,
        help_text='tenant_id (sub do Keycloak) do criador do grupo.',
    )

    class Meta:
        db_table = 'shared_debts'
        verbose_name = 'Shared Debt'
        verbose_name_plural = 'Shared Debts'


class SharedDebtMember(BaseModel):
    """
    Membro de um grupo de dívida compartilhada.

    tenant_id fica NULL enquanto o membro é apenas um "slot" adicionado por
    nome (ainda não reivindicado via link de convite). Ao entrar pelo convite,
    o usuário recebe um membro com tenant_id preenchido.
    """

    shared_debt = models.ForeignKey(
        to=SharedDebt,
        db_column='shared_debt_id',
        on_delete=models.CASCADE,
        related_name='members',
    )
    tenant_id = models.CharField(
        max_length=36,
        db_column='tenant_id',
        db_index=True,
        null=True,
        blank=True,
        help_text='tenant_id do Keycloak; NULL até a pessoa entrar via link.',
    )
    display_name = models.CharField(
        max_length=120,
        db_column='display_name',
        null=False,
    )
    email = models.EmailField(
        db_column='email',
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'shared_debt_members'
        verbose_name = 'Shared Debt Member'
        verbose_name_plural = 'Shared Debt Members'
        constraints = [
            models.UniqueConstraint(
                fields=['shared_debt', 'tenant_id'],
                condition=Q(tenant_id__isnull=False),
                name='uniq_member_per_tenant',
            ),
        ]


class SharedEntry(BaseModel):
    """Uma despesa compartilhada dentro de um grupo."""

    PAYMENT_METHOD_CHOICES = [
        ('dinheiro', 'Dinheiro'),
        ('cartao', 'Cartao'),
    ]

    shared_debt = models.ForeignKey(
        to=SharedDebt,
        db_column='shared_debt_id',
        on_delete=models.CASCADE,
        related_name='entries',
    )
    paid_by = models.ForeignKey(
        to=SharedDebtMember,
        db_column='paid_by_id',
        on_delete=models.PROTECT,
        related_name='paid_entries',
    )
    description = models.CharField(
        max_length=255,
        db_column='description',
        null=False,
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        db_column='amount',
        null=False,
        help_text='Valor positivo da despesa compartilhada.',
    )
    date = models.DateField(
        db_column='date',
        null=False,
    )
    payment_method = models.CharField(
        max_length=10,
        choices=PAYMENT_METHOD_CHOICES,
        db_column='payment_method',
        db_index=True,
        default='dinheiro',
        null=False,
    )
    credit_card = models.ForeignKey(
        to='cards.CreditCard',
        db_column='credit_card_id',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shared_entries',
        help_text='Preenchido apenas quando o usuário atual pagou no próprio cartão.',
    )
    category = models.ForeignKey(
        to='catalog.ExpenseCategory',
        db_column='category_id',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shared_entries',
        help_text='Categoria opcional da despesa compartilhada.',
    )
    created_by_tenant_id = models.CharField(
        max_length=36,
        db_column='created_by_tenant_id',
        db_index=True,
        null=False,
    )

    installment_group_id = models.UUIDField(
        db_column='installment_group_id',
        null=True,
        blank=True,
        db_index=True,
        help_text='UUID que agrupa todas as parcelas de um mesmo parcelamento.',
    )
    total_installments = models.PositiveSmallIntegerField(
        db_column='total_installments',
        default=1,
        help_text='Total de parcelas (1 = não parcelado).',
    )
    installment_number = models.PositiveSmallIntegerField(
        db_column='installment_number',
        default=1,
        help_text='Número desta parcela (1-based).',
    )

    class Meta:
        db_table = 'shared_entries'
        verbose_name = 'Shared Entry'
        verbose_name_plural = 'Shared Entries'


class SharedEntryParticipant(BaseModel):
    """
    Participante de uma despesa compartilhada (rateio igualitário entre
    todos os participantes de uma SharedEntry).
    """

    entry = models.ForeignKey(
        to=SharedEntry,
        db_column='entry_id',
        on_delete=models.CASCADE,
        related_name='participants',
    )
    member = models.ForeignKey(
        to=SharedDebtMember,
        db_column='member_id',
        on_delete=models.CASCADE,
        related_name='participations',
    )

    class Meta:
        db_table = 'shared_entry_participants'
        verbose_name = 'Shared Entry Participant'
        verbose_name_plural = 'Shared Entry Participants'
        constraints = [
            models.UniqueConstraint(
                fields=['entry', 'member'],
                name='uniq_participant_per_entry',
            ),
        ]


class SharedDebtInvite(BaseModel):
    """Convite por link para entrar em um grupo de dívida compartilhada."""

    shared_debt = models.ForeignKey(
        to=SharedDebt,
        db_column='shared_debt_id',
        on_delete=models.CASCADE,
        related_name='invites',
    )
    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        db_column='token',
    )
    expires_at = models.DateTimeField(
        db_column='expires_at',
        null=True,
        blank=True,
    )
    created_by_tenant_id = models.CharField(
        max_length=36,
        db_column='created_by_tenant_id',
        null=False,
    )

    class Meta:
        db_table = 'shared_debt_invites'
        verbose_name = 'Shared Debt Invite'
        verbose_name_plural = 'Shared Debt Invites'


class SharedRecurringTemplate(BaseModel):
    """
    Gasto fixo recorrente mensal de um grupo compartilhado.

    Ao ser materializado (via generate_month), cria uma SharedEntry real
    para o mês/ano solicitado, caso ainda não exista.
    """

    PAYMENT_METHOD_CHOICES = [
        ('dinheiro', 'Dinheiro'),
        ('cartao', 'Cartao'),
    ]

    shared_debt = models.ForeignKey(
        to=SharedDebt,
        db_column='shared_debt_id',
        on_delete=models.CASCADE,
        related_name='recurring_templates',
    )
    description = models.CharField(max_length=255, db_column='description')
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, db_column='amount',
        help_text='Valor positivo da despesa mensal.',
    )
    paid_by = models.ForeignKey(
        to=SharedDebtMember,
        db_column='paid_by_id',
        on_delete=models.PROTECT,
        related_name='recurring_templates',
    )
    participant_ids = models.JSONField(
        db_column='participant_ids',
        default=list,
        help_text='Lista de IDs de SharedDebtMember que dividem o gasto.',
    )
    payment_method = models.CharField(
        max_length=10,
        choices=PAYMENT_METHOD_CHOICES,
        db_column='payment_method',
        default='dinheiro',
    )
    category = models.ForeignKey(
        to='catalog.ExpenseCategory',
        db_column='category_id',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='recurring_templates',
    )
    day_of_month = models.PositiveSmallIntegerField(
        db_column='day_of_month',
        default=1,
        help_text='Dia do mês em que a despesa se repete (1–28).',
    )
    is_active = models.BooleanField(
        db_column='is_active',
        default=True,
        help_text='Falso = template pausado, não gera novas entradas.',
    )

    class Meta:
        db_table = 'shared_recurring_templates'
        verbose_name = 'Shared Recurring Template'
        verbose_name_plural = 'Shared Recurring Templates'
