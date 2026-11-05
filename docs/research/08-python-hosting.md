# 08 - Python API hosting comparison

Date: 2026-11-04. Method: vendor pricing and docs pages fetched and read on this date (URLs in the Sources section). Search snippets were used only where marked. Anything I could not confirm on a primary page is marked UNVERIFIED. Prices are USD unless stated. This supersedes the hosting leads in `04-platform-and-delivery.md`.

## Workload assumed

One FastAPI service (Google ADK, Python), 512 MB RAM (256 MB is probably too small for ADK: UNVERIFIED, measure it). Roughly 1,000 searches a month, each an SSE stream of up to 60 s, so about 17 active hours a month. Browsers connect directly to `api.concertscout.app`. A Redis-like store holds rate limits, API cache and the spend counter. Egress is negligible (a few GB at most).

## Ranked recommendation

1. **Fly.io, 512 MB shared-cpu-1x, autostop to zero, Upstash Redis free tier.** About $0.50-$4/month (about $1 with autostop, $3.69 if kept always-on). No platform minimum, free TLS certificates, shared IPv4 and inbound traffic, real long-lived HTTP. Cost of the choice: a cold start of about 2 s from `stopped` before your Python imports run, a CLI/Dockerfile workflow, and no built-in PR previews.
2. **Railway Hobby, one service, Upstash free (or Railway Redis).** About $5.50-$7/month. Simplest developer experience (GitHub deploy, PR environments, dashboard, no cold start if you leave sleeping off). The $5 plan fee is a floor, so it costs 3-10x more than Fly for this traffic. Railway Hobby is still $5, not higher (checked below).
3. **Vercel Python Functions on Hobby** ($0). Cheapest and lowest-ops if the terms allow it: FastAPI is zero-config, `StreamingResponse` is documented, Hobby max duration is 300 s. Two real risks: Hobby is "personal, non-commercial use only" (affiliate links could breach it), and the ADK import cold start is UNVERIFIED. Worth a one-hour spike, not the default.
4. Render Starter ($7), Cloudflare Containers ($5 floor), Northflank free sandbox (terms UNVERIFIED), Google Cloud Run (free compute, but weak custom-domain story), Modal (150 s HTTP cap, free credits), AWS Lambda (cheap, high setup burden).
5. Not recommended: Hetzner with Coolify or Dokploy (cheap plans unavailable, orderable plan is over budget), Koyeb (free tier status unclear, acquired by Mistral).

Why Fly over Railway: the total budget is $10-15 including LLM, and a $5 floor is a third or more of it for a service that runs about 17 hours a month. Why not Cloud Run despite the $0 compute: its documented custom-domain options are a Preview feature or a load balancer, which clashes with the "api.concertscout.app with TLS" requirement.

## Monthly cost table (this workload)

