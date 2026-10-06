import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"
MAX_PASSWORD_BYTES = 72  # bcrypt only uses the first 72 bytes

InvalidTokenError = jwt.InvalidTokenError


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    encoded = password.encode()
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(encoded, hashed.encode())


# Checked when the email is unknown, so failed logins take the same time either way.
DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing")


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    claims = jwt.decode(
        token,
        get_settings().jwt_secret.get_secret_value(),
        algorithms=[ALGORITHM],
        options={"require": ["sub", "exp"]},
    )
    try:
        return uuid.UUID(claims["sub"])
    except (ValueError, TypeError) as exc:
        raise InvalidTokenError("Invalid subject") from exc
