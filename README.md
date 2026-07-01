# 🛸 schwifty-lab

Welcome to **schwifty-lab** — a creative playground for experiments and ideas.

Here you'll discover code samples, project snippets, and various experiments inspired by my blog and personal interests.

Some things may be polished, others experimental, but all are intended to spark new ideas.

[![pr-validate-ai-agent](https://github.com/SupaaHiro/schwifty-lab/actions/workflows/pr-validate-ai-agent.yml/badge.svg)](https://github.com/SupaaHiro/schwifty-lab/actions/workflows/pr-validate-ai-agent.yml)
[![pr-validate-lint](https://github.com/SupaaHiro/schwifty-lab/actions/workflows/pr-validate-lint.yml/badge.svg)](https://github.com/SupaaHiro/schwifty-lab/actions/workflows/pr-validate-lint.yml)

## My Blog

Find companion articles for the examples in this repo on the schwifty-lab blog: [schwifty-lab](https://supaahiro.github.io/schwifty-lab/)

## What's inside?

- ⚡ `blog-posts/` — code samples (Kubernetes manifests, Helm charts, kustomize overlays, ...) referenced from blog articles in `_posts/`.
- 🔬 `projects/` — standalone experiments and tools, each with its own README and toolchain:

  | Project | What it is |
  |---|---|
  | [`ai-agent`](projects/ai-agent) | LangGraph ReAct + RAG agent demo, OpenAI or local llama.cpp |
  | [`code-sign`](projects/code-sign) | PowerShell Authenticode signing toolkit for a local CA |
  | [`yaml-encryption`](projects/yaml-encryption) | CLI wrapping SOPS/age to encrypt Kubernetes secret manifests |
  | [`talos-vms`](projects/talos-vms) | Ansible playbooks provisioning VMware ESXi VMs for Talos/Omni |
  | [`api-resilience`](projects/api-resilience) | .NET solution exploring API resilience patterns |
  | [`cryptography`](projects/cryptography) | Notes and examples on public/private key cryptography |

## How to use

Clone it, poke around and get inspired:

```bash
git clone https://github.com/SupaaHiro/schwifty-lab
```

Run the Jekyll blog locally:

```bash
bundle install
start-dev.bat web
```

## Contributing to this repo

- Commits go directly to `master` — no GitFlow, no `develop`/`feature` branches.
- Commit messages are linted by [commitlint](https://commitlint.js.org/) via a Husky hook (`.commitlintrc.yml`): conventional-commit type + sentence-case subject. Run `npm install` once at the repo root so the hook is active.
- CI (`.github/workflows/`) runs the `projects/ai-agent` test suite and YAML/PowerShell linting on every push to `master` and pull request.
- See [`CLAUDE.md`](CLAUDE.md) for a fuller map of the repo and its conventions.

## Disclaimer

I am not responsible for any problems or existential crises caused by this repo.

## License

This project is licensed under a **No-Commercial License** (see LICENSE file), since it depends on third-party libraries, which allow free use for personal, experimental, or research purposes, but may impose restrictions on commercial use.
