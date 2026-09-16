PY ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
export PYTHONPATH := tools

.PHONY: help setup test lint format runbooks index triage demo links stale versions check clean

help:
	@echo "setup     cria .venv, instala o pacote e as ferramentas de dev"
	@echo "test      roda a suíte de testes com o python do venv"
	@echo "lint      ruff check + ruff format --check"
	@echo "runbooks  valida front matter, seções, comandos e links (sretriage check-runbooks)"
	@echo "index     regenera a tabela de runbooks/README.md"
	@echo "triage    roda o sretriage contra os alvos padrão e escreve reports/"
	@echo "demo      sobe o servidor de teste local e roda o triage contra ele"
	@echo "links     audita os links externos (reports/link-audit.md)"
	@echo "stale     lista runbooks vencidos (reports/stale-runbooks.md)"
	@echo "versions  atualiza docs/versions.md a partir do upstream"
	@echo "check     test + lint + runbooks + index --check"

setup:
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -e ".[dev]"
	@echo "pronto: use 'make test' (o Makefile usa .venv quando ele existe)"

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format:
	$(PY) -m ruff format .

runbooks:
	$(PY) -m sretriage check-runbooks

index:
	$(PY) -m sretriage index

triage:
	$(PY) -m sretriage run --target https://example.org --target-host 1.1.1.1 --out reports/

demo:
	$(PY) tools/demo_server.py --port 8099 & \
	sleep 1; \
	$(PY) -m sretriage run --target http://127.0.0.1:8099/healthz --target https://example.org --target-host 1.1.1.1 --out reports/; \
	status=$$?; \
	kill %1 2>/dev/null || true; \
	exit $$status

links:
	$(PY) tools/audit_links.py links

stale:
	$(PY) tools/audit_links.py stale

versions:
	$(PY) tools/update_versions.py

check: test lint runbooks
	$(PY) -m sretriage index --check

clean:
	rm -rf .pytest_cache .ruff_cache reports/triage-*.md
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
