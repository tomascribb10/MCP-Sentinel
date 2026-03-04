"""
sentinel_admin_api.auth
========================
JWT token utilities and password hashing for the standalone Admin API.

If Keystone is configured (``[keystone] auth_url`` is set), token
validation is delegated to Keystone instead.  This module handles
the standalone (local DB) case only.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(
    data: dict,
    secret_key: str,
    expires_minutes: int,
) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload["exp"] = expire
    payload["iat"] = datetime.now(timezone.utc)
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def decode_token(token: str, secret_key: str) -> dict:
    """
    Decode and validate a JWT token.

    Raises:
        jose.JWTError: if the token is invalid or expired.
    """
    return jwt.decode(token, secret_key, algorithms=[ALGORITHM])
