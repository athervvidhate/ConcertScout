"""Gemini text embeddings, 512 dimensions, through Pydantic AI's `Embedder`.

The Gemini API key path is explicit, so `GOOGLE_GENAI_USE_VERTEXAI` in the environment never
switches this to Vertex. The model reports no usage, so every call records an estimate instead.
"""

import datetime as dt
import hashlib
import logging
import math
from collections.abc import Sequence

from pydantic import BaseModel, SecretStr
from pydantic_ai import Embedder
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior, UserError
from redis.asyncio import Redis

from concert_scout import cache, telemetry

logger = logging.getLogger(__name__)

MODEL = "gemini-embedding-001"
# Gemini's output is Matryoshka-trained, so its first 512 values are a usable embedding.
DIMENSIONS = 512
# The same window as the interpreter's answer, so a repeated Search embeds nothing.
QUERY_TTL = dt.timedelta(hours=6)
# The Gemini API takes up to 100 texts a request.
BATCH_SIZE = 100
CHARS_PER_TOKEN = 4

type Vector = list[float]


class EmbedderError(Exception):
    """Embedding failed. The message never holds the text, which can be a visitor's Search."""


class CachedVector(BaseModel):
    values: Vector


def make_embedder(api_key: SecretStr) -> Embedder:
    # Google's SDK is slow to import, and a deployment without a key never needs it.
    from pydantic_ai.embeddings.google import GoogleEmbeddingModel
    from pydantic_ai.providers.google import GoogleProvider

    model = GoogleEmbeddingModel(MODEL, provider=GoogleProvider(api_key=api_key.get_secret_value()))
    return Embedder(model, settings={"dimensions": DIMENSIONS})


def unit(vector: Sequence[float]) -> Vector:
    """The vector scaled to length 1. Gemini normalizes only its full 3,072 dimensions."""
    length = math.sqrt(sum(x * x for x in vector))
    if length == 0:
        raise EmbedderError("empty vector")
    return [x / length for x in vector]


async def embed_query(embedder: Embedder, redis: Redis, text: str) -> Vector:
    """The unit vector for a Search's Taste words, kept six hours."""
    digest = hashlib.sha256(f"{MODEL}\x00{DIMENSIONS}\x00{text}".encode()).hexdigest()
    key = f"embed:query:{digest}"
    if cached := await cache.read(redis, key, CachedVector):
        return cached.values
    try:
        result = await embedder.embed_query(text)
    except (ModelAPIError, UnexpectedModelBehavior, UserError) as exc:
        raise EmbedderError(type(exc).__name__) from None
    telemetry.record_embedding(_tokens([text]))
    [vector] = _checked(result.embeddings, 1)
    await cache.write(redis, key, CachedVector(values=vector), QUERY_TTL)
    return vector


async def embed_documents(embedder: Embedder, texts: Sequence[str]) -> list[Vector]:
    """Unit vectors for Sonic Cards, in order, a request per BATCH_SIZE."""
    vectors: list[Vector] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        try:
            result = await embedder.embed_documents(batch)
        except (ModelAPIError, UnexpectedModelBehavior, UserError) as exc:
            raise EmbedderError(type(exc).__name__) from None
        telemetry.record_embedding(_tokens(batch))
        vectors += _checked(result.embeddings, len(batch))
    return vectors


def _checked(embeddings: Sequence[Sequence[float]], expected: int) -> list[Vector]:
    if len(embeddings) != expected or any(len(e) != DIMENSIONS for e in embeddings):
        raise EmbedderError("unexpected embedding shape")
    return [unit(e) for e in embeddings]


def _tokens(texts: Sequence[str]) -> int:
    return sum(math.ceil(len(text) / CHARS_PER_TOKEN) for text in texts)
