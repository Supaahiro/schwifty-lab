# Composite actions

Local composite actions shared across this repo's workflows, following the same
convention used in the `blog` and `k8s-platform` sibling repos.

| Action | Purpose |
| --- | --- |
| `toolchain/` | Resolves node / python / dotnet versions from `.github/versions.json`, applying per-branch overrides, and exposes each as an output. |
| `setup-node-cached/` | `toolchain` + `actions/setup-node` (npm cache keyed on the directory's lockfile) + `npm ci`. |
| `setup-python-poetry-cached/` | `toolchain` + `actions/setup-python` + Poetry + `poetry install`, with the in-project virtualenv cached on `poetry.lock`. |

`toolchain/` is the one piece under a cross-repo sync contract: it is kept
**byte-identical** with the copies in `blog` and `k8s-platform`, so the three can
be diffed against each other. Two consequences of that, both deliberate:

- Its `zensical` output resolves to nothing here — this repo's site is Jekyll.
  Per the action's own "outputs are a fixed superset" rule, an unused output is
  ignored rather than removed.
- Its header still reads *"keep in sync across blog and k8s-platform"*. Add
  `schwifty-lab` to that line in all three copies at once, the next time one of
  them is edited for another reason; changing it here alone would break the very
  property the contract exists for.

`.github/versions.json` is repo-local and **not** part of that contract — it
carries this repo's own node/python/dotnet versions and an empty
`branchOverrides` (there is no `develop` branch here).

`setup-python-poetry-cached/` has no counterpart in `blog`, where Python only
serves yamllint and the docs build. It was written here because two projects
(`ai-agent`, `pdns-admin-lite/backend`) need the identical five steps.

## When to add one

Only extract a step sequence into a composite action here once it's actually
reused, or a single workflow step grows past ~3 sub-steps. A one-off,
single-step task belongs inline in its workflow instead — an action adds
indirection without paying for itself.
