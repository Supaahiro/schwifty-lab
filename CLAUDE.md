# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository overview

`schwifty-lab` is two things in one repo:

1. A Jekyll blog (root-level `_posts/`, `_config.yml`, `_config.local.yml`, `Gemfile`) published at https://supaahiro.github.io/schwifty-lab/.
2. A `projects/` monorepo of independent, self-contained demo/tool projects that the blog posts reference. Each project under `projects/*` has its own README, its own toolchain, and should be treated as a standalone unit — there is no shared build system or shared dependency graph between them.
3. `blog-posts/*` holds per-article code samples (Kubernetes manifests, Helm charts, kustomize overlays, etc.) referenced from `_posts/`.

Current projects:
- `projects/ai-agent` — Python/Poetry, a LangGraph ReAct+RAG agent demo (OpenAI or local llama.cpp). See its own README and the Architecture section below.
- `projects/code-sign` — PowerShell Authenticode signing toolkit for a local CA.
- `projects/yaml-encryption` — Python CLI wrapping SOPS/age for encrypting Kubernetes secret manifests.
- `projects/talos-vms` — Ansible playbooks provisioning VMware ESXi VMs for Talos/Omni.
- `projects/api-resilience` — .NET solution (client/server/contracts/logger).
- `projects/cryptography` — documentation + a single Python test file illustrating public/private key concepts.
- `projects/pdns-admin-lite` — FastAPI backend (Poetry) + Vue 3/Vite frontend managing PowerDNS records via its REST API; docker-compose dev stack with Caddy edge, nginx static server, and a seeded demo PowerDNS.

## Commit conventions

Commits are enforced by commitlint via a Husky `commit-msg` hook (`.husky/commit-msg`, config in `.commitlintrc.yml`), which requires **npm install at the repo root** to be active (`core.hooksPath` is wired by the `prepare` script). Rules:
- Conventional-commit type, one of: `feat, fix, hotfix, release, refactor, perf, test, docs, chore, ci, build, revert`.
- Scope, if present, lower-case.
- Subject in **sentence-case** (first letter capitalized), non-empty, max 72 chars.
- This repo does **not** use GitFlow — commits go directly to `master`, no `develop`/`feature`/`hotfix` branches.

## CI

`.github/workflows/`:
- `pr-validate-ai-agent.yml` — runs `poetry install` + `pytest` for `projects/ai-agent`, triggered on push to `master` and on pull requests touching `projects/ai-agent/**`. `pyproject.toml` sets `[tool.pytest.ini_options] pythonpath = ["."]` — without it, `poetry run pytest` (the bare console-script entry point) doesn't add the project root to `sys.path`, and `core`/`main`/`tools` imports fail in CI even though they work locally via `python -m pytest`.
- `pr-validate-lint.yml` — two jobs: `yamllint -c .yamllint.yml .` repo-wide, and a PowerShell check (`.ps1`/`.psm1`/`.psd1`) that parses every script via `[System.Management.Automation.Language.Parser]::ParseFile()` (never executes them) and checks BOM encoding via PSScriptAnalyzer's `PSUseBOMForUnicodeEncodedFile` rule.

`.github/actions/` and `.github/scripts/` are intentionally empty (see their `README.md`): only extract a composite action or script once something is actually reused or a single step grows past ~3 sub-steps — a lone `poetry install && pytest` stays inline in its workflow.

`.github/dependabot.yml` tracks `github-actions`, `pip` (`projects/ai-agent`), and `npm` (root `package.json`), weekly, targeting `master`. No `bundler` entry: the root `Gemfile` has a local path dependency (`blog-jekyll-theme`, a sibling repo) that Dependabot's isolated environment can never reach, which fails every run for that ecosystem outright.

## Common commands

**Jekyll blog** (from repo root):
```bash
bundle install
start-dev.bat web        # bundle exec jekyll serve --livereload --config _config.local.yml
```

**YAML lint** (from repo root):
```bash
pip install yamllint
yamllint -c .yamllint.yml .
```

**ai-agent** (from `projects/ai-agent`, conda env `langchain-python3.13` in this workspace):
```bash
poetry install
poetry run pytest              # full suite
poetry run pytest tests/test_history.py -v   # single file
poetry run pytest tests/test_memory.py::test_update_memory_merges_user_info  # single test
python main.py                 # interactive REPL, requires config.json + .env
```
`tests/test_kb.py` and `tests/test_history.py`/`test_memory.py` need no live API key or llama.cpp server — only `test_kb.py` needs network access once, to download the HuggingFace embedding model. `main.py` itself needs a real provider (OpenAI key or a running llama.cpp/Ollama/LM Studio server) to actually converse.

## Architecture: projects/ai-agent

A ReAct + RAG agent built on LangGraph, with two independently-swappable axes: **chat provider** (OpenAI vs. local llama.cpp-compatible server) and **embedding provider** (OpenAI vs. local HuggingFace sentence-transformers).

- **Config-driven, not code-driven**: all runtime behavior (provider choice, model names, KB paths, history window) comes from `config.json`, validated against the Pydantic models in `core/config.py` (`Config`, with a `model_validator` enforcing that the section matching `provider` is present). `config.example.openai.json` / `config.example.llamacpp.json` are the templates to copy.
- **`main.py` is import-safe**: all bootstrap (config load, provider selection, embeddings, tools, graph compile) is wrapped in `build_app(cfg) -> CompiledStateGraph`, called only from `main()`. Importing `main.py` performs no I/O — this is what makes `_trim_history` unit-testable in isolation.
- **Provider registry** (`providers/__init__.py`): `PROVIDERS: dict[str, BuildChatModel]` maps `config.provider` to a `build_chat_model(config)` function. Adding a new provider means adding a module under `providers/` with that function and one registry entry — no branching logic elsewhere.
- **Tools** (`tools/__init__.py`): `load_all_tools()` aggregates datetime/math tools, KB search (`tools/kb.py`, lazily builds a Chroma retriever on first use via a closure from `core.vectordb.vdb_builder`), and persistent memory (`tools/memory.py`, a flat `user_info` dict merged from tool calls, backed by a JSON file).
- **Vector DB** (`core/vectordb.py`): `vdb_builder()` returns a closure that (re)builds a Chroma collection. Document IDs are `source_path#content_hash` — stable across runs, unique across chunks of the same file, and change automatically when a chunk's content changes. `_builder_function` diffs against `collection.get(ids=...)` and only embeds chunks not already present, so re-runs with unchanged docs skip embedding entirely. There's no garbage collection of stale IDs for deleted/edited source docs — a known limitation.
- **Agent graph** (`agent.py`): a two-node LangGraph (`agent` ↔ `tools`) built with `StateGraph`; `AgentState` carries `messages` via the `add_messages` reducer. `main.py`'s `_trim_history` trims the conversation to `history_window` messages without ever starting the kept slice on a `ToolMessage` — trimming mid tool-call/response pair produces an invalid sequence that OpenAI-compatible APIs reject with a 400.
