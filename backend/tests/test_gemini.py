import math
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.errors import AIServiceError
from app.services import gemini
from app.services.gemini import ChatTurn


def api_error(code: int, message: str = "error") -> errors.APIError:
    return errors.APIError(code, {"error": {"code": code, "message": message}})


def embedding_response(count: int, dim: int = 768):
    return SimpleNamespace(
        embeddings=[SimpleNamespace(values=[3.0, 4.0] + [0.0] * (dim - 2)) for _ in range(count)]
    )


class StubModels:
    """Each call pops the next scripted outcome: an exception to raise, or a response."""

    def __init__(self, embed=None, generate=None):
        self.embed_script = list(embed or [])
        self.generate_script = list(generate or [])
        self.embed_requests = []
        self.generate_requests = []

    def _next(self, script, default):
        outcome = script.pop(0) if script else default
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def embed_content(self, *, model, contents, config):
        self.embed_requests.append(SimpleNamespace(model=model, contents=contents, config=config))
        return self._next(self.embed_script, embedding_response(len(contents)))

    def generate_content(self, *, model, contents, config):
        self.generate_requests.append(
            SimpleNamespace(model=model, contents=contents, config=config)
        )
        return self._next(self.generate_script, SimpleNamespace(text="ok", candidates=[]))


@pytest.fixture
def stub(monkeypatch):
    models = StubModels()
    monkeypatch.setattr(gemini, "_get_client", lambda: SimpleNamespace(models=models))
    sleeps: list[float] = []
    monkeypatch.setattr(gemini, "_sleep", sleeps.append)
    models.sleeps = sleeps
    return models


def use_settings(monkeypatch, **updates):
    settings = get_settings().model_copy(update=updates)
    monkeypatch.setattr(gemini, "get_settings", lambda: settings)


def test_l2_normalize_unit_length():
    vector = gemini.l2_normalize([3.0, 4.0])
    assert vector == pytest.approx([0.6, 0.8])
    assert math.sqrt(sum(v * v for v in vector)) == pytest.approx(1.0)


def test_l2_normalize_zero_vector_raises():
    with pytest.raises(AIServiceError) as exc:
        gemini.l2_normalize([0.0, 0.0])
    assert exc.value.kind == "empty"


def test_embed_batches_and_preserves_order(stub):
    texts = [f"text {i}" for i in range(120)]
    vectors = gemini.embed_texts(texts, "RETRIEVAL_DOCUMENT")
    assert [len(r.contents) for r in stub.embed_requests] == [50, 50, 20]
    assert [c for r in stub.embed_requests for c in r.contents] == texts
    assert len(vectors) == 120
    assert vectors[0][:2] == pytest.approx([0.6, 0.8])


def test_embed_respects_batch_size_setting(stub, monkeypatch):
    use_settings(monkeypatch, embed_batch_size=1)
    gemini.embed_texts(["a", "b", "c"], "RETRIEVAL_DOCUMENT")
    assert [len(r.contents) for r in stub.embed_requests] == [1, 1, 1]


def test_embed_passes_task_type_and_dimensionality(stub):
    gemini.embed_query("question")
    config = stub.embed_requests[0].config
    assert config.task_type == "RETRIEVAL_QUERY"
    assert config.output_dimensionality == 768
    assert stub.embed_requests[0].model == get_settings().gemini_embedding_model


def test_embed_wrong_dimension_raises(stub):
    stub.embed_script = [embedding_response(1, dim=3072)]
    with pytest.raises(AIServiceError) as exc:
        gemini.embed_query("question")
    assert exc.value.kind == "dimension"


def test_retries_429_then_succeeds(stub):
    stub.embed_script = [api_error(429), api_error(429), embedding_response(1)]
    assert len(gemini.embed_query("q")) == 768
    assert len(stub.embed_requests) == 3
    assert stub.sleeps == [1, 2]


def test_gives_up_after_4_attempts(stub):
    stub.embed_script = [api_error(429)] * 10
    with pytest.raises(AIServiceError) as exc:
        gemini.embed_query("q")
    assert exc.value.kind == "quota"
    assert len(stub.embed_requests) == 4
    assert stub.sleeps == [1, 2, 4]


def test_server_error_is_retried(stub):
    stub.generate_script = [api_error(503), SimpleNamespace(text="fine", candidates=[])]
    assert gemini.generate("system", [ChatTurn("user", "hi")]) == "fine"
    assert len(stub.generate_requests) == 2


def test_400_not_retried(stub):
    stub.embed_script = [api_error(400, "bad request")]
    with pytest.raises(AIServiceError) as exc:
        gemini.embed_query("q")
    assert exc.value.kind == "bad_request"
    assert len(stub.embed_requests) == 1


def test_invalid_key_400_maps_to_auth(stub):
    stub.embed_script = [api_error(400, "API key not valid. Please pass a valid API key.")]
    with pytest.raises(AIServiceError) as exc:
        gemini.embed_query("q")
    assert exc.value.kind == "auth"


