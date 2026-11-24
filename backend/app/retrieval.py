from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from .config import settings

EventFn = Callable[[dict[str, Any]], Awaitable[None]]

WIKI_API = "https://en.wikipedia.org/w/api.php"
GOOGLE_NEWS = "https://news.google.com/rss/search"
BING_NEWS = "https://www.bing.com/news/search"

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "about",
    "after",
    "all",
    "also",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "between",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "might",
    "must",
    "not",
    "of",
    "on",
    "or",
    "our",
    "over",
    "should",
    "that",
    "the",
    "their",
    "them",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
}

_TIME_CUES = {
    "announced",
    "appointed",
    "cast",
    "casting",
    "confirmed",
    "current",
    "currently",
    "dead",
    "elected",
    "latest",
    "launched",
    "lost",
    "new",
    "next",
    "now",
    "release",
    "released",
    "resigned",
    "signed",
    "status",
    "today",
    "update",
    "won",
    "2024",
    "2025",
    "2026",
    "2027",
    "2028",
}

_STRIP_TAGS = [
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "svg",
    "iframe",
    "figure",
]


def _headers() -> dict[str, str]:
    return {"User-Agent": settings.user_agent, "Accept-Language": "en-US,en;q=0.9"}


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _iso_from_struct(entry: Any) -> Optional[str]:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        dt = datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
        return dt.isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _source_from_rss(
    entry: Any, fallback_title: str, default_publisher: str = "News"
) -> str:
    news_source = entry.get("news_source")
    if isinstance(news_source, str) and news_source.strip():
        return _clean(news_source)
    src = entry.get("source")
    if isinstance(src, dict) and src.get("title"):
        return _clean(src["title"])
    if " - " in fallback_title:
        return _clean(fallback_title.rsplit(" - ", 1)[-1])
    return default_publisher


def _strip_publisher_suffix(title: str, publisher: str) -> str:
    suffix = f" - {publisher}"
    if title.endswith(suffix):
        return title[: -len(suffix)].strip()
    return title


def _norm_url(url: str) -> str:
    try:
        parts = urlparse(url)
    except ValueError:
        return url
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    return f"{host}{path}" or url.lower()


def _dedupe_key(source: dict[str, Any]) -> str:
    url = source.get("url") or ""
    if url:
        return _norm_url(url)
    return _clean(source.get("title", "")).lower()


def _tokens(text: str) -> set[str]:
    return {
        word
        for word in _WORD_RE.findall((text or "").lower())
        if len(word) >= 3 and word not in _STOPWORDS
    }


def _focus_terms(question: str, claims: list[dict[str, Any]]) -> set[str]:
    parts = [question]
    parts.extend(str(claim.get("text", "")) for claim in claims)
    return _tokens(" ".join(parts))


def _is_time_sensitive(question: str) -> bool:
    return bool(_tokens(question) & _TIME_CUES)


def _relevance(
    source: dict[str, Any], focus: set[str], time_sensitive: bool
) -> float:
    if not focus:
        return 0.0
    title_terms = _tokens(source.get("title", ""))
    body_terms = _tokens(source.get("text", ""))
    title_hits = len(focus & title_terms)
    body_hits = len(focus & body_terms)
    combined = focus & (title_terms | body_terms)
    score = (2.0 * title_hits + body_hits) / (2.0 * len(focus))
    score += len(combined) / len(focus)
    if title_hits == 0:
        score *= 0.5
    if time_sensitive and source.get("kind") == "news":
        score += 0.15
    return round(score, 4)


def _publisher_key(source: dict[str, Any]) -> str:
    return _clean(source.get("publisher", "")).lower()


