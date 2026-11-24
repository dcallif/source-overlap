from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, AsyncIterator, Protocol

import httpx

from .config import settings


class LLMError(RuntimeError):
    pass


class BadRequest(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(body)
        self.status = status
        self.body = body


class LLMBackend(Protocol):
    label: str

    async def list_models(self) -> list[str]: ...

    async def resolve_model(self) -> str: ...

    async def chat(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1200,
        schema: dict[str, Any] | None = None,
    ) -> str: ...

    async def chat_json(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1200,
        schema: dict[str, Any] | None = None,
    ) -> Any: ...


def _normalize_base(url: str) -> str:
    return url.rstrip("/")


async def list_models(client: httpx.AsyncClient) -> list[str]:
    try:
        resp = await client.get(
            f"{_normalize_base(settings.lm_studio_url)}/models", timeout=5.0
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        raise LLMError(
            f"LM Studio is not reachable at {settings.lm_studio_url}. "
            "Open LM Studio, load a model, and start the local server on port 1234."
        ) from exc
    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]


_MODEL_SIZE_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*b\b", re.IGNORECASE)


def _model_size(name: str) -> float | None:
    matches = _MODEL_SIZE_RE.findall(name)
    if not matches:
        return None
    return max(float(value) for value in matches)


def pick_model(models: list[str]) -> str:
    if not models:
        raise LLMError(
            "LM Studio is running but no model is loaded. Load a model in LM Studio first."
        )
    # Skip embedding-only models when auto-picking a chat model.
    chat_models = [m for m in models if "embed" not in m.lower()]
    candidates = chat_models or models
    sized = [(model, _model_size(model)) for model in candidates]
    medium = [
        (model, size)
        for model, size in sized
        if size is not None and 7 <= size <= 14
    ]
    if medium:
        return max(medium, key=lambda item: item[1])[0]
    small = [
        (model, size)
        for model, size in sized
        if size is not None and size < 7
    ]
    if small:
        return max(small, key=lambda item: item[1])[0]
    large = [
        (model, size)
        for model, size in sized
        if size is not None and size > 14
    ]
    if large:
        return min(large, key=lambda item: item[1])[0]
    return candidates[0]


async def resolve_model(client: httpx.AsyncClient) -> str:
    if settings.lm_studio_model:
        return settings.lm_studio_model
    return pick_model(await list_models(client))


_LOCAL_PROBE_TTL = 10.0
_LOCAL_PROBE_CACHE: tuple[float, bool] | None = None
_LOCAL_PROBE_LOCK = asyncio.Lock()


async def local_ready(force: bool = False) -> bool:
    """True when LM Studio is reachable and has a chat model loaded."""
    global _LOCAL_PROBE_CACHE
    now = time.monotonic()
    if not force and _LOCAL_PROBE_CACHE:
        cached_at, ready = _LOCAL_PROBE_CACHE
        if now - cached_at < _LOCAL_PROBE_TTL:
            return ready

    async with _LOCAL_PROBE_LOCK:
        now = time.monotonic()
        if not force and _LOCAL_PROBE_CACHE:
            cached_at, ready = _LOCAL_PROBE_CACHE
            if now - cached_at < _LOCAL_PROBE_TTL:
                return ready

        ready = False
        try:
            async with httpx.AsyncClient(
                timeout=settings.local_probe_timeout
            ) as client:
                resp = await client.get(
                    f"{_normalize_base(settings.lm_studio_url)}/models"
                )
                resp.raise_for_status()
                data = resp.json()
            models = [
                m.get("id", "") for m in data.get("data", []) if m.get("id")
            ]
            ready = any(
                "embed" not in str(model).lower() for model in models
            )
        except (httpx.HTTPError, ValueError):
            ready = False

        _LOCAL_PROBE_CACHE = (now, ready)
        return ready


def public_info() -> dict[str, Any]:
    return {
        "enabled": bool(
            settings.public_llm_enabled
            and settings.public_llm_url
            and settings.public_llm_model
        ),
        "label": settings.public_llm_label,
        "model": settings.public_llm_model,
        "url": settings.public_llm_url,
    }


def build_payload(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1200,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "temperature": settings.lm_temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "result", "strict": True, "schema": schema},
        }
    # Reasoning models (e.g. Qwen3.x) spend many seconds emitting "thinking"
    # tokens before the answer. LM Studio honours reasoning_effort: none.
    if settings.lm_disable_thinking:
        payload["reasoning_effort"] = "none"
    return payload


