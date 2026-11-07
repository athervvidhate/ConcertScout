"""Record every outbound call and model answer of a Search, so it can replay unchanged."""

import datetime as dt
import hashlib
import json
import os
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote, quote_plus, urlencode

import httpx
from pydantic import BaseModel
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

from concert_scout.models import Concert
from concert_scout.sources import ticketmaster

SNAPSHOTS = Path(__file__).parent / "snapshots"
SECRET_PARAMS = {"apikey", "api_key", "access_token"}


class Recorded(BaseModel):
    status: int
    content_type: str
    body: str


class Snapshot(BaseModel):
    """Third-party data, so it stays in the gitignored snapshots folder."""

    id: str
    text: str
    today: dt.date
    seconds_to_poster: float | None
    lastfm_enabled: bool
    records: dict[str, Recorded]
    answers: dict[str, str]


def request_key(request: httpx.Request) -> str:
    """Names a request without its API key, which must never reach a snapshot."""
    params = sorted(
        (k, v) for k, v in request.url.params.multi_items() if k.casefold() not in SECRET_PARAMS
    )
    url = request.url.copy_with(query=None)
    digest = hashlib.sha256(request.content).hexdigest()[:16]
    return f"{request.method} {url}?{urlencode(params)} {digest}"


def model_key(messages: Sequence[ModelMessage]) -> str:
    """Names a model request by its text, because its timestamps and run IDs change per run."""
    text: list[str] = []
    for message in messages:
        text.append(str(getattr(message, "instructions", None)))
        text.extend(f"{p.part_kind}:{getattr(p, 'content', '')}" for p in message.parts)
    return hashlib.sha256("\n".join(text).encode()).hexdigest()[:16]


class RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(
        self, inner: httpx.AsyncBaseTransport | None = None, secrets: Sequence[str] = ()
    ) -> None:
        self.inner = inner or httpx.AsyncHTTPTransport()
        self.records: dict[str, Recorded] = {}
        self.secrets = {value for value in secrets if value}

    def redact(self, text: str) -> str:
        for value in sorted(self.secrets, key=len, reverse=True):
            for encoded in {value, quote(value, safe=""), quote_plus(value)}:
                text = text.replace(encoded, "[redacted]")
        return text

    async def aclose(self) -> None:
        await self.inner.aclose()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        self.secrets.update(
            value
            for key, value in request.url.params.multi_items()
            if key.casefold() in SECRET_PARAMS and value
        )
        response = await self.inner.handle_async_request(request)
        body = await response.aread()
        content_type = response.headers.get("content-type", "application/json")
        self.records[self.redact(request_key(request))] = Recorded(
            status=response.status_code, content_type=content_type, body=self.redact(body.decode())
        )
        return httpx.Response(
            response.status_code, headers={"content-type": content_type}, content=body
        )


class ReplayTransport(httpx.AsyncBaseTransport):
    def __init__(self, snapshot: Snapshot) -> None:
        self.records = snapshot.records
        self.misses: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        key = request_key(request)
        record = self.records.get(key)
        if record is None:
            self.misses.append(key)
            return httpx.Response(404, json={})
        return httpx.Response(
            record.status, headers={"content-type": record.content_type}, content=record.body
        )


class RecordingModel(WrapperModel):
    def __init__(self, wrapped: Model) -> None:
        super().__init__(wrapped)
        self.answers: dict[str, str] = {}

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        response = await super().request(messages, model_settings, model_request_parameters)
        self.answers[model_key(messages)] = ModelMessagesTypeAdapter.dump_json([response]).decode()
        return response


class ReplayModel(WrapperModel):
    """Repeats recorded answers. With `live`, it calls the wrapped model instead and costs money."""

    def __init__(self, wrapped: Model, snapshot: Snapshot, live: bool) -> None:
        super().__init__(wrapped)
        self.answers = snapshot.answers
        self.live = live
        self.misses: list[str] = []

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        if self.live:
            return await super().request(messages, model_settings, model_request_parameters)
        key = model_key(messages)
        answer = self.answers.get(key)
        if answer is None:
            self.misses.append(f"model request {key}")
            raise UnexpectedModelBehavior("The Snapshot has no answer for this model request")
        response = ModelMessagesTypeAdapter.validate_json(answer)[0]
        assert isinstance(response, ModelResponse)
        return response


def path_for(snapshot_id: str) -> Path:
    return SNAPSHOTS / f"{snapshot_id}.json"


def save(snapshot: Snapshot) -> None:
    SNAPSHOTS.mkdir(exist_ok=True)
    # Snapshots hold Search text and third-party data. Do not overwrite earlier evidence.
    descriptor = os.open(path_for(snapshot.id), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(snapshot.model_dump_json())


def load(snapshot_id: str) -> Snapshot:
    return Snapshot.model_validate_json(path_for(snapshot_id).read_text())


def source_concerts(snapshot: Snapshot) -> list[Concert]:
    """The source records a Poster's facts must match, parsed from Ticketmaster's own answers."""
    concerts: dict[str, Concert] = {}
    for key, record in snapshot.records.items():
        if "/events.json" in key and record.status == 200:
            for concert in ticketmaster.parse_concerts(json.loads(record.body)):
                concerts[concert.id] = concert
    return list(concerts.values())
