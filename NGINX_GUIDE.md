# 📖 Guia de Referência — Nginx

## 1. O que é e como funciona

Nginx é um **servidor web / proxy reverso** de alta performance. Diferente do Apache (que cria uma thread por conexão), o Nginx usa um modelo **event-driven assíncrono** — um processo consegue lidar com milhares de conexões simultâneas com baixo consumo de memória.

```
Cliente (Browser)
      │
      ▼
  [ Nginx ]  ← ponto único de entrada
      │
      ├──► Serve arquivos estáticos direto do disco (rápido)
      ├──► Proxy para backend (Django, Node, etc.)
      ├──► Termina SSL/TLS
      └──► Redireciona HTTP → HTTPS
```

---

## 2. Estrutura de arquivos (instalação padrão)

```
/etc/nginx/
├── nginx.conf              ← config principal (global)
├── sites-available/        ← configs dos sites (desativados)
│   └── meu-site.conf
├── sites-enabled/          ← symlinks dos sites ativos
│   └── meu-site.conf → ../sites-available/meu-site.conf
├── conf.d/                 ← configs extras carregadas automaticamente
└── snippets/               ← trechos reutilizáveis (SSL, etc.)
```

```bash
# Ativar site
ln -sf /etc/nginx/sites-available/meu-site.conf /etc/nginx/sites-enabled/

# Desativar site
rm /etc/nginx/sites-enabled/meu-site.conf

# Validar config antes de aplicar (SEMPRE faça isso!)
nginx -t

# Recarregar sem derrubar conexões
systemctl reload nginx
```

---

## 3. Hierarquia de blocos (sintaxe)

```nginx
# ── Contexto: main (global) ──────────────────────────────
worker_processes auto;          # qtd de processos worker

events {                        # ── Contexto: events ──
    worker_connections 1024;    # conexões por worker
}

http {                          # ── Contexto: http ──
    include mime.types;

    server {                    # ── Contexto: server (virtual host) ──
        listen 80;
        server_name meusite.com;

        location / {            # ── Contexto: location (rota) ──
            root /var/www/html;
            index index.html;
        }
    }
}
```

> **Regra:** diretivas de um contexto **não funcionam em outro**.
> - `root` → funciona em `server` e `location`
> - `listen` → só funciona em `server`
> - `proxy_pass` → só funciona em `location`

---

## 4. Diretivas essenciais

### `listen` — porta e protocolo
```nginx
listen 80;            # HTTP
listen 443 ssl;       # HTTPS
listen [::]:80;       # IPv6
```

### `server_name` — qual domínio/host atende
```nginx
server_name meusite.com www.meusite.com;
server_name _;   # curinga — pega qualquer host
```

### `root` vs `alias` — onde estão os arquivos
```nginx
# root: concatena root + URI
location /static/ {
    root /var/www;          # serve /var/www/static/arquivo.js
}

# alias: substitui o prefixo do location pelo path
location /static/ {
    alias /var/www/assets/; # serve /var/www/assets/arquivo.js
}
```

### `try_files` — tenta caminhos em ordem
```nginx
# Angular/React SPA: tenta o arquivo, depois diretório, senão index.html
location / {
    try_files $uri $uri/ /index.html;
}
# $uri        → tenta o arquivo exato (ex: /logo.png)
# $uri/       → tenta como diretório
# /index.html → fallback para o SPA
```

### `location` — matching de rotas

```nginx
location = /healthz        { return 200 "ok"; }      # Exato
location ^~ /static/       { root /var/www; }         # Prefixo prioritário
location ~ \.php$           { fastcgi_pass ...; }      # Regex case-sensitive
location ~* \.(jpg|png)$    { expires 30d; }           # Regex case-insensitive
location /                  { try_files $uri /index.html; } # Prefixo simples
```

**Ordem de precedência:** `=` → `^~` → `~` / `~*` → prefixo simples

---

## 5. Proxy reverso

```nginx
location /api/ {
    proxy_pass         http://localhost:8000/;
    proxy_http_version 1.1;

    # Headers obrigatórios para o backend saber o IP real
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_connect_timeout 60s;
    proxy_read_timeout    60s;
}
```

> ⚠️ **`proxy_pass` com barra vs sem barra:**
> ```nginx
> proxy_pass http://localhost:8000/;  # /api/users → :8000/users      (remove /api)
> proxy_pass http://localhost:8000;   # /api/users → :8000/api/users  (mantém /api)
> ```

---

## 6. SSL / TLS