def fallback_payload(payload: dict[str, Any], body: str) -> dict[str, Any] | None:
    adjusted = dict(payload)
    dropped = False
    if "reasoning_effort" in body:
        adjusted.pop("reasoning_effort", None)
        dropped = True
    if "response_format" in body:
        adjusted.pop("response_format", None)
        dropped = True
    return adjusted if dropped else None


def _process_sse_line(line: str, parts: list[str]) -> bool:
    line = line.rstrip("\r")
    if not line.startswith("data:"):
        return False
    chunk = line[5:].strip()
    if chunk == "[DONE]":
        return True
    try:
        event = json.loads(chunk)
    except json.JSONDecodeError:
        return False
    choices = event.get("choices") or []
    if not choices:
        return False
    text = (choices[0].get("delta") or {}).get("content")
    if text:
        parts.append(text)
    return False


async def consume_chat_chunks(
    content_type: str, chunks: AsyncIterator[str]
) -> str:
    if "text/event-stream" not in content_type:
        raw = "".join([chunk async for chunk in chunks])
        data = json.loads(raw)
        return (data["choices"][0]["message"]["content"] or "").strip()

    parts: list[str] = []
    buffer = ""
    async for chunk in chunks:
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if _process_sse_line(line, parts):
                return "".join(parts).strip()
    if buffer:
        _process_sse_line(buffer, parts)
    return "".join(parts).strip()


