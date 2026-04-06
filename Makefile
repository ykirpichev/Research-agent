.PHONY: help install test lint format clean run docs

help:
	@echo "Research Agent - Available commands"
	@echo "===================================="
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make install          Install dependencies with Poetry"
	@echo "  make install-dev      Install with dev dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make test             Run test suite"
	@echo "  make test-cov         Run tests with coverage report"
	@echo "  make lint             Run all linters (ruff + mypy)"
	@echo "  make format           Format code (black + isort)"
	@echo "  make clean            Clean up generated files"
	@echo ""
	@echo "Running:"
	@echo "  make run              Run CLI help"
	@echo "  make explore          Run exploration (requires configured LLM)"
	@echo ""
	@echo "Docs & Build:"
	@echo "  make docs-build       Build documentation"
	@echo "  make build            Build package"
	@echo ""

install:
	poetry install --no-dev

install-dev:
	poetry install

test:
	poetry run pytest tests/ -v

test-cov:
	poetry run pytest tests/ -v --cov=research_agent --cov-report=html --cov-report=term-missing

lint:
	poetry run ruff check src/ tests/
	poetry run mypy src/research_agent

format:
	poetry run black src/ tests/
	poetry run isort src/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .coverage -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type f -name '.DS_Store' -delete

run:
	poetry run research-agent --help

explore:
	poetry run research-agent explore . --max-ideas 10

docs-build:
	poetry run sphinx-build -b html docs/ docs/_build

build:
	poetry build

dev-server:
	poetry run uvicorn research_agent.api.app:app --reload --port 8000

env-init:
	[ -f .env ] || cp .env.example .env
	@echo "✓ Created .env file (update with your API keys)"

pre-commit-install:
	poetry run pre-commit install

.DEFAULT_GOAL := help
