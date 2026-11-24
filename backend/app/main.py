from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import connectors, llm, service, sources
from .config import settings

app = FastAPI(title="Source Overlap", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    max_sources: int | None = Field(default=None, ge=2, le=12)
    refresh: bool = False

    @field_validator("question")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 3:
            raise ValueError("question is too short")
        return cleaned


class ModelRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)


class SourceAddRequest(BaseModel):
    url: str = Field(min_length=4, max_length=500)
    label: str = Field(default="", max_length=80)


class SourceUpdateRequest(BaseModel):
    enabled: bool


def _session_from_request(
    request: Request, response: Response | None = None
) -> connectors.Session:
    session = connectors.registry.get(
        request.cookies.get(settings.session_cookie_name)
    )
    if session is None:
        session = connectors.registry.create()
        if response is not None:
            response.set_cookie(
                settings.session_cookie_name,
                session.id,
                max_age=settings.session_ttl_seconds,
                httponly=True,
                secure=(
                    settings.session_cookie_secure
                    or request.url.scheme == "https"
                ),
                samesite="lax",
                path="/",
            )
    return session


def _llm_for_session(
    session: connectors.Session | None,
) -> tuple[llm.LLMBackend | None, str | None]:
    if session and session.connector and not session.connector.closed:
        return (
            connectors.BridgeLLM(
                session.connector, session.selected_model
            ),
            session.id,
        )
    if settings.require_connector:
        raise HTTPException(
            status_code=409,
            detail=(
                "Connect your local model first. Open the connection panel "
                "and run the source-overlap-connect command."
            ),
        )
    return None, None


def _origin(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api")
async def root() -> dict[str, Any]:
    return {
        "name": "Source Overlap API",
        "endpoints": [
            "/api/ask",
            "/api/ask/stream",
            "/api/health",
            "/api/models",
            "/api/sources",
            "/api/session/status",
            "/api/session/pairing",
            "/api/connector",
        ],
    }


@app.get("/api/health")
async def health() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            models = await llm.list_models(client)
        except llm.LLMError as exc:
            return {
                "lm_studio": False,
                "url": settings.lm_studio_url,
                "models": [],
                "error": str(exc),
            }
    return {
        "lm_studio": True,
        "url": settings.lm_studio_url,
        "model": settings.lm_studio_model or (models[0] if models else None),
        "models": models,
        "error": None if models else "No model loaded in LM Studio.",
    }


@app.get("/api/models")
async def models() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            items = await llm.list_models(client)
        except llm.LLMError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"models": items}


@app.get("/api/sources")
async def list_sources() -> dict[str, Any]:
    return sources.store.snapshot()


@app.post("/api/sources", status_code=201)
async def add_source(payload: SourceAddRequest) -> dict[str, Any]:
    try:
        return await sources.store.add(payload.url, payload.label)
    except sources.SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/sources/{source_id}")
async def update_source(
    source_id: str, payload: SourceUpdateRequest
) -> dict[str, Any]:
    try:
        return sources.store.set_enabled(source_id, payload.enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown source.") from None


@app.delete("/api/sources/{source_id}")
async def remove_source(source_id: str) -> dict[str, Any]:
    try:
        return sources.store.remove(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown source.") from None
    except sources.SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/session/status")
async def session_status(
    request: Request, response: Response
) -> dict[str, Any]:
    session = _session_from_request(request, response)
    return session.status()


@app.post("/api/session/pairing")
async def session_pairing(
    request: Request, response: Response
) -> dict[str, Any]:
    session = _session_from_request(request, response)
    code, expires = connectors.registry.make_pairing(session)
    origin = _origin(request)
    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    connector_url = f"{ws_scheme}://{request.url.netloc}/api/connector"
    return {
        "code": code,
        "expires_at": connectors.pairing_expiry_iso(expires),
        "connector_url": connector_url,
        "command": (
            f"python -m source_overlap_connector --server {origin} --code {code}"
        ),
    }


@app.post("/api/session/model")
async def session_model(
    payload: ModelRequest, request: Request, response: Response
) -> dict[str, Any]:
    session = _session_from_request(request, response)
    if not session.connector or session.connector.closed:
        raise HTTPException(status_code=409, detail="No local model is connected.")
    if payload.model not in session.connector.models:
        raise HTTPException(
            status_code=400, detail="That model is not loaded in LM Studio."
        )
    session.selected_model = payload.model
    return session.status()


@app.post("/api/session/disconnect")
async def session_disconnect(
    request: Request, response: Response
) -> dict[str, Any]:
    session = _session_from_request(request, response)
    connectors.registry.revoke_token(session)
    if session.connector:
        await session.connector.close("Disconnected from the app")
        session.connector = None
    session.selected_model = None
    return session.status()


@app.websocket("/api/connector")
async def connector_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=15.0)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
        await websocket.close(code=4400, reason="Connector handshake timed out.")
        return

    if not isinstance(first, dict):
        await websocket.close(code=4400, reason="Invalid connector handshake.")
        return

    if first.get("type") == "pair":
        session, token = connectors.registry.pair(str(first.get("code") or ""))
    elif first.get("type") == "resume":
        session, token = connectors.registry.resume(
            str(first.get("token") or "")
        )
    else:
        session, token = None, None

    if session is None or token is None:
        await websocket.close(
            code=4401,
            reason="Pairing expired. Open the app again for a new code.",
        )
        return

    if session.connector:
        await session.connector.close("Replaced by a new connector")

    connector = connectors.Connector(websocket, session.id)
    connector.feed(
        {
            "type": "status",
            "lm_studio": first.get("lm_studio"),
            "models": first.get("models") or [],
            "error": first.get("error"),
        }
    )
    session.connector = connector
    session.touch()

    try:
        await connector.send(
            {
                "type": "ready",
                "token": token,
                "heartbeat_seconds": 25,
                "session_id": session.id,
            }
        )
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict):
                connector.feed(message)
                session.touch()
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        connectors.registry.detach(session, connector)


@app.post("/api/ask")
async def ask(request: AskRequest, http_request: Request) -> dict[str, Any]:
    session = connectors.registry.get(
        http_request.cookies.get(settings.session_cookie_name)
    )
    backend, scope = _llm_for_session(session)
    try:
        return await service.run_pipeline(
            request.question,
            request.max_sources,
            request.refresh,
            backend=backend,
            cache_scope=scope,
            source_config=sources.store.retrieval_config(),
        )
    except llm.LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/ask/stream")
async def ask_stream(
    request: AskRequest, http_request: Request
) -> StreamingResponse:
    session = connectors.registry.get(
        http_request.cookies.get(settings.session_cookie_name)
    )
    backend, scope = _llm_for_session(session)

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def runner() -> None:
        try:
            result = await service.run_pipeline(
                request.question,
                request.max_sources,
                request.refresh,
                emit,
                backend=backend,
                cache_scope=scope,
                source_config=sources.store.retrieval_config(),
            )
            await queue.put({"type": "result", "data": result})
        except llm.LLMError as exc:
            await queue.put({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001 - surface errors to the client
            await queue.put(
                {"type": "error", "message": f"Unexpected error: {exc}"}
            )
        finally:
            await queue.put(None)

    async def stream():
        task = asyncio.create_task(runner())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield json.dumps(event, default=str) + "\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _serve_frontend() -> None:
    dist = Path(settings.frontend_dist)
    index = dist / "index.html"
    if not index.exists():
        return
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError:
            raise HTTPException(status_code=404) from None
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


_serve_frontend()
