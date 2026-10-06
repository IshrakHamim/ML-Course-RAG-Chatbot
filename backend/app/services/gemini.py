"""The only module that talks to the Gemini API."""

import logging
import math
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, TypeVar

import httpx
from google import genai
from google.genai import errors, types

from app.core.config import get_settings
from app.core.errors import AIServiceError

logger = logging.getLogger(__name__)

TaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]
TIMEOUT_MS = 30_000
MAX_ATTEMPTS = 4
TEMPERATURE = 0.2
_sleep = time.sleep
T = TypeVar("T")


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["user", "model"]
    text: str


@lru_cache
def _get_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        vertexai=settings.gemini_use_vertex,
        http_options=types.HttpOptions(timeout=TIMEOUT_MS),
    )


def _error_kind(exc: errors.APIError) -> str:
    message = (exc.message or "").lower()
    if exc.code == 429:
        return "quota"
    if exc.code in (401, 403) or (exc.code == 400 and "api key" in message):
        return "auth"
    if exc.code == 404:
        return "model_not_found"
    return "unavailable"


def _call(operation: str, fn: Callable[[], T]) -> T:
    """Run a Gemini call with a retry on 429, 5xx, and network errors (1s, 2s, 4s backoff)."""
    for attempt in range(MAX_ATTEMPTS):
        start = time.perf_counter()
        try:
            result = fn()
        except errors.APIError as exc:
            kind = _error_kind(exc)
            retryable = exc.code == 429 or exc.code >= 500
            error = AIServiceError(kind, f"{operation}: HTTP {exc.code} {exc.message}")
        except httpx.TimeoutException as exc:
            retryable, error = True, AIServiceError("timeout", f"{operation}: {exc}")
        except httpx.TransportError as exc:
            retryable, error = True, AIServiceError("unavailable", f"{operation}: {exc}")
        else:
            logger.debug("Gemini %s took %.0fms", operation, (time.perf_counter() - start) * 1000)
            return result
        if not retryable or attempt == MAX_ATTEMPTS - 1:
            logger.warning("Gemini %s failed: %s", operation, error.detail)
            raise error
        delay = 2**attempt
        logger.warning("Gemini %s attempt %d failed (%s); retrying in %ds", operation,
                       attempt + 1, error.kind, delay)  # fmt: skip
        _sleep(delay)
    raise AssertionError("unreachable")


def l2_normalize(vec: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        raise AIServiceError("empty", "embedding is a zero vector")
    return [v / norm for v in vec]


def _embed_batch(texts: list[str], task_type: TaskType) -> list[list[float]]:
    settings = get_settings()
    config = types.EmbedContentConfig(
        task_type=task_type, output_dimensionality=settings.embedding_dim
    )
    response = _call(
        "embed",
        lambda: _get_client().models.embed_content(
            model=settings.gemini_embedding_model, contents=texts, config=config
        ),
    )
    embeddings = response.embeddings or []
    if len(embeddings) != len(texts):
        raise AIServiceError("empty", f"expected {len(texts)} embeddings, got {len(embeddings)}")
    vectors = []
    for embedding in embeddings:
        values = embedding.values or []
        if len(values) != settings.embedding_dim:
            raise AIServiceError(
                "dimension", f"got {len(values)} values, EMBEDDING_DIM={settings.embedding_dim}"
            )
        vectors.append(l2_normalize(values))
    return vectors


def embed_texts(texts: list[str], task_type: TaskType) -> list[list[float]]:
    size = get_settings().embed_batch_size
    vectors: list[list[float]] = []
    for start in range(0, len(texts), size):
        vectors.extend(_embed_batch(texts[start : start + size], task_type))
    return vectors


def embed_query(text: str) -> list[float]:
    return embed_texts([text], "RETRIEVAL_QUERY")[0]


def generate(system_instruction: str, turns: list[ChatTurn]) -> str:
    settings = get_settings()
    contents = [types.Content(role=t.role, parts=[types.Part(text=t.text)]) for t in turns]
    config = types.GenerateContentConfig(
        system_instruction=system_instruction, temperature=TEMPERATURE
    )
    start = time.perf_counter()
    response = _call(
        "generate",
        lambda: _get_client().models.generate_content(
            model=settings.gemini_chat_model, contents=contents, config=config
        ),
    )
    text = (response.text or "").strip()
    if not text:
        reasons = [str(getattr(c, "finish_reason", "")) for c in (response.candidates or [])]
        raise AIServiceError("empty", f"no text in response (finish_reason={reasons})")
    logger.info("Gemini generate ok in %.0fms", (time.perf_counter() - start) * 1000)
    return text


HINTS = {
    "quota": "Quota exceeded or rate limited: wait a minute, or check the key's quota.",
    "model_not_found": "Model not found: check GEMINI_CHAT_MODEL / GEMINI_EMBEDDING_MODEL in .env "
    "and the models available to this key.",
    "timeout": "The request timed out: check your network connection and try again.",
    "unavailable": "The Gemini service returned an error; see the message above.",
    "empty": "Gemini returned an empty response.",
}


def _auth_hint(api_key: str, use_vertex: bool) -> str:
    if api_key.startswith("AQ.") and not use_vertex:
        return "This looks like a Vertex AI express key (AQ.): set GEMINI_USE_VERTEX=true."
    if api_key.startswith("AIza") and use_vertex:
        return "This looks like an AI Studio key (AIza): set GEMINI_USE_VERTEX=false."
    return "The key was rejected: check GEMINI_API_KEY, or try flipping GEMINI_USE_VERTEX."


def run_check() -> int:
    """Smoke-test the key and models. Returns a process exit code."""
    settings = get_settings()
    key = settings.gemini_api_key.get_secret_value()

    def say(line: str) -> None:
        sys.stdout.write(line + "\n")

    def fail(step: str, exc: AIServiceError) -> int:
        say(f"FAILED at {step}: {exc.detail or exc.kind}")
        if exc.kind == "auth":
            say(_auth_hint(key, settings.gemini_use_vertex))
        elif exc.kind == "dimension":
            say(f"Vector length does not match EMBEDDING_DIM={settings.embedding_dim}.")
        else:
            say(HINTS.get(exc.kind, ""))
        return 1

    mode = "Vertex AI (express)" if settings.gemini_use_vertex else "Google AI Studio"
    say(f"Mode: {mode}; chat model {settings.gemini_chat_model}; "
        f"embedding model {settings.gemini_embedding_model}")  # fmt: skip
    try:
        reply = generate("Reply with exactly one word.", [ChatTurn("user", "Say OK.")])
        say(f"Generate: OK ({reply[:40]!r})")
    except AIServiceError as exc:
        return fail("generate", exc)
    try:
        vector = _embed_batch(["hello world"], "RETRIEVAL_QUERY")[0]
        say(f"Embed: OK, vector length {len(vector)} (EMBEDDING_DIM={settings.embedding_dim})")
    except AIServiceError as exc:
        return fail("embed", exc)
    if settings.embed_batch_size > 1:
        try:
            _embed_batch(["first text", "second text"], "RETRIEVAL_DOCUMENT")
            say("Batch embed: OK")
        except AIServiceError as exc:
            say(f"FAILED at batch embed: {exc.detail or exc.kind}")
            say("This key/model may accept only one text per call: set EMBED_BATCH_SIZE=1 in .env.")
            return 1
    say("All checks passed: OK")
    return 0
