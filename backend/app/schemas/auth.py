import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import MAX_PASSWORD_BYTES


def normalize_email(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    _normalize_email = field_validator("email", mode="before")(normalize_email)

    @field_validator("password")
    @classmethod
    def _password_rules(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(value.encode()) > MAX_PASSWORD_BYTES:
            raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=1000)

    _normalize_email = field_validator("email", mode="before")(normalize_email)


class UserOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