| Platform | Compute | Platform minimum | Egress | Redis | Est. total / month |
|---|---|---|---|---|---|
| Fly.io (autostop) | 512 MB at $3.69/mo full-time, so about $0.30 for about 60 active hours | none | $0.02/GB NA/EU | Upstash free: $0 | **$0.50-1.50** (always-on: $3.69-4) |
| Railway Hobby | about $5 for 0.5 GB always on ($10/GB-month) plus small CPU | $5 fee (includes $5 credit) | $0.05/GB | Upstash free: $0 (Railway Redis adds its own memory usage) | **$5.50-7** |
| Vercel Hobby | free within caps (4 h Active CPU, 360 GB-h memory) | $0 | 100 GB free | Upstash via Marketplace: $0 | **$0** (Pro: $20) |
| Render Starter | $7 (512 MB, 0.5 CPU) | Hobby workspace $0 | 5 GB then $0.15/GB | Upstash free; Render free Key Value is 25 MB and wiped on restart | **$7** |
| Google Cloud Run | inside free tier (180k vCPU-s, 360k GiB-s, 2M requests: figures from search results, UNVERIFIED on the primary page) | none, but a billing account | 1 GiB free then paid (UNVERIFIED) | Upstash free | **$0** plus domain cost (load balancer cost UNVERIFIED) |
| Cloudflare Containers | `basic` (1 GiB) usage is inside included 25 GiB-h | $5 Workers Paid | $0.025/GB, 1 TB included | Upstash free | **$5** |
| Northflank | free sandbox lists "up to $20/mo of resources", 2 services, 1 database; paid 0.5 vCPU/1 GB is $12/mo | $0 listed | $0.06/GB | one free DB slot, or Upstash | **$0 (terms UNVERIFIED) to $12** |
| Modal Starter | $30/mo free credits, $0.0000131/core-s, $0.00000222/GiB-s | $0 | not listed | Upstash free | **$0** |
| AWS Lambda | inside free tier (1M requests, 400k GB-s) | none | streaming $0.008/GB after 100 GB free | Upstash free | **$0-1** plus CloudFront in front (UNVERIFIED) |
| Hetzner + Coolify/Dokploy | CPX12 (1 vCPU, 2 GB) EUR 11.99 incl. IPv4 | none | 20 TB included | Redis on the box, or Upstash free | **about EUR 12 (about $13-14)** |
| Koyeb | page shows Pro $29/mo with $10 compute; free tier status conflicting | $29 (Pro) | $0.02/GB after 1 TB | none listed | **$29 or UNVERIFIED free** |

All Upstash-free figures assume the traffic stays under 500K commands a month (about 25-50K requests at 10-20 commands each).

## Per-platform notes

Each block: scale-to-zero and cold start; SSE and timeouts; free tier; custom domain; GitHub deploy and previews; Redis; solo-dev burden.

### Fly.io
- Scale to zero: `auto_stop_machines`, `auto_start_machines`, `min_machines_running = 0`. Docs: cold start from `stopped` is "about 2 seconds or more for common apps"; resume from `suspended` is "a few hundred milliseconds" with caveats. Your ADK import time comes on top (UNVERIFIED, measure it).
- SSE: Fly Proxy forwards long HTTP responses; I did not find a documented hard timeout (UNVERIFIED). Send a keepalive comment every 15-20 s anyway.
- Free tier: none for new orgs; $1 trial credit for 7 days. No minimum bill.
- Domains: free for the first 10 single-hostname certificates; shared IPv4 and IPv6 free; a dedicated IPv4 is $2/month and not needed for a CNAME.
- Deploy: `fly deploy` from CLI or a GitHub Action (UNVERIFIED on this pass). No native PR previews; use a second app for staging.
- Redis: no first-party Redis in the pricing page; Upstash is offered as an extension billed on the Fly invoice. Use the free Upstash tier directly (same price, fewer moving parts).
- Burden: medium. Dockerfile, `fly.toml`, secrets via `fly secrets`. Stopped Machines still pay rootfs at $0.15/GB-month.

### Railway
- Hobby is **$5/month with $5 included usage**, and unused credit does not carry over. Pro is $20 with $20 credit. This confirms the plan price has not risen above $5 on the pricing page fetched 2026-11-04. The earlier "+40% in 2026" claim in note 04 is unsupported.
- Rates: $10/GB-month RAM, $20/vCPU-month, $0.05/GB egress, $0.15/GB-month volumes. Trial: one-time $5 credit, 30 days, no card.
- Scale to zero: "Serverless" app sleeping after 5 minutes without outbound packets (5-10 min in practice). First request after sleep has a cold boot and "may return a 502". Open DB connections, and any outbound request (including to Redis or Upstash), keep the service awake, so with this app it will rarely sleep. Treat Railway as always-on.
- SSE: requests run up to 15 minutes while data flows, close after 5 minutes idle. 60 s streams are fine. SSE is not named explicitly in the docs.
- Free tier: trial credit only.
- Domains: custom domains supported, automatic TLS at no cost (CNAME and TXT records).
- Deploy: GitHub deploy native. PR environments exist (created on PR open, deleted on merge); plan availability and billing not stated on the pages I read, UNVERIFIED for Hobby.
- Redis: one-click Redis template (single node, you own it once you modify it). Persistence and memory sizing not documented on the page read.
- Burden: lowest of the paid options.

