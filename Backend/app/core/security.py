import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings
from app.models.user import UserRole


def _password_bytes(password: str) -> bytes:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, role: UserRole | str) -> str:
    now = datetime.now(timezone.utc)
    role_value = role.value if isinstance(role, UserRole) else role
    payload = {
        "sub": str(user_id),
        "role": role_value,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    claims: dict[str, Any] = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "role", "iat", "exp"]},
    )
    if not isinstance(claims["sub"], str) or claims["role"] not in {
        UserRole.ADMIN.value,
        UserRole.STUDENT.value,
    }:
        raise jwt.InvalidTokenError("Invalid token claims.")
    return claims