def test_401_maps_to_auth(stub):
    stub.embed_script = [api_error(401)]
    with pytest.raises(AIServiceError) as exc:
        gemini.embed_query("q")
    assert exc.value.kind == "auth"


def test_404_maps_to_model_not_found(stub):
    stub.generate_script = [api_error(404, "models/x is not found")]
    with pytest.raises(AIServiceError) as exc:
        gemini.generate("system", [ChatTurn("user", "hi")])
    assert exc.value.kind == "model_not_found"


def test_timeout_maps_to_timeout(stub):
    stub.embed_script = [httpx.ReadTimeout("slow")] * 4
    with pytest.raises(AIServiceError) as exc:
        gemini.embed_query("q")
    assert exc.value.kind == "timeout"
    assert len(stub.embed_requests) == 4


@pytest.mark.parametrize("text", [None, "", "   "])
def test_generate_empty_or_blocked_raises(stub, text):
    blocked = SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason="SAFETY")])
    stub.generate_script = [blocked]
    with pytest.raises(AIServiceError) as exc:
        gemini.generate("system", [ChatTurn("user", "hi")])
    assert exc.value.kind == "empty"


def test_generate_uses_temperature_0_2_and_system_instruction(stub):
    turns = [ChatTurn("user", "q1"), ChatTurn("model", "a1"), ChatTurn("user", "q2")]
    assert gemini.generate("Be grounded.", turns) == "ok"
    request = stub.generate_requests[0]
    assert request.config.temperature == 0.2
    assert request.config.system_instruction == "Be grounded."
    assert [c.role for c in request.contents] == ["user", "model", "user"]
    assert request.contents[2].parts[0].text == "q2"
    assert request.model == get_settings().gemini_chat_model


def test_client_uses_30s_timeout_and_vertex_flag(monkeypatch):
    created = {}
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: created.update(kwargs))
    gemini._get_client.cache_clear()
    try:
        gemini._get_client()
    finally:
        gemini._get_client.cache_clear()
    assert created["http_options"].timeout == 30_000
    assert created["vertexai"] is get_settings().gemini_use_vertex
    assert created["api_key"] == "test-key"


def test_check_gemini_success(stub, capsys):
    assert gemini.run_check() == 0
    output = capsys.readouterr().out
    assert "vector length 768" in output
    assert "OK" in output


def test_check_gemini_hints_vertex_for_AQ_key(stub, monkeypatch, capsys):
    use_settings(monkeypatch, gemini_api_key=SecretStr("AQ.example"), gemini_use_vertex=False)
    stub.generate_script = [api_error(401)]
    assert gemini.run_check() == 1
    assert "GEMINI_USE_VERTEX=true" in capsys.readouterr().out


def test_check_gemini_model_not_found_hint(stub, capsys):
    stub.generate_script = [api_error(404)]
    assert gemini.run_check() == 1
    assert "GEMINI_CHAT_MODEL" in capsys.readouterr().out


def test_check_gemini_dimension_mismatch_fails(stub, capsys):
    stub.embed_script = [embedding_response(1, dim=3072)]
    assert gemini.run_check() == 1
    assert "EMBEDDING_DIM" in capsys.readouterr().out


def test_check_gemini_batch_hint(stub, capsys):
    stub.embed_script = [embedding_response(1), api_error(400, "only one input supported")]
    assert gemini.run_check() == 1
    assert "EMBED_BATCH_SIZE=1" in capsys.readouterr().out


def test_cli_check_gemini_dispatch(monkeypatch):
    from app import cli

    monkeypatch.setattr(gemini, "run_check", lambda: 0)
    assert cli.main(["check-gemini"]) == 0


def test_batch_rejected_falls_back_to_one_text_per_call(stub, monkeypatch):
    monkeypatch.setattr(gemini, "_single_input_only", False)
    stub.embed_script = [api_error(400, "only one input is supported")]
    vectors = gemini.embed_texts(["a", "b", "c"], "RETRIEVAL_DOCUMENT")
    assert len(vectors) == 3
    assert [len(r.contents) for r in stub.embed_requests] == [3, 1, 1, 1]
    gemini.embed_texts(["d", "e"], "RETRIEVAL_DOCUMENT")
    assert [len(r.contents) for r in stub.embed_requests][4:] == [1, 1]


def test_single_text_400_still_raises(stub, monkeypatch):
    monkeypatch.setattr(gemini, "_single_input_only", False)
    stub.embed_script = [api_error(400, "bad"), api_error(400, "bad")]
    with pytest.raises(AIServiceError):
        gemini.embed_texts(["a"], "RETRIEVAL_DOCUMENT")


def test_check_gemini_suggests_ai_studio_when_vertex_api_disabled(stub, monkeypatch, capsys):
    use_settings(monkeypatch, gemini_api_key=SecretStr("AQ.example"), gemini_use_vertex=True)
    stub.generate_script = [api_error(403, "Agent Platform API has not been used in project 1")]
    assert gemini.run_check() == 1
    assert "GEMINI_USE_VERTEX=false" in capsys.readouterr().out
