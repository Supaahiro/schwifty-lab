# CLAUDE.md

## Working with the project owner

Implementation and architectural decisions belong to the user. When the user
makes a choice, follow it: do not challenge it, reopen the discussion, or replace
it with a solution you prefer. If a concrete technical obstacle arises, describe
it with supporting evidence and ask only for the clarification needed to proceed.
A different preference is not an obstacle.

Do not independently introduce new rules, prohibitions, or permanent constraints
for the project. Your choices during a task do not become the user's decisions.
This file describes the project and helps readers navigate the code; it is not a
record of prescriptions accumulated from previous sessions.

Do not modify this document without the user's explicit consent.

## What schwifty-lab is

A Jekyll blog and a collection of independent demo and utility projects.
Posts live at the repository root; `projects/` contains the applications and
tools they reference, while `blog-posts/` contains examples for individual articles.

Each project has its own toolchain and README. There is no shared build system
or dependency graph across the projects. The blog is published at
`https://supaahiro.github.io/schwifty-lab/`.

## Where the code lives

| Path | Contents |
|---|---|
| `_posts/`, `_config.yml`, `_config.local.yml`, `Gemfile` | Blog content, Jekyll configuration, and Ruby dependencies |
| `blog-posts/` | Per-article examples, including Kubernetes manifests and Helm charts |
| `projects/ai-agent/` | Python/uv LangGraph agent with retrieval and persistent memory |
| `projects/code-sign/` | PowerShell Authenticode signing toolkit |
| `projects/yaml-encryption/` | Python CLI wrapping SOPS and age |
| `projects/talos-vms/` | Ansible provisioning for Talos/Omni virtual machines |
| `projects/api-resilience/` | .NET client, server, contracts, and logging example |
| `projects/cryptography/` | Cryptography explanations and Python examples |
| `.github/` | Validation workflow, dependency updates, actions, and scripts |

The AI agent selects chat and embedding providers through `config.json`,
validated by `core/config.py` within that project. Provider registration lives
in `providers/__init__.py`, tool registration in `tools/__init__.py`, and the
LangGraph conversation loop in `agent.py`.

Importing `main.py` performs no I/O; bootstrap runs through `build_app`.
History trimming preserves tool-call/response boundaries. Vector indexing
reuses unchanged content IDs; removal of stale IDs is not implemented.
See `projects/ai-agent/README.md` for setup and configuration.

## Build and tests

Validate the affected project using its own toolchain. CI selects project jobs
by changed paths and also checks YAML and committed line endings. The workflow is
`.github/workflows/pr-validate.yml`; project jobs cover PowerShell syntax and
encoding, the AI agent, and the .NET example.

The AI agent uses pytest through uv; the .NET example runs a Release build.
PowerShell validation parses scripts and checks encoding without executing the
scripts.

The AI agent's history, memory, and knowledge-base tests do not need a live model
provider. The knowledge-base tests may download a HuggingFace embedding model on
first use. The application's interactive session requires configured credentials
or a reachable local provider. Its pytest configuration sets `pythonpath = ["."]`
so imports work when running `uv run pytest`.
Repeat checks after relevant changes or to investigate a failure.

## Essential commands

From the repository root, for the blog:

```powershell
bundle install
./start-dev.bat web
```

`Gemfile` references the local theme at `../blog-jekyll-theme`; that path must
resolve from the checkout for Bundler to install it.
The startup script runs Jekyll with `_config.local.yml` and live reload.

For repository tooling, from the root:

```powershell
npm install
pip install yamllint
yamllint -c .yamllint.yml .
```

From `projects/ai-agent/`:

```powershell
uv sync
uv run pytest
uv run pytest tests/test_history.py -v
uv run pytest tests/test_memory.py::test_update_memory_merges_user_info
uv run python main.py
```

The interactive command requires `config.json` and the applicable `.env`
settings. Example configurations and provider setup are in the project's README.
Other projects document their own commands in their READMEs.

Changes land through topic branches and PRs into `master`. Conventional Commits are enforced by
Husky and commitlint; scopes are lowercase and subjects use sentence-case with a
72-character limit. See `.commitlintrc.yml` for accepted types.

`.github/versions.json` defines CI toolchain versions. The shared CI contracts
are in `.github/actions/README.md` and `.github/scripts/README.md`; the
toolchain action and encoding script follow the copies in `Supaahiro/blog`.
Dependency update configuration lives in `.github/dependabot.yml`; Bundler
updates are omitted because the theme is a local path dependency. The AI agent's
updates use the `uv` ecosystem and arrive grouped in a single PR.
