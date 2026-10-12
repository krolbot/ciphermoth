override SHELL := /bin/bash

COMPOSE_PROD := docker compose -f docker-compose.prod.yml

.PHONY: all
all: clean dev

.PHONY: setup
setup:
	@if [ -f backend/.db.env ]; then \
		echo 'backend/.db.env already exists, leaving it untouched.'; \
	else \
		echo 'Creating backend/.db.env with a generated database password...'; \
		sed "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$$(openssl rand -base64 32)|" \
			backend/.db.env.template > backend/.db.env; \
		echo 'Done. Run "make dev" to start CipherMoth.'; \
	fi

# Development: local, build from source, hot-reload (UI :3000, API :8000)

.PHONY: dev
dev:
	@echo 'Starting the dev stack with hot-reload (UI :3000, API :8000)...'
	docker compose up -d --build

.PHONY: down
down:
	@echo 'Stopping the dev stack (database volume is kept)...'
	docker compose down

.PHONY: clean
clean:
	@echo 'Removing the dev stack and its database volume...'
	-docker compose down --volumes --remove-orphans --rmi local
	@echo 'Removing cache files...'
	-find . -type f -name '*.py[co]' -delete -o -type d -name __pycache__ -delete

# Production: the real vault, run from prebuilt GHCR images (needs a sibling .env)

.PHONY: prod-up
prod-up:
	@echo 'Pulling and starting the production stack from GHCR images...'
	$(COMPOSE_PROD) up -d

.PHONY: prod-up-autoupdate
prod-up-autoupdate:
	@echo 'Starting production + the opt-in one-click self-updater (Docker socket)...'
	$(COMPOSE_PROD) --profile autoupdate up -d

.PHONY: prod-down
prod-down:
	@echo 'Stopping the production stack (database volume is kept)...'
	$(COMPOSE_PROD) down

.PHONY: clean-prod
clean-prod:
	@echo 'WARNING: this DESTROYS the production database volume -> your real vault.'
	@echo 'There is no password recovery. This cannot be undone.'
	@read -r -p 'Type "destroy" to confirm: ' ans; \
	if [ "$$ans" = "destroy" ]; then \
		$(COMPOSE_PROD) down --volumes --remove-orphans; \
		echo 'Production stack and volume removed.'; \
	else \
		echo 'Aborted. Nothing was removed.'; \
	fi

# Release: bump versions, stamp the changelog, tag, push, and publish a GitHub
# release (which triggers the signed image build). Usage: make release VERSION=1.1.0
.PHONY: release release-dry
release:
	@test -n "$(VERSION)" || { echo 'usage: make release VERSION=X.Y.Z'; exit 1; }
	@scripts/release.sh "$(VERSION)"

release-dry:
	@test -n "$(VERSION)" || { echo 'usage: make release-dry VERSION=X.Y.Z'; exit 1; }
	@scripts/release.sh "$(VERSION)" --dry-run

.PHONY: lint
lint:
	cd backend && uv run ruff check .
	cd frontend && npm run lint

.PHONY: typecheck
typecheck:
	cd backend && uv run ty check .

.PHONY: format
format:
	cd backend && uv run ruff format .
	cd frontend && npm run format

# Tests run against a throwaway Postgres in a tmpfs container (no volume), removed afterwards.
TEST_DB_CONTAINER := ciphermoth-test-db
TEST_DB_PORT := 55432
TEST_DB_URL := postgresql://ciphermoth_test:ciphermoth_test@127.0.0.1:$(TEST_DB_PORT)/ciphermoth_test

define run_backend_tests
	@docker rm -f $(TEST_DB_CONTAINER) >/dev/null 2>&1 || true
	@docker run -d --rm --name $(TEST_DB_CONTAINER) \
		-e POSTGRES_USER=ciphermoth_test -e POSTGRES_PASSWORD=ciphermoth_test \
		-e POSTGRES_DB=ciphermoth_test -p 127.0.0.1:$(TEST_DB_PORT):5432 \
		--tmpfs /var/lib/postgresql/data postgres:16-alpine >/dev/null
	@for i in $$(seq 1 30); do \
		docker exec $(TEST_DB_CONTAINER) pg_isready -U ciphermoth_test -d ciphermoth_test >/dev/null 2>&1 && break; \
		sleep 1; \
	done
	@cd backend && CIPHERMOTH_TEST_DB_URL=$(TEST_DB_URL) $(1) uv run pytest $(2); \
		status=$$?; docker rm -f $(TEST_DB_CONTAINER) >/dev/null 2>&1; exit $$status
endef

.PHONY: test
test:
	$(call run_backend_tests,,)
	cd frontend && npm test
	node --test docker/frontend/runtime-config.test.mjs

# Builds the frontend image and checks its Content-Security-Policy in Chromium.
.PHONY: test-browser
test-browser:
	docker build -f docker/frontend/Dockerfile --build-arg VITE_API_URL=__CIPHERMOTH_API_URL__ -t ciphermoth-frontend:browser-test .
	cd docker/frontend/browser && npm ci && npx playwright install chromium && npm test

# Fuzzing with many more Hypothesis examples, fault injection and scale tests.
.PHONY: test-stress
test-stress:
	$(call run_backend_tests,HYPOTHESIS_PROFILE=stress,-m "stress or not stress")

.PHONY: check
check:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run ty check .
	cd frontend && npm run lint && npm run format:check
