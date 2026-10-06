import pytest
from pydantic import ValidationError

from app.core.config import Settings


def make_settings(**overrides) -> Settings:
    values = {"gemini_api_key": "key", "jwt_secret": "s" * 32}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_valid_settings_load():
    settings = make_settings()
    assert settings.embedding_dim == 768
    assert settings.max_upload_bytes == 10 * 1024 * 1024


def test_blank_api_key_rejected():
    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        make_settings(gemini_api_key="   ")


def test_short_jwt_secret_rejected():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        make_settings(jwt_secret="x" * 31)


def test_overlap_must_be_less_than_size():
    with pytest.raises(ValidationError, match="CHUNK_OVERLAP"):
        make_settings(chunk_size=400, chunk_overlap=400)


def test_embedding_dim_max_2000():
    with pytest.raises(ValidationError):
        make_settings(embedding_dim=2001)


def test_min_score_range():
    with pytest.raises(ValidationError):
        make_settings(rag_min_score=1.5)


def test_cors_origins_split():
    settings = make_settings(cors_origins="http://a.com, http://b.com")
    assert settings.cors_origin_list == ["http://a.com", "http://b.com"]