```nginx
server {
    listen 443 ssl;
    server_name meusite.com;

    ssl_certificate     /etc/ssl/certs/fullchain.pem;
    ssl_certificate_key /etc/ssl/private/privkey.pem;

    ssl_protocols     TLSv1.2 TLSv1.3;
    ssl_ciphers       HIGH:!aNULL:!MD5;
    ssl_session_cache shared:SSL:10m;
}

# Forçar HTTPS
server {
    listen 80;
    server_name meusite.com;
    return 301 https://$host$request_uri;
}
```

---

## 7. Cache de assets estáticos

```nginx
# Cache longo para arquivos com hash no nome (JS, CSS, imagens)
location ~* \.(js|css|woff2?|png|jpg|svg|ico)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}

# Sem cache para index.html (SPA precisa buscar versão nova)
location = /index.html {
    add_header Cache-Control "no-store, no-cache, must-revalidate";
}
```

---

## 8. Headers de segurança

```nginx
server_tokens off;  # Esconde a versão do Nginx nas respostas de erro

add_header X-Content-Type-Options    "nosniff"                             always;
add_header X-Frame-Options           "DENY"                                always;
add_header X-XSS-Protection          "1; mode=block"                       always;
add_header Referrer-Policy           "strict-origin-when-cross-origin"     always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

# Content Security Policy — controla o que o browser pode carregar
add_header Content-Security-Policy
  "default-src 'self';
   script-src  'self' 'unsafe-inline';
   style-src   'self' 'unsafe-inline';
   img-src     'self' data:;
   connect-src 'self' https://minha-api.com;"
  always;
```

---

## 9. Variáveis internas úteis

| Variável | Valor |
|---|---|
| `$host` | Header `Host` da requisição |
| `$uri` | Caminho da URL (sem query string) |
| `$args` | Query string (`?foo=bar`) |
| `$remote_addr` | IP do cliente |
| `$scheme` | `http` ou `https` |
| `$request_method` | `GET`, `POST`, etc. |
| `$server_port` | Porta onde o servidor está ouvindo |
| `$proxy_add_x_forwarded_for` | IP chain para proxy |
| `$request_uri` | URI completa (com query string) |

---

## 10. Arquitetura deste projeto no EC2

```
Internet
  │
  ├─ :80   → Nginx (host EC2) → redirect 301 HTTPS
  ├─ :443  → Nginx → Keycloak (IAM)      → localhost:8080  (Docker)
  └─ :4200 → Nginx → /api/*              → Django/Gunicorn → localhost:8000  (Docker)
                   → /*                  → Angular/Nginx   → localhost:3000  (Docker)
```

O **Nginx roda direto no host EC2** (não em Docker) e age como proxy reverso único para os dois projetos rodando na mesma máquina.

**Certificados SSL** ficam no projeto IAM:
```
/home/ubuntu/identity-and-access-management/certs/fullchain.pem
/home/ubuntu/identity-and-access-management/certs/privkey.pem
```

**Config do Nginx** em:
```
/etc/nginx/sites-available/projetos-pessoais   ← arquivo
/etc/nginx/sites-enabled/projetos-pessoais     ← symlink ativando
```

### Exemplo da config (simplificado)

```nginx
# :80 → força HTTPS
server {
    listen 80;
    return 301 https://$host$request_uri;
}

# :4200 → Financial System
server {
    listen 4200 ssl;
    server_name ec2-54-147-150-5.compute-1.amazonaws.com;

    ssl_certificate     /home/ubuntu/.../certs/fullchain.pem;
    ssl_certificate_key /home/ubuntu/.../certs/privkey.pem;

    # Backend Django (Docker porta 8000)
    location /api/ {
        proxy_pass         http://localhost:8000/;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    # Frontend Angular (Docker porta 3000)
    location / {
        proxy_pass http://localhost:3000;
    }
}

# :443 → Keycloak
server {
    listen 443 ssl;
    location / {
        proxy_pass http://localhost:8080;
    }
}
```

---

## 11. Comandos do dia a dia

```bash
nginx -t                       # Valida a config (SEMPRE antes de reload!)
nginx -T                       # Mostra config completa compilada
systemctl reload nginx         # Aplica mudanças SEM derrubar conexões ativas
systemctl restart nginx        # Reinicia (derruba conexões ativas)
systemctl status nginx         # Verifica se está rodando
systemctl enable nginx         # Inicia automaticamente com o servidor

# Logs em tempo real
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# Testar headers de fora
curl -I https://meusite.com
curl -v https://meusite.com/api/
```

---

> 💡 **Regra de ouro:** sempre rode `nginx -t` antes de `systemctl reload`.
> Um erro de sintaxe com `restart` pode derrubar o servidor sem conseguir subir de volta.
