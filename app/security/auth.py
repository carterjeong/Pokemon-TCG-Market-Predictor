"""Authentication scaffolding — SECURITY WORKSTREAM.

Owner: CyberSec partner (feature/jwt-auth branch).

This module defines the *contract* the backend codes against so Carter's
routes can already declare `Depends(get_current_user)`. The implementation
is intentionally a stub that fails closed (401) until real JWT validation
lands.

TODO(security):
  * issue/verify JWTs (jwt_secret_key -> AWS Secrets Manager, not env)
  * token endpoint (POST /api/v1/auth/token) + refresh strategy
  * password hashing (argon2/bcrypt) + user table or IdP integration
  * rotate keys; consider RS256 with JWKS instead of HS256
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


class CurrentUser(BaseModel):
    subject: str
    scopes: list[str] = []


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> CurrentUser:
    """Fail-closed stub: every protected route 401s until JWT auth lands."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication not yet implemented (see feature/jwt-auth).",
        headers={"WWW-Authenticate": "Bearer"},
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
