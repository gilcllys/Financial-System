# Backend — Financial System API

API REST do sistema financeiro pessoal, construída com Django + Django REST Framework, com autenticação via Keycloak e isolamento de dados por `tenant_id`.

## 📌 Visão geral

Este backend centraliza a regra de negócio do projeto:

- cadastro e consulta de gastos;
- compras parceladas;
- gastos repetidos por quantidade;
- cartões de crédito;
- categorias personalizadas;
- dívidas com a Vitória;
- compras de supermercado com itens;
- analytics mensais, diários, por categoria e por cartão.

A aplicação roda sobre PostgreSQL e expõe endpoints REST autenticados por Bearer token JWT.

---

## 🧰 Stack tecnológica

### Runtime e framework

| Tecnologia | Versão | Onde aparece |
|---|---:|---|
| Python | 3.10 | `backend/Dockerfile` |
| Django | 5.2.7 | `requirements.txt` |
| Django REST Framework | 3.16.1 | `requirements.txt` |
| PostgreSQL | 16 (imagem Docker) | `docker-compose.yml` |
| Gunicorn | 23.0.0 | `requirements.txt` + `entrypoint.sh` |

### Bibliotecas relevantes

| Biblioteca | Versão |
|---|---:|
| `django-cors-headers` | 4.9.0 |
| `PyJWT` | 2.10.1 |
| `requests` | 2.32.3 |
| `python-dotenv` | 1.2.1 |
| `psycopg2-binary` | 2.9.11 |
| `whitenoise` | `>=6.0.0,<7.0.0` |
| `cryptography` | `>=41.0.0,<45.0.0` |
| `drf-yasg` | 1.21.11 |

---

## 🏗️ Arquitetura de módulos

Os apps Django registrados em `INSTALLED_APPS` são:

### `expenses`
Responsável pelo núcleo financeiro.

- tabela `expenses`;
- CRUD de gastos;
- filtro por mês, ano, categoria, método de pagamento e busca textual;
- criação especial via `CreateExpenseBehavior`;
- compras parceladas (`is_installment=True`);
- criação em lote quando `quantity > 1`;
- analytics:
  - mensal;
  - por categoria;
  - por cartão;
  - diário.

### `cards`
Gerencia cartões de crédito.

- tabela `credit_cards`;
- nome do cartão;
- dia do vencimento;
- melhor dia de compra;
- últimos 4 dígitos;
- relacionamento com gastos pagos no cartão.

### `catalog`
Catálogo de categorias de despesas.

- tabela `expense_categories`;
- categorias do sistema (`tenant_id = 'system'`) + categorias do usuário;
- CRUD para categorias customizadas.

### `debts`
Controla dívidas relacionadas à Vitória.

- tabela `vitoria_debts`;
- cada dívida aponta para uma `Expense`;
- flag `is_paid`;
- resumo consolidado de pendências/pagas;
- ação para marcar dívida como paga.

### `supermarket`
Modela compras de supermercado em dois níveis.

- `supermarket_expenses`: compra principal (mercado, data, endereço);
- `supermarket_expense_items`: itens da compra (descrição, quantidade, preço unitário);
- serializer calcula `total` somando os itens carregados via `prefetch_related('items')`.

---

## 🔐 Sistema de autenticação

A autenticação é feita por `financial_system.authentication.KeycloakAuthentication`.

### Fluxo

1. O frontend envia `Authorization: Bearer <token>`.
2. O backend extrai o JWT.
3. Há dois caminhos possíveis:
   - **com `KEYCLOAK_CLIENT_SECRET`**: usa **introspection** no Keycloak;
   - **sem `KEYCLOAK_CLIENT_SECRET`**: usa validação **offline via JWKS**.

### Validação via JWKS

O backend busca as chaves públicas em:

```text
{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs
```

As chaves são cacheadas por **3600 segundos** (`JWKS_CACHE_TTL = 3600`).

Na decodificação do JWT, o backend valida:

- **assinatura RSA** usando `RSAAlgorithm.from_jwk(...)`;
- **expiração** (`exp`);
- **audience** (`aud`) contra `KEYCLOAK_CLIENT_ID`, se `KEYCLOAK_VERIFY_AUDIENCE=True`;
- **issuer** (`iss`) contra:

```text
{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}
```

### Validação via introspection

Quando o cliente é confidential:

```text
POST /realms/{realm}/protocol/openid-connect/token/introspect
```

com autenticação Basic usando:

- `KEYCLOAK_CLIENT_ID`
- `KEYCLOAK_CLIENT_SECRET`

Mesmo nesse fluxo, o backend ainda valida o `iss` retornado.

