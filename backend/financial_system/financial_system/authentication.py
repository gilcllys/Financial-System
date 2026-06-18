import datetime
import json
import logging

import jwt
import requests
from django.conf import settings
from django.core.cache import cache
from jwt.algorithms import RSAAlgorithm
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)

JWKS_CACHE_KEY = 'keycloak_jwks'
JWKS_CACHE_TTL = 3600  # 1 hora


class KeycloakPrincipal:
    """
    Representa o usuário autenticado pelo Keycloak.

    Objeto leve, sem persistência em banco — carrega apenas os claims
    do token JWT. Compatível com DRF (IsAuthenticated verifica is_authenticated).
    """

    is_anonymous = False
    is_active = True

    def __init__(self, payload: dict):
        self.tenant_id: str = payload.get('sub', '')
        self.email: str = payload.get('email', '')
        self.first_name: str = payload.get('given_name', '')
        self.last_name: str = payload.get('family_name', '')

    @property
    def is_authenticated(self):
        return bool(self.tenant_id)

    @property
    def pk(self):
        return self.tenant_id

    def __str__(self):
        return self.tenant_id


def _fetch_jwks():
    jwks_url = (
        f"{settings.KEYCLOAK_SERVER_URL}"
        f"/realms/{settings.KEYCLOAK_REALM}"
        f"/protocol/openid-connect/certs"
    )
    try:
        response = requests.get(jwks_url, timeout=5, verify=settings.KEYCLOAK_VERIFY_SSL)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error("Falha ao buscar JWKS do Keycloak: %s", e)
        raise AuthenticationFailed(
            "Não foi possível validar as credenciais de autenticação."
        )


def get_keycloak_jwks():
    cached = cache.get(JWKS_CACHE_KEY)
    if cached:
        return cached
    jwks = _fetch_jwks()
    cache.set(JWKS_CACHE_KEY, jwks, JWKS_CACHE_TTL)
    return jwks


def _introspect_token(token: str) -> dict:
    """
    Valida o token via endpoint de introspection do Keycloak.

    Usado quando o cliente é confidential (private) — autentica com
    client_id + client_secret, garantindo que tokens revogados sejam rejeitados.
    """
    introspect_url = (
        f"{settings.KEYCLOAK_SERVER_URL}"
        f"/realms/{settings.KEYCLOAK_REALM}"
        f"/protocol/openid-connect/token/introspect"
    )
    try:
        response = requests.post(
            introspect_url,
            data={'token': token},
            auth=(settings.KEYCLOAK_CLIENT_ID, settings.KEYCLOAK_CLIENT_SECRET),
            verify=settings.KEYCLOAK_VERIFY_SSL,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error("Falha ao chamar introspection do Keycloak: %s", e)
        raise AuthenticationFailed(
            "Não foi possível validar as credenciais de autenticação."
        )


class KeycloakAuthentication(BaseAuthentication):
    """
    Autentica requisições validando o Bearer token JWT emitido pelo Keycloak.

    Retorna um KeycloakPrincipal com os claims do token — sem persistência
    em banco. O tenant_id (sub) é usado diretamente nos modelos.

    Estratégia dupla:
      - KEYCLOAK_CLIENT_SECRET configurado → introspection (cliente confidential)
      - Sem client_secret → validação offline via JWKS (cliente público)
    """

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ', 1)[1].strip()

        if getattr(settings, 'KEYCLOAK_CLIENT_SECRET', None):
            payload = self._validate_via_introspection(token)
        else:
            payload = self._decode_via_jwks(token)

        principal = KeycloakPrincipal(payload)
        if not principal.tenant_id:
            raise AuthenticationFailed("Token não contém o campo 'sub'.")

        return (principal, token)

    def _validate_via_introspection(self, token: str) -> dict:
        result = _introspect_token(token)
        if not result.get('active', False):
            raise AuthenticationFailed("Token inativo ou revogado.")

        # [SEC-A07] Valida o issuer mesmo no path de introspection
        expected_issuer = (
            f"{settings.KEYCLOAK_SERVER_URL.rstrip('/')}"
            f"/realms/{settings.KEYCLOAK_REALM}"
        )
        token_iss = result.get('iss', '')
        if token_iss and token_iss != expected_issuer:
            logger.warning(
                "Token rejeitado via introspection: issuer inválido '%s'. Esperado: '%s'.",
                token_iss,
                expected_issuer,
            )
            raise AuthenticationFailed("Token emitido por emissor não confiável.")

        return result

    def _decode_via_jwks(self, token: str) -> dict:
        jwks = get_keycloak_jwks()
        decode_errors = []

        audience = getattr(settings, 'KEYCLOAK_CLIENT_ID', None)
        # [SEC-A07] Verifica a claim 'aud' por padrão; desative KEYCLOAK_VERIFY_AUDIENCE
        #           apenas se o Keycloak não emitir a claim e não houver alternativa.
        verify_audience = getattr(settings, 'KEYCLOAK_VERIFY_AUDIENCE', True)

        # [SEC-A07] Constrói o issuer esperado para validação da claim 'iss'
        expected_issuer = (
            f"{settings.KEYCLOAK_SERVER_URL.rstrip('/')}"
            f"/realms/{settings.KEYCLOAK_REALM}"
        )

        # [SEC-A07] leeway de 60s tolera dessincronização de clock entre WSL/EC2
        leeway = datetime.timedelta(seconds=60)

        decode_options = {
            'verify_exp': True,
            'verify_aud': verify_audience,
        }

        for key_data in jwks.get('keys', []):
            try:
                public_key = RSAAlgorithm.from_jwk(json.dumps(key_data))
                return jwt.decode(
                    token,
                    public_key,
                    algorithms=settings.KEYCLOAK_ALGORITHMS,
                    audience=audience if verify_audience else None,
                    issuer=expected_issuer,
                    options=decode_options,
                    leeway=leeway,
                )
            except jwt.ExpiredSignatureError:
                raise AuthenticationFailed("Token expirado.")
            except jwt.InvalidAudienceError:
                # [SEC-A07] NÃO fazer fallback sem audience — rejeitar imediatamente
                logger.warning(
                    "Token rejeitado: audience inválido para cliente '%s'.", audience,
                )
                raise AuthenticationFailed(
                    "Token não autorizado para este recurso (audience inválido)."
                )
            except jwt.InvalidIssuerError:
                logger.warning(
                    "Token rejeitado: issuer inválido. Esperado: '%s'.", expected_issuer,
                )
                raise AuthenticationFailed("Token emitido por emissor não confiável.")
            except jwt.InvalidTokenError as exc:
                decode_errors.append(str(exc))

        # Força refresh do cache JWKS — pode ter ocorrido rotação de chave
        cache.delete(JWKS_CACHE_KEY)
        logger.warning(
            "Falha ao validar token JWT contra todas as chaves JWKS. Erros: %s",
            '; '.join(decode_errors),
        )
        # [SEC-A09] Não expõe detalhes técnicos na resposta ao cliente
        raise AuthenticationFailed("Token inválido.")
