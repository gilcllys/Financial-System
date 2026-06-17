# Frontend — Financial System SPA

SPA Angular do sistema financeiro pessoal, desenhada com foco **mobile-first**, autenticação via Keycloak e consumo da API Django.

## 📌 Visão geral

O frontend é a camada de experiência do usuário do projeto. Ele entrega:

- visão dos gastos do mês atual;
- histórico completo com busca e paginação;
- cartões de crédito e gastos por cartão;
- categorias personalizadas;
- compras parceladas;
- mercado com itens;
- dashboard de analytics com Chart.js;
- controle de dívidas com a Vitória.

A aplicação usa componentes standalone, lazy loading por rota e autenticação OIDC via `keycloak-js`.

---

## 🧰 Stack tecnológica

| Tecnologia | Versão | Onde aparece |
|---|---:|---|
| Angular | `^17.3.0` | `package.json` |
| Angular CLI | `^17.3.17` | `package.json` |
| TypeScript | `~5.4.2` | `package.json` |
| RxJS | `~7.8.0` | `package.json` |
| Chart.js | `^4.5.1` | `package.json` |
| Keycloak JS | `^24.0.5` | `package.json` |
| Nginx | `1.27-alpine` | `Dockerfile` |
| Node.js | `20-alpine` | `Dockerfile` |

### Padrões usados

- ✅ **Standalone Components**
- ✅ **Signals** (`signal`, `computed`) em telas como gastos, analytics e Vitória
- ✅ **Lazy loading** com `loadComponent`
- ✅ **APP_INITIALIZER** para inicializar autenticação antes da aplicação subir
- ✅ **HTTP Interceptor** para anexar Bearer token
- ✅ **PreloadAllModules** no roteamento

---

## 🗂️ Arquitetura de pastas

```text
src/app/
├── core/          (auth, interceptors, services, models)
├── features/      (telas: expenses, cards, categories, analytics, etc.)
├── layout/        (navbar, bottom nav)
└── shared/        (componentes reutilizáveis)
```

### Detalhamento rápido

- `core/auth/`: integração com Keycloak (`auth.service`, `auth.guard`, `auth.interceptor`)
- `core/services/`: clients HTTP da API
- `core/models/`: contratos TypeScript dos dados
- `features/`: telas lazy-loaded por domínio
- `layout/`: shell da aplicação autenticada
- `shared/`: peças reaproveitáveis de UI

---

## 🧭 Telas disponíveis

| Rota | Componente | Descrição |
|---|---|---|
| `/expenses` | `ExpenseListComponent` | Gastos do mês atual com filtros, busca com debounce e paginação |
| `/history` | `ExpenseListComponent` | Histórico completo, sem aplicar filtro de mês por padrão |
| `/cards` | `CardListComponent` | Lista de cartões de crédito |
| `/cards/:id/expenses` | `CardExpensesComponent` | Gastos vinculados a um cartão específico |
| `/installments` | `InstallmentsComponent` | Agrupa compras parceladas pela descrição `Parcela X/Y` |
| `/categories` | `CategoryListComponent` | Lista e gerenciamento de categorias |
| `/supermarket` | `SupermarketListComponent` | Compras de supermercado |
| `/analytics` | `AnalyticsComponent` | Gráficos mensais, diários, por categoria e por cartão |
| `/vitoria` | `VitoriaComponent` | Dívidas do casal, com marcação de pagamento |

### Outras rotas existentes

- `/expenses/new`
- `/expenses/:id/edit`
- `/cards/new`
- `/cards/:id/edit`
- `/categories/new`
- `/categories/:id/edit`
- `/supermarket/new`
- `/supermarket/:id/edit`
- `/supermarket/:id`
- `/reports`

---

## 🔐 Autenticação

A autenticação é centralizada em `AuthService` e começa antes da app renderizar, via `APP_INITIALIZER` em `app.config.ts`.

### Fluxo atual

1. O Angular cria uma instância do `Keycloak(...)` com dados do `environment`.
2. `auth.init()` roda com:
   - `onLoad: 'check-sso'`
   - `pkceMethod: 'S256'`
   - `checkLoginIframe: false`
   - `silentCheckSsoRedirectUri: window.location.origin + '/silent-check-sso.html'`
3. Se já existir sessão SSO ativa, o token é carregado sem redirecionamento visível.
4. Se não existir sessão, o frontend chama `keycloak.login(...)`.
5. Após autenticar, `scheduleTokenRefresh()` executa `updateToken(60)` a cada **30 segundos**.
6. O interceptor HTTP adiciona `Authorization: Bearer <token>` em toda request autenticada.

### `silent-check-sso.html`

Arquivo mínimo usado pelo Keycloak para o login silencioso:

```html
<script>parent.postMessage(location.href, location.origin);</script>
```

### `auth.guard`

O guard só libera a navegação quando `auth.isAuthenticated` é verdadeiro. Caso contrário, redireciona para `/`, o que dispara o fluxo de autenticação novamente.

### Interceptor

```ts
const cloned = req.clone({
  headers: req.headers.set('Authorization', `Bearer ${token}`),
});
```

---

## 🔌 Serviços

Todos os serviços usam `HttpClient` e constroem URLs a partir de `environment.apiBaseUrl`.

### `expense.service.ts`
Base: `http://localhost:8000/api/expenses/expenses`

Métodos principais:

- `list(filters)` → lista paginada com filtros
- `listByCard(cardId)` → gastos de um cartão
- `get(id)` → detalhe
- `create(payload)` → usa `/create-expense/`
- `update(id, payload)` → PUT
- `delete(id)` → DELETE

#### Função `normalize()`

```ts
function normalize(raw: any): Expense {
  return {
    ...raw,
    category_id: raw.category_id ?? raw.category,
    amount: parseFloat(raw.amount),
  };
}
```

