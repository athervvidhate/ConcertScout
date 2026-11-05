# 09 - Model options for the two LLM calls (as of 2026-11-04)

All model IDs and prices come from OpenRouter's live API (`https://openrouter.ai/api/v1/models` and `/models/{id}/endpoints`, fetched 2026-11-04) unless a source is cited. Anthropic's live pricing page confirms the claim in doc 02. Items I could not confirm are marked UNVERIFIED.

## Shortlist to evaluate head to head

| # | Model (OpenRouter ID) | Why it is on the list |
|---|---|---|
| 1 | `anthropic/claude-haiku-5.5` (baseline) | Cheapest "known good" structured output. Reasoning can be turned off. Served by Anthropic, Vertex and Bedrock, all ZDR-listed. |
| 2 | `deepseek/deepseek-v4.1-flash` | The Chinese-lab pick. Open weights, hosted by about 35 ZDR-listed, mostly US or Western inference companies. Reasoning can be turned off. AA measured 1.26 s time to first answer token in non-reasoning mode. |
| 3 | `qwen/qwen3.8-flash` | Second Chinese-lab pick. Reasoning is optional. The catch: Alibaba is the only provider, and it is not on the ZDR list, so it cannot be used with `provider.zdr=true`. |
| 4 | `google/gemma-4-31b-it` | Western open-weight model, non-reasoning by default, 16 ZDR-listed providers, about $0.10/$0.34 at the cheapest. The cheap control for "does a small dense model know enough artists?" |

Optional fifth run: `xiaomi/mimo-v2.6-flash` ($0.14/$0.28, 4 ZDR providers). AA gives it Intelligence Index 27 at $0.13/task, but 30 s time to first token, UNVERIFIED for non-reasoning mode.

