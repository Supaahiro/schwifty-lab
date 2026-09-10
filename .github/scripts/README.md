# Scripts

Local scripts invoked from workflows, following the same convention used in the
`blog` and `k8s-platform` sibling repos.

| Script | Purpose |
| --- | --- |
| `check-file-encoding.sh` | Verifies that git-tracked files are stored the way `.gitattributes` says they should be — BOM presence (`bom` / `no-bom` modes) and line endings in the committed blob (`eol` mode). |

`check-file-encoding.sh` is ported from `blog` and kept in sync with it.

Only the `eol` mode is currently wired into `pr-validate.yml`, repo-wide and
unfiltered. It matters here specifically because this repo takes a lot of
Dependabot traffic: commits authored through the GitHub API bypass
`.gitattributes`, so they can land CRLF blobs that surface later as whole-file
diffs. Note that `eol` reads the *index*, where git normalizes text files to LF
regardless of the checkout setting — so `.ps1` / `.bat` files declared
`eol=crlf` in `.gitattributes` are not flagged.

BOM checking for PowerShell is handled separately, by PSScriptAnalyzer's
`PSUseBOMForUnicodeEncodedFile` rule in the `powershell-lint` job, which also
parses each script.

## When to add one

Only extract a step into a script here once it's actually reused across
workflows/repos, or a single `run:` block grows complex enough that inline YAML
hurts readability. A short, single-use command belongs inline in its workflow
step instead.
