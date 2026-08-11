# Makefile for local development

.PHONY: run test lint migrate

run:
	uvicorn app.main:app --reload

test:
	python -m pytest

lint:
	ruff check .
	ruff format .

migrate:
	alembic upgrade head

migrate-make:
	alembic revision --autogenerate -m "$(msg)"

install:
	uv pip install -e ".[dev]"