### Objeto autenticado

O usuário autenticado não é persistido em tabela local. O backend cria um objeto leve `KeycloakPrincipal` com claims do token:

- `tenant_id` ← claim `sub`
- `email`
- `first_name`
- `last_name`

---

## 🧩 Multi-tenancy

O sistema implementa multi-tenancy lógico por linha usando `tenant_id`.

### Como funciona

- `tenant_id` recebe o valor da claim `sub` do token Keycloak.
- Esse valor é salvo nos modelos principais.
- Cada `get_queryset()` filtra por `self.request.user.tenant_id`.
- `perform_create()` e `perform_update()` reinjetam o `tenant_id` autenticado.
- `perform_destroy()` faz checagem explícita de ownership antes de excluir.

### Exemplo real

```python
models.Expense.objects.filter(tenant_id=self.request.user.tenant_id)
```

### Benefício

Mesmo em um único banco PostgreSQL, cada usuário só enxerga seus próprios dados.

---

## 🌐 Endpoints principais

> Base URL local: `http://localhost:8000`

### `expenses`

| Método | URL | Descrição |
|---|---|---|
| GET | `/api/expenses/expenses/` | Lista paginada de gastos com filtros `month`, `year`, `category_id`, `payment_method`, `search`, `page`, `page_size` |
| POST | `/api/expenses/expenses/` | Cria gasto simples via CRUD padrão do `ModelViewSet` |
| GET | `/api/expenses/expenses/{id}/` | Detalha um gasto |
| PUT/PATCH | `/api/expenses/expenses/{id}/` | Atualiza um gasto |
| DELETE | `/api/expenses/expenses/{id}/` | Remove um gasto do tenant autenticado |
| GET | `/api/expenses/expenses/per-credit-card/{card_id}/` | Lista todos os gastos de um cartão, sem paginação |
| GET | `/api/expenses/expenses/analytics/monthly/?year=2026` | Totais por mês |
| GET | `/api/expenses/expenses/analytics/by-category/?month=6&year=2026` | Totais por categoria |
| GET | `/api/expenses/expenses/analytics/by-card/?month=6&year=2026` | Totais por cartão |
| GET | `/api/expenses/expenses/analytics/daily/?month=6&year=2026` | Totais diários do mês |
| POST | `/api/expenses/expenses/create-expense/` | Rota customizada esperada pelo frontend para parcelamentos e criação múltipla |

### `cards`

| Método | URL | Descrição |
|---|---|---|
| GET | `/api/cards/credit-cards/` | Lista cartões do tenant |
| POST | `/api/cards/credit-cards/` | Cria cartão |
| GET | `/api/cards/credit-cards/{id}/` | Detalha cartão |
| PUT/PATCH | `/api/cards/credit-cards/{id}/` | Atualiza cartão |
| DELETE | `/api/cards/credit-cards/{id}/` | Exclui cartão |

### `catalog`

| Método | URL | Descrição |
|---|---|---|
| GET | `/api/catalog/categories/` | Lista categorias do sistema + do usuário |
| POST | `/api/catalog/categories/` | Cria categoria customizada |
| GET | `/api/catalog/categories/{id}/` | Detalha categoria |
| PUT/PATCH | `/api/catalog/categories/{id}/` | Atualiza categoria |
| DELETE | `/api/catalog/categories/{id}/` | Remove categoria do tenant |

### `debts`

| Método | URL | Descrição |
|---|---|---|
| GET | `/api/debts/vitoria-debts/` | Lista dívidas com dados inline da despesa vinculada |
| POST | `/api/debts/vitoria-debts/` | Cria dívida vinculando uma `Expense` |
| GET | `/api/debts/vitoria-debts/{id}/` | Detalha dívida |
| PUT/PATCH | `/api/debts/vitoria-debts/{id}/` | Atualiza dívida |
| DELETE | `/api/debts/vitoria-debts/{id}/` | Exclui dívida |
| GET | `/api/debts/vitoria-debts/summary/` | Resumo de pendentes/pagas |
| POST | `/api/debts/vitoria-debts/{id}/mark-paid/` | Marca uma dívida como paga |

### `supermarket`

