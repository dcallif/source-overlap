# Source Overlap

Ask a question, pull real sources from the live web, and see **what they agree
on and where they diverge** — as a Venn diagram plus a source-by-claim matrix.

A local-first research tool. No search API keys and no cloud LLM: retrieval uses
public Wikipedia and news RSS feeds, and stance extraction runs on a model in
[LM Studio](https://lmstudio.ai/) on your machine. It runs locally, or as a
hosted app that connects back to your own LM Studio through a small CLI relay.

```
question
  └─ decompose into atomic claims (+ search queries)         [local LLM]
  └─ retrieve + rank sources: Wikipedia + Google News (+ Bing) [keyless]
  └─ judge each (source, claim): supports / contradicts / not mentioned
                                                             [local LLM]
  └─ aggregate → per-claim consensus, verdict, Venn, matrix
```

## What it shows

- **Verdict card** — the central claim, an overall answer
  (supported / contested / contradicted / thin evidence / no coverage), and
  coverage/agreement metrics.
- **Venn diagram** — the three most informative sources as circles; each region
  holds the claims those sources jointly support. Click a region to inspect it.
- **Source-by-claim matrix** — every source × every claim, with green checks,
  red crosses, and a click-through to the exact supporting quote.
- **Source cards** — publisher, date, link, and how often each source supported
  or contradicted.

A Venn diagram only depicts three sets cleanly, so the diagram uses the top
three sources; the matrix always covers all retrieved sources.

### How "agreement" is decided

Corroboration counts **independent publishers**, not raw URLs, so two pages from
the same outlet (or two Wikipedia articles) cannot manufacture consensus. Each
atomic claim gets a status:

| Status | Meaning |
|---|---|
| `consensus` | 2+ independent publishers support it, none contradict |
| `contested` | at least one supports and at least one contradicts |
| `contradicted` | at least one contradicts, none support |
| `single_source` | exactly one publisher supports it, none contradict |
| `unaddressed` | no publisher clearly addresses it |

The **agreement** metric is the share of claims addressed by 2+ publishers that
are not contradicted. It shows `n/a` when no claim has enough independent
coverage, rather than a misleading `0%`.

This is a comparison of sources, **not a fact-checker**. "No coverage" means no
retrieved source corroborated the claim in this sample — it is not disproof.

## Requirements

- **LM Studio** with a chat model loaded (a 7B–14B instruct model works; larger
  models judge more reliably) and the local server running on port 1234.
  Large models are slow: a 27B model can take minutes per question, so start
  with 4 sources and a smaller model.
- Python 3.11+ (developed on 3.15) and Node 18+ for local development.
- Python 3.10+ on the machine with LM Studio when using the hosted connector.

## Run it

**1. Start the local model**

In LM Studio: load a model, open the Developer tab, start the server (default
`http://127.0.0.1:1234`).

**2. Backend**

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

**3. Frontend**

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The status pill in the header shows whether the
backend can reach LM Studio.

You can also deep-link a question: `http://localhost:5173/?q=your+question`.

The page is served by the frontend dev server. It proxies `/api` and the
connector WebSocket to the backend on port 8000.

## Hosted mode (Render)

A single Docker web service serves the built frontend, the API, and the
connector WebSocket. Each visitor pairs the hosted app with LM Studio running on
their own computer; the model and source text never move to the server.

**1. Push the repository to GitHub.**

**2. Deploy the blueprint.** In Render, choose **New → Blueprint** and select the
repo. `render.yaml` creates one free Docker web service with
`REQUIRE_CONNECTOR=true` and HTTPS session cookies.

You can also create the service manually:

- Runtime: **Docker**, Dockerfile: `./Dockerfile`
- Plan: **Free**
- Health check path: `/healthz`
- Environment: `REQUIRE_CONNECTOR=true`, `SESSION_COOKIE_SECURE=true`,
  `CACHE_DIR=/tmp/source-overlap-cache`

**3. Connect your model.** Open the deployed site, copy the generated command
(or click **Copy** in the Local model panel), install the connector once, and
run it on the computer with LM Studio:

```powershell
python -m pip install ./connector
python -m source_overlap_connector --server https://YOUR-APP.onrender.com --code ABCD-1234
```

Use a new pairing code each time the code expires or the service restarts.

Render's free tier notes:

- The service sleeps after 15 minutes without traffic. Polling and connector
  heartbeats keep it awake while the site or connector is open; the first request
  after sleep can take about a minute.
- Sessions and pairing codes are in memory, so run **one** instance. A restart
  clears them; re-pair with a fresh code.
- The filesystem is ephemeral. Results cached for a local model are kept in
  memory per session, so they disappear with a restart.

The connector only relays `/v1/models` and `/v1/chat/completions` to LM Studio.
It opens an outbound WebSocket and never exposes an inbound port. It is not
published to PyPI yet, so users install it from a clone of this repository (or
you can build and distribute the wheel from `connector/`).

## Configuration

Set these in `backend/.env` (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `LM_STUDIO_URL` | `http://127.0.0.1:1234/v1` | OpenAI-compatible endpoint |
| `LM_STUDIO_MODEL` | *(first model)* | Force a specific model id |
| `LM_TEMPERATURE` | `0.1` | Lower = more consistent JSON |
| `LM_TIMEOUT` | `600` | Seconds allowed between streamed tokens |
| `LM_DISABLE_THINKING` | `true` | Turn off Qwen3 reasoning for fast, clean JSON |
| `MAX_SOURCES` | `6` | Default number of sources to judge |
| `FETCH_TIMEOUT` | `20` | Seconds per web request |
| `ENABLE_BING_NEWS` | `true` | Second keyless news feed (direct links) |
| `CACHE_TTL_SECONDS` | `86400` | Cache per question; `0` disables |
| `REQUIRE_CONNECTOR` | `false` | Refuse asks unless a connector is paired |
| `SESSION_TTL_SECONDS` | `43200` | Idle lifetime of an anonymous session |
| `PAIRING_TTL_SECONDS` | `600` | Lifetime of a pairing code |
| `SESSION_COOKIE_NAME` | `source_overlap_session` | Anonymous session cookie |
| `SESSION_COOKIE_SECURE` | `false` | Set true when served over HTTPS |
| `FRONTEND_DIST` | `../frontend/dist` | Static build served by FastAPI |
| `CACHE_DIR` | `backend/.cache` | Disk cache directory |

`LM_STUDIO_URL` and `LM_STUDIO_MODEL` are used in local/direct mode. In hosted
mode the model comes from the paired connector, and the app is expected to be
served behind HTTPS. Keep `REQUIRE_CONNECTOR=false` for local development.

Results are cached under `backend/.cache/`; the UI's **Re-run fresh** button
bypasses the cache.

## API

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/ask` | `{question, max_sources?, refresh?}` → full result |
| `POST` | `/api/ask/stream` | Same body; NDJSON progress + final result |
| `GET` | `/api/health` | Direct-mode LM Studio reachability |
| `GET` | `/api/models` | Direct-mode models |
| `GET` | `/api/session/status` | Connector, LM Studio, and model status |
| `POST` | `/api/session/pairing` | New pairing code and connector command |
| `POST` | `/api/session/model` | `{model}` → select a loaded connector model |
| `POST` | `/api/session/disconnect` | Revoke the connector token and disconnect |
| `WS` | `/api/connector` | Connector relay (pair/resume, heartbeat, HTTP bridge) |
| `GET` | `/healthz` | Container health check |

The stream emits `{"type":"status"}` progress events, then either
`{"type":"result","data":...}` or `{"type":"error","message":...}`.

Connector messages are JSON. The connector first sends `pair` (with the code) or
`resume` (with its token) plus LM Studio status. The server replies with
`ready`. The connector then sends `heartbeat`/`status` every 25 seconds and
answers relayed `http` messages with `start`, `chunk`, `end`, or `error`.

## Layout

```
backend/
  app/
    main.py         FastAPI routes, sessions, WebSocket relay, static frontend
    connectors.py   connector protocol, pairing, BridgeLLM, session registry
    service.py      pipeline + per-session result cache
    retrieval.py    Wikipedia + Google News/Bing RSS, dedupe, enrichment
    analysis.py     claim decomposition, stance judging, aggregation, Venn
    llm.py          direct LM Studio client + shared payload/SSE helpers
    config.py       settings (.env)
connector/
  source_overlap_connector/
    __main__.py     CLI relay: LM Studio <-> hosted app
frontend/
  src/
    App.vue
    components/     VerdictCard, AgreementBars, SourcesPanel, LocalModelPanel
    api/client.js
Dockerfile          multi-stage frontend + backend image
render.yaml         Render free-tier blueprint
```

## Limitations

- **Venn is 3 sets.** More sources are always visible in the matrix.
- **Google News links are JS redirect pages**, so only their RSS headline/snippet
  is available for judging. Bing (enabled by default) yields direct publisher
  links, which are fetched when the site allows it.
- **Local models vary.** Malformed JSON is retried once; if it still fails, that
  source is treated as "not mentioned" rather than guessed.
- **Reasoning models are slow.** Qwen3 "thinking" is disabled automatically
  (`LM_DISABLE_THINKING`); very large models can still be slow. Responses are
  streamed, so an idle timeout only fires if tokens stop arriving.
- **Silence is not refutation.** Sparse coverage shows up as `unaddressed`.
- **Hosted mode needs the connector.** There is no server-side model fallback in
  v1, so the connector must be running while the hosted app is used.
- **Free hosting is single-instance.** In-memory sessions and pairing codes mean
  the service should not be scaled horizontally, and a restart requires re-pairing.
