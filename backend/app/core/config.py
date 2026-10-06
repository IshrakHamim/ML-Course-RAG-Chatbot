from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    gemini_api_key: SecretStr
    gemini_use_vertex: bool = True
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = Field(768, ge=1, le=2000)
    embed_batch_size: int = Field(50, ge=1, le=250)
    database_url: str = "postgresql+psycopg://rag:rag@localhost:5432/ragbot"
    jwt_secret: SecretStr
    jwt_expire_minutes: int = Field(120, ge=1)
    rag_top_k: int = Field(5, ge=1, le=50)
    rag_min_score: float = Field(0.6, ge=0.0, le=1.0)
    chunk_size: int = Field(3000, ge=200)
    chunk_overlap: int = Field(400, ge=0)
    memory_turns: int = Field(6, ge=0)
    max_message_chars: int = Field(2000, ge=1)
    max_upload_mb: int = Field(10, ge=1)
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    @field_validator("gemini_api_key")
    @classmethod
    def _api_key_not_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("GEMINI_API_KEY is missing; set it in .env")
        return value

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().strip()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters; set it in .env")
        return value

    @model_validator(mode="after")
    def _overlap_smaller_than_size(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Load settings once. Invalid or missing values stop the process with a readable message."""
    try:
        return Settings()
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            message = error["msg"].removeprefix("Value error, ")
            if error["type"] == "missing":
                message = f"{str(error['loc'][0]).upper()} is missing"
            elif error["loc"] and not message.startswith(str(error["loc"][0]).upper()):
                message = f"{str(error['loc'][0]).upper()}: {message}"
            problems.append(message)
        raise SystemExit("Invalid configuration in .env: " + "; ".join(problems)) from None
