# 02 - Agent architecture research (as of 2026-11-04)

Sources were fetched live on 2026-11-04 unless marked. Third-party aggregator figures are marked UNVERIFIED.

## Bottom line

Replace the four-agent ADK pipeline with **a deterministic Python pipeline and two small LLM calls**. The app does not need an agent loop.

1. **Code does the relaying.** Geocode (a geocoding API or a city table), parse dates (dateparser, or the router emits ISO dates), map genre to a Ticketmaster classification ID, call Spotify, related-artists and Ticketmaster concurrently with `asyncio.gather`, then dedupe and filter. None of this needs an LLM.
2. **LLM call 1 (router/parser, cheap tier).** Free text goes in; a Pydantic object comes out (location text, ISO date range, artists, genre, playlist URL, `needs_clarification`). This replaces the root agent, the date handling and the genre mapping.
3. **LLM call 2 (ranker, one call).** Give it a compact taste profile plus about 50 candidates, each with a short ID, artist, genre, date, venue and distance. It returns `[{id, score, reason}]`. **The LLM never sees or emits URLs, images or times.** Code hydrates the full Concert objects from the IDs, and drops any ID that was not offered.
4. **Stream progress over SSE.** Emit stage events (`parsing`, `fetching_spotify`, `found N events`, `ranking`) and then the results, instead of one blocking 3-minute blob. Most of the 3 minutes will disappear once the serial LLM hops are gone. Remove the call-and-wait structure first, then add streaming.
5. **Framework: none.** Use the provider SDK, or Pydantic AI for typed structured output and model-swap if wanted. Do not use ADK, LangGraph, or the Claude Agent SDK. Stay in Python (FastAPI backend already exists).
6. **Quality:** a 30-50 case golden set (parser accuracy) plus a Pydantic Evals or Promptfoo run in CI, and OTel tracing via Logfire or Langfire/Langfuse. Treat event and playlist text as untrusted data.
7. **Defer** durable execution, MCP server, generative-UI protocols and proactive alerts. The MCP server and alerts are the best later layers (see 5 and 7).

Model recommendation: the router on Claude Haiku 5.5 or Gemini 3.5 Flash-Lite, the ranker on the same cheap model first. Move the ranker up a tier only if evals show it matters. Estimated cost is about $0.002-$0.03 per search (section 3).

## Current-app problems this fixes (from code read)

- `final_recommender_agent` re-emits all concert JSON including `url`/`image_url` under `output_schema`. This is slow, costs output tokens, and risks hallucinated or mangled URLs.
- The root agent only validates input and hands off. A single structured parse call does this better.
- `gemini-2.0-flash` is deprecated, with a June 1, 2026 shutdown listed (section 3). The app must migrate regardless.
- `ticketmaster_agent` builds API URLs with the key in the query string, and `_extract_event_info` indexes `_embedded.venues[0]` unguarded. Both are non-LLM defects to fix in the deterministic layer.

## 1. Architectural guidance

- **Multi-agent is for breadth-first, parallelisable, high-value work, and it costs about 15x chat tokens** (agents about 4x). It fits poorly where steps depend on each other or share context. Anthropic, Jun 2025: https://www.anthropic.com/engineering/built-multi-agent-research-system. Concert search is a fixed linear fan-out/fan-in. That is a function, not a multi-agent system.
- **Context engineering:** keep the smallest set of high-signal tokens; hold lightweight references and load content just in time; tools should be token-efficient and non-overlapping; subagents return condensed summaries. Anthropic, 2025-09-29: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- **Reference by ID, then hydrate.** The model returns IDs and judgements; code joins them back to the source records. This is the direct application of the just-in-time reference idea above. It makes URL hallucination impossible and cuts output tokens roughly 10x versus re-emitting JSON. This is a design pattern from the sources above, not a named feature.
- **Programmatic tool calling** (Claude writes code that calls tools inside a sandbox so intermediate results stay out of context; average tokens on research tasks 43.6k to 27.3k, -37%) and **tool search** (`defer_loading`, about 77k to 8.7k tokens of tool definitions, -85%). Both were beta behind `advanced-tool-use-2025-11-20` as of the post, 2025-11-24: https://www.anthropic.com/engineering/advanced-tool-use. Current GA status UNVERIFIED. **Not relevant here:** with only about 3 data sources and a fixed flow, plain Python already is the "programmatic" caller. Pydantic AI also ships `CodeMode` and `tool_search` (release notes 2026-11-04) if an open-ended agent is ever wanted.
- **Structured outputs:** use native schema-constrained output (Pydantic model) for the router and ranker. Keep schemas small; the ADK `Concert` schema with 9 free-text fields is the anti-pattern.
- **Fan-out with cheap subagents** only pays off if sub-tasks need judgement (e.g. 50 independent "is this event a fit" checks). One ranker call over 50 short rows is cheaper and gives consistent relative scores. Batch API halves cost if the work is not interactive (section 3).

