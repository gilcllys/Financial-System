"""
Django settings for financial_system project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# Carregar .env.local (dev) com prioridade sobre .env (produção)
env_local = Path(__file__).resolve().parent.parent.parent / '.env.local'
env_file = Path(__file__).resolve().parent.parent.parent / '.env'

if env_local.exists():
    load_dotenv(env_local)
else:
    load_dotenv(env_file)

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY")

# [SEC-A05] DEBUG padrão False — nunca True em produção sem override explícito
_debug_env = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
_allowed = os.getenv("ALLOWED_HOSTS", "*")
# Segurança: bloqueia DEBUG=True se ALLOWED_HOSTS não for wildcard (produção)
DEBUG = _debug_env if ("*" in _allowed) else False

# [SEC-A05] ALLOWED_HOSTS sem wildcard como padrão; localhost sempre incluído para healthchecks
_hosts_env = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
ALLOWED_HOSTS = list({*_hosts_env, 'localhost', '127.0.0.1'})


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'catalog',
    'cards',
    'expenses',
    'debts',
    'supermarket',
]

MIDDLEWARE = [
    'django.middleware.gzip.GZipMiddleware',          # compressão gzip (deve ser primeiro)
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'financial_system.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'financial_system.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv("DB_NAME"),
        'USER': os.getenv("DB_USERNAME"),
        'PASSWORD': os.getenv("DB_PASSWORD"),
        'HOST': os.getenv("DB_HOST"),
        'PORT': os.getenv("DB_PORT"),
        # Mantém conexões abertas por até N segundos entre requests (evita overhead
        # de TCP handshake por request). Em produção, use valor > 0.
        # 0 = fecha conexão após cada request (padrão Django sem pooling).
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
    }
}

# SSL só em produção (Neon DB exige)
if os.getenv("DB_SSL_MODE", "require") != "disable":
    DATABASES['default']['OPTIONS'] = {
        'sslmode': 'require',
        'channel_binding': 'require',
    }


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise: serve arquivos estáticos comprimidos (gzip + brotli) com hash no nome
# para cache eterno no browser. Requer 'collectstatic' no build.
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Cache — LocMemCache em dev, Redis em prod via env CACHE_BACKEND
# ---------------------------------------------------------------------------
# Para Redis em produção, defina no .env:
#   CACHE_BACKEND=django.core.cache.backends.redis.RedisCache
#   CACHE_LOCATION=redis://redis:6379/1
CACHES = {
    'default': {
        'BACKEND': os.getenv(
            'CACHE_BACKEND',
            'django.core.cache.backends.locmem.LocMemCache',
        ),
        'LOCATION': os.getenv('CACHE_LOCATION', 'financial-cache'),
    }
}

# ---------------------------------------------------------------------------
# Django REST Framework — autenticação via Keycloak
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'financial_system.authentication.KeycloakAuthentication',
    ],
    # [SEC-A07] Rate limiting — proteção contra força bruta e abuso de API
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': os.getenv('THROTTLE_RATE_ANON', '20/minute'),
        'user': os.getenv('THROTTLE_RATE_USER', '200/minute'),
    },
}

# ---------------------------------------------------------------------------
# Keycloak / OIDC
# ---------------------------------------------------------------------------
KEYCLOAK_SERVER_URL = os.getenv("KEYCLOAK_SERVER_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "master")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "financial-backend")
KEYCLOAK_ALGORITHMS = os.getenv("KEYCLOAK_ALGORITHMS", "RS256").split(",")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", None)
KEYCLOAK_VERIFY_SSL = os.getenv("KEYCLOAK_VERIFY_SSL", "True").lower() not in ("false", "0", "no")
# [SEC-A07] Controla se a claim 'aud' do JWT deve ser validada (padrão: True)
# Só desative se o Keycloak não incluir audience no token e não houver alternativa
KEYCLOAK_VERIFY_AUDIENCE = os.getenv("KEYCLOAK_VERIFY_AUDIENCE", "True").lower() not in ("false", "0", "no")

# ---------------------------------------------------------------------------
# CORS — [SEC-A05/A01] NUNCA usar CORS_ALLOW_ALL_ORIGINS=True em produção
# Configure CORS_ALLOWED_ORIGINS no .env com a lista de origens permitidas
# ---------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = False
_raw_cors = os.getenv("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _raw_cors.split(",") if o.strip()]

# ---------------------------------------------------------------------------
# Security Headers — [SEC-A05] Defense-in-depth
# ---------------------------------------------------------------------------
SECURE_BROWSER_XSS_FILTER = True          # X-XSS-Protection: 1; mode=block
SECURE_CONTENT_TYPE_NOSNIFF = True        # X-Content-Type-Options: nosniff
X_FRAME_OPTIONS = 'DENY'                  # Clickjacking protection
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# [SEC-A05] Em produção (DEBUG=False) ativa HSTS e Secure cookies
if not DEBUG:
    SECURE_HSTS_SECONDS = 31_536_000      # 1 ano
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ---------------------------------------------------------------------------
# Logging estruturado — [SEC-A09] Rastreabilidade de erros e eventos de auth
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'financial_system': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}

# ---------------------------------------------------------------------------
# Logging estruturado — saída para stdout (capturado pelo Docker/CloudWatch)
# ---------------------------------------------------------------------------
# Variáveis de ambiente disponíveis:
#   LOG_LEVEL        (default INFO)  — nível raiz da aplicação
#   DJANGO_LOG_LEVEL (default WARNING) — logs internos do Django
#   DB_LOG_LEVEL     (default WARNING) — queries SQL (use DEBUG para debug)
