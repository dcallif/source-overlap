from __future__ import annotations

import asyncio
import re
from typing import Any

from . import llm

_OPEN_QUESTION_RE = re.compile(
    r"^\s*(?:(?:in|on|at|by|during)\s+)?"
    r"(?:what|when|where|who|whom|whose|which|why|how)\b",
    re.IGNORECASE,
)

_PLACEHOLDER_RE = re.compile(
    r"\b(?:a|an|the)\s+(?:specific|certain|particular|unknown|unspecified|given)"
    r"(?:\s+[a-z]+){0,2}\s+"
    r"(?:year|date|time|day|month|person|name|number|amount|company|country|"
    r"city|place|entity)\b"
    r"|\bsome\s+(?:\w+\s+){0,2}"
    r"(?:year|date|time|person|name|number|amount|company|country|city|place|"
    r"entity)\b",
    re.IGNORECASE,
)


def is_open_question(question: str) -> bool:
    return bool(_OPEN_QUESTION_RE.match(question.strip()))


def _is_placeholder_claim(text: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(text))


DECOMPOSE_SYSTEM = """You are a precise research analyst. Given a user's question, \
decompose it into atomic factual claims that a source could separately support or \
contradict, and propose 3-4 short web search queries that would find relevant sources.

Rules:
- If the question is yes/no, make the core proposition the first claim.
- Split compound statements and unstated presuppositions into separate claims. If the \
question asks "Is X confirmed?", list X itself as a claim (not just "X is confirmed").
- Only include claims the question actually asserts or presupposes. Do NOT invent \
alternative or speculative claims (for example, do not add "X is in negotiations" \
unless the question raises it).
- Phrase every claim as a positive, checkable proposition in a neutral voice, never as a \
question. Do not add hedging like "allegedly" unless the claim itself is about an allegation.
- Produce between 2 and 4 claims, each under 25 words.
- Write concrete, falsifiable statements that name the actual entities. Never
  use placeholders like "a specific year" or "some person".
- "centrality" is how central the claim is to the question (0.0-1.0).
- Queries must be plain keyword queries: no question words, no quotation marks, and \
never a verbatim copy of the question. Each query must name the key entities, and at \
least one must pair the main entity with the role, action, or event being asked about.

Return ONLY JSON in this shape:
{"claims":[{"text":"...","centrality":0.8}],"queries":["...","..."]}"""

JUDGE_SYSTEM = """You judge a single source against a list of claims. For each claim return one stance:

- "supports": the source states or clearly implies the claim is true.
- "contradicts": the source states or clearly implies the claim is false.
- "not_mentioned": the source does not address the claim.

Rules:
- Decide using ONLY the provided source text. Never use outside knowledge.
- The source title/headline is part of the source text. If it describes the person or \
entity as the new, next, or confirmed holder of a role, that supports a claim that they \
were cast, appointed, or announced.
- A paraphrase or clear logical equivalent counts as supports/contradicts; the
  wording does not need to match exactly.
- Silence is "not_mentioned", never "contradicts".
- Reserve "not_mentioned" for sources genuinely about a different topic. If the source \
clearly addresses the claim but you cannot tell whether it supports or contradicts, use \
"not_mentioned".
- "quote" must be an exact substring copied from the source text (max 240 characters) \
that justifies the decision. Use an empty string for "not_mentioned".
- "confidence" is 0.0-1.0.

Return ONLY JSON in this shape:
{"stances":[{"claim_id":"c1","stance":"supports","confidence":0.8,"quote":"..."}]}"""

VALID_STANCES = {"supports", "contradicts", "not_mentioned"}

DECOMPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "centrality": {"type": "number"},
                },
                "required": ["text", "centrality"],
                "additionalProperties": False,
            },
        },
        "queries": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["claims", "queries"],
    "additionalProperties": False,
}

