# Configuração de Environment

## Arquivos de Environment

O projeto utiliza diferentes arquivos de environment para desenvolvimento e produção:

- **`src/environments/environment.development.ts`**: Usado durante o desenvolvimento (`npm run start`)
- **`src/environments/environment.ts`**: Usado em produção (`npm run build`)

## Configuração da API

A URL da API backend está configurada nos arquivos de environment:

```typescript
export const environment = {
  production: false, // ou true para produção
  apiUrl: 'https://financial-backend-gilcllys.fly.dev'
};
```

### Desenvolvimento Local

Se você estiver rodando o backend localmente, altere a URL em `environment.development.ts`:

```typescript
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000'
};
```

## Como usar

O arquivo `src/app/utils/constants.ts` importa automaticamente a configuração do environment:

```typescript
import { environment } from '../../environments/environment.development';

export const API_BASE_URL = environment.apiUrl;
```

Todos os serviços que fazem chamadas à API usam `API_BASE_URL` como base URL.

## Endpoints disponíveis

Baseado na API fornecida:

- **POST** `/api/register/` - Registro de usuário
- **POST** `/api/login/` - Login de usuário  
- **POST** `/api/logout/` - Logout de usuário
- **POST** `/api/token/refresh/` - Refresh do token
- **GET** `/api/auth/profile/user/` - Perfil do usuário
- **GET/POST** `/api/auth/cost/expense/` - Gestão de despesas
- **GET** `/api/auth/cost/expense_category/` - Categorias de despesas
- **GET** `/api/auth/cost/supermach_expense/` - Supermercado despesas
- **GET** `/api/auth/cost/supermach_expense_item/` - Items de despesas de supermercado

## Autenticação

O projeto usa JWT (JSON Web Tokens) para autenticação:

1. Após o login bem-sucedido, os tokens são armazenados no `localStorage`:
   - `access_token`: Token de acesso
   - `refresh_token`: Token para renovação
   - `user`: Dados do usuário

2. O `AuthService` gerencia automaticamente o estado de autenticação usando signals Angular.

3. Todas as requisições autenticadas devem incluir o token no header `Authorization: Bearer <token>`.
