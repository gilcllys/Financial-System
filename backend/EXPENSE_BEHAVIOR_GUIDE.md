# Behavior para Criação de Expenses com Parcelamento

## Arquivos Criados/Modificados:

### 1. `expense_behavior.py` - Behavior Class
- **CreateExpenseBehavior**: Classe que gerencia a criação de expenses
  - Verifica se é entrada (incoming) ou saída (outgoing)
  - Suporta criação à vista ou parcelada
  - Para parcelamento: divide o valor e cria múltiplas expenses
  - Adiciona 1 mês entre cada parcela

### 2. `viewsets.py` - Action no ExpenseViewSet
- **Action `create_expense`**: Endpoint POST `/api/expenses/create-expense/`
  - Recebe dados da expense
  - Chama o behavior para processar
  - Retorna resultado com detalhes das expenses criadas

## Como Usar:

### Exemplo 1: Despesa À Vista (Outgoing)
```json
POST /api/expenses/create-expense/

{
  "user_id": 1,
  "category_id": 2,
  "description": "Compra no supermercado",
  "amount": -250.00,
  "date": "2026-03-01",
  "quantity": 1,
  "is_installment": false,
  "installments": 1
}
```

### Exemplo 2: Despesa Parcelada (12x)
```json
POST /api/expenses/create-expense/

{
  "user_id": 1,
  "category_id": 3,
  "description": "Notebook Dell",
  "amount": -3600.00,
  "date": "2026-03-01",
  "quantity": 1,
  "is_installment": true,
  "installments": 12
}
```
**Resultado:** Cria 12 expenses de -300.00 cada, de 01/03/2026 a 01/02/2027

### Exemplo 3: Receita (Incoming)
```json
POST /api/expenses/create-expense/

{
  "user_id": 1,
  "category_id": 1,
  "description": "Salário Mensal",
  "amount": 5000.00,
  "date": "2026-03-01",
  "quantity": 1,
  "is_installment": false
}
```

## Respostas da API:

### Sucesso - À Vista:
```json
{
  "success": true,
  "message": "Despesa criada com sucesso",
  "type": "outgoing",
  "is_installment": false,
  "installments": 1,
  "total_amount": -250.0,
  "expense": {
    "id": 1,
    "description": "Compra no supermercado",
    "amount": -250.0,
    "date": "2026-03-01"
  }
}
```

### Sucesso - Parcelado:
```json
{
  "success": true,
  "message": "12 parcelas criadas com sucesso",
  "type": "outgoing",
  "is_installment": true,
  "installments": 12,
  "total_amount": -3600.0,
  "installment_amount": -300.0,
  "expenses": [
    {
      "id": 1,
      "description": "Notebook Dell - Parcela 1/12",
      "amount": -300.0,
      "date": "2026-03-01"
    },
    {
      "id": 2,
      "description": "Notebook Dell - Parcela 2/12",
      "amount": -300.0,
      "date": "2026-04-01"
    },
    ...
  ]
}
```

### Erro:
```json
{
  "success": false,
  "message": "Erro ao criar despesa(s): ...",
  "error": "Detalhes do erro"
}
```

## Lógica Implementada:

1. **Tipo de Transação:**
   - `amount > 0` = Receita (incoming)
   - `amount < 0` = Despesa (outgoing)

2. **Parcelamento:**
   - Se `is_installment = true` e `installments > 1`:
     - Divide o valor total pelo número de parcelas
     - Cria uma expense para cada parcela
     - Adiciona descrição com "Parcela X/Y"
     - Incrementa a data em 1 mês a cada parcela

3. **À Vista:**
   - Cria uma única expense com os dados fornecidos

## Dependências Necessárias:

Adicione ao requirements.txt:
```
python-dateutil>=2.8.2
```

Instale com:
```bash
pip install python-dateutil
```
