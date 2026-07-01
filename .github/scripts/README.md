# Scripts

This directory is meant to hold local scripts invoked from workflows,
following the same convention used in the `blog` and `k8s-platform` sibling
repos.

Only extract a step into a script here once it's actually reused across
workflows/repos, or a single `run:` block grows complex enough that inline
YAML hurts readability. A short, single-use command belongs inline in its
workflow step instead.
