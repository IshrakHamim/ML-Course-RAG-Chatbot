"""Deterministic stand-in for app.services.gemini, so tests never call the real API."""

import hashlib
import math
import re

from app.core.config import get_settings
from app.core.errors import AIServiceError
from app.services.gemini import ChatTurn

STOPWORDS = {
    "a", "an", "and", "are", "about", "can", "do", "does", "for", "how", "i", "in", "is", "it",
    "me", "of", "on", "or", "say", "the", "this", "to", "what", "when", "which", "with", "you",
}  # fmt: skip


def bag_of_words_vector(text: str) -> list[float]:
    dim = get_settings().embedding_dim
    vector = [0.0] * dim
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if word in STOPWORDS:
            continue
        bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % dim
        vector[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        vector[0] = 1.0
        return vector
    return [v / norm for v in vector]


class FakeGemini:
    def __init__(self) -> None:
        self.answer = "The answer from the context."
        self.rewrite_answer: str | None = None
        self.fail_with: AIServiceError | None = None
        self.fail_rewrite = False
        self.embed_calls: list[tuple[list[str], str]] = []
        self.generate_calls: list[tuple[str, list[ChatTurn]]] = []
        self.rewrite_calls: list[list[ChatTurn]] = []

    def embed_texts(self, texts: list[str], task_type: str) -> list[list[float]]:
        if self.fail_with:
            raise self.fail_with
        self.embed_calls.append((list(texts), task_type))
        return [bag_of_words_vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text], "RETRIEVAL_QUERY")[0]

    def generate(self, system_instruction: str, turns: list[ChatTurn]) -> str:
        if self.fail_with:
            raise self.fail_with
        if "standalone" in system_instruction:
            if self.fail_rewrite:
                raise AIServiceError("quota", "fake rewrite failure")
            self.rewrite_calls.append(list(turns))
            return self.rewrite_answer if self.rewrite_answer is not None else turns[-1].text
        self.generate_calls.append((system_instruction, list(turns)))
        return self.answer
