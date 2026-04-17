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


class KeycloakAuthentication(BaseAuthentication):
    """
    Autentica requisições validando o Bearer token JWT emitido pelo Keycloak.

    Fluxo:
      1. Extrai o token do header Authorization: Bearer <token>
      2. Busca (ou usa cache) das chaves públicas JWKS do Keycloak
      3. Valida assinatura, expiração e audience
      4. Cria ou recupera um Django User shadow pelo campo 'sub' do token
    """

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ', 1)[1].strip()
        payload = self._decode_token(token)
        user = self._get_or_create_shadow_user(payload)
        return (user, token)

    def _decode_token(self, token):
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

        # Nenhuma chave validou — invalida cache para forçar re-fetch no próximo request
        cache.delete(JWKS_CACHE_KEY)
        raise AuthenticationFailed(
            f"Token inválido. Detalhes: {'; '.join(decode_errors)}"
        )

    def _get_or_create_shadow_user(self, payload):
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
