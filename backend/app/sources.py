from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
from typing import Any
from urllib.parse import urlparse

import feedparser
import httpx

from .config import settings

BUILTIN_SOURCES: list[dict[str, Any]] = [
    {
        "id": "wikipedia",
        "label": "Wikipedia",
        "description": "Search and read full encyclopedia articles.",
        "kind": "encyclopedia",
    },
    {
        "id": "google_news",
        "label": "Google News",
        "description": "Keyless news search; provides headlines and snippets.",
        "kind": "news",
    },
    {
        "id": "bing_news",
        "label": "Bing News",
        "description": "Keyless news search with direct publisher links.",
        "kind": "news",
    },
]

_BUILTIN_IDS = {item["id"] for item in BUILTIN_SOURCES}
_BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "ip6-localhost"}


class SourceError(ValueError):
    pass


def _normalize_url(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise SourceError("Enter a feed URL.")
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    return cleaned


def _feed_id(url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"rss-{digest}"


PRESET_FEEDS: list[dict[str, str]] = [
    {"label": "Snopes", "url": "https://www.snopes.com/feed/"},
    {"label": "PolitiFact", "url": "https://www.politifact.com/rss/"},
    {
        "label": "BBC World",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
    },
    {"label": "NPR Top Stories", "url": "https://feeds.npr.org/1001/rss.xml"},
    {"label": "Nature", "url": "https://www.nature.com/nature.rss"},
]


def _blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not ip.is_global


def _host_literal_blocked(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    if lowered in _BLOCKED_HOSTS or lowered.endswith(".local"):
        return True
    try:
        return _blocked_ip(ipaddress.ip_address(lowered))
    except ValueError:
        return False


async def _assert_public_host(host: str) -> None:
    if _host_literal_blocked(host):
        raise SourceError("That feed address is not allowed.")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except OSError as exc:
        raise SourceError("Could not resolve that feed address.") from exc
    for info in infos:
        address = str(info[4][0]).split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if _blocked_ip(ip):
            raise SourceError("That feed address is not allowed.")


async def _validate_feed_url(value: str) -> tuple[str, str]:
    url = _normalize_url(value)
    parts = urlparse(url)
    if parts.scheme not in {"http", "https"}:
        raise SourceError("Feed URLs must start with http:// or https://.")
    if not parts.hostname:
        raise SourceError("That does not look like a valid feed URL.")
    if parts.username or parts.password:
        raise SourceError("Feed URLs cannot include a username or password.")
    await _assert_public_host(parts.hostname)
    return url, parts.hostname


async def _verify_feed(url: str) -> None:
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": settings.user_agent},
            timeout=min(settings.fetch_timeout, 12.0),
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SourceError(
            "Could not reach that feed. Check the URL and try again."
        ) from exc

    parsed = feedparser.parse(resp.content)
    if not parsed.entries:
        raise SourceError(
            "No RSS or Atom entries were found at that URL."
        )


class SourceStore:
    def __init__(self) -> None:
        self._loaded = False
        self.disabled: set[str] = set()
        self.custom: list[dict[str, Any]] = []

    @property
    def path(self):
        return settings.cache_dir / "sources.json"

    def _seed_presets(self) -> None:
        existing_ids = {source["id"] for source in self.custom}
        existing_urls = {source["url"] for source in self.custom}
        changed = False
        for preset in PRESET_FEEDS:
            url = preset["url"]
            source_id = _feed_id(url)
            if source_id in existing_ids or url in existing_urls:
                for source in self.custom:
                    if source["id"] == source_id or source["url"] == url:
                        if not source.get("locked"):
                            source["locked"] = True
                            changed = True
                continue
            self.custom.append(
                {
                    "id": source_id,
                    "label": preset["label"],
                    "url": url,
                    "enabled": True,
                    "locked": True,
                }
            )
            existing_ids.add(source_id)
            existing_urls.add(url)
            changed = True
        if changed:
            self._persist()

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            if not settings.enable_bing_news:
                self.disabled.add("bing_news")
            self._seed_presets()
            return
        try:
            data = json.loads(
                self.path.read_text(encoding="utf-8-sig")
            )
        except (OSError, ValueError):
            data = {}

        disabled = data.get("disabled") or []
        self.disabled = {
            str(item)
            for item in disabled
            if isinstance(item, str) and item in _BUILTIN_IDS
        }

        for raw in data.get("custom") or []:
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or "").strip()
            source_id = str(raw.get("id") or "").strip()
            if not url or not source_id:
                continue
            self.custom.append(
                {
                    "id": source_id,
                    "label": str(raw.get("label") or "Custom feed").strip()
                    or "Custom feed",
                    "url": url,
                    "enabled": bool(raw.get("enabled", True)),
                    "locked": bool(raw.get("locked", False)),
                }
            )
        self._seed_presets()

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"disabled": sorted(self.disabled), "custom": self.custom}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def snapshot(self) -> dict[str, Any]:
        self._load()
        items: list[dict[str, Any]] = []
        for source in BUILTIN_SOURCES:
            items.append(
                {
                    **source,
                    "builtin": True,
                    "enabled": source["id"] not in self.disabled,
                }
            )
        for source in self.custom:
            items.append(
                {
                    "id": source["id"],
                    "label": source["label"],
                    "description": source["url"],
                    "kind": "news",
                    "builtin": False,
                    "enabled": bool(source.get("enabled", True)),
                    "locked": bool(source.get("locked", False)),
                    "url": source["url"],
                }
            )
        return {
            "sources": items,
            "enabled_count": sum(1 for item in items if item["enabled"]),
            "max_custom": settings.max_custom_sources,
        }

    def retrieval_config(self) -> dict[str, Any]:
        self._load()
        return {
            "enabled": [
                source["id"]
                for source in BUILTIN_SOURCES
                if source["id"] not in self.disabled
            ],
            "custom": [
                {
                    "id": source["id"],
                    "label": source["label"],
                    "url": source["url"],
                }
                for source in self.custom
                if source.get("enabled", True)
            ],
        }

    async def add(self, url: str, label: str = "") -> dict[str, Any]:
        self._load()
        if len(self.custom) >= settings.max_custom_sources:
            raise SourceError(
                f"You can add up to {settings.max_custom_sources} custom feeds."
            )
        normalized_url, host = await _validate_feed_url(url)
        if any(source["url"] == normalized_url for source in self.custom):
            raise SourceError("That feed has already been added.")
        await _verify_feed(normalized_url)

        cleaned_label = " ".join(str(label or "").split())[:80]
        self.custom.append(
            {
                "id": _feed_id(normalized_url),
                "label": cleaned_label or host,
                "url": normalized_url,
                "enabled": True,
                "locked": False,
            }
        )
        self._persist()
        return self.snapshot()

    def set_enabled(self, source_id: str, enabled: bool) -> dict[str, Any]:
        self._load()
        if source_id in _BUILTIN_IDS:
            if enabled:
                self.disabled.discard(source_id)
            else:
                self.disabled.add(source_id)
            self._persist()
            return self.snapshot()
        for source in self.custom:
            if source["id"] == source_id:
                source["enabled"] = bool(enabled)
                self._persist()
                return self.snapshot()
        raise KeyError(source_id)

    def remove(self, source_id: str) -> dict[str, Any]:
        self._load()
        if source_id in _BUILTIN_IDS:
            raise SourceError("Built-in sources cannot be removed.")
        for index, source in enumerate(self.custom):
            if source["id"] == source_id:
                if source.get("locked"):
                    raise SourceError(
                        "This preset feed can be toggled but not removed."
                    )
                self.custom.pop(index)
                self._persist()
                return self.snapshot()
        raise KeyError(source_id)


store = SourceStore()