## 2. Frameworks for this size of app

| Framework | Current version (release page, 2026-11) | Fit |
|---|---|---|
| Google ADK (Python) | v2.13.0, 2026-10-22 (https://github.com/google/adk-python/releases). v2 adds graph workflows, eval metrics, `abort_signal`, OTel GenAI v2 default with a breaking span change | Heavy. The current app is on 1.4.2 and a v2 move is a major migration. Its fixed `SequentialAgent` of LLM agents is the root cause of the design problem. |
| Pydantic AI | v2.66.0, 2026-11-04 (https://github.com/pydantic/pydantic-ai/releases). Has Temporal/DBOS-style durable support, `pydantic_evals`, AG-UI 1.0, Vercel AI adapter, ModelFallback, CodeMode. v2.66 notes several security advisories (upgrade to latest) | Best framework if one is wanted: typed structured output, model-agnostic, evals and OTel in the same ecosystem, Python. |
| LangGraph | langgraph 1.2.19 (2026-10-30) (https://github.com/langchain-ai/langgraph/releases) | Graph/checkpointing machinery. Overkill for a fixed pipeline. |
| OpenAI Agents SDK (Python) | v0.24.0, 2026-10-15; still 0.x; native OTel export only in an alpha (https://github.com/openai/openai-agents-python/releases) | Tied to OpenAI; no benefit here. |
| Claude Agent SDK | Python and TypeScript; embeds the Claude Code agent loop and binary, with file/bash tools, hooks, subagents; API-key auth only for third parties (https://code.claude.com/docs/en/agent-sdk/overview) | Built for coding-agent-style loops. Wrong shape for a stateless search endpoint. |
| Vercel AI SDK | `ai@7.0.162`, 2026-11-03 (https://github.com/vercel/ai/releases). Has `WorkflowAgent` with durable runs and OTel bridge | Strongest TypeScript option and the best streaming/UI story, but would force a TS rewrite of the Python backend. Reconsider only if the backend moves to Next.js. |
| Mastra (TS) | `@mastra/core@1.82.0`, 2026-11-04; frequent breaking changes between minors (https://github.com/mastra-ai/mastra/releases) | TS-only and churning. Skip. |
| Plain provider SDK | n/a | **Recommended for the first version.** Two calls and a schema is under 100 lines. Add Pydantic AI only when you want model fallback or built-in evals. |

Python vs TypeScript: both ecosystems are mature in 2026 and Pydantic AI (v2.x) matches TS offerings on streaming adapters. The backend is Python/FastAPI, so there is no reason to change language.

## 3. Models and cost

**Gemini** (https://aistudio.google.com/docs/deprecations, https://aistudio.google.com/docs/pricing; the old ai.google.dev URLs redirect there):
- `gemini-2.0-flash` and `-001`: Deprecated, shutdown **June 1, 2026** (listed as earliest date). The page says replacement `gemini-3.6-flash`. **The app's model ID is at or past shutdown; verify it still responds.**
- `gemini-2.5-flash` shuts down Dec 1, 2026 and routes to `gemini-3.5-flash-lite`, billed at Flash-Lite rates.
- Current: `gemini-3.8-flash` (released 2026-09-02), `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite` (shutdown May 7, 2027), `gemini-3.1-pro-preview`, and a "Gemini 4 Argon" listed in pricing (not otherwise verified).
- Per 1M tokens (input/output, standard; batch is 50%): 3.8 Flash $0.75/$3.75 (**doubles Jan 1, 2027**); 3.6 Flash same; 3.5 Flash-Lite $0.30/$2.50; 3.1 Flash-Lite $0.25/$1.50; 2.5 Flash-Lite $0.10/$0.40; 3.1 Pro preview $2/$12. Cached input about 10% of input price, plus an hourly storage charge.

**Claude** (https://platform.claude.com/docs/en/about-claude/pricing): Haiku 5.5 $0.10/$0.50 (prompts up to 100k; $0.50/$2.50 above); Sonnet 5.5 $2/$10; Opus 5.5 $4/$20; Fable 5.1 $10/$50. Cache reads are 10% of input (Haiku 5.5 $0.01, Sonnet 5.5 $0.10); 5-minute cache writes are 1.25x; Batch API is 50% off.

**OpenAI** (https://developers.openai.com/api/docs/pricing): gpt-6-luna $0.10/$0.50; gpt-6.1-terra $1/$5; gpt-6.1-sol $2/$10; gpt-5.4-nano $0.20/$1.25; gpt-5.4-mini $0.75/$4.50; gpt-5-nano $0.05/$0.40; batch about 50%. The 5.6 and 6 families are many and overlapping; I did not check their quality tiers.

**Estimate per search** (router about 1k in/100 out; ranker about 6k in [50 candidates at about 80 tokens, plus profile and instructions] /1.5k out; my assumption, thinking tokens excluded):

| Router + ranker models | Approx. cost |
|---|---|
| Haiku 5.5 + Haiku 5.5 | about $0.0015 |
| Gemini 3.5 Flash-Lite both | about $0.006 |
| Gemini 3.8 Flash both | about $0.011 (about $0.022 after Jan 1, 2027 price doubling) |
| Haiku 5.5 router + Sonnet 5.5 ranker | about $0.028 |

Batch halves these but is irrelevant to interactive search; it fits nightly alert scans. The prompts are small, so caching saves little; it matters only if the shared system prompt/taste profile grows past the provider minimum (check minimums before relying on it). Quality tiers across vendors were not benchmarked here, so choose the ranker by your own eval set.

## 4. Long-running runs and streaming

- The first fix is to cut latency by removing serial LLM steps, which should take the run to seconds, then stream stage events. A 3-minute single request with a raised timeout is the symptom.
- **SSE** from FastAPI (`StreamingResponse`/`EventSourceResponse`) is sufficient. Use named events for stages and a final `results` event.
- **AI SDK UI message stream / resumable streams** need the `resumable-stream` package, Redis and a persisted `activeStreamId` per chat (https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-resume-streams). Pydantic AI has a Vercel AI adapter and AG-UI 1.0 support, so you can adopt either protocol later without a framework change.
- **AG-UI** is an agent-to-frontend event protocol. Third-party sources call it the most nascent of the UI protocols (UNVERIFIED, vendor blogs: https://www.copilotkit.ai/blog/the-developer-s-guide-to-generative-ui-in-2026).
- **Durable execution** (Temporal, Inngest, DBOS, Vercel Workflow, Trigger.dev): Vercel Workflow's last doc date I could confirm was Dec 2025, in Beta; GA status UNVERIFIED. Pydantic AI integrates Temporal and Azure Durable Task. **Overkill for a search that finishes in seconds.** It becomes worth it only for the proactive-alert scanner (long fan-out over many users, retries, schedules). A cron job plus a DB table of `last_seen` is enough to start.

## 5. Generative UI and agent-facing surfaces

- **MCP Apps:** servers declare a `ui://` resource, rendered as a sandboxed iframe in the host. Supported in Claude, Claude Desktop, VS Code Copilot, Microsoft 365 Copilot, Goose, Postman and others (https://modelcontextprotocol.io/extensions/apps/overview). I did not confirm ChatGPT apps' current relationship to it.
- **A2UI** (declarative UI JSON) and **AG-UI** (transport): complementary per vendor sources (UNVERIFIED, secondary).
- **WebMCP:** proposed standard for sites to expose tools to browser agents (declarative HTML forms or imperative JS). Early preview only as of 2026-02-10 (https://developer.chrome.com/blog/webmcp-epp).
- **For this app:** the concert card list is fixed-shape, so ordinary React rendering of the typed results is right. Skip generative UI. **Exposing the product as an MCP server** (`search_concerts(location, dates, artists, genre)` returning structured results, with an optional MCP App card list) is the cheapest way to get agent-facing distribution. It needs the deterministic pipeline first, since the MCP tool should wrap the same function.

## 6. Quality, evals, safety

- **Evals:** Pydantic Evals (plain functions accepted as evaluators; CI provenance attributes in v2.64) and ADK's eval (token/duration metrics in v2.10+) are the framework-native options; Braintrust, Langfuse and Promptfoo are the vendor options (I did not fetch their pages; versions UNVERIFIED). Start with Anthropic's guidance: about 20 test queries, an LLM judge with a rubric, judge end state not path, plus human spot checks (https://www.anthropic.com/engineering/built-multi-agent-research-system).
- **Deterministic evals first:** router accuracy on a golden set (dates, locations, genres), ID validity (every returned ID was offered), schema validity, latency and cost budgets. These need no ground truth and can gate CI.
- **No-ground-truth recommendation metrics:** for the ranker, check (a) agreement with a held-out set of the user's own saved/clicked concerts, (b) rank stability across repeated runs and prompt variants, (c) constraint satisfaction (date/location/genre as hard filters in code), (d) diversity (no more than N from one artist), (e) pairwise LLM-judge against a baseline ranker. Keep the judge on a different model family than the ranker. These are standard practices, not sourced to a specific page.
- **Tracing:** OTel GenAI semantic conventions have moved to https://github.com/open-telemetry/semantic-conventions-genai (status not read; treat as unstable). ADK v2.13 changed default span schema and removed the `call_llm` span, so pin the schema version if staying on ADK.
- **Prompt injection:** event descriptions and playlist names are attacker-controlled. Willison's lethal trifecta (private data + untrusted content + exfiltration channel): remove a leg (https://simonw.substack.com/p/the-lethal-trifecta-for-ai-agents). Design patterns paper, summarised 2025-06-13 (https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/): once an agent reads untrusted input, constrain what it can do. Here that is easy: the ranker has **no tools**, receives only short structured fields (omit free-text descriptions entirely, or truncate and label as data), and outputs only IDs and a short reason validated against the offered set. Render reasons as plain text, never as HTML or links. CaMeL-style systems are unnecessary at this level.

## 7. Personalization and memory

- **Taste profile:** compute deterministically from Spotify (top artists, genres weighted by play rank/recency), stored as a small JSON; pass that to the ranker. No memory framework is needed.
- **Embeddings vs LLM rerank:** `gemini-embedding-2` is current and `gemini-embedding-001` shuts down May 14, 2028 (deprecations page). Embeddings fit candidate generation over a large catalogue. With about 50 candidates, a single LLM rerank is cheaper to build and explains itself. Add embeddings only if the candidate set grows into the hundreds or thousands.
- **Feedback loop:** log shown/clicked/saved/dismissed per concert ID, and feed recent positives and negatives into the profile. This also builds the labelled set that fixes the "no ground truth" problem.
- **Proactive alerts:** a scheduled job (cron/worker) re-runs the deterministic fetch per saved search, diffs against `last_seen` event IDs, and only calls the ranker on new events. Use batch pricing there (50% off). This is where durable execution might become relevant at scale, not before.
