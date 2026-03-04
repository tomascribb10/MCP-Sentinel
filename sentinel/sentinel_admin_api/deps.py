"""
sentinel_admin_api.deps
========================
FastAPI dependency injection for the Admin API.

Dependencies
------------
get_conductor()     — oslo.messaging RPC client to sentinel-conductor
get_current_user()  — validates JWT and returns the current user dict
require_superuser() — raises 403 if the current user is not a superuser
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from sentinel_admin_api.auth import decode_token
from sentinel_admin_api.schemas import CurrentUser

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# These are populated by main.py at startup
_conductor_client = None
_conf = None


def set_conductor_client(client) -> None:
    global _conductor_client
    _conductor_client = client


def set_conf(conf) -> None:
    global _conf
    _conf = conf


def get_conductor():
    """Return the oslo.messaging RPC client for sentinel-conductor."""
    if _conductor_client is None:
        raise RuntimeError("Conductor client not initialised")
    return _conductor_client


def get_conf():
    if _conf is None:
        raise RuntimeError("CONF not initialised")
    return _conf


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    conductor=Depends(get_conductor),
    conf=Depends(get_conf),
) -> CurrentUser:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token, conf.auth.admin_api_secret_key)
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = conductor.call({}, "get_user_by_username", username=username)
    if user is None or not user.get("is_active", False):
        raise credentials_exc

    return CurrentUser(
        id=user["id"],
        username=user["username"],
        email=user.get("email"),
        is_superuser=user.get("is_superuser", False),
    )


def require_superuser(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )
    return current_user


# Type aliases for route signatures
ConductorDep = Annotated[object, Depends(get_conductor)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
SuperUserDep = Annotated[CurrentUser, Depends(require_superuser)]
ConfDep = Annotated[object, Depends(get_conf)]