| Método | URL | Descrição |
|---|---|---|
| GET | `/api/supermarket/supermarket-expenses/` | Lista compras de supermercado com itens |
| POST | `/api/supermarket/supermarket-expenses/` | Cria compra principal |
| GET | `/api/supermarket/supermarket-expenses/{id}/` | Detalha compra |
| PUT/PATCH | `/api/supermarket/supermarket-expenses/{id}/` | Atualiza compra |
| DELETE | `/api/supermarket/supermarket-expenses/{id}/` | Exclui compra |
| GET | `/api/supermarket/supermarket-expense-items/` | Lista itens do tenant |
| POST | `/api/supermarket/supermarket-expense-items/` | Cria item vinculado a uma compra |
| GET | `/api/supermarket/supermarket-expense-items/{id}/` | Detalha item |
| PUT/PATCH | `/api/supermarket/supermarket-expense-items/{id}/` | Atualiza item |
| DELETE | `/api/supermarket/supermarket-expense-items/{id}/` | Exclui item |

### ⚠️ Observação importante sobre custom actions

Ao inspecionar as rotas geradas pelo DRF, o código atual registra:

- `/api/expenses/expenses/create-expense/` → ligado ao método `perform_destroy`
- `/api/debts/vitoria-debts/summary/` → ligado ao método `perform_destroy`

Ou seja: a **regra de negócio existe** (`create_expense()` e `summary()` estão implementados), mas as decorators `@action(...)` foram posicionadas acima de `perform_destroy`. Para manutenção futura, vale revisar esse ponto antes de confiar nesses dois endpoints em produção.

---

## 🧠 Regras de negócio importantes

### 1) Criação de gastos parcelados (`installments`)

A lógica está em `expenses.behaviors.CreateExpenseBehavior`.

Payload típico:

```json
{
  "category_id": 3,
  "description": "Notebook",
  "amount": -3600.00,
  "date": "2026-06-17",
  "payment_method": "cartao",
  "credit_card_id": 2,
  "is_installment": true,
  "installments": 12,
  "need_pay_vitoria": false
}
```

Com `is_installment=true` e `installments > 1`:

- `quantity` é ignorado;
- o valor é dividido por `installments`;
- o backend cria **N registros independentes**;
- a descrição vira `"Notebook - Parcela 1/12"`, `"Notebook - Parcela 2/12"` etc.;
- cada parcela avança `+1 mês` usando `relativedelta(months=1)`.

### 2) Criação de gastos com `quantity > 1`

Quando `quantity > 1` e **não** é parcelado:

- o backend cria **N linhas iguais**;
- cada linha preserva o mesmo valor, descrição e data;
- a resposta informa `quantity` e `total_amount = amount * quantity`.

### 3) Dívida com a Vitória

Se `need_pay_vitoria=True`:

- a cada `Expense` criada, o backend cria uma `VitoriaDebt` relacionada;
- isso acontece tanto em gasto simples quanto em múltiplos ou parcelados.

### 4) Analytics

Os endpoints de analytics usam agregações no banco com `Sum`, `Count`, `Abs` e `ExtractMonth`:

- **monthly**: receitas, despesas, saldo e volume por mês;
- **by-category**: total e percentual por categoria;
- **by-card**: total e percentual por cartão;
- **daily**: movimento diário, preenchendo dias sem lançamento com zero.

---

## ⚡ Performance

Há várias otimizações explícitas no código:

- `select_related('category', 'credit_card')` em `expenses` para evitar N+1;
- `select_related('expense', 'expense__category')` em `debts`;
- `prefetch_related('items')` em `supermarket`;
- `GZipMiddleware` em primeiro lugar na cadeia de middleware;
- paginação padrão no endpoint de gastos:
  - `page_size = 20`
  - `max_page_size = 100`
- `CONN_MAX_AGE` configurável via `DB_CONN_MAX_AGE` (default `60`);
- índices compostos em `expenses`:
  - `tenant_id + date`
  - `tenant_id + credit_card`
- cache local/Redis para JWKS.

---

## 🛡️ Segurança

Medidas visíveis no código alinhadas a problemas clássicos do OWASP Top 10:

### Controle de acesso / IDOR
- filtros por `tenant_id` em todos os `get_queryset()`;
- `perform_destroy()` com ownership check;
- validação extra de ownership em FKs sensíveis:
  - `debts` valida se a `Expense` pertence ao tenant;
  - `supermarket items` validam se o parent pertence ao tenant.

### Configuração segura
- `DEBUG=False` por padrão;
- `ALLOWED_HOSTS` explícito;
- `CORS_ALLOW_ALL_ORIGINS = False`;
- security headers (`X-Frame-Options`, `nosniff`, HSTS, referrer policy);
- cookies `Secure` quando `DEBUG=False`.

### Autenticação robusta
- validação de `iss`;
- validação de `aud` por padrão;
- rejeição de token expirado ou revogado;
- cache JWKS com refresh em rotação de chave.

### Hardening de API
- throttle do DRF:
  - anônimo: `20/minute`
  - autenticado: `200/minute`