### Render
- Prices: web service $7 (512 MB, 0.5 CPU), $25 (2 GB, 1 CPU). Workspace plans: Hobby $0, Pro $25. Hobby bandwidth 5 GB included, then $0.15/GB. Key Value: Free 25 MB (in-memory, wiped on any restart), $10 for 256 MB. A third-party review mentions a plan change on 1 August 2026; the pricing page I read does not (UNVERIFIED).
- Free web service: spins down after 15 min idle; cold start "about one minute"; 750 free hours a month; no persistent disk. Too slow for a first visitor.
- Starter ($7) does not spin down (always-on).
- SSE and timeouts: UNVERIFIED (not read). Domains and GitHub deploy are standard; PR previews on Hobby workspaces UNVERIFIED.
- Burden: low. Cost is the problem: $7 is fixed.

### Vercel Python Functions
- FastAPI: zero-config (`app` in `app.py`, `main.py`, etc., or `tool.vercel.entrypoint`). The whole app becomes one function on Fluid compute. Lifespan events supported, shutdown cleanup limited to 500 ms.
- Streaming: `StreamingResponse` documented. Duration limit includes streamed responses: Hobby 300 s default and max; Pro 300 s default, 800 s max, 1800 s beta. Python bundle limit 500 MB (up to 5 GB with beta Large Functions).
- Billing: Active CPU only (waiting on LLM or network I/O is free) plus provisioned memory time. Hobby includes 4 h Active CPU, 360 GB-h, 1M invocations; Hobby cannot buy more usage, so it hard-stops. Pro is $20 with a $20 credit.
- Hobby terms: "personal, non-commercial use." Affiliate links or any revenue risk a violation. UNVERIFIED how strictly enforced.
- Cold start: not documented on the pages read (UNVERIFIED). google-adk import time is the unknown.
- Domains, GitHub deploy, preview deployments per PR: native. Upstash via Vercel Marketplace.
- Burden: lowest overall, and it unifies with the Next.js project.

### Google Cloud Run
- Scales to zero (only requests scale from zero). Cold start is not quantified in the docs; Cloud Run may keep idle instances up to 15 minutes. Min instances cost idle money.
- Timeout: default 300 s, max 3600 s. Docs do not specifically address SSE.
- Free tier: figures from search results (180k vCPU-s, 360k GiB-s, 2M requests); the primary pricing page returned only a title (UNVERIFIED on the page itself). One article claims an August 2026 rate cut; unconfirmed.
- Custom domain: the recommended path is a global external Application Load Balancer (cost not stated on the page; I believe it is a fixed monthly charge, UNVERIFIED). **Domain mapping is Preview (Limited availability), "not production-ready"**, though available in us-central1 and several other regions, with automatic TLS in about 15-24 h. Firebase Hosting is a third option (its proxy timeout, UNVERIFIED, may cut 60 s streams).
- Deploy: Cloud Build or GitHub Actions; revision tags can give preview URLs (UNVERIFIED). Redis: Memorystore is not cheap (UNVERIFIED), use Upstash.
- Burden: medium-high (project, billing, IAM, Artifact Registry).

### Koyeb
- Pricing page now shows Pro $29/month with $10 included compute; scale-to-zero listed; 1 TB bandwidth. The only free item shown is a Postgres tier. Search results disagree on whether the free Starter tier still exists for new accounts (Mistral announced the acquisition in February 2026). No managed Redis listed. Not worth pursuing.

