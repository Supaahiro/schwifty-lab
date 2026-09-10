#!/usr/bin/env bash
# .github/scripts/check-file-encoding.sh
#
# Purpose:  Verify that git-tracked files are stored the way .gitattributes says
#           they should be - byte-order-mark presence, and line endings in the
#           committed blob - catching encoding drift that dotnet format/eslint/
#           prettier don't check.
# Usage:    check-file-encoding.sh <bom|no-bom> <pathspec> [pathspec...]
#           check-file-encoding.sh eol [pathspec...]
# Args:
#   $1    MODE       "bom" to require UTF-8 with BOM, "no-bom" to require
#                     UTF-8 without BOM, "eol" to require normalized (LF)
#                     line endings in the index.
#   $2..  PATHSPECS   One or more git pathspecs (e.g. '*.cs' '*.csproj'),
#                      matched repo-wide via `git ls-files`. Required for the
#                      BOM modes; optional for eol, which defaults to the whole
#                      repository.
# Output: Violating file paths to stdout; exits 1 if any are found.
# Example:
#   check-file-encoding.sh bom '*.cs' '*.csproj' '*.props' '*.targets' '*.proj' '*.sln' '*.slnx'
#   check-file-encoding.sh no-bom '*.ts' '*.html' '*.scss'
#   check-file-encoding.sh eol
# Requirements:
#   - Run from inside a git worktree (uses `git ls-files`).
# Version: 1.1.0 (2026-08-22)
#
# Changelog:
#   1.1.0 - New "eol" mode: fail when a tracked text file's blob is CRLF or mixed.
#           git normalizes text files to LF in the repository regardless of the
#           eol= checkout setting, so anything else means the blob was written
#           without .gitattributes applied - which is what happens on every
#           Dependabot commit, since those go through the GitHub API rather than
#           a working tree. Left unchecked it produces whole-file diffs on the
#           next edit (backend/Directory.Packages.props has been renormalized
#           three times for exactly this reason).
#   1.0.0 - Baseline: BOM / no-BOM check over git-tracked files for a set of pathspecs.

set -euo pipefail

MODE="${1:?MODE is required (bom, no-bom or eol)}"
shift
PATTERNS=("$@")

case "$MODE" in
  bom | no-bom)
    if [[ ${#PATTERNS[@]} -eq 0 ]]; then
      echo "ERROR: at least one pathspec is required" >&2
      exit 1
    fi
    ;;
  eol)
    # Whole repository by default: denormalized blobs are not confined to the
    # extensions the BOM check cares about.
    [[ ${#PATTERNS[@]} -eq 0 ]] && PATTERNS=(".")
    ;;
  *)
    echo "ERROR: MODE must be 'bom', 'no-bom' or 'eol', got '${MODE}'" >&2
    exit 1
    ;;
esac

if [[ "$MODE" == "eol" ]]; then
  echo "Checking index line endings (expected: lf) for: ${PATTERNS[*]}"

  # `git ls-files --eol` prints: i/<index-eol> w/<worktree-eol> attr/<attrs><TAB><path>
  # The index value is the one that matters. Git normalizes every text file to LF in
  # the repository - `eol=crlf` only affects checkout - so a blob reporting i/crlf or
  # i/mixed was written without .gitattributes applied. Binary files report i/none or
  # i/-text and are never flagged.
  mapfile -t denormalized < <(
    git ls-files --eol -- "${PATTERNS[@]}" |
      awk '$1 == "i/crlf" || $1 == "i/mixed" { sub(/^[^	]*	/, ""); print }'
  )

  if [[ ${#denormalized[@]} -gt 0 ]]; then
    echo ""
    echo "ERROR: ${#denormalized[@]} file(s) are committed with non-normalized line endings:"
    printf '  %s
' "${denormalized[@]}"
    echo ""
    echo "Fix from a working tree, which is what applies .gitattributes:"
    echo "    git add --renormalize ."
    echo "    git commit -m 'style: Renormalize line endings'"
    echo ""
    echo "Commits authored through the GitHub API - Dependabot's, for instance - bypass"
    echo ".gitattributes, so they can land denormalized blobs and need this treatment."
    exit 1
  fi

  echo "OK: every tracked text file is stored with normalized (LF) line endings."
  exit 0
fi

echo "Checking encoding (expected: UTF-8 ${MODE}) for: ${PATTERNS[*]}"

violations=()

while IFS= read -r -d '' file; do
  bom_hex=$(head -c 3 -- "$file" | od -An -tx1 | tr -d ' \n')

  has_bom=false
  if [[ "$bom_hex" == "efbbbf" ]]; then
    has_bom=true
  fi

  if [[ "$MODE" == "bom" && "$has_bom" == false ]]; then
    violations+=("$file")
  elif [[ "$MODE" == "no-bom" && "$has_bom" == true ]]; then
    violations+=("$file")
  fi
done < <(git ls-files -z -- "${PATTERNS[@]}")

if [[ ${#violations[@]} -gt 0 ]]; then
  echo ""
  echo "ERROR: ${#violations[@]} file(s) do not have the expected UTF-8 ${MODE} encoding:"
  printf '  %s\n' "${violations[@]}"
  exit 1
fi

echo "OK: all matched files have the expected UTF-8 ${MODE} encoding."
