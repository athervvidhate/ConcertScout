.PHONY: install dev start phone redis supabase api frontend-dev frontend-start check check-accounts e2e check-live check-context

API_HOST ?= 127.0.0.1
LAN_IP = $(shell ipconfig getifaddr en0)

install:
	cd api && uv sync --locked
	cd frontend && npm ci

# The API always runs in production mode. `dev` uses `next dev` for UI work.
dev: install supabase
	$(MAKE) -j3 redis api frontend-dev

# A full run, with the frontend's production build on port 3000.
start: install supabase
	cd frontend && npm run build
	$(MAKE) -j3 redis api frontend-start

# The same full run, reachable from a phone on this network. Phones treat plain HTTP as insecure,
# so location and the Spotify connection need a real HTTPS deployment.
phone: install supabase
	cd frontend && npm run build
	@echo "On your phone, open http://$(LAN_IP):3000"
	API_HOST=0.0.0.0 CORS_ORIGINS='["http://127.0.0.1:3000","http://localhost:3000","http://$(LAN_IP):3000"]' $(MAKE) -j3 redis api frontend-start

# Accounts run on a local Supabase stack in Docker: Postgres, Auth and the Data API.
# Sign-in emails land in its inbox at http://127.0.0.1:54324.
supabase:
	cd frontend && npx supabase start --workdir ..

redis:
	@redis-cli ping >/dev/null 2>&1 || exec redis-server --save "" --appendonly no

api:
	cd api && uv run uvicorn --factory concert_scout.app:create_app --host $(API_HOST) --port 8000 --no-proxy-headers

frontend-dev:
	cd frontend && npm run dev

frontend-start:
	cd frontend && npm start

check:
	cd api && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
	cd frontend && npm run lint && npm run typecheck && npm test

# Account ownership against the real local Supabase stack.
check-accounts: supabase
	cd api && uv run pytest -m supabase

# Production browser journeys with isolated Redis and domain adapter fixtures.
e2e: supabase
	cd frontend && npm run build:e2e && npm run test:e2e

# Explicit network/cost check against the configured real providers.
check-live:
	cd api && uv run pytest -m live tests/live

# Local transcript adapters, without a model request. Claude mod runtime checks are optional.
check-context:
	python3 -m unittest discover -s tests -p 'test_agent_context.py'
