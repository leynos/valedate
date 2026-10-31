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