def _select_diverse(
    ranked: list[dict[str, Any]],
    max_sources: int,
    max_per_publisher: int = 2,
    max_wiki: int = 2,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    chosen: set[int] = set()
    per_publisher: dict[str, int] = defaultdict(int)
    wiki_count = 0

    best_wiki = next(
        (
            source
            for source in ranked
            if source.get("kind") == "encyclopedia"
            and source.get("relevance", 0.0) >= 0.4
        ),
        None,
    )
    if best_wiki is not None and max_sources > 0:
        selected.append(best_wiki)
        chosen.add(id(best_wiki))
        per_publisher[_publisher_key(best_wiki)] += 1
        wiki_count = 1

    for source in ranked:
        if len(selected) >= max_sources:
            break
        if id(source) in chosen:
            continue
        publisher = _publisher_key(source)
        if per_publisher[publisher] >= max_per_publisher:
            continue
        if source.get("kind") == "encyclopedia" and wiki_count >= max_wiki:
            continue
        selected.append(source)
        chosen.add(id(source))
        per_publisher[publisher] += 1
        if source.get("kind") == "encyclopedia":
            wiki_count += 1

    if len(selected) < max_sources:
        for source in ranked:
            if id(source) in chosen:
                continue
            selected.append(source)
            chosen.add(id(source))
            if len(selected) >= max_sources:
                break
    return selected


def extract_article_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    container = soup.find("article") or soup.body or soup
    paragraphs = [
        _clean(p.get_text(" ", strip=True)) for p in container.find_all("p")
    ]
    text = "\n".join(p for p in paragraphs if len(p) > 40)
    if len(text) < 200:
        text = _clean(container.get_text(" ", strip=True))
    return text


async def search_wikipedia(
    client: httpx.AsyncClient, query: str, limit: int = 2
) -> list[dict[str, Any]]:
    try:
        resp = await client.get(
            WIKI_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
                "srprop": "snippet",
                "format": "json",
            },
            headers=_headers(),
            timeout=settings.fetch_timeout,
        )
        resp.raise_for_status()
        hits = resp.json().get("query", {}).get("search", [])
    except (httpx.HTTPError, ValueError):
        return []

    titles = [h.get("title") for h in hits if h.get("title")]
    if not titles:
        return []

    async def fetch_extract(title: str) -> dict[str, Any] | None:
        try:
            resp = await client.get(
                WIKI_API,
                params={
                    "action": "query",
                    "prop": "extracts",
                    "explaintext": 1,
                    "exsectionformat": "plain",
                    "redirects": 1,
                    "titles": title,
                    "format": "json",
                },
                headers=_headers(),
                timeout=settings.fetch_timeout,
            )
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("pages", {})
        except (httpx.HTTPError, ValueError):
            return None

        for page in pages.values():
            page_title = page.get("title") or title
            extract = (page.get("extract") or "").strip()
            if not page_title or len(extract) < 120:
                return None
            return {
                "title": page_title,
                "publisher": "Wikipedia",
                "url": (
                    "https://en.wikipedia.org/wiki/"
                    + quote(page_title.replace(" ", "_"))
                ),
                "kind": "encyclopedia",
                "published": None,
                "text": extract[:9000],
                "provider": "wikipedia",
                "provider_label": "Wikipedia",
            }
        return None

    results = await asyncio.gather(*(fetch_extract(title) for title in titles))
    return [item for item in results if item]


def _unwrap_bing(link: str) -> str:
    if "bing.com/news/apiclick" not in link:
        return link
    query = parse_qs(urlparse(link).query)
    return unquote(query.get("url", [""])[0]) or link


def _parse_feed(
    raw: bytes,
    unwrap_bing: bool = False,
    *,
    provider_id: str = "news",
    provider_label: str = "News",
    default_publisher: str = "News",
    kind: str = "news",
) -> list[dict[str, Any]]:
    feed = feedparser.parse(raw)
    items: list[dict[str, Any]] = []
    for entry in feed.entries:
        link = entry.get("link") or ""
        if unwrap_bing:
            link = _unwrap_bing(link)
        raw_title = _clean(entry.get("title", ""))
        publisher = _source_from_rss(entry, raw_title, default_publisher)
        title = _strip_publisher_suffix(raw_title, publisher) or raw_title
        summary = _clean(
            BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ")
        )
        if not summary or summary.lower() == title.lower() or title.lower() in summary.lower():
            text = summary or title
        else:
            text = _clean(f"{title}. {summary}")
        if len(text) < 80:
            continue
        items.append(
            {
                "title": title,
                "publisher": publisher,
                "url": link,
                "kind": kind,
                "published": _iso_from_struct(entry),
                "text": text[:4000],
                "provider": provider_id,
                "provider_label": provider_label,
            }
        )
    return items