def stance_schema(claim_ids: list[str]) -> dict[str, Any]:
    """Structured-output schema pinned to the exact claim ids for this request."""
    return {
        "type": "object",
        "properties": {
            "stances": {
                "type": "array",
                "minItems": len(claim_ids),
                "maxItems": len(claim_ids),
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string", "enum": claim_ids},
                        "stance": {
                            "type": "string",
                            "enum": ["supports", "contradicts", "not_mentioned"],
                        },
                        "confidence": {"type": "number"},
                        "quote": {"type": "string"},
                    },
                    "required": ["claim_id", "stance", "confidence", "quote"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["stances"],
        "additionalProperties": False,
    }


ANSWER_SYSTEM = """You answer a user's question using ONLY the supplied sources. \
Give the specific value the question asks for (a year, name, number, place, or status) \
when the sources state it.

Rules:
- If the sources do not state the answer, return an empty string for "answer" and use \
"unclear" for "agreement". Do not call that a disagreement.
- Only use "disagree" when the sources give conflicting answers.
- "summary" is one sentence that directly answers the question and names the key entity.
- Use only source ids from the provided list. Prefer ids that explicitly state the answer.
- Return at least one source id whenever "answer" is not empty.
- Never use outside knowledge. Never answer with a question or a placeholder.
- "confidence" is 0.0-1.0.

Return ONLY JSON in this shape:
{"answer":"...","summary":"...","agreement":"agree","source_ids":["s1"],"confidence":0.8}"""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "summary": {"type": "string"},
        "agreement": {
            "type": "string",
            "enum": ["agree", "disagree", "unclear"],
        },
        "source_ids": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": ["answer", "summary", "agreement", "source_ids", "confidence"],
    "additionalProperties": False,
}


def _normalize_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _norm_stance(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"supports", "support", "true", "yes", "confirms", "confirmed", "affirms", "agree"}:
        return "supports"
    if text in {
        "contradicts",
        "contradict",
        "false",
        "no",
        "denies",
        "denied",
        "refutes",
        "disputes",
        "disagree",
    }:
        return "contradicts"
    return "not_mentioned"


def _clamp(value: Any, default: float = 0.5) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, num))


def _normalize_claims(payload: Any) -> list[dict[str, Any]]:
    raw_claims: list[Any] = []
    if isinstance(payload, dict):
        raw_claims = payload.get("claims") or []
    elif isinstance(payload, list):
        raw_claims = payload

    claims: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_claims, start=1):
        if isinstance(raw, str):
            text, centrality = raw, 0.5
        elif isinstance(raw, dict):
            text = raw.get("text") or raw.get("claim") or ""
            centrality = raw.get("centrality", 0.5)
        else:
            continue
        text = " ".join(str(text).split())
        if len(text) < 8 or _is_placeholder_claim(text):
            continue
        claims.append(
            {
                "id": f"c{len(claims) + 1}",
                "text": text,
                "centrality": _clamp(centrality),
            }
        )
    claims.sort(key=lambda c: c["centrality"], reverse=True)
    for i, claim in enumerate(claims, start=1):
        claim["id"] = f"c{i}"
    return claims[:5]


_LEADING_QUESTION = re.compile(
    r"^(?:(?:is|are|was|were|do|does|did|has|have|had|can|could|will|would|should|"
    r"who|whom|whose|what|when|where|why|how|it|there)\b[\s,:-]*)+",
    re.IGNORECASE,
)


