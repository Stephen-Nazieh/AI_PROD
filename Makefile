# DeParadigm Media — studio task runner.
#
# Thin wrapper over the commands documented in AGENTS.md so they're discoverable
# from one place. Everything runs through the project venv (env/bin/python3); no
# global Python state is assumed. Run `make` or `make help` for the menu.
#
# This file does NOT replace setup_env.sh (deps) — it orchestrates the entrypoints.

PY      := env/bin/python3
SKILLS  := 01_SKILLS
BRIDGE  := runtime/agents/paperclip_bridge.py
BRIDGE_LOG := /tmp/bridge.log

# Use the venv python if present, else fall back to system python3.
PYBIN := $(shell [ -x "$(PY)" ] && echo "$(PY)" || echo python3)

.DEFAULT_GOAL := help

.PHONY: help setup test test-suite doctor status runs bridge bridge-stop \
        db kb compile clean-pyc

help: ## Show this menu
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## One-time: create venv + install deps (01_SKILLS/setup_env.sh)
	bash $(SKILLS)/setup_env.sh

test: doctor ## Alias for `doctor` (fast control-plane smoke tests)

doctor: ## Fast smoke tests / health checks (studio doctor)
	$(PYBIN) tests/smoke_test.py

test-suite: ## Full syntax/import/functional suite over all modules
	$(PYBIN) $(SKILLS)/test_suite.py run

status: ## Services + companies/units/runs overview
	$(PYBIN) $(SKILLS)/studio.py status

runs: ## Production run dashboard (stage progress)
	$(PYBIN) $(SKILLS)/studio.py runs

db: ## Bootstrap/reset the production-tracking schema (port 5432)
	$(PYBIN) $(SKILLS)/init_database.py

kb: ## Knowledge-base CLI passthrough — `make kb ARGS="..."`
	$(PYBIN) $(SKILLS)/studio.py kb $(ARGS)

bridge: ## Start the Paperclip bridge in the background (logs to $(BRIDGE_LOG))
	@pgrep -f "$(BRIDGE)" >/dev/null && echo "bridge already running (pid $$(pgrep -f '$(BRIDGE)'))" || \
	  ( nohup $(PYBIN) $(BRIDGE) > $(BRIDGE_LOG) 2>&1 & echo "bridge started → $(BRIDGE_LOG)" )

bridge-stop: ## Stop the Paperclip bridge (quiesce poller before registry migrations)
	@pkill -f "$(BRIDGE)" && echo "bridge stopped" || echo "bridge not running"

compile: ## Byte-compile every module (cheap syntax gate)
	$(PYBIN) -m compileall -q $(SKILLS) runtime tests

clean-pyc: ## Remove __pycache__ / *.pyc
	find . -path ./node_modules -prune -o -name '__pycache__' -type d -print -exec rm -rf {} + 2>/dev/null; true