### Northflank
- Pricing page lists a free Sandbox: 2 services, 2 jobs, 1 database, up to $20/month of resources, "always on, no sleeping." Paid compute: $0.01667/vCPU-hour and $0.00833/GB-hour; nf-compute-50 (0.5 vCPU, 1 GB) is $12/month; egress $0.06/GB. Redis add-on price not itemized (an example calculator shows $5.52 for one Redis).
- The page carries a notice of a security incident and advises rotating credentials. Check status before trusting it with secrets. Free-tier conditions (duration, card, abuse limits) UNVERIFIED. SSE, domains, GitHub CI not read. Worth a look only if you want $0 always-on.

### Modal
- Starter: $0 base, $30/month free compute credits, containers stay billable 60 s after last input. Web endpoints (`fastapi_endpoint`, `asgi_app`) are listed as "limited" on Starter.
- **Each HTTP request has a hard 150 s limit**; longer runs return a 303 redirect to a result URL, which does not work for CORS requests. A 60 s SSE stream fits, but a browser-direct stream over 150 s would not. Streaming/SSE not discussed on the page; cold-start behaviour, custom domains and preview environments UNVERIFIED. Built for ML workloads rather than long-lived small web apps.

### Cloudflare Containers and Python Workers
- Containers need Workers Paid ($5/month). Instance types: lite 256 MiB (1/16 vCPU), basic 1 GiB (1/4 vCPU). Billed per 10 ms active; included 25 GiB-h memory, 375 vCPU-min; egress 1 TB included in NA/EU. A Worker routes to a Durable Object, which starts the container. Status (beta or GA), cold start time, and SSE/wall-clock limits through the Worker are UNVERIFIED; the docs say only that the container "starts on demand."
- Python Workers: the docs name FastAPI among packages but do not state GA status or limits (UNVERIFIED). They run Python in the Workers runtime, so google-adk compatibility is very doubtful (UNVERIFIED). Skip.
- Burden: medium; more moving parts (Worker + Durable Object + Dockerfile) than Fly.

### AWS Lambda with response streaming
- Native streaming is Node.js only. For Python, use a custom runtime or the Lambda Web Adapter. Function URL streaming not available inside a VPC. Streamed responses do not stop when the client disconnects; you pay for full duration. Streaming: first 6 MB free per request, then $0.008/GB; 100 GB/month free.
- Free tier 1M requests and 400k GB-s per month (Event Functions). Timeout up to 15 minutes (my knowledge, not on the page fetched; UNVERIFIED). Cold start: Python container image with ADK likely several seconds (UNVERIFIED).
- Custom domain on a Function URL needs CloudFront plus ACM (UNVERIFIED on this pass). Redis: ElastiCache is not cheap; use Upstash.
- Burden: high (IAM, ECR or zip layers, adapter, CloudFront).

### Hetzner with Coolify or Dokploy
- As of 2026-11-04 (Hetzner page fetched), every CX (x86) and CAX (Arm) plan on the Cost-Optimized page showed "currently unavailable." Prices there: CX23 (2 vCPU, 4 GB) EUR 5.99 incl. IPv4, CAX11 EUR 6.49. A 2026-09-08 article reports the orderable Regular Performance plans: CPX12 (1 vCPU, 2 GB) EUR 11.99 and CPX22 EUR 19.99, after price increases on 1 April and 15 June 2026 and a capacity notice dated 26 June 2026.
- Dokploy needs at least 2 GB RAM and 30 GB disk (its docs); Coolify minimums not on the page read. Both are free self-hosted. Traefik/Let's Encrypt TLS (Dokploy). GitHub deploys and PR previews: not covered on the pages I read; both advertise them (UNVERIFIED).
- No scale to zero, no cold start, no timeout limits. Burden: highest (OS patching, backups, security, the control plane itself eats RAM). Budget: about $13-14 a month for hosting alone, over the entire target. Not worth it.

## Upstash Redis free tier (confirmed 2026-11-04)