- busca textual limitada a 200 caracteres para reduzir abuso;
- mensagens de erro de autenticação não expõem detalhes internos.

### Supply chain / dependências
- versões pinadas em `requirements.txt`;
- upper bounds em bibliotecas sensíveis (`cryptography`, `whitenoise`, `dj-database-url`).

---

## 🚀 Como rodar localmente

### Opção A — com Docker

Na raiz do projeto:

```bash
cp backend/.env.example backend/.env
# edite backend/.env

docker compose up --build
```

Serviços:

- frontend: `http://localhost:4200`
- backend: `http://localhost:8000`
- banco: rede interna Docker

### Opção B — sem Docker (venv)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env.local
# edite .env.local

cd financial_system
python manage.py migrate
python manage.py runserver
```

> O `settings.py` carrega `.env.local` com prioridade sobre `.env`.

---

## 🐳 Execução em containers

### `entrypoint.sh`
Ao iniciar o container do backend:

1. entra em `/app/financial_system`;
2. roda `python manage.py migrate --noinput`;
3. sobe Gunicorn em `0.0.0.0:8000`.

### Gunicorn
Configuração atual:

- `--workers ${GUNICORN_WORKERS:-3}`
- `--worker-class sync`
- `--worker-connections 1000`
- `--timeout 30`
- `--keep-alive 5`
- `--max-requests 1000`
- `--max-requests-jitter 100`

---

## 🔧 Variáveis de ambiente

| Variável | Default | Descrição |
|---|---|---|
| `SECRET_KEY` | sem default | Chave secreta do Django |
| `DEBUG` | `False` | Liga/desliga modo debug; em produção é forçado para `False` se `ALLOWED_HOSTS` não tiver `*` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hosts permitidos |
| `DB_NAME` | sem default | Nome do banco |
| `DB_USERNAME` | sem default | Usuário do banco |
| `DB_PASSWORD` | sem default | Senha do banco |
| `DB_HOST` | sem default | Host do banco |
| `DB_PORT` | sem default | Porta do banco |
| `DB_CONN_MAX_AGE` | `60` | Reuso de conexões do Django |
| `DB_SSL_MODE` | `require` | Se diferente de `disable`, ativa `sslmode=require` |
| `CACHE_BACKEND` | `django.core.cache.backends.locmem.LocMemCache` | Backend de cache |
| `CACHE_LOCATION` | `financial-cache` | Namespace/localização do cache |
| `THROTTLE_RATE_ANON` | `20/minute` | Rate limit para anônimos |
| `THROTTLE_RATE_USER` | `200/minute` | Rate limit para autenticados |
| `KEYCLOAK_SERVER_URL` | `http://localhost:8080` | Base URL do Keycloak |
| `KEYCLOAK_REALM` | `master` | Realm do Keycloak |
| `KEYCLOAK_CLIENT_ID` | `financial-backend` | Audience/cliente esperado pelo backend |
| `KEYCLOAK_CLIENT_SECRET` | `None` | Ativa fluxo de introspection quando definido |
| `KEYCLOAK_ALGORITHMS` | `RS256` | Algoritmos aceitos para JWT |
| `KEYCLOAK_VERIFY_SSL` | `True` | Verifica TLS ao chamar Keycloak |
| `KEYCLOAK_VERIFY_AUDIENCE` | `True` | Valida a claim `aud` |
| `CORS_ALLOWED_ORIGINS` | vazio | Lista CSV de origens permitidas |
| `DJANGO_LOG_LEVEL` | `INFO` | Nível de log usado nos loggers `django` e `financial_system` |
| `GUNICORN_WORKERS` | `3` | Quantidade de workers no container |

### Exemplo mínimo de `.env.local`

```env
SECRET_KEY=change-me
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=financial_db
DB_USERNAME=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
DB_SSL_MODE=disable
KEYCLOAK_SERVER_URL=https://ec2-54-147-150-5.compute-1.amazonaws.com
KEYCLOAK_REALM=projetos-pessoais
KEYCLOAK_CLIENT_ID=financial-frontend
KEYCLOAK_VERIFY_SSL=True
KEYCLOAK_VERIFY_AUDIENCE=True
CORS_ALLOWED_ORIGINS=http://localhost:4200
```

---

## 📝 Observações finais

- O backend assume autenticação obrigatória em toda a API (`IsAuthenticated`).
- O frontend atual aponta para o backend em `http://localhost:8000`.
- Para produção, vale revisar principalmente os endpoints customizados de `expenses` e `debts` por causa do posicionamento das decorators.