Ela resolve duas diferenças comuns entre backend e frontend:

- garante `category_id` mesmo que a API retorne `category`;
- converte `amount` de string/decimal serializado para `number`.

### `card.service.ts`
Base: `/api/cards/credit-cards`

- CRUD simples de cartões.

### `category.service.ts`
Base: `/api/catalog/categories`

- lista categorias do sistema e do usuário;
- cria, atualiza e remove categorias customizadas.

### `debt.service.ts`
Base: `/api/debts/vitoria-debts`

- `list()` → lista dívidas;
- `summary()` → resumo agregado;
- `markPaid(id)` → POST em `/{id}/mark-paid/`.

### `analytics.service.ts`
Base: `/api/expenses/expenses/analytics`

- `monthly(year)`
- `byCategory(month, year)`
- `byCard(month, year)`
- `daily(month, year)`

### `supermarket.service.ts`
Bases:

- `/api/supermarket/supermarket-expenses`
- `/api/supermarket/supermarket-expense-items`

Possui `normalizeExpense()` e `normalizeItem()` para:

- converter `unit_price` e `total` para `number`;
- garantir `items` como array;
- suportar resposta paginada ou array simples em `list()`.

---

## 🎨 Design system

O design system está dividido em:

- `src/styles/_tokens.scss`
- `src/styles/_base.scss`
- `src/styles/_components.scss`

### Tokens CSS

Exemplos relevantes:

- cor primária: `--color-primary: #0052ff`
- sucesso: `--color-semantic-up: #05b169`
- erro/despesa: `--color-semantic-down: #cf202f`
- tipografia principal: `Inter`
- tipografia numérica: `JetBrains Mono`
- spacing em escala de 4px
- border radius padronizado
- alturas de navegação:
  - `--navbar-h: 64px`
  - `--bottom-nav-h: 64px`

### Estilo visual

O tema tem cara **Coinbase-inspired**:

- azul forte como cor de ação;
- superfícies claras e limpas;
- ênfase em números financeiros com fonte mono;
- badges semânticas para alta/baixa;
- cards arredondados com sombra leve.

### Responsividade mobile-first

O CSS mostra isso claramente:

- layout base pensado para telas pequenas;
- FAB visível no mobile e escondido no desktop;
- breakpoints em `640px` e `1024px`;
- `page-content` considera navbar + bottom nav;
- formulários e tabelas adaptáveis.

---

## 📊 Comportamento das telas importantes

### `/expenses`
- usa Signals para estado local;
- aplica filtro do mês atual por padrão;
- busca com `debounceTime(400)`;
- suporta paginação por `page` e `page_size`.

### `/history`
- reutiliza o mesmo componente de gastos;
- recebe `data: { historyMode: true }` na rota;
- desativa o filtro de mês automático.

### `/installments`
- identifica parcelamentos por regex em `description`;
- agrupa descrições como `Parcela 3/12`;
- calcula progresso e total por compra parcelada.

### `/analytics`
- carrega quatro fontes de dados paralelas;
- renderiza gráficos `bar`, `doughnut` e `line` com Chart.js;
- usa Signals para ano, mês e datasets.

### `/vitoria`
- exibe pendentes e pagos;
- atualiza resumo local após `markPaid()` sem recarregar a tela inteira.

---

## 🐳 Build e deploy

### Docker multi-stage

O `Dockerfile` do frontend tem duas etapas:

1. **builder**
   - imagem `node:20-alpine`
   - `npm ci`
   - `npm run build`

2. **runtime**
   - imagem `nginx:1.27-alpine`
   - copia `dist/financial-frontend/browser`
   - usa `nginx.conf` customizado

### Nginx SPA config

O `nginx.conf` implementa:

- fallback SPA com `try_files $uri $uri/ /index.html;`
- headers de segurança;
- `Content-Security-Policy` com `connect-src` liberando backend e Keycloak;
- `frame-src`/`frame-ancestors` para o `silent-check-sso.html`;
- cache longo para assets com hash;
- `no-store` para `index.html`.

### Exemplo de build local

```bash
cd frontend
npm ci
npm run build
```

---

## 🔧 Variáveis de ambiente / configuração

O frontend, no estado atual, usa **configuração estática de build** em `src/environments/environment.ts`.

```ts
export const environment = {
  production: true,
  apiBaseUrl: 'http://localhost:8000',
  keycloak: {
    url: 'https://ec2-54-147-150-5.compute-1.amazonaws.com',
    realm: 'projetos-pessoais',
    clientId: 'financial-frontend',
  },
};
```

### Campos

| Campo | Valor atual | Uso |
|---|---|---|
| `production` | `true` | Flag de ambiente no build atual |
| `apiBaseUrl` | `http://localhost:8000` | Base da API consumida pelos services |
| `keycloak.url` | `https://ec2-54-147-150-5.compute-1.amazonaws.com` | URL do provedor OIDC |
| `keycloak.realm` | `projetos-pessoais` | Realm usado no login |
| `keycloak.clientId` | `financial-frontend` | Cliente público do SPA |

> Se mudar backend ou Keycloak, é preciso **alterar o arquivo e rebuildar a imagem**.

---

## 🚀 Rodando localmente

### Com Docker Compose

Na raiz do repositório:

```bash
docker compose up --build
```

A SPA ficará em:

```text
http://localhost:4200
```

### Sem Docker

```bash
cd frontend
npm ci
npm start
```

---

## 📝 Observações finais

- A autenticação depende de um Keycloak externo disponível.
- O frontend já está preparado para silent SSO via iframe.
- A rota `/reports` existe no roteamento, mas as rotas mais maduras hoje são `expenses`, `analytics`, `cards`, `supermarket` e `vitoria`.