def _keyword_query(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip('"').strip()
    cleaned = re.sub(r"[?!.]+$", "", cleaned).strip()
    cleaned = _LEADING_QUESTION.sub("", cleaned)
    cleaned = re.sub(r"^(?:the|a|an)\b[\s,:-]*", "", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def _normalize_queries(payload: Any, question: str) -> list[str]:
    raw = payload.get("queries") if isinstance(payload, dict) else None
    queries: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = _keyword_query(value)
        if not (3 <= len(text) <= 160):
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        queries.append(text)

    add(question)
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                add(item)
    return queries[:4]


async def decompose(
    backend: llm.LLMBackend, model: str, question: str
) -> tuple[list[dict[str, Any]], list[str]]:
    payload = await backend.chat_json(
        model,
        DECOMPOSE_SYSTEM,
        f"Question: {question}",
        max_tokens=500,
        schema=DECOMPOSE_SCHEMA,
    )
    claims = _normalize_claims(payload)
    queries = _normalize_queries(payload, question)
    return claims, queries


async def judge_source(
    backend: llm.LLMBackend,
    model: str,
    source: dict[str, Any],
    claims: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    claim_lines = "\n".join(
        f"- {c['id']}: {c['text']}" for c in claims
    )
    title = " ".join(str(source.get("title", "")).split())
    body = str(source.get("text", ""))
    if title and title.lower() not in body.lower():
        body = f"{title}\n\n{body}"
    text = body[:4000]
    user = (
        "CLAIMS:\n"
        f"{claim_lines}\n\n"
        f"SOURCE ({source['publisher']}):\n{text}\n\n"
        "Return exactly one stance for every claim id listed above, in order."
    )
    try:
        payload = await backend.chat_json(
            model,
            JUDGE_SYSTEM,
            user,
            max_tokens=600,
            schema=stance_schema([c["id"] for c in claims]),
        )
    except (llm.LLMError, ValueError) as exc:
        empty = [
            {
                "source_id": source["id"],
                "claim_id": c["id"],
                "stance": "not_mentioned",
                "confidence": 0.0,
                "quote": "",
                "quote_verified": False,
            }
            for c in claims
        ]
        return empty, f"{source['publisher']}: {exc}"

    raw_stances = payload.get("stances") if isinstance(payload, dict) else payload
    if not isinstance(raw_stances, list):
        raw_stances = []

    by_claim: dict[str, dict[str, Any]] = {}
    haystack = " ".join(source["text"].split()).lower()
    for raw in raw_stances:
        if not isinstance(raw, dict):
            continue
        claim_id = str(raw.get("claim_id", "")).strip()
        if not claim_id:
            continue
        stance = _norm_stance(raw.get("stance"))
        quote = " ".join(str(raw.get("quote") or "").split())[:240]
        verified = False
        if quote and stance != "not_mentioned" and len(quote) >= 12:
            verified = quote.lower() in haystack
        by_claim[claim_id] = {
            "source_id": source["id"],
            "claim_id": claim_id,
            "stance": stance,
            "confidence": _clamp(raw.get("confidence"), 0.0),
            "quote": "" if stance == "not_mentioned" else quote,
            "quote_verified": verified,
        }

    return (
        [
            by_claim.get(
                c["id"],
                {
                    "source_id": source["id"],
                    "claim_id": c["id"],
                    "stance": "not_mentioned",
                    "confidence": 0.0,
                    "quote": "",
                    "quote_verified": False,
                },
            )
            for c in claims
        ],
        None,
    )


async def answer_question(
    backend: llm.LLMBackend,
    model: str,
    question: str,
    sources: list[dict[str, Any]],
) -> dict[str, Any] | None:
    blocks: list[str] = []
    for source in sources[:8]:
        text = " ".join(str(source.get("text") or "").split())[:1600]
        published = source.get("published") or "date unknown"
        blocks.append(
            f"[{source['id']}] {source['publisher']} ({published})\n"
            f"Title: {source['title']}\n{text}"
        )
    if not blocks:
        return None

    user = f"QUESTION: {question}\n\nSOURCES:\n\n" + "\n\n".join(blocks)
    payload = await backend.chat_json(
        model,
        ANSWER_SYSTEM,
        user,
        max_tokens=500,
        schema=ANSWER_SCHEMA,
    )
    if not isinstance(payload, dict):
        return None

    answer = _normalize_text(payload.get("answer"), 160)
    if not answer:
        return None
    summary = _normalize_text(payload.get("summary"), 600) or answer
    agreement = str(payload.get("agreement") or "unclear").lower()
    if agreement not in {"agree", "disagree", "unclear"}:
        agreement = "unclear"

    valid_ids = {source["id"] for source in sources}
    source_ids: list[str] = []
    for item in payload.get("source_ids") or []:
        source_id = str(item)
        if source_id in valid_ids and source_id not in source_ids:
            source_ids.append(source_id)

    answer_lower = answer.lower()
    if not answer_lower.startswith("sources disagree") and len(answer) >= 3:
        for source in sources:
            if source["id"] in source_ids:
                continue
            if answer_lower in str(source.get("text") or "").lower():
                source_ids.append(source["id"])

    if not source_ids:
        return None
    if answer_lower.startswith("sources disagree"):
        if agreement == "unclear":
            return None
        agreement = "disagree"
    elif agreement == "unclear" and len(source_ids) >= 2:
        agreement = "agree"

    return {
        "answer": answer,
        "summary": summary,
        "agreement": agreement,
        "source_ids": source_ids,
        "confidence": _clamp(payload.get("confidence"), 0.5),
    }


def _publisher_key(source: dict[str, Any]) -> str:
    return " ".join(str(source.get("publisher") or "").split()).lower()


def _claim_status(support: int, contradict: int) -> str:
    if support >= 2 and contradict == 0:
        return "consensus"
    if support >= 1 and contradict >= 1:
        return "contested"
    if contradict >= 1 and support == 0:
        return "contradicted"
    if support == 1:
        return "single_source"
    return "unaddressed"


def _pick_top_sources(
    sources: list[dict[str, Any]], claims: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    def score(source: dict[str, Any]) -> tuple[int, int, int]:
        supports = sum(
            1
            for c in claims
            for source_id in c["support_sources"]
            if source_id == source["id"]
        )
        mentions = sum(
            1
            for c in claims
            for source_id in c["support_sources"] + c["contradict_sources"]
            if source_id == source["id"]
        )
        return (mentions, supports, len(source.get("text", "")))

    return sorted(sources, key=score, reverse=True)[:3]


def _build_venn(
    sources: list[dict[str, Any]], claims: list[dict[str, Any]]
) -> dict[str, Any]:
    top = _pick_top_sources(sources, claims)
    labels = ["A", "B", "C"]
    top_ids = [s["id"] for s in top]
    regions: dict[str, list[str]] = {}
    outside: list[str] = []

    for claim in claims:
        mask = "".join(
            "1" if source_id in claim["support_sources"] else "0"
            for source_id in top_ids
        )
        if "1" not in mask:
            outside.append(claim["id"])
            continue
        regions.setdefault(mask, []).append(claim["id"])

    return {
        "sources": [
            {
                "id": s["id"],
                "label": labels[i],
                "title": s["title"],
                "publisher": s["publisher"],
                "kind": s["kind"],
                "url": s["url"],
            }
            for i, s in enumerate(top)
        ],
        "regions": regions,
        "outside": outside,
    }


def _build_verdict(
    sources: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    direct_answer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    total = len(sources)
    disclaimer = (
        "This tool compares what retrieved sources say. It is not a "
        "fact-checker, and no retrieved coverage is not disproof."
    )
    if direct_answer and direct_answer.get("answer"):
        agreement = direct_answer.get("agreement")
        answer_key = {
            "agree": "supported",
            "disagree": "contested",
        }.get(agreement, "insufficient_evidence")
        cited = len(direct_answer.get("source_ids") or [])
        if agreement == "agree":
            if cited == 1:
                explanation = "1 retrieved source points to this answer."
            elif cited > 1:
                explanation = (
                    f"{cited} retrieved sources point to this answer."
                )
            else:
                explanation = "The retrieved sources point to this answer."
        elif agreement == "disagree":
            explanation = (
                "The retrieved sources disagree, so this answer is not settled."
            )
        else:
            explanation = (
                "The retrieved sources do not clearly settle this question."
            )
        return {
            "answer": answer_key,
            "headline": direct_answer["answer"],
            "central_claim": direct_answer.get("summary") or direct_answer["answer"],
            "explanation": explanation,
            "disclaimer": disclaimer,
            "direct_answer": direct_answer,
        }
    if not claims:
        return {
            "answer": "no_coverage",
            "headline": "Nothing to compare",
            "central_claim": "",
            "explanation": "No claims could be extracted from the question.",
            "disclaimer": disclaimer,
        }
    if total == 0:
        return {
            "answer": "no_coverage",
            "headline": "No sources retrieved",
            "central_claim": claims[0]["text"],
            "explanation": (
                "The search returned no usable sources. Try rephrasing the "
                "question or using more specific, concrete terms."
            ),
            "disclaimer": disclaimer,
        }

    # Always speak to the most central claim so the verdict answers the actual
    # question instead of a peripheral claim that happened to be mentioned.
    central = max(
        claims,
        key=lambda c: (c["centrality"], c["mention_count"]),
    )
    support = central["support_publisher_count"]
    contradict = central["contradict_publisher_count"]
    publisher_total = len(
        {_publisher_key(source) for source in sources if _publisher_key(source)}
    ) or total
    status = central["status"]

    if status == "consensus":
        headline = "Sources agree"
        explanation = (
            f"{support} independent publishers support this claim "
            f"and none contradict it."
        )
    elif status == "contested":
        headline = "Sources disagree"
        explanation = (
            f"{support} independent publisher(s) support this claim while "
            f"{contradict} contradict it. The retrieved sources are not aligned."
        )
    elif status == "contradicted":
        headline = "Sources contradict this"
        explanation = (
            f"{contradict} independent publishers contradict this claim "
            f"and none support it."
        )
    elif status == "single_source":
        headline = "Only one source"
        explanation = (
            "Exactly one independent publisher supports this claim and none "
            "contradict it, so it is not independently corroborated."
        )
    else:
        headline = "Not addressed"
        explanation = (
            f"None of the {publisher_total} independent publishers in this "
            "sample clearly address this claim. No corroboration was found, "
            "which is not proof the claim is false."
        )

    return {
        "answer": {
            "consensus": "supported",
            "contested": "contested",
            "contradicted": "contradicted",
            "single_source": "insufficient_evidence",
            "unaddressed": "no_coverage",
        }[status],
        "headline": headline,
        "central_claim": central["text"],
        "explanation": explanation,
        "disclaimer": (
            "This tool compares what retrieved sources say. It is not a "
            "fact-checker, and no retrieved coverage is not disproof."
        ),
    }


def aggregate(
    question: str,
    sources: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    stances: list[dict[str, Any]],
    meta: dict[str, Any],
    warnings: list[str] | None = None,
    direct_answer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if direct_answer and direct_answer.get("answer") and not claims:
        valid_ids = {source["id"] for source in sources}
        cited = [
            source_id
            for source_id in direct_answer.get("source_ids") or []
            if source_id in valid_ids
        ]
        summary = _normalize_text(
            direct_answer.get("summary") or direct_answer["answer"], 400
        )
        if cited and len(summary) >= 8:
            claims = [{"id": "c1", "text": summary, "centrality": 1.0}]
            stances = [
                {
                    "source_id": source_id,
                    "claim_id": "c1",
                    "stance": "supports",
                    "confidence": direct_answer.get("confidence", 0.5),
                    "quote": "",
                    "quote_verified": False,
                }
                for source_id in cited
            ]

    by_claim: dict[str, list[dict[str, Any]]] = {c["id"]: [] for c in claims}
    for stance in stances:
        by_claim.setdefault(stance["claim_id"], []).append(stance)

    publisher_by_id = {
        source["id"]: _publisher_key(source) for source in sources
    }
    publisher_total = len(
        {publisher for publisher in publisher_by_id.values() if publisher}
    )

    enriched_claims: list[dict[str, Any]] = []
    for claim in claims:
        rows = by_claim.get(claim["id"], [])
        support_sources = [
            r["source_id"] for r in rows if r["stance"] == "supports"
        ]
        contradict_sources = [
            r["source_id"] for r in rows if r["stance"] == "contradicts"
        ]
        support_publishers = {
            publisher_by_id[source_id]
            for source_id in support_sources
            if publisher_by_id.get(source_id)
        }
        contradict_publishers = {
            publisher_by_id[source_id]
            for source_id in contradict_sources
            if publisher_by_id.get(source_id)
        }
        enriched_claims.append(
            {
                **claim,
                "support_sources": support_sources,
                "contradict_sources": contradict_sources,
                "support_publisher_count": len(support_publishers),
                "contradict_publisher_count": len(contradict_publishers),
                "mention_count": len(support_sources) + len(contradict_sources),
                "status": _claim_status(
                    len(support_publishers), len(contradict_publishers)
                ),
            }
        )

    total_cells = max(1, len(sources) * len(enriched_claims))
    mentioned_cells = sum(c["mention_count"] for c in enriched_claims)
    coverage = round(mentioned_cells / total_cells, 3)

    judged = [
        c
        for c in enriched_claims
        if c["support_publisher_count"] + c["contradict_publisher_count"] >= 2
    ]
    if judged:
        agreement = round(
            sum(
                1 for c in judged if c["contradict_publisher_count"] == 0
            )
            / len(judged),
            3,
        )
    else:
        agreement = None

    corroborated = sum(
        1
        for c in enriched_claims
        if c["support_publisher_count"] >= 2
        and c["contradict_publisher_count"] == 0
    )

    for source in sources:
        source["support_count"] = sum(
            1 for c in enriched_claims if source["id"] in c["support_sources"]
        )
        source["contradict_count"] = sum(
            1
            for c in enriched_claims
            if source["id"] in c["contradict_sources"]
        )

    return {
        "question": question,
        "claims": enriched_claims,
        "sources": sources,
        "stances": stances,
        "verdict": _build_verdict(sources, enriched_claims, direct_answer),
        "direct_answer": direct_answer,
        "venn": _build_venn(sources, enriched_claims),
        "metrics": {
            "sources": len(sources),
            "publishers": publisher_total,
            "claims": len(enriched_claims),
            "corroborated": corroborated,
            "coverage": coverage,
            "agreement": agreement,
        },
        "meta": {**meta, "warnings": warnings or []},
    }


async def judge_all(
    backend: llm.LLMBackend,
    model: str,
    sources: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    emit,
) -> tuple[list[dict[str, Any]], list[str]]:
    semaphore = asyncio.Semaphore(2)
    results: list[dict[str, Any]] = []
    warnings: list[str] = []
    completed = 0

    async def run(source: dict[str, Any]) -> list[dict[str, Any]]:
        nonlocal completed
        async with semaphore:
            outcome, error = await judge_source(backend, model, source, claims)
        completed += 1
        if error:
            warnings.append(f"Could not judge {error}")
        await emit(
            {
                "type": "status",
                "stage": "judging",
                "message": (
                    f"Judged {completed}/{len(sources)}: "
                    f"{source['publisher']} — {source['title'][:60]}"
                ),
                "progress": completed,
                "total": len(sources),
            }
        )
        return outcome

    tasks = [asyncio.create_task(run(source)) for source in sources]
    for coro in asyncio.as_completed(tasks):
        results.extend(await coro)
    return results, warnings
