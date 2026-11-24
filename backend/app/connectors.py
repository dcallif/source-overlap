from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import WebSocket

from . import llm
from .config import settings


class BridgeError(RuntimeError):
    def __init__(
        self, message: str, status: int | None = None, body: str = ""
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_code(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


class Connector:
    def __init__(self, websocket: WebSocket, session_id: str) -> None:
        self.websocket = websocket
        self.session_id = session_id
        self.models: list[str] = []
        self.lm_studio = False
        self.last_error: str | None = None
        self.pending: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self.closed = False
        self._send_lock = asyncio.Lock()

    async def send(self, message: dict[str, Any]) -> None:
        async with self._send_lock:
            await self.websocket.send_json(message)

    def feed(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type in {"heartbeat", "status"}:
            self.lm_studio = bool(message.get("lm_studio"))
            self.models = [str(item) for item in message.get("models") or []]
            self.last_error = message.get("error") or None

        request_id = message.get("id")
        if request_id:
            queue = self.pending.get(str(request_id))
            if queue:
                queue.put_nowait(message)

    def fail_pending(self, message: str) -> None:
        self.closed = True
        for queue in list(self.pending.values()):
            queue.put_nowait(
                {"type": "error", "message": message, "status": None}
            )

    async def close(self, reason: str = "Connector replaced") -> None:
        self.fail_pending(reason)
        try:
            await self.websocket.close(code=1012, reason=reason)
        except Exception:
            pass

    async def open_http(
        self,
        path: str,
        body: dict[str, Any] | None,
        timeout: float,
    ) -> tuple[int, str, AsyncIterator[str]]:
        if self.closed:
            raise BridgeError("Your local model connector is not connected.")

        request_id = secrets.token_hex(8)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.pending[request_id] = queue

        try:
            await self.send(
                {
                    "type": "http",
                    "id": request_id,
                    "method": "POST" if body is not None else "GET",
                    "path": path,
                    "body": body,
                }
            )
        except Exception as exc:
            self.pending.pop(request_id, None)
            raise BridgeError(
                "Lost the connection to your local model connector."
            ) from exc

        start_timeout = min(timeout, 30.0)
        try:
            first = await asyncio.wait_for(queue.get(), start_timeout)
        except asyncio.TimeoutError as exc:
            self.pending.pop(request_id, None)
            raise BridgeError(
                "Your local model did not respond in time. "
                "Check that LM Studio is still running."
            ) from exc

        if first.get("type") == "error":
            self.pending.pop(request_id, None)
            raise BridgeError(
                str(first.get("message") or "Local model request failed."),
                status=first.get("status"),
                body=str(first.get("body") or ""),
            )
        if first.get("type") != "start":
            self.pending.pop(request_id, None)
            raise BridgeError("Your local model connector sent an invalid response.")

        status = int(first.get("status") or 0)
        content_type = str(first.get("content_type") or "")

        async def chunks() -> AsyncIterator[str]:
            finished = False
            try:
                while True:
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout)
                    except asyncio.TimeoutError as exc:
                        raise BridgeError(
                            f"Your local model stopped sending tokens for "
                            f"{int(timeout)}s. The model may still be loading, "
                            "or it may be too large for this machine."
                        ) from exc
                    message_type = message.get("type")
                    if message_type == "chunk":
                        yield str(message.get("data") or "")
                    elif message_type == "end":
                        finished = True
                        break
                    elif message_type == "error":
                        finished = True
                        raise BridgeError(
                            str(
                                message.get("message")
                                or "Local model request failed."
                            ),
                            status=message.get("status"),
                            body=str(message.get("body") or ""),
                        )
            finally:
                self.pending.pop(request_id, None)
                if not finished:
                    try:
                        await self.send({"type": "cancel", "id": request_id})
                    except Exception:
                        pass

        return status, content_type, chunks()


class BridgeLLM:
    label = "your local LM Studio"

    def __init__(
        self, connector: Connector, selected_model: str | None = None
    ) -> None:
        self.connector = connector
        self.selected_model = selected_model

    async def list_models(self) -> list[str]:
        return list(self.connector.models)

    async def resolve_model(self) -> str:
        models = await self.list_models()
        if self.selected_model and self.selected_model in models:
            return self.selected_model
        if not models:
            raise llm.LLMError(
                self.connector.last_error
                or "LM Studio is not running or no model is loaded."
            )
        return llm.pick_model(models)

    async def _stream_chat(
        self, payload: dict[str, Any], timeout: float
    ) -> str:
        try:
            status, content_type, chunks = await self.connector.open_http(
                "/v1/chat/completions", payload, timeout
            )
        except BridgeError as exc:
            if exc.status and 400 <= int(exc.status) < 500:
                raise llm.BadRequest(int(exc.status), exc.body or str(exc))
            raise llm.LLMError(str(exc)) from exc

        if status >= 400:
            body = "".join([chunk async for chunk in chunks])[:500]
            raise llm.BadRequest(status, body)

        try:
            return await llm.consume_chat_chunks(content_type, chunks)
        except BridgeError as exc:
            raise llm.LLMError(str(exc)) from exc

    async def chat(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1200,
        schema: dict[str, Any] | None = None,
    ) -> str:
        payload = llm.build_payload(model, system, user, max_tokens, schema)
        timeout = settings.lm_timeout
        try:
            content = await self._stream_chat(payload, timeout)
        except llm.BadRequest as exc:
            adjusted = llm.fallback_payload(payload, exc.body)
            if adjusted is None:
                raise llm.LLMError(
                    f"LM Studio returned HTTP {exc.status}: {exc.body}"
                ) from exc
            try:
                content = await self._stream_chat(adjusted, timeout)
            except llm.BadRequest as retry_exc:
                raise llm.LLMError(
                    f"LM Studio returned HTTP {retry_exc.status}: "
                    f"{retry_exc.body}"
                ) from retry_exc
        if not content:
            raise llm.LLMError("LM Studio returned an empty response.")
        return content

    async def chat_json(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1200,
        schema: dict[str, Any] | None = None,
    ) -> Any:
        raw = await self.chat(
            model, system, user, max_tokens=max_tokens, schema=schema
        )
        try:
            return llm.extract_json(raw)
        except ValueError:
            retry_user = (
                f"{user}\n\nYour previous reply could not be parsed as JSON. "
                "Reply with ONLY the requested JSON object and nothing else."
            )
            raw = await self.chat(
                model,
                system,
                retry_user,
                max_tokens=max_tokens,
                schema=schema,
            )
            return llm.extract_json(raw)


class Session:
    def __init__(self) -> None:
        self.id = secrets.token_urlsafe(24)
        self.created_at = time.time()
        self.last_seen = self.created_at
        self.pairing_hash: str | None = None
        self.pairing_expires = 0.0
        self.connector_token_hash: str | None = None
        self.connector: Connector | None = None
        self.selected_model: str | None = None

    def touch(self) -> None:
        self.last_seen = time.time()

    def new_pairing_code(self) -> str:
        raw = secrets.token_hex(4).upper()
        code = f"{raw[:4]}-{raw[4:]}"
        self.pairing_hash = _hash(_normalize_code(code))
        self.pairing_expires = time.time() + settings.pairing_ttl_seconds
        return code

    def issue_token(self) -> str:
        token = secrets.token_urlsafe(32)
        self.connector_token_hash = _hash(token)
        return token

    def verify_pairing(self, code: str) -> bool:
        if not self.pairing_hash:
            return False
        if time.time() > self.pairing_expires:
            self.pairing_hash = None
            return False
        if not secrets.compare_digest(
            self.pairing_hash, _hash(_normalize_code(code))
        ):
            return False
        self.pairing_hash = None
        self.pairing_expires = 0.0
        return True

    def verify_token(self, token: str) -> bool:
        return bool(
            self.connector_token_hash
            and secrets.compare_digest(self.connector_token_hash, _hash(token))
        )

    def status(self) -> dict[str, Any]:
        connector = self.connector
        models = list(connector.models) if connector else []
        if self.selected_model and self.selected_model not in models:
            resolved = None
        else:
            resolved = self.selected_model
        if resolved is None and models:
            try:
                resolved = llm.pick_model(models)
            except llm.LLMError:
                resolved = None
        return {
            "connected": connector is not None and not connector.closed,
            "lm_studio": bool(connector and connector.lm_studio),
            "models": models,
            "model": resolved,
            "selected_model": self.selected_model,
            "last_error": connector.last_error if connector else None,
            "requires_connector": settings.require_connector,
            "llm_provider": settings.llm_provider,
            "public_llm": llm.public_info(),
            "project_url": settings.project_url,
        }


class SessionRegistry:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.pairing_index: dict[str, str] = {}
        self.token_index: dict[str, str] = {}

    def _prune(self) -> None:
        now = time.time()
        for session_id, session in list(self.sessions.items()):
            if now - session.last_seen > settings.session_ttl_seconds:
                self.sessions.pop(session_id, None)
                if session.pairing_hash:
                    self.pairing_index.pop(session.pairing_hash, None)
                if session.connector_token_hash:
                    self.token_index.pop(session.connector_token_hash, None)
        for code_hash, session_id in list(self.pairing_index.items()):
            session = self.sessions.get(session_id)
            if session is None or time.time() > session.pairing_expires:
                self.pairing_index.pop(code_hash, None)

    def get(self, session_id: str | None) -> Session | None:
        self._prune()
        if not session_id:
            return None
        session = self.sessions.get(session_id)
        if session:
            session.touch()
        return session

    def create(self) -> Session:
        self._prune()
        session = Session()
        self.sessions[session.id] = session
        return session

    def make_pairing(self, session: Session) -> tuple[str, float]:
        if session.pairing_hash:
            self.pairing_index.pop(session.pairing_hash, None)
        code = session.new_pairing_code()
        if session.pairing_hash:
            self.pairing_index[session.pairing_hash] = session.id
        return code, session.pairing_expires

    def pair(self, code: str) -> tuple[Session | None, str | None]:
        self._prune()
        code_hash = _hash(_normalize_code(code))
        session_id = self.pairing_index.pop(code_hash, None)
        if not session_id:
            return None, None
        session = self.sessions.get(session_id)
        if not session or not session.verify_pairing(code):
            return None, None
        if session.connector_token_hash:
            self.token_index.pop(session.connector_token_hash, None)
        token = session.issue_token()
        if session.connector_token_hash:
            self.token_index[session.connector_token_hash] = session.id
        session.touch()
        return session, token

    def resume(self, token: str) -> tuple[Session | None, str | None]:
        self._prune()
        token_hash = _hash(token)
        session_id = self.token_index.pop(token_hash, None)
        if not session_id:
            return None, None
        session = self.sessions.get(session_id)
        if not session or not session.verify_token(token):
            return None, None
        if session.connector_token_hash:
            self.token_index.pop(session.connector_token_hash, None)
        new_token = session.issue_token()
        if session.connector_token_hash:
            self.token_index[session.connector_token_hash] = session.id
        session.touch()
        return session, new_token

    def revoke_token(self, session: Session) -> None:
        if session.connector_token_hash:
            self.token_index.pop(session.connector_token_hash, None)
        session.connector_token_hash = None

    def detach(self, session: Session, connector: Connector) -> None:
        if session.connector is connector:
            session.connector = None
        connector.fail_pending("The local model connector disconnected.")


registry = SessionRegistry()


def pairing_expiry_iso(expires: float) -> str:
    return datetime.fromtimestamp(expires, timezone.utc).isoformat()
