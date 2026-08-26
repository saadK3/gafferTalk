from dataclasses import dataclass
from uuid import UUID

import jwt
from jwt import PyJWKClient


class InvalidAccessTokenError(ValueError):
    """Raised when a bearer token cannot identify a valid Supabase user."""


@dataclass(frozen=True)
class AuthenticatedAccount:
    id: UUID


class SupabaseJwtVerifier:
    def __init__(self, supabase_url: str, audience: str = "authenticated") -> None:
        self.issuer = f"{supabase_url.rstrip('/')}/auth/v1"
        self.audience = audience
        self._jwks = PyJWKClient(f"{self.issuer}/.well-known/jwks.json", cache_keys=True)

    def verify(self, token: str) -> AuthenticatedAccount:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256", "EdDSA"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
            return AuthenticatedAccount(id=UUID(str(claims["sub"])))
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
            raise InvalidAccessTokenError("The access token is invalid or expired.") from error
