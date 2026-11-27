# Developers' guide

This guide records the repository's build and CI arrangements for contributors.

## CodeScene coverage publication

Main owns CodeScene (CV-005). Nothing a pull request can start talks to
CodeScene or holds its credential.

- **Pull requests** (`.github/workflows/ci.yml`) run the tests, then measure
  coverage and ratchet it with the shared `generate-coverage` action over
  `./valedate`. The report is not uploaded anywhere.
- **Main** (`.github/workflows/coverage-main.yml`) is the one publisher. It
  runs on each push to `main` (and on manual dispatch), in the `codescene`
  environment whose deployment policy admits `main` alone. It generates the
  same coverage, writes the ratchet baseline that pull requests compare
  against, and uploads through the shared `upload-codescene-coverage` action.
  With no `CS_ACCESS_TOKEN` in the environment, the shared action records a
  skipped upload and the run still succeeds, so the publisher works before a
  CodeScene project exists.
- **Known exception.** Merges made with `GITHUB_TOKEN`, such as Dependabot
  automerge, fire no push event, so they reach the publisher only through a
  later push or a manual dispatch. A manual dispatch uploads coverage but does
  not save the ratchet baseline, which the shared action writes only on a push
  to `main`; pull requests keep comparing against the older baseline until a
  later push advances it.

The `generate-coverage` selection in both workflows must match field for field
(`python-source`, format and interpreter), and `.github/cv005.toml` repeats the
`python-source`.

### The CV-005 contract check

`make test-workflow-contracts` runs the shared `cv005-contracts` checker
against this repository's workflows. `make all` includes it, and CI runs it.
The checker is fetched from the `leynos/shared-actions` commit named by
`CV005_CONTRACTS_REF` in the `Makefile`, so the first run needs network access.
Always pin a full 40-character commit: a fix to the contract arrives as a pin
bump, never as a local copy of the rules. The command exits 0 when every clause
holds, 1 with one `clause: message` line per violation, and 2 when the tree or
the configuration cannot be read.

## Docstring coverage

`make lint` first runs `make interrogate`, which needs `uv` and fails on any
Python definition it scans under `valedate`, `tests` and `scripts` without a
docstring. It also fails on any `MISSED` row, because interrogate rounds its
percentage to one decimal and so can pass a lone gap in a sufficiently large
codebase. Interrogate 1.7.0 skips a path whose first component below a target
begins with `.tox`, `.venv`, `venv`, `.git` or `.hg`, so
`tests/test_interrogate_gate.py` fails if a tracked Python file sits at such a
name, or in a directory of that name, directly under a target.
`scripts/uv_gate.py` is the vendored shared-actions helper; it is not edited
here, and it ships with complete docstrings. Add a new Python directory to
`INTERROGATE_TARGETS`; the same test asserts the wiring.

## YAML lint

`make lint` runs `make yamllint` and `make actionlint` as prerequisites.
`make yamllint` runs `yamllint --strict` over every tracked `.yml` and `.yaml`
file, reading `.yamllint.yml`, which extends the estate base
`.yamllint-estate.yml` (a verbatim copy of the concordat canon; do not edit
it). The base ignores Helm chart templates (`**/charts/**/templates/`), so a
tracked file there is passed to yamllint but not checked, and a local `ignore`
in `.yamllint.yml` replaces that entry rather than adding to it. Run it from
the repository root, because yamllint resolves `extends` against the current
directory. `make actionlint` checks the GitHub Actions workflows, accepting the
runner labels in `.github/actionlint.yaml`, and runs ShellCheck over their
`run:` scripts when it is on `PATH`.

Install the tools locally at the versions CI uses:
`uv tool install yamllint==1.38.0`, and the `actionlint` 1.7.12 and
`shellcheck` 0.11.0 release binaries (a package manager's builds can differ and
change what the lint reports). CI installs the same pinned versions with the
`install-yaml-lint` action of `leynos/shared-actions` before it runs
`make lint`. The `YAMLLINT` and `ACTIONLINT` variables name the commands when
they are not on `PATH`.