Not recommended: Muse Spark (see section 2), `z-ai/glm-5.3-flash` and `minimax/minimax-m3.1-flash` (reasoning is mandatory, so time to first token will miss the 2 s target and reasoning tokens are billed as output), `mistralai/mistral-small-2603` (AA Intelligence Index 4), `google/gemini-3.5-flash-lite` (mandatory reasoning, AA time to first token 5.48 s, about 4x Haiku's cost).

## Comparison table

Per-search cost = interpreter (1,500 in / 150 out) + ranker (4,000 in / 700 out), so 5,500 in and 850 out in total. Prices are per 1M tokens, with no reasoning tokens counted. "Searches per $5" is gross, before the OpenRouter credit fee (section 4); multiply by about 0.95 for the fee.

| Model | In / out ($/M) | Context | Per search | Searches per $5 | Structured output | Reasoning | Providers (count; notable) |
|---|---|---|---|---|---|---|---|
| Haiku 5.5 (baseline) | 0.10 / 0.50 | 1M (price rises above 100k prompt, not relevant) | $0.00097 | about 5,100 | yes (`structured_outputs`) | optional, `none` supported | Anthropic, Vertex, Azure, Bedrock; same list price |
| DeepSeek V4.1 Flash, cheapest ZDR endpoint | 0.045 / 0.50 (Wafer US, mxfp4) | 1M | $0.00067 | about 7,400 | yes | optional, default high, `none` supported | 35 ZDR; also Together, Fireworks, Parasail, DeepInfra, Baseten, Nebius, Google |
| DeepSeek V4.1 Flash, typical fp8 | 0.14 / 0.42 (DeepInfra) | 1M | $0.00113 | about 4,400 | yes | as above | as above |
| DeepSeek V4.1 Flash, big-vendor price | 0.30 / 1.20 (Together, Fireworks, Parasail, Vertex) | 1M | $0.00267 | about 1,900 | yes | as above | as above |
| Qwen3.8 Flash | 0.15 / 0.47 | 1M | $0.00122 | about 4,100 | yes | optional, default on | Alibaba Cloud only (two endpoints); no ZDR |
| Gemma 4 31B | 0.10 / 0.34 (CoreWeave fp4); 0.14 / 0.40 bf16 | 262k | $0.00084 to $0.00124 | about 4,000 to 6,000 | yes on most endpoints | off by default | 16 ZDR; CoreWeave, Crusoe, DeepInfra, Venice, Parasail |
| MiMo V2.6 Flash (optional) | 0.14 / 0.28 | 1M | $0.00101 | about 5,000 | yes | optional | Xiaomi, DeepInfra, Cohere, Makora, Venice, GMI |
| Muse Spark 1.3 (Standard) | 1.25 / 4.25 | 1M | $0.0105 | about 480 | yes | mandatory | Meta only |
| Muse Spark 1.3 Contributor | 0.10 / 0.20 | 1M | $0.00072 before reasoning tokens | about 6,900 before reasoning tokens | yes | mandatory | Meta only; trains on your data |
| Muse Spark Open | 1.25 / 4.25 | 1M | $0.0105 | about 480 | yes | mandatory | Fireworks, Together, Nebius, Modal, Makora, Baseten |

Rows I excluded after looking: GLM-5.3 Flash $0.15/$0.50 (mandatory reasoning), MiniMax M3.1 Flash $0.15/$0.60 (mandatory reasoning, and a 50% off-peak override between 15:00 and 01:00 UTC), Seed 2.0 Mini $0.10/$0.40 (only ByteDance's own endpoint, no AA score), Gemini 3.5 Flash-Lite $0.30/$2.50 (see above), Kimi K3 and K3.1 Pro (list prices of $2+/M output; the API shows anomalous input prices such as $0.192, UNVERIFIED), Qwen3.7 Flash $0.03/$0.13 (no structured-output flag in the model list). The OpenRouter model list for GLM-5.2 ($0.006 in / $6.80 out) and DeepSeek V4 Pro ($0.115 in) shows similar oddities. Treat "top provider" prices on `/models` as unreliable and read `/endpoints` instead.

Verified baseline: the Anthropic pricing page lists Haiku 5.5 at $0.10 input and $0.50 output for prompts up to 100k tokens, and $0.50 / $2.50 above that. Cache reads are $0.01 and the Batch API is $0.05 / $0.25. Source: https://platform.claude.com/docs/en/about-claude/pricing (fetched 2026-11-04). Doc 02's figure is correct. OpenRouter's `anthropic/claude-haiku-5.5` shows the same $0.10 / $0.50.

## 1. Landscape (OpenRouter, 2026-11-04)

Cheap and mid-tier text models with `structured_outputs` and `response_format` in their supported parameters. Prices are from the cheapest listed endpoint at fetch time.

| Family | Models (ID, $ in / out per M, context) |
|---|---|
| DeepSeek | `deepseek-v4.1-flash` 0.045 / 0.50 to 0.30 / 1.20, 1M. `deepseek-v4-flash` 0.091 / 0.182, 1M (older, 0423). `deepseek-v4-pro-0813` anomalous pricing, `deepseek-v4-pro` 1.60 / 3.20. |
| Qwen | `qwen3.8-flash` 0.15 / 0.47, 1M. `qwen3.8-27b` 0.15 / 1.875. `qwen3.7-flash` 0.03 / 0.13 (no structured-output flag). `qwen3.7-plus` 0.32 / 1.28. `qwen3.6-35b-a3b` 0.10 / 0.90, 262k. |
| Kimi | `kimi-k3` (anomalous: 0.192 / 16), `kimi-k3.1-pro` 2.00 / 10.00, `kimi-k2.6` 0.65 / 3.41. Too expensive for this job. |
| GLM | `glm-5.3-flash` 0.15 / 0.50 (floor about 0.03 / 0.22 on fp4 endpoints), `glm-5.3-flashx` 0.37 / 1.25, `glm-4.7-flash` 0.061 / 0.40, `glm-5.3` anomalous. |
| MiniMax | `minimax-m3.1-flash` 0.15 / 0.60, `minimax-m3` 0.30 / 1.20. |
| ByteDance Seed | `seed-2.0-mini` 0.10 / 0.40, `seed-2.0-lite` 0.25 / 2.00, `seed-2-1-turbo` 0.50 / 2.50. |
| Xiaomi | `mimo-v2.6-flash` 0.14 / 0.28, `mimo-v2.6-pro` 0.435 / 0.87. |
| Google | `gemma-4-31b-it` 0.10 / 0.34 to 0.20 / 0.40, `gemma-4-26b-a4b-it` 0.042 / 0.126 (cheapest, 262k), `gemini-3.5-flash-lite` 0.30 / 2.50, `gemini-3.8-flash` 0.825 / 4.125. |
| Mistral | `mistral-small-2603` 0.15 / 0.60, `ministral-14b-2512` 0.20 / 0.20, `mistral-large-4-0` 0.70 / 2.10. |
| Others worth knowing | `nvidia/nemotron-3.5-super-vl` 0.15 / 0.50 (AA index 14), `nvidia/nemotron-3.5-lightning` 0.07 / 0.20 (AA index 6), `openai/gpt-oss-120b` 0.014 / 0.052 (131k, older), `openai/gpt-6-luna` 0.10 / 0.50 (same price as Haiku 5.5), `tencent/hy4` 0.417 / 1.25, `particle-ai/particle-1` 0.05 / 0.50 (coding model post-trained on DeepSeek V4.1 Flash). |

Llama: `meta-llama/llama-4-maverick` ($0.35/$1.00) and `llama-3.3-70b-instruct` ($0.20/$0.52) are still listed. The owner is right that they are old. No new Llama generation appears in the list.

Latency and throughput: OpenRouter's API returned `null` for `latency_last_30m` and `throughput_last_30m` on every endpoint I queried, and the model pages did not render those numbers through the fetcher. So I have no live OpenRouter tokens-per-second figures: UNVERIFIED. The only independent time-to-first-token numbers are from Artificial Analysis (section 3).

Reasoning flags from the model list (`reasoning.mandatory`): GLM-5.3 Flash true, MiniMax M3.1 Flash true, Muse Spark (all variants) true, Gemini 3.5 Flash-Lite true. DeepSeek V4.1 Flash, Qwen3.8 Flash, Haiku 5.5, Gemma 4, Mistral Small 4 and Seed 2.0 Mini are false. DeepSeek V4.1 Flash defaults to reasoning on (effort `high`); send `reasoning: {effort: "none"}` or `{enabled: false}` for the interpreter and ranker. Reasoning tokens are billed as output tokens: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens (2026-11-04). Left on, they would multiply the output side of the estimate several times and wreck time to first token.

## 2. "Muse"

Muse is Meta's model family from Meta Superintelligence Labs. Facts, all from live pages:

- **Muse Spark 1.1 / 1.2 / 1.3** are closed and hosted. Meta's own API serves them (public preview, US developers at launch), and OpenRouter lists `meta/muse-spark-1.1`, `-1.2`, `-1.3` with Meta as the only provider. Price is $1.25 in / $4.25 out per M, 1M context. Sources: https://dev.meta.ai/docs/models.md (2026-11-04), https://aiweekly.co/node/5972 (published 2026-07-09, citing CNBC, $20 free credit).
- **Contributor tier** (`meta/muse-spark-1.3-contributor`): $0.10 in / $0.20 out. Meta's docs state that content "may be used to train future Meta models" in exchange for the lower price, and the tier is selected by model ID. Do not send user search text there without the owner accepting that.
- **Muse Spark Open** (`meta/muse-spark-open`) is open-weight: 816B total, 42B active MoE, 256 experts, 1M context. The license allows commercial use up to $20M revenue and requires a "Built with Muse Spark Open" display. It is not on Meta's own Model API; third parties host it on OpenRouter (Fireworks, Together, Nebius, Modal, Makora, Baseten) at $1.25 / $4.25. The OpenRouter description calls it coding-optimized. Source: https://www.deeplearning.ai/the-batch/meta-releases-wonder-opens-spark/ (2026-10-23).
- **Muse Glimmer 30B** (`meta/muse-glimmer-30b`) is a smaller open-weight dense model distilled from Muse Spark, at $0.30 / $1.20 and a 131k context. I did not benchmark it: UNVERIFIED for fit.
- Artificial Analysis lists Muse Spark Open (xhigh) at Intelligence Index 25, $2.02 per task, 13.8 s to first answer token (https://artificialanalysis.ai/leaderboards/models, 2026-11-04). DeepLearning.AI cites an AA index of 39 for it, probably from a different index version: UNVERIFIED which is current.

Verdict: Muse is not suited to this job. Reasoning is mandatory on every variant, so time to first token will miss the 2 s target. Standard pricing is about 11x Haiku per search. The only cheap variant (Contributor) trains on user prompts and is also reasoning-only. If the owner wants a Muse run for curiosity, test `muse-spark-1.3` Standard on 20 queries only.

## 3. Benchmarks and evidence

Artificial Analysis leaderboard (https://artificialanalysis.ai/leaderboards/models, fetched 2026-11-04; the page gave no index version, and `artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index` names v5.0.1):

| Model | Intelligence Index | Cost per task | Time to first answer token |
|---|---|---|---|
| DeepSeek V4.1 Flash 1017, non-reasoning | 19 | $0.43 | 1.26 s |
| DeepSeek V4.1 Flash 1017, high / max | 29 / 33 | $0.46 / $0.60 | 22.6 s / 44.9 s |
| Claude Haiku 5.5, low / medium | 19 / 25 | $0.04 / $0.09 | 9.6 s / 11.1 s |
| Claude Haiku 5.5, non-reasoning | not listed | | |
| GLM-5.3 Flash | 28 | $0.58 | 77 s |
| MiniMax-M3.1-Flash | 29 | $0.49 | 65.6 s |
| MiMo-V2.6-Flash | 27 | $0.13 | 30.5 s |
| Gemini 3.5 Flash-Lite | 12 | $0.69 | 5.5 s |
| Mistral Small 4 | 4 | $0.04 | 16.4 s |
| GPT-6 Luna, non-reasoning | 9 | $0.07 | 1.15 s |
| Qwen3.8 Flash, Gemma 4 31B, Seed 2.0 Mini | not extractable | | |

These are general-intelligence numbers over agentic-style tasks, not niche knowledge. The "time to first answer token" column includes reasoning time, so only the non-reasoning rows predict our streaming UX. The 2 s target is plausible for DeepSeek V4.1 Flash non-reasoning (1.26 s) and GPT-6 Luna non-reasoning (1.15 s); Haiku 5.5 non-reasoning latency is UNVERIFIED and must be measured.

Structured-output reliability: I found no independent benchmark for the shortlisted models. OpenRouter states that schema enforcement varies by endpoint: some providers guarantee conformance and others treat the schema as a hint, and "Schema compliance is not guaranteed on every endpoint" (https://openrouter.ai/docs/guides/features/structured-outputs, 2026-11-04). So reliability must be measured per provider endpoint. See the eval plan.

Music and artist knowledge: no independent evidence found for any candidate. UNVERIFIED across the board. Parameter count is the only proxy: Gemma 4 31B (dense, about 31B) is the smallest on the list and the most likely to fail on indie artists; DeepSeek V4.1 Flash is 552B total, 8B active on input (per its OpenRouter description), so it is a large sparse model with more stored world knowledge than its active size suggests. Treat this as a hypothesis for the eval, not a finding.

## 4. OpenRouter mechanics

All from https://openrouter.ai/docs/... pages fetched 2026-11-04.

- **Structured outputs:** `response_format: {type: "json_schema", json_schema: {name, strict: true, schema}}`. Support is per endpoint, listed under each model's Providers section as `structured_outputs`. Streaming works; the partial JSON validates once complete. Non-streaming requests can use the Response Healing plugin. A model without support errors out.
- **`provider.require_parameters: true`:** routes only to endpoints that support every parameter in the request. By default, `response_format` and `tools` are soft preferences, so without this flag OpenRouter may silently send your schema to an endpoint that ignores it. Always set it for both calls.
- **Provider routing fields:** `sort` (`price`, `throughput`, `latency`), `order`, `only`, `ignore`, `allow_fallbacks`, `require_parameters`, `data_collection` (`allow`/`deny`), `zdr`, `quantizations`, `max_price` ({prompt, completion} per M), `preferred_min_throughput`, `preferred_max_latency` (soft preferences, percentile-based).
- **Default routing:** weighted random across providers by price, throughput, time to first token, reliability and tool-call quality. Follow-up requests stick to the same provider while its cache is warm.
- **`:floor`** appends to the slug, sorts by price, and makes flex tiers eligible. **`:nitro`** sorts by throughput and makes priority tiers eligible. Floor can land on fp4 endpoints at $0.006/M input for DeepSeek, with possible quality loss. Use `quantizations: ["fp8","bf16"]` if you want to rule that out.
- **`max_price`:** requests above the ceiling are not run. Useful as a budget guard, for example `{prompt: 0.35, completion: 1.3}` for DeepSeek.
- **Fees:** inference is billed at provider list price with no markup. Credit purchase fee is 5.5% on Standard (8% Business). BYOK has no fee under $25,000 per month. Sources: https://openrouter.ai/pricing and https://openrouter.ai/docs/faq (2026-11-04). So $5 buys about $4.74 of inference.
- **Free tier:** `:free` variants exist (for example `google/gemma-4-31b-it:free`, `nvidia/nemotron-3.5-super-vl:free`). Limits are 20 requests per minute and 50 per day, rising to 1,000 per day after buying at least $10 of credits. Fine for evals, not for production, and free endpoints are not on the ZDR list (UNVERIFIED for each).
- **Prompt caching:** DeepSeek is implicit, reads at 0.1x; Z.AI implicit; Alibaba Qwen needs explicit `cache_control`, writes 1.25x, reads 0.1x, and works only on specific models; Anthropic explicit, reads 0.1x. With 1,500 and 4,000 token prompts and most of the ranker prompt being per-user candidates, savings are small. Skip caching for v1.
- **Data policy:** "Prompt and completion are not logged by default" (FAQ). Opt-in logging gives a 1% discount. Inputs go to whichever provider you route to, and "some Model Providers may use your Inputs and Outputs for model training" (https://openrouter.ai/privacy, updated 2026-08-31). The privacy page does not say prompts are never stored, so rely on routing controls, not on OpenRouter's defaults.
- **ZDR routing:** `provider: {zdr: true}` per request (or account and guardrail settings, combined by OR). Only ZDR endpoints qualify, and "Safety Retention" endpoints (abuse screening, no training) are allowed unless the account disallows them. Unverified endpoints are excluded. OpenRouter will screen all traffic for CSAM from 2026-10-27 and may retain flagged content. Live list: `https://openrouter.ai/api/v1/endpoints/zdr` (1,118 entries on 2026-11-04). Source: https://openrouter.ai/docs/guides/features/zdr.
- **ZDR coverage of the shortlist (from that list):** Haiku 5.5 on Vertex and Bedrock yes. DeepSeek V4.1 Flash yes (35 endpoints). Gemma 4 31B yes (16). Qwen3.8 Flash no (Alibaba only). Muse Spark Open yes (7). Muse Spark 1.3 and Contributor no.
- **China-hosted versus US-hosted open weights:** the same open weights (DeepSeek, GLM, MiniMax, MiMo, Muse Open) are served by many Western hosts (Together, Fireworks, Parasail, DeepInfra, Nebius, CoreWeave, Baseten, Google Vertex) alongside lab-run endpoints (Z.AI, Minimax, Xiaomi, Alibaba, StreamLake, SiliconFlow, Baidu). I did not find a field in the endpoints API that states each provider's country, so the mapping of each host to a jurisdiction is UNVERIFIED and should be checked on the provider's own policy. The practical rule: for DeepSeek, GLM, MiniMax and MiMo, use `provider.only` with a Western ZDR host and `allow_fallbacks: false`, or use `zdr: true` plus `data_collection: "deny"`. For models served only by the lab (Qwen3.8 Flash on Alibaba Cloud, Seed 2.0 Mini on ByteDance), the lab is the data processor and no ZDR guarantee is listed for Qwen. Alibaba's endpoint is labelled "Alibaba Cloud Int." and also has a `us-east-1` tag; actual data residency: UNVERIFIED.
- **Privacy implications for us:** prompts carry free-text search and artist names, and the ranker prompt also carries Spotify-derived taste data. That is personal data under most regimes. Recommendation: send `provider: {require_parameters: true, zdr: true, data_collection: "deny"}` for every call. Never use `:free`, Contributor tiers, or lab-only endpoints for real user traffic. Strip any user identifiers from the prompt. Note that `zdr: true` can shrink the provider pool and raise latency; the evals should run with it on.
- **EU residency:** DeepSeek V4.1 Flash, Qwen3.8 Flash and Muse pages say "not currently available through EU in-region routing."

## 5. Pydantic AI and OpenRouter

Source: https://pydantic.dev/docs/ai/models/openrouter/ (2026-11-04; the old ai.pydantic.dev URL redirects).

- Install: `pip install "pydantic-ai-slim[openrouter]"`.
- Classes: `OpenRouterModel`, `OpenRouterProvider(api_key, app_url, app_title)`, `OpenRouterModelSettings`. A string such as `'openrouter:deepseek/deepseek-v4.1-flash'` also works with `Agent`. `OPENROUTER_API_KEY` is read from the environment.
- Settings: `openrouter_provider` passes the routing object (for example `{'only': [...], 'allow_fallbacks': False}`, and by extension `zdr`, `require_parameters`, `max_price`; the page shows `order` and `allow_fallbacks` only, so the other fields are UNVERIFIED but should pass through as the same JSON). `openrouter_reasoning={'effort': ...}` sets reasoning. `extra_body` carries any other field. `openrouter_usage={'include': True}` returns cost data.
- Structured output: the page does not document `NativeOutput`, `ToolOutput` or `PromptedOutput` for OpenRouter beyond Anthropic notes. Use the default tool-based output first, then try `NativeOutput` (json_schema) per model and let the eval pick. Reliability differs per endpoint, so record which mode each model passed.
- Doc 02 mentions Pydantic AI v2.66.0 (2026-11-04). I did not re-check the version here.

## Cost summary and how far $5 goes

Per-search costs are in the comparison table. For a 1,000-search month (a plausible hobby load) the baseline costs about $0.97 and the cheapest DeepSeek endpoint about $0.67, so a $5 to $10 monthly budget is not the constraint at this scale; time to first token, privacy and quality are. Even DeepSeek at big-vendor prices ($0.0027) gives about 1,900 searches per $5 (about 1,800 after the 5.5% credit fee).

Risk to the budget: leaving reasoning on. At DeepSeek V4.1 Flash's default effort, a few thousand reasoning tokens per call at $0.50 to $1.20/M adds $0.002 to $0.006 per call and 20+ seconds of latency. Set `reasoning: {effort: "none"}`, set `max_tokens`, and assert `usage.completion_tokens` in the eval.

## Eval plan (minimal)

Use the 30 to 50 case golden set from doc 02, plus a 20-query "indie artists" set (small and regional acts, ideally from the owner's real taste).

1. Run the interpreter and ranker for all four models with `require_parameters`, `zdr`, reasoning off, `max_tokens` capped.
2. Record for each: schema-valid rate, ID validity (every ID was offered), reason quality (pairwise LLM judge on a different family than the model under test), median and p95 time to first token and total latency, tokens used, and OpenRouter-reported cost.
3. Test two DeepSeek endpoints (a fp4 floor host and a fp8 mainstream host) to see whether quantization matters.
4. Pick the cheapest model that is within noise of Haiku 5.5 on judge win rate and meets the 2 s time-to-first-token target. If none beats Haiku on indie-artist reasons, stay on Haiku: the cost difference is under $0.001 per search.

## Sources (all fetched 2026-11-04 unless noted)

- https://openrouter.ai/api/v1/models and `/api/v1/models/{id}/endpoints`, `/api/v1/endpoints/zdr`
- https://openrouter.ai/models, /deepseek, /qwen, /moonshotai, /z-ai, /minimax, /bytedance-seed
- https://openrouter.ai/meta/muse-spark-1.3-contributor, /meta/muse-spark-open, /qwen/qwen3.8-flash, /deepseek/deepseek-v4.1-flash
- https://openrouter.ai/docs/guides/features/structured-outputs, /docs/guides/routing/provider-selection, /docs/guides/features/zdr, /docs/guides/best-practices/prompt-caching, /docs/guides/best-practices/reasoning-tokens, /docs/faq, /pricing, /privacy
- https://platform.claude.com/docs/en/about-claude/pricing
- https://dev.meta.ai/docs/models.md
- https://www.deeplearning.ai/the-batch/meta-releases-wonder-opens-spark/ (published 2026-10-23)
- https://aiweekly.co/node/5972 (published 2026-07-09)
- https://artificialanalysis.ai/leaderboards/models
- https://pydantic.dev/docs/ai/models/openrouter/
