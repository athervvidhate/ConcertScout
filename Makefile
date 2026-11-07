.PHONY: install dev start redis api frontend-dev frontend-start check

install:
	cd api && uv sync --locked
	cd frontend && npm ci

# The API always runs in production mode. `dev` uses `next dev` for UI work.
dev: install
	$(MAKE) -j3 redis api frontend-dev

# A full run, with the frontend's production build on port 3000.
start: install
	cd frontend && npm run build
	$(MAKE) -j3 redis api frontend-start

redis:
	@redis-cli ping >/dev/null 2>&1 || exec redis-server --save "" --appendonly no

api:
	cd api && uv run uvicorn --factory concert_scout.app:create_app --host 127.0.0.1 --port 8000 --no-proxy-headers

frontend-dev:
	cd frontend && npm run dev

frontend-start:
	cd frontend && npm start

check:
	cd api && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
	cd frontend && npm run lint && npm run typecheck && npm test
