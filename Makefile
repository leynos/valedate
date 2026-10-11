# Every uv call goes through the vendored helper, which cleans the environment,
# uses the global uv cache, runs offline first and goes online at most once. See
# https://github.com/leynos/shared-actions/tree/main/uv_gate for the contract.
UV_GATE ?= python3 scripts/uv_gate.py
UV ?= uv
# The helper finds uv on PATH, so a caller's UV=/path/to/uv is honoured by putting
# that uv's directory first on PATH for every recipe.
export PATH := $(if $(findstring /,$(UV)),$(patsubst %/,%,$(dir $(UV))):)$(PATH)
# A UV given on the command line or in the environment must exist: the helper would
# otherwise fall back to whichever uv is found next on PATH.
ifneq ($(filter command line environment,$(origin UV)),)
ifneq ($(findstring /,$(UV)),)
ifeq ($(wildcard $(UV)),)
$(error UV=$(UV) does not exist)
endif
endif
endif
MDLINT ?= markdownlint-cli2
NIXIE ?= nixie
TOOLS = ruff ty $(MDLINT) $(MDTABLEFIX) uv
VENV_TOOLS = pytest

# `make fmt` and `make check-fmt` call mdtablefix directly. `--git` selects the
# Markdown files Git tracks and `--include-untracked` adds the untracked files
# Git does not ignore, so a new document is formatted before it is staged.
# Both modes need mdtablefix 0.6.1 or later; CI pins the version at its
# install-mdtablefix step.
MDTABLEFIX ?= mdtablefix
MDTABLEFIX_SELECT = --git --include-untracked
MDTABLEFIX_RULES = --wrap --renumber --breaks --ellipsis --fences

.PHONY: prepare help all clean build build-release lint fmt check-fmt \
        markdownlint nixie test typecheck $(TOOLS) $(VENV_TOOLS)

prepare: ## Install the locked development environment, offline first
	$(UV_GATE) prepare --group dev

.DEFAULT_GOAL := all

all: build check-fmt test typecheck

build: uv prepare ## Build virtual-env and install deps

build-release: ## Build artefacts (sdist & wheel)
	python -m build --sdist --wheel

clean: ## Remove build artifacts
	rm -rf build dist *.egg-info \
	  .mypy_cache .pytest_cache .coverage coverage.* \
	  lcov.info htmlcov .venv
	find . -type d -name '__pycache__' -print0 | xargs -0 -r rm -rf

define ensure_tool
	@command -v $(1) >/dev/null 2>&1 || { \
	  printf "Error: '%s' is required, but not installed\n" "$(1)" >&2; \
	  exit 1; \
	}
endef

define ensure_tool_venv
	@$(UV_GATE) run -- which $(1) >/dev/null 2>&1 || { \
	  printf "Error: '%s' is required in the virtualenv, but is not installed\n" "$(1)" >&2; \
	  exit 1; \
	}
endef

ifneq ($(strip $(TOOLS)),)
$(TOOLS): ## Verify required CLI tools
	$(call ensure_tool,$@)
endif


ifneq ($(strip $(VENV_TOOLS)),)
.PHONY: $(VENV_TOOLS)
$(VENV_TOOLS): prepare ## Verify required CLI tools in venv
	$(call ensure_tool_venv,$@)
endif

fmt: ruff $(MDTABLEFIX) $(MDLINT) ## Format sources
	ruff format
	ruff check --select I --fix
	$(MDTABLEFIX) --in-place $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)
	$(MDLINT) --fix "**/*.md"

check-fmt: ruff $(MDTABLEFIX) ## Verify formatting
	ruff format --check
	$(MDTABLEFIX) --check $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)

lint: ruff ## Run linters
	ruff check

typecheck: build ty ## Run typechecking
	ty --version
	ty check valedate tests

markdownlint: $(MDLINT) ## Lint Markdown files
	$(MDLINT) '**/*.md'

nixie: ## Validate Mermaid diagrams
	$(call ensure_tool,$(NIXIE))
	$(NIXIE) --no-sandbox

test: build uv $(VENV_TOOLS) ## Run tests
	$(UV_GATE) run -- pytest -v -n auto tests

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":"; printf "Available targets:\n"} {printf "  %-20s %s\n", $$1, $$2}'
