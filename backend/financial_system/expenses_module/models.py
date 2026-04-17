from django.db import models


class BaseModel(models.Model):
    id = models.AutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ExpenseCategory(BaseModel):
    name = models.CharField(
        max_length=100,
        db_column='name',
        db_index=True,
        null=False,
    )
    description = models.TextField(
        db_column='description',
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'expense_categories'
        verbose_name = "Expense Category"
        verbose_name_plural = "Expense Categories"


class CreditCard(BaseModel):
    keycloak_user_id = models.CharField(
        max_length=36,
        db_column='keycloak_user_id',
        db_index=True,
        null=False,
        help_text='UUID do usuário no Keycloak (sub claim)',
    )
    name = models.CharField(
        max_length=100,
        db_column='name',
        db_index=True,
        null=False,
    )
    due_date = models.IntegerField(
        db_column='due_date',
        null=False,
        help_text='Dia do vencimento da fatura (1-31)',
    )
    best_purchase_date = models.IntegerField(
        db_column='best_purchase_date',
        null=False,
        help_text='Melhor dia para compra (1-31)',
    )
    last_four_digits = models.CharField(
        max_length=4,
        db_column='last_four_digits',
        null=False,
    )

    class Meta:
        db_table = 'credit_cards'
        verbose_name = "Credit Card"
        verbose_name_plural = "Credit Cards"


class Expense(BaseModel):
    PAYMENT_METHOD_CHOICES = [
        ('dinheiro', 'Dinheiro'),
        ('cartao', 'Cartão'),
    ]

    keycloak_user_id = models.CharField(
        max_length=36,
        db_column='keycloak_user_id',
        db_index=True,
        null=False,
        help_text='UUID do usuário no Keycloak (sub claim)',
    )
    category_id = models.ForeignKey(
        to='ExpenseCategory',
        db_column='category_id',
        db_index=True,
        null=False,
        on_delete=models.DO_NOTHING
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
        to='CreditCard',
        db_column='credit_card_id',
        db_index=True,
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
    )
    description = models.CharField(
        max_length=255,
        db_column='description',
        db_index=True,
        null=False,
    )
    quantity = models.IntegerField(
        db_column='quantity',
        db_index=True,
        null=False,
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        db_column='amount',
        db_index=True,
        null=False,
    )
    date = models.DateField(
        db_column='date',
        db_index=True,
        null=False,
    )

    class Meta:
        db_table = 'expenses'
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"


class SupermachExepense(BaseModel):
    store_name = models.CharField(
        max_length=100,
        db_column='store_name',
        db_index=True,
        null=False,
    )
    date = models.DateField(
        db_column='date',
        db_index=True,
        null=False,
    )
    adress = models.CharField(
        max_length=100,
        db_column='address',
        db_index=True,
        null=True,
    )

    class Meta:
        db_table = 'supermach_expenses'
        verbose_name = "Supermach Expense"
        verbose_name_plural = "Supermach Expenses"


class SupermachExpenseItem(BaseModel):
    supermach_expense_id = models.ForeignKey(
        to='SupermachExepense',
        db_column='supermach_expense_id',
        db_index=True,
        null=False,
        on_delete=models.DO_NOTHING
    )
    description = models.CharField(
        max_length=255,
        db_column='description',
        db_index=True,
        null=False,
    )
    quantity = models.IntegerField(
        db_column='quantity',
        db_index=True,
        null=False,
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        db_column='amount',
        db_index=True,
        null=False,
    )

    class Meta:
        db_table = 'supermach_expense_items'
        verbose_name = "Supermach Expense Item"
        verbose_name_plural = "Supermach Expense Items"
