from __future__ import annotations

import copy
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx

from . import analysis, llm, retrieval
from .config import settings

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]


async def _noop(_: dict[str, Any]) -> None:
    return None


CACHE_VERSION = "2"
_MEMORY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_MEMORY_CACHE_LIMIT = 128


def _cache_key(question: str, max_sources: int, extra: str = "") -> str:
    payload = (
        f"v{CACHE_VERSION}|{' '.join(question.lower().split())}|{max_sources}"
        f"|{extra}"
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _read_cache(key: str) -> dict[str, Any] | None:
    if settings.cache_ttl_seconds <= 0:
        return None
    path = settings.cache_dir / f"{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    age = time.time() - data.get("cached_at", 0)
    if age > settings.cache_ttl_seconds:
        return None
    return data.get("result")


def _write_cache(key: str, result: dict[str, Any]) -> None:
    if settings.cache_ttl_seconds <= 0:
        return
    path = settings.cache_dir / f"{key}.json"
    try:
        path.write_text(
            json.dumps({"cached_at": time.time(), "result": result}),
            encoding="utf-8",
        )
    except OSError:
        pass


def _memory_read(key: str) -> dict[str, Any] | None:
    if settings.cache_ttl_seconds <= 0:
        return None
    entry = _MEMORY_CACHE.get(key)
    if not entry:
        return None
    cached_at, result = entry
    if time.time() - cached_at > settings.cache_ttl_seconds:
        _MEMORY_CACHE.pop(key, None)
        return None
    return copy.deepcopy(result)


def _memory_write(key: str, result: dict[str, Any]) -> None:
    if settings.cache_ttl_seconds <= 0:
        return
    now = time.time()
    for stale_key, (cached_at, _) in list(_MEMORY_CACHE.items()):
        if now - cached_at > settings.cache_ttl_seconds:
            _MEMORY_CACHE.pop(stale_key, None)
    if len(_MEMORY_CACHE) >= _MEMORY_CACHE_LIMIT:
        oldest = min(_MEMORY_CACHE, key=lambda item: _MEMORY_CACHE[item][0])
        _MEMORY_CACHE.pop(oldest, None)
    _MEMORY_CACHE[key] = (now, copy.deepcopy(result))


async def run_pipeline(
    question: str,
    max_sources: int | None = None,
    refresh: bool = False,
    emit: EmitFn | None = None,
    backend: llm.LLMBackend | None = None,
    cache_scope: str | None = None,
) -> dict[str, Any]:
    emit = emit or _noop
    question = " ".join(question.split())
    limit = max(2, min(12, max_sources or settings.max_sources))
    key = _cache_key(question, limit)
    scoped_key: str | None = None

    if cache_scope is None and not refresh:
        cached = _read_cache(key)
        if cached:
            await emit(
                {
                    "type": "status",
                    "stage": "cached",
                    "message": "Loaded a cached result (add refresh to re-run)",
                }
            )
            cached["meta"]["cached"] = True
            return cached

    started = time.time()
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.fetch_timeout,
    ) as client:
        llm_backend = backend or llm.DirectLLM(client)
        await emit(
            {
                "type": "status",
                "stage": "connecting",
                "message": f"Connecting to {llm_backend.label}",
            }
        )
        model = await llm_backend.resolve_model()

        if cache_scope is not None:
            scoped_key = _cache_key(question, limit, f"{cache_scope}|{model}")
            if not refresh:
                cached = _memory_read(scoped_key)
                if cached:
                    await emit(
                        {
                            "type": "status",
                            "stage": "cached",
                            "message": (
                                "Loaded a cached result for this model "
                                "(add refresh to re-run)"
                            ),
                        }
                    )
                    cached["meta"]["cached"] = True
                    return cached

        await emit(
            {
                "type": "status",
                "stage": "planning",
                "message": f"Decomposing the question with {model}",
            }
        )
        claims, queries = await analysis.decompose(
            llm_backend, model, question
        )
        await emit(
            {
                "type": "status",
                "stage": "planning",
                "message": (
                    f"Split into {len(claims)} claim(s); "
                    f"searching {len(queries)} query variant(s)"
                ),
            }
        )

        sources = await retrieval.gather_sources(
            client, question, queries, claims, limit, emit
        )

        stances: list[dict[str, Any]] = []
        warnings: list[str] = []
        if sources:
            await emit(
                {
                    "type": "status",
                    "stage": "judging",
                    "message": f"Judging {len(sources)} sources against each claim",
                    "progress": 0,
                    "total": len(sources),
                }
            )
            stances, warnings = await analysis.judge_all(
                llm_backend, model, sources, claims, emit
            )

    elapsed_ms = int((time.time() - started) * 1000)
    result = analysis.aggregate(
        question,
        sources,
        claims,
        stances,
        {
            "model": model,
            "provider": llm_backend.label,
            "sources_requested": limit,
            "sources_retrieved": len(sources),
            "elapsed_ms": elapsed_ms,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "queries": queries,
            "cached": False,
        },
        warnings=warnings,
    )
    result["meta"]["disclaimer"] = result["verdict"].get("disclaimer", "")
    if cache_scope is None:
        _write_cache(key, result)
    elif scoped_key is not None:
        _memory_write(scoped_key, result)
    await emit({"type": "status", "stage": "done", "message": "Analysis complete"})
    return result
