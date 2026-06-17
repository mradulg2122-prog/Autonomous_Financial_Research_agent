.PHONY: help up down logs build test lint format migrate dev docs

help:
	@echo "ARA-1 Developer Commands"
	@echo "========================"
	@echo "  make up          Start all Docker services"
	@echo "  make down        Stop all Docker services"
	@echo "  make build       Rebuild Docker images"
	@echo "  make logs        Tail all service logs"
	@echo "  make dev         Run FastAPI dev server (local)"
	@echo "  make test        Run all tests with coverage"
	@echo "  make test-unit   Run unit tests only"
	@echo "  make test-int    Run integration tests only"
	@echo "  make lint        Lint with flake8 + mypy"
	@echo "  make format      Format with black + isort"
	@echo "  make migrate     Run Alembic migrations"
	@echo "  make docs        Open API docs in browser"
	@echo "  make benchmark   Run all 8 benchmark challenges"
	@echo "  make clean       Remove .pyc / __pycache__"

# ── Docker ─────────────────────────────────────────────────────
up:
	docker-compose up -d

down:
	docker-compose down

build:
	docker-compose build --no-cache

logs:
	docker-compose logs -f

restart:
	docker-compose down && docker-compose up -d

# ── Development ────────────────────────────────────────────────
dev:
	uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && python -m http.server 3000

# ── Database ───────────────────────────────────────────────────
migrate:
	alembic upgrade head

migrate-down:
	alembic downgrade -1

migrate-history:
	alembic history --verbose

# ── Testing ────────────────────────────────────────────────────
test:
	pytest backend/tests/ -v --cov=backend --cov-report=term-missing --cov-report=html

test-unit:
	pytest backend/tests/unit/ -v -m unit

test-int:
	pytest backend/tests/integration/ -v -m integration

test-watch:
	ptw backend/tests/ -- -v

# ── Benchmark ──────────────────────────────────────────────────
benchmark:
	python -c "import asyncio; from backend.evaluation.benchmarks import run_all_benchmarks; result = asyncio.run(run_all_benchmarks()); print(f'Passed: {result[\"passed\"]}/{result[\"total_challenges\"]} | Avg Score: {result[\"average_score\"]:.2f}')"

# ── Code Quality ───────────────────────────────────────────────
lint:
	flake8 backend/ --max-line-length=100 --exclude=backend/db/migrations/
	mypy backend/ --ignore-missing-imports --exclude backend/db/migrations

format:
	black backend/ --line-length=100
	isort backend/ --profile=black

check:
	black backend/ --check --line-length=100
	isort backend/ --check-only --profile=black

# ── Utilities ──────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	rm -rf .coverage htmlcov/ .pytest_cache/

docs:
	@echo "Opening API docs..."
	start http://localhost:8000/docs

shell:
	docker-compose exec backend python -c "from backend.core.config import settings; print(settings.model_dump())"
