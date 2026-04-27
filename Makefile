.PHONY: help dev run stop reset local local-backend local-frontend \
       setup seed seed-demo log-crawl test test-backend test-frontend \
       logs logs-backend version bump-patch bump-minor bump-major \
       docker-image setup-venv clean lint format

# ── VERSION ────────────────────────────────────────────────────────
VERSION_FILE := VERSION
VERSION := $(shell cat $(VERSION_FILE) 2>/dev/null || echo "0.0.0")
MAJOR := $(shell echo $(VERSION) | cut -d. -f1)
MINOR := $(shell echo $(VERSION) | cut -d. -f2)
PATCH := $(shell echo $(VERSION) | cut -d. -f3)

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

##@ Help
help: ## Show available targets (grouped)
	@echo ""
	@echo "  ARTs v$(VERSION) - Autonomous Relational Triage System"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; section=""} \
		/^##@/ {section=substr($$0, 5); printf "\n  \033[1;33m%s\033[0m\n", section; next} \
		/^[a-zA-Z_-]+:.*?##/ {printf "    \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""

##@ Development
dev: ## Start full stack with hot-reload (Docker)
	docker compose up --build

local: ## Run backend + frontend locally (no Docker)
	@echo "--> Starting ARTs v$(VERSION) locally..."
	@echo "    Backend  -> http://localhost:8000"
	@echo "    Frontend -> http://localhost:3000"
	@echo ""
	@trap 'kill 0' INT TERM; \
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 & \
	cd frontend && WATCHPACK_POLLING=true NEXT_PUBLIC_API_URL=http://localhost:8000 npx next dev -p 3000 & \
	wait

local-backend: ## Run backend only (no Docker)
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

local-frontend: ## Run frontend only (no Docker)
	cd frontend && WATCHPACK_POLLING=true NEXT_PUBLIC_API_URL=http://localhost:8000 npx next dev -p 3000

##@ Database
setup: ## Run schema setup and seed rules (requires running db)
	docker compose exec backend python -m scripts.setup_db
	docker compose exec backend python -m scripts.seed_rules

seed: ## Seed classification rules only (requires running db)
	docker compose exec backend python -m scripts.seed_rules

seed-demo: ## Seed demo data for dashboard charts
	cd backend && python -m scripts.seed_demo_data

##@ Cycle harvest (DragonSuite → API)
# Single CLI for ingesting failures; uses shared/crawler_utils (same as POST /triage/discover).
# Set DRAGONSUITE_API_BASE if not using the local mock on :9000.
CYCLE ?= 580
log-crawl: ## Harvest one cycle: make log-crawl CYCLE=580  optional: LIMIT=100
	cd backend && PYTHONPATH=.. python3 scripts/log_crawler.py $(CYCLE) $(LIMIT)

##@ Docker
run: ## Production-mode build and launch (detached)
	docker compose up -d --build

stop: ## Stop all services
	docker compose down

reset: ## Wipe all data and Docker volumes, rebuild from scratch
	docker compose down -v
	docker compose up -d --build db redis
	@echo "--> Waiting for database to be ready..."
	@sleep 5
	docker compose up -d --build backend frontend
	@echo "--> Reset complete. All services restarted."

docker-image: ## Build Docker images with auto-version-bump
	@$(MAKE) bump-patch
	@NEW_VERSION=$$(cat $(VERSION_FILE)); \
	echo "--> Building Docker images tagged v$$NEW_VERSION"; \
	docker build -t arts-backend:$$NEW_VERSION -t arts-backend:latest ./backend; \
	docker build -t arts-frontend:$$NEW_VERSION -t arts-frontend:latest ./frontend; \
	echo "--> Images built: arts-backend:$$NEW_VERSION, arts-frontend:$$NEW_VERSION"

##@ Testing
test: ## Run backend (pytest) and frontend (vitest) tests
	cd backend && python -m pytest tests/ -v
	cd frontend && npx vitest run

test-backend: ## Run backend tests only
	cd backend && python -m pytest tests/ -v

test-frontend: ## Run frontend tests only
	cd frontend && npx vitest run

##@ Code Quality
lint: ## Run linters (eslint + ruff/flake8)
	@echo "--> Linting frontend..."
	cd frontend && npx next lint || true
	@echo "--> Linting backend..."
	cd backend && (python -m ruff check . 2>/dev/null || python -m flake8 --max-line-length=120 app/ 2>/dev/null || echo "  Install ruff or flake8: pip install ruff")

format: ## Auto-format code (prettier + black)
	@echo "--> Formatting frontend..."
	cd frontend && (npx prettier --write "src/**/*.{ts,tsx,css}" 2>/dev/null || echo "  Install prettier: npm install -D prettier")
	@echo "--> Formatting backend..."
	cd backend && (python -m black . 2>/dev/null || echo "  Install black: pip install black")

##@ Versioning
version: ## Show current version
	@echo "ARTs v$(VERSION)"

bump-patch: ## Increment patch version (X.Y.Z -> X.Y.Z+1)
	@NEW_PATCH=$$(($(PATCH) + 1)); \
	echo "$(MAJOR).$(MINOR).$$NEW_PATCH" > $(VERSION_FILE); \
	echo "Version bumped: $(VERSION) -> $(MAJOR).$(MINOR).$$NEW_PATCH"

bump-minor: ## Increment minor version (X.Y.Z -> X.Y+1.0)
	@NEW_MINOR=$$(($(MINOR) + 1)); \
	echo "$(MAJOR).$$NEW_MINOR.0" > $(VERSION_FILE); \
	echo "Version bumped: $(VERSION) -> $(MAJOR).$$NEW_MINOR.0"

bump-major: ## Increment major version (X.Y.Z -> X+1.0.0)
	@NEW_MAJOR=$$(($(MAJOR) + 1)); \
	echo "$$NEW_MAJOR.0.0" > $(VERSION_FILE); \
	echo "Version bumped: $(VERSION) -> $$NEW_MAJOR.0.0"

##@ Environment Setup
setup-venv: ## Create Python virtualenv and install backend dependencies
	@echo "--> Creating virtualenv at $(VENV)..."
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt
	@echo "--> Virtualenv ready. Activate with: source $(VENV)/bin/activate"

##@ Cleanup
clean: ## Remove virtualenv and build artifacts
	@echo "--> Cleaning build artifacts..."
	rm -rf $(VENV)
	rm -rf frontend/.next frontend/node_modules
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "--> Clean complete."

##@ Logs
logs: ## Tail all service logs
	docker compose logs -f

logs-backend: ## Tail backend logs only
	docker compose logs -f backend
