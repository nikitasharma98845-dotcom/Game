.PHONY: install test lint rtp run migrate docker

install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/python -m pytest -q

lint:
	.venv/bin/ruff check bot tests
	.venv/bin/mypy bot

rtp:
	.venv/bin/python -m scripts.rtp_report --rounds 100000

run:
	.venv/bin/python -m bot

migrate:
	.venv/bin/alembic upgrade head

docker:
	docker compose up --build
