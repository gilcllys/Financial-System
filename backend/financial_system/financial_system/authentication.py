import json
import logging

import jwt
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from jwt.algorithms import RSAAlgorithm
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)

JWKS_CACHE_KEY = 'keycloak_jwks'
JWKS_CACHE_TTL = 3600  # 1 hora


def _fetch_jwks():
    jwks_url = (
        f"{settings.KEYCLOAK_SERVER_URL}"
        f"/realms/{settings.KEYCLOAK_REALM}"
        f"/protocol/openid-connect/certs"
    )
    try:
        response = requests.get(jwks_url, timeout=5)
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

    Estratégia dupla:
      1. Validação offline via JWKS (rápida, sem round-trip ao Keycloak)
      2. Introspection via client_secret (confirma token ativo e não revogado)

    Quando KEYCLOAK_CLIENT_SECRET está configurado, a introspection é usada
    como validação primária (cliente confidential). Caso contrário, cai para
    validação JWKS pura.
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

        user = self._get_or_create_shadow_user(payload)
        return (user, token)

    def _validate_via_introspection(self, token: str) -> dict:
        """Valida token pelo endpoint de introspection (cliente confidential)."""
        result = _introspect_token(token)

        if not result.get('active', False):
            raise AuthenticationFailed("Token inativo ou revogado.")

        return result

    def _decode_via_jwks(self, token: str) -> dict:
        """Valida token offline pelas chaves públicas JWKS (cliente público)."""
        jwks = get_keycloak_jwks()
        decode_errors = []

        for key_data in jwks.get('keys', []):
            try:
                public_key = RSAAlgorithm.from_jwk(json.dumps(key_data))
                return jwt.decode(
                    token,
                    public_key,
                    algorithms=settings.KEYCLOAK_ALGORITHMS,
                    audience=settings.KEYCLOAK_CLIENT_ID,
                    options={'verify_exp': True},
                )
            except jwt.ExpiredSignatureError:
                raise AuthenticationFailed("Token expirado.")
            except jwt.InvalidAudienceError:
                raise AuthenticationFailed("Token com audience inválido.")
            except jwt.InvalidTokenError as exc:
                decode_errors.append(str(exc))

        cache.delete(JWKS_CACHE_KEY)
        raise AuthenticationFailed(
            f"Token inválido. Detalhes: {'; '.join(decode_errors)}"
        )

    def _get_or_create_shadow_user(self, payload: dict) -> User:
        sub = payload.get('sub')
        if not sub:
            raise AuthenticationFailed("Token não contém o campo 'sub'.")

        user, _ = User.objects.get_or_create(
            username=sub,
            defaults={
                'email': payload.get('email', ''),
                'first_name': payload.get('given_name', ''),
                'last_name': payload.get('family_name', ''),
            },
        )
        return user