From https://upstash.com/pricing/redis:
- Free: 1 database, **250 MB** max data, 10 GB monthly bandwidth, **500K commands/month**. (Note 04 said 256 MB; the page says 250 MB.)
- Pay as you go: $0.20 per 100K commands, storage $0.25/GB after the first 1 GB, bandwidth free up to 200 GB then $0.03/GB. Max request size 10 MB.
- Fixed plans start at $10/month (250 MB).
- The page does not mention inactivity archiving or deletion of free databases; historically I recall it, so verify in the console (UNVERIFIED).
- Fit: rate limiting plus cache plus spend counter fits well within 500K commands for this traffic. Count commands per request in the code (INCR + EXPIRE for limits, GET/SET for cache, INCRBYFLOAT for spend) before relying on it. It is a network hop from the API, so pick the Upstash region next to the host. Hard-capped free commands double as a safety net; set the PAYG budget cap if you add a card.
- On Fly: also offered as a Fly extension billed on the Fly invoice at Upstash list price; no reason to prefer that over direct signup.

## Decision notes

- Cold-start impact is the real tradeoff. Fly at about 2 s plus ADK import is acceptable for a portfolio demo if the frontend shows a "warming up" state (the progress bar added in commit b2a0fd4 already helps). If it proves too slow, set `min_machines_running = 1` (about $3.69) and the cost is still below Railway.
- Per the repo's own rule against stopgaps: do not choose a free tier that sleeps for about a minute (Render Free) or one that depends on card-free terms that may change (Koyeb, Northflank sandbox).
- Keep SSE heartbeats (comment line every 15-20 s) on whichever host to survive idle-timeout proxies.
- Open question to settle before building: how heavy is `import google.adk` plus the agent at startup, and what is the RSS memory of the process? That decides 256 vs 512 MB and whether Vercel's cold start is acceptable.

## Sources (all fetched 2026-11-04 unless noted)

- Railway pricing: https://railway.com/pricing ; plans: https://docs.railway.com/reference/pricing/plans ; app sleeping: https://docs.railway.com/reference/app-sleeping ; limits: https://docs.railway.com/networking/public-networking/specs-and-limits ; environments: https://docs.railway.com/environments ; domains: https://docs.railway.com/reference/public-networking ; Redis: https://docs.railway.com/databases/redis
- Render: https://render.com/pricing.md ; https://render.com/docs/free ; plan-change claim (third party, UNVERIFIED): https://jwatte.com/blog/render-com-platform-review.md
- Fly.io: https://docs.fly.io/about/pricing ; https://docs.fly.io/launch/autostop-autostart
- Google Cloud Run: https://docs.cloud.google.com/run/docs/configuring/request-timeout ; https://docs.cloud.google.com/run/docs/about-instance-autoscaling ; https://docs.cloud.google.com/run/docs/mapping-custom-domains ; pricing page returned only a title, free-tier and rates came from search results (UNVERIFIED): https://cloud.google.com/run/pricing
- Koyeb: https://www.koyeb.com/pricing ; third-party search results on free tier, UNVERIFIED
- Northflank: https://northflank.com/pricing
- Modal: https://modal.com/pricing ; https://modal.com/docs/guide/webhook-timeouts
- Vercel: https://vercel.com/docs/functions/limitations (updated 2026-08-24) ; https://vercel.com/docs/frameworks/backend/fastapi (updated 2026-08-27) ; https://vercel.com/pricing
- Cloudflare: https://developers.cloudflare.com/containers/pricing/ ; https://developers.cloudflare.com/containers/platform-details/limits/ ; https://developers.cloudflare.com/containers/ ; https://developers.cloudflare.com/workers/languages/python/
- AWS Lambda: https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html ; https://aws.amazon.com/lambda/pricing/
- Hetzner: https://www.hetzner.com/cloud/cost-optimized ; https://www.vincentschmalbach.com/hetzner-cheap-cloud-unavailable-price-increases/ (article, 2026-09-08)
- Coolify: https://coolify.io/docs/get-started/introduction ; Dokploy: https://docs.dokploy.com/docs/core/installation
- Upstash: https://upstash.com/pricing/redis