async def _stream_chat(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
    timeout: httpx.Timeout,
    *,
    url: str | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    target = url or (
        f"{_normalize_base(settings.lm_studio_url)}/chat/completions"
    )
    async with client.stream(
        "POST",
        target,
        json=payload,
        timeout=timeout,
        headers=headers,
    ) as resp:
        if resp.status_code >= 400:
            body = (await resp.aread())[:500].decode("utf-8", "replace")
            raise BadRequest(resp.status_code, body)

        content_type = resp.headers.get("content-type", "")
        return await consume_chat_chunks(content_type, resp.aiter_text())


_RETRYABLE_STATUS = {429, 502, 503, 504}
_PUBLIC_LOCK = asyncio.Lock()


def _http_error(label: str, exc: BadRequest) -> str:
    if exc.status == 429:
        return (
            f"{label} (public model) is rate-limited right now (HTTP 429). "
            "Wait a moment and try again, or connect a local model."
        )
    if exc.status == 402:
        return (
            f"{label} (public model) rejected the request (HTTP 402). "
            "The public endpoint may require a key or be unavailable."
        )
    return f"{label} (public model) returned HTTP {exc.status}: {exc.body}"


async def chat(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1200,
    schema: dict[str, Any] | None = None,
    *,
    url: str | None = None,
    headers: dict[str, str] | None = None,
    label: str = "LM Studio",
    timeout_seconds: float | None = None,
) -> str:
    payload = build_payload(model, system, user, max_tokens, schema)
    seconds = timeout_seconds or settings.lm_timeout
    timeout = httpx.Timeout(seconds, connect=15.0)

    attempt_payload = payload
    fallback_used = False
    retry_count = 0

    while True:
        try:
            content = await _stream_chat(
                client,
                attempt_payload,
                timeout,
                url=url,
                headers=headers,
            )
            break
        except BadRequest as exc:
            if exc.status in _RETRYABLE_STATUS and retry_count < 2:
                retry_count += 1
                await asyncio.sleep(3.0 * retry_count)
                continue
            if not fallback_used:
                adjusted = fallback_payload(
                    attempt_payload, exc.body
                )
                if adjusted is not None:
                    fallback_used = True
                    attempt_payload = adjusted
                    continue
            raise LLMError(_http_error(label, exc)) from exc
        except httpx.ReadTimeout as exc:
            raise LLMError(timeout_message(label, seconds)) from exc
        except httpx.HTTPError as exc:
            raise LLMError(_connection_message(exc, label)) from exc

    if not content:
        raise LLMError(f"{label} returned an empty response.")
    return content


def timeout_message(
    label: str = "LM Studio", seconds: float | None = None
) -> str:
    wait = int(seconds or settings.lm_timeout)
    if label == "LM Studio":
        return (
            f"LM Studio stopped sending tokens for {wait}s. "
            "The model may still be loading or be too large for this machine. "
            "Try a smaller model, or raise LM_TIMEOUT in backend/.env."
        )
    return (
        f"{label} (public model) stopped sending tokens for {wait}s. "
        "The public endpoint may be busy. Try again, or connect a local model."
    )


def _connection_message(exc: Exception, label: str = "LM Studio") -> str:
    if label == "LM Studio":
        return (
            f"Request to LM Studio failed ({exc.__class__.__name__}). "
            "Check that the local server is still running."
        )
    return (
        f"Could not reach {label} (public model) "
        f"({exc.__class__.__name__}). "
        "Check your network, or connect a local model."
    )


def extract_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("could not parse JSON from model output")


async def chat_json(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1200,
    schema: dict[str, Any] | None = None,
    *,
    url: str | None = None,
    headers: dict[str, str] | None = None,
    label: str = "LM Studio",
    timeout_seconds: float | None = None,
) -> Any:
    raw = await chat(
        client,
        model,
        system,
        user,
        max_tokens=max_tokens,
        schema=schema,
        url=url,
        headers=headers,
        label=label,
        timeout_seconds=timeout_seconds,
    )
    try:
        return extract_json(raw)
    except ValueError:
        retry_user = (
            f"{user}\n\nYour previous reply could not be parsed as JSON. "
            "Reply with ONLY the requested JSON object and nothing else."
        )
        raw = await chat(
            client,
            model,
            system,
            retry_user,
            max_tokens=max_tokens,
            schema=schema,
            url=url,
            headers=headers,
            label=label,
            timeout_seconds=timeout_seconds,
        )
        return extract_json(raw)


class DirectLLM:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.label = f"LM Studio at {settings.lm_studio_url}"

    async def list_models(self) -> list[str]:
        return await list_models(self.client)

    async def resolve_model(self) -> str:
        return await resolve_model(self.client)

    async def chat(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1200,
        schema: dict[str, Any] | None = None,
    ) -> str:
        return await chat(
            self.client,
            model,
            system,
            user,
            max_tokens=max_tokens,
            schema=schema,
        )

    async def chat_json(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1200,
        schema: dict[str, Any] | None = None,
    ) -> Any:
        return await chat_json(
            self.client,
            model,
            system,
            user,
            max_tokens=max_tokens,
            schema=schema,
        )


class PublicLLM:
    """OpenAI-compatible public endpoint, keyless by default."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.model = settings.public_llm_model
        self.label = f"{settings.public_llm_label} ({self.model})"

    def _headers(self) -> dict[str, str] | None:
        if settings.public_llm_api_key:
            return {
                "Authorization": f"Bearer {settings.public_llm_api_key}"
            }
        return None

    async def list_models(self) -> list[str]:
        return [self.model] if self.model else []

    async def resolve_model(self) -> str:
        if not self.model:
            raise LLMError(
                "No PUBLIC_LLM_MODEL is configured. Set it in backend/.env "
                "or connect a local model."
            )
        return self.model

    async def chat(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1200,
        schema: dict[str, Any] | None = None,
    ) -> str:
        async with _PUBLIC_LOCK:
            return await chat(
                self.client,
                model or self.model,
                system,
                user,
                max_tokens=max_tokens,
                schema=schema,
                url=settings.public_llm_url,
                headers=self._headers(),
                label=settings.public_llm_label,
                timeout_seconds=settings.public_llm_timeout,
            )

    async def chat_json(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1200,
        schema: dict[str, Any] | None = None,
    ) -> Any:
        async with _PUBLIC_LOCK:
            return await chat_json(
                self.client,
                model or self.model,
                system,
                user,
                max_tokens=max_tokens,
                schema=schema,
                url=settings.public_llm_url,
                headers=self._headers(),
                label=settings.public_llm_label,
                timeout_seconds=settings.public_llm_timeout,
            )