async def search_google_news(
    client: httpx.AsyncClient, query: str, limit: int = 4
) -> list[dict[str, Any]]:
    try:
        resp = await client.get(
            GOOGLE_NEWS,
            params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
            headers=_headers(),
            timeout=settings.fetch_timeout,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        return []
    return _parse_feed(
        resp.content,
        provider_id="google_news",
        provider_label="Google News",
    )[:limit]


async def search_bing_news(
    client: httpx.AsyncClient, query: str, limit: int = 4
) -> list[dict[str, Any]]:
    try:
        resp = await client.get(
            BING_NEWS,
            params={"q": query, "format": "RSS", "setlang": "en", "cc": "US"},
            headers=_headers(),
            timeout=settings.fetch_timeout,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        return []
    return _parse_feed(
        resp.content,
        unwrap_bing=True,
        provider_id="bing_news",
        provider_label="Bing News",
    )[:limit]


async def search_custom_feed(
    client: httpx.AsyncClient,
    feed: dict[str, Any],
    focus: set[str],
    time_sensitive: bool,
    limit: int = 5,
) -> list[dict[str, Any]]:
    url = str(feed.get("url") or "")
    if not url:
        return []
    try:
        resp = await client.get(
            url,
            headers=_headers(),
            timeout=min(settings.fetch_timeout, 12.0),
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        return []

    label = str(feed.get("label") or "Custom feed")
    items = _parse_feed(
        resp.content,
        provider_id=str(feed.get("id") or "custom"),
        provider_label=label,
        default_publisher=label,
    )
    scored: list[dict[str, Any]] = []
    for item in items:
        score = _relevance(item, focus, time_sensitive)
        if score <= 0:
            continue
        item["relevance"] = score
        scored.append(item)
    scored.sort(key=lambda item: item["relevance"], reverse=True)
    return scored[:limit]


async def enrich_news_source(
    client: httpx.AsyncClient, source: dict[str, Any]
) -> dict[str, Any]:
    url = source.get("url") or ""
    if not url or "news.google.com" in _norm_url(url):
        return source
    try:
        resp = await client.get(
            url,
            headers=_headers(),
            timeout=min(settings.fetch_timeout, 12.0),
            follow_redirects=True,
        )
        final_url = str(resp.url)
        if "news.google.com" in final_url:
            return source
        if resp.status_code >= 400:
            return source
        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type:
            return source
        text = extract_article_text(resp.text)
    except httpx.HTTPError:
        return source

    if len(text) > len(source.get("text", "")) + 200:
        source = {**source, "text": text[:9000], "url": final_url}
    return source


async def gather_sources(
    client: httpx.AsyncClient,
    question: str,
    queries: list[str],
    claims: list[dict[str, Any]],
    max_sources: int,
    emit: EventFn,
    enabled: set[str] | None = None,
    custom_feeds: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    focus = _focus_terms(question, claims)
    time_sensitive = _is_time_sensitive(question)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    if enabled is None:
        enabled = {"wikipedia", "google_news"}
        if settings.enable_bing_news:
            enabled.add("bing_news")

    unique_queries: list[str] = []
    for query in queries:
        cleaned = _clean(query)
        if cleaned and cleaned.lower() not in {q.lower() for q in unique_queries}:
            unique_queries.append(cleaned)

    for query in unique_queries:
        await emit(
            {
                "type": "status",
                "stage": "retrieving",
                "message": f'Searching for "{query}"',
            }
        )
        wiki = (
            await search_wikipedia(client, query, limit=2)
            if "wikipedia" in enabled
            else []
        )
        news = (
            await search_google_news(client, query, limit=5)
            if "google_news" in enabled
            else []
        )
        if "bing_news" in enabled:
            news = news + await search_bing_news(client, query, limit=5)

        for item in wiki + news:
            key = _dedupe_key(item)
            if key in seen:
                continue
            seen.add(key)
            item["relevance"] = _relevance(item, focus, time_sensitive)
            candidates.append(item)

    if custom_feeds:
        await emit(
            {
                "type": "status",
                "stage": "retrieving",
                "message": f"Scanning {len(custom_feeds)} custom feed(s)",
            }
        )
        feed_results = await asyncio.gather(
            *(
                search_custom_feed(client, feed, focus, time_sensitive)
                for feed in custom_feeds
            )
        )
        for group in feed_results:
            for item in group:
                key = _dedupe_key(item)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(item)

    await emit(
        {
            "type": "status",
            "stage": "retrieving",
            "message": (
                f"Retrieved {len(candidates)} candidate sources; "
                "ranking by relevance"
            ),
        }
    )

    candidates.sort(key=lambda item: item["relevance"], reverse=True)
    enrich_budget = min(len(candidates), max_sources * 2)
    head = candidates[:enrich_budget]

    semaphore = asyncio.Semaphore(4)

    async def enrich(index: int) -> tuple[int, dict[str, Any]]:
        async with semaphore:
            return index, await enrich_news_source(client, head[index])

    news_indexes = [i for i, item in enumerate(head) if item["kind"] == "news"]
    if news_indexes:
        for index, item in await asyncio.gather(*(enrich(i) for i in news_indexes)):
            head[index] = item

    for item in candidates:
        item["relevance"] = _relevance(item, focus, time_sensitive)
    candidates.sort(key=lambda item: item["relevance"], reverse=True)

    ordered = _select_diverse(candidates, max_sources)

    await emit(
        {
            "type": "status",
            "stage": "retrieving",
            "message": (
                f"Selected {len(ordered)} sources from "
                f"{len({_publisher_key(item) for item in ordered})} publisher(s)"
            ),
        }
    )

    for i, item in enumerate(ordered, start=1):
        item["id"] = f"s{i}"
        item["snippet"] = _clean(item["text"])[:360]
    return ordered
