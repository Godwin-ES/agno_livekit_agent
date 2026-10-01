# EchoRun agent

EchoRun is a real-time voice agent that combines LiveKit's audio pipeline with an
Agno agent, Groq-hosted `gpt-oss`, real tools, persistent memory, and a versioned
activity stream for the browser. The custom `livekit_plugins_agno` adapter is the
centerpiece: it turns Agno's streaming output into LiveKit speech while publishing
tool and memory events without blocking the voice path.

## Architecture

```text
Browser microphone / lk.chat
        │
        ▼
LiveKit room ─▶ Deepgram STT ─▶ LLMAdapter ─▶ Agno agent ─▶ tools
      ▲                               │             └──────▶ SQLite memory + notes
      ├── agent audio ◀─ Deepgram TTS ◀┘
      ├── lk.transcription
      └── reliable `agent.events` ◀── tool lifecycle, memory, and turn latency
```

The LiveKit worker registers an explicit name (`echorun-agent` by default), so it
only joins rooms whose tokens dispatch that name. The frontend supplies a stable
`visitor_id` participant attribute; display-name changes no longer split memory.

## Toolset

| Capability | Implementation | Data source |
|---|---|---|
| Weather + three-day forecast | Custom async tool | Open-Meteo |
| Local time | Custom async tool | Open-Meteo geocoding + `zoneinfo` |
| Currency conversion | Custom async tool | Frankfurter / ECB |
| Safe calculation | Custom bounded AST evaluator | Local |
| Search and news | Agno `DuckDuckGoTools` | DuckDuckGo |
| Article reading | Agno `Newspaper4kTools` | Publisher pages |
| Background knowledge | Agno `WikipediaTools` | Wikipedia |
| Stocks and company info | Limited Agno `YFinanceTools` | Yahoo Finance |
| Technology stories | Limited Agno `HackerNewsTools` | Hacker News |
| User notes | Custom user-scoped tool | SQLite |
| Stable preferences and facts | Agno agentic memory | SQLite |

Custom HTTP tools share a four-second client timeout and one bounded retry. They
return structured cards plus a short `say` value, and recover with a speakable
error instead of raising into the call. The calculator accepts numeric arithmetic,
parentheses, percentages, and a small math-function allowlist; it rejects names,
attribute access, imports, collections, and expensive exponents.

## Event protocol

Messages are reliable JSON packets on topic `agent.events`, currently `v: 1`:

- `tool.started` — call id, turn, tool, redacted/bounded arguments
- `tool.completed` — duration and structured result card
- `tool.failed` — duration and safe error text
- `memory.updated` — current Agno memory snapshot
- `turn.metrics` — STT, LLM first token, TTS first byte, end-to-end time, tool count

Arguments and results are limited to 4 KiB. Publication is isolated behind a
non-blocking callback and can never fail the audio stream. Only `RunContentEvent`
becomes speech; completion payloads and reasoning are intentionally discarded.

## Local setup

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
cp .env.example .env
uv sync
uv run main.py dev
```

Required credentials are `LIVEKIT_*`, `DEEPGRAM_API_KEY`, and `GROQ_API_KEY`.
`GROQ_MODEL` defaults to `openai/gpt-oss-20b`; use
`openai/gpt-oss-120b` when stronger multi-tool planning is worth the extra latency.
`PREEMPTIVE_GENERATION` defaults to `false` to avoid storing cancelled partial
runs. Secrets stay in `.env`; memories and notes stay in ignored `data/*.db` files.

## Tests

```bash
uv run pytest
```

The suite covers mocked weather/time/currency traffic, timeouts, unknown places,
safe math attacks and resource bounds, user-scoped notes, content-only speech,
tool event mapping and field limits, callback isolation, generator closure, stable
identity, and metric folding. Tests never call a live API.

## Live verification matrix

Run this matrix against both configured models after deploying the backend. Record
the metrics-panel end-to-end time rather than estimating it.

| Prompt | Expected tool/path | 20B result / latency | 120B result / latency |
|---|---|---|---|
| What's the weather in Lagos? | `get_weather` | Pending live check | Pending live check |
| What time is it in Tokyo? | `get_time` | Pending live check | Pending live check |
| Convert 150 euros to dollars | `convert_currency` | Pending live check | Pending live check |
| What's 18 percent of 2,450? | `calculate` | Pending live check | Pending live check |
| Latest SpaceX news; tell me more about the first | search → article | Pending live check | Pending live check |
| How's Nvidia stock doing? | YFinance price/info | Pending live check | Pending live check |
| Remember Celsius; reconnect; weather in Accra | memory → weather | Pending live check | Pending live check |
| Add a note to email Sam; list notes | notes | Pending live check | Pending live check |
| Interrupt midway through an answer | clean cancellation, no duplicate speech | Pending live check | Pending live check |

## Deployment

Deploy the backend before the frontend because token dispatch requires the named
worker to be registered first.

```bash
./deploy.sh
```

The script preserves `~/agno-livekit-agent/.env` and `data/` on the Oracle VM,
rebuilds the container, starts it, and prints the last worker logs. Confirm those
logs include a registered worker for the configured `AGENT_NAME`. Then deploy the
frontend with the same `AGENT_NAME` in Vercel and run the matrix above on its
preview URL before promoting it.
