import jwt
from django.conf import settings
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed


class ServicePrincipal:
    """Small authenticated principal for machine-to-machine ingestion."""

    def __init__(self, auth_type):
        self.auth_type = auth_type

    @property
    def is_authenticated(self):
        return True


class StaticTokenAuthentication(authentication.BaseAuthentication):
    """
    Accepts static token from either:
    - Authorization: Token <token>
    - X-Analytics-Token: <token>
    """

    def authenticate(self, request):
        configured_token = getattr(settings, 'ANALYTICS_INGEST_TOKEN', '')
        if not configured_token:
            return None

        raw_header = authentication.get_authorization_header(request).decode('utf-8')
        header_token = request.headers.get('X-Analytics-Token')

        provided = None
        if raw_header.startswith('Token '):
            provided = raw_header.split(' ', 1)[1].strip()
        elif header_token:
            provided = header_token.strip()
        else:
            return None

        if provided != configured_token:
            raise AuthenticationFailed('Invalid static token.')

        return ServicePrincipal(auth_type='token'), provided


class ApiKeyAuthentication(authentication.BaseAuthentication):
    """
    Accepts API key from:
    - X-API-Key: <api-key>
    """

    def authenticate(self, request):
        configured_api_key = getattr(settings, 'ANALYTICS_API_KEY', '')
        if not configured_api_key:
            return None

        provided = request.headers.get('X-API-Key')
        if not provided:
            return None

        if provided.strip() != configured_api_key:
            raise AuthenticationFailed('Invalid API key.')

        return ServicePrincipal(auth_type='api_key'), provided


class JWTIngestionAuthentication(authentication.BaseAuthentication):
    """
    Accepts JWT from:
    - Authorization: Bearer <jwt>
    """

    def authenticate(self, request):
        configured_secret = getattr(settings, 'ANALYTICS_JWT_SECRET', '')
        if not configured_secret:
            return None

        raw_header = authentication.get_authorization_header(request).decode('utf-8')
        if not raw_header.startswith('Bearer '):
            return None

        token = raw_header.split(' ', 1)[1].strip()

        audience = getattr(settings, 'ANALYTICS_JWT_AUDIENCE', '') or None
        issuer = getattr(settings, 'ANALYTICS_JWT_ISSUER', '') or None
        algorithm = getattr(settings, 'ANALYTICS_JWT_ALGORITHM', 'HS256')

        try:
            claims = jwt.decode(
                token,
                configured_secret,
                algorithms=[algorithm],
                audience=audience,
                issuer=issuer,
                options={'verify_aud': audience is not None},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationFailed(f'Invalid JWT token: {exc}')

        return ServicePrincipal(auth_type='jwt'), claims
