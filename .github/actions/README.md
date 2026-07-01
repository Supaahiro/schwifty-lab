# Composite actions

This directory is meant to hold local composite actions shared across this
repo's workflows, following the same convention used in the `blog` and
`k8s-platform` sibling repos.

Only extract a step sequence into a composite action here once it's actually
reused, or a single workflow step grows past ~3 sub-steps. A one-off,
single-step task (e.g. `poetry install && pytest`) belongs inline in its
workflow instead — an action adds indirection without paying for itself.
