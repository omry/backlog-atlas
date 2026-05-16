# Maintainer Guide

This guide is for local development and release prep for Backlog Atlas.

## Repository Shape

Backlog Atlas is a small Python package with three main surfaces:

- a CLI that fetches GitHub issue and pull request state, derives backlog
  records, and writes JSON/web artifacts
- bundled templates and static web assets used by installed target repos
- tests and release automation for validating and publishing the package

Generated backlog output is intended to live on a target repository's
`backlog-atlas` branch, not on `main`.

For end-user installation and operation, see [`USER-GUIDE.md`](./USER-GUIDE.md).

## Local Environment

Use either a virtual environment or conda environment for local development.

With `venv`:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

With conda:

```sh
conda create -n backlog-atlas python=3.12
conda activate backlog-atlas
```

Then install the package in editable mode with the local development tools:

```sh
python -m pip install -e ".[dev]"
```

Install and authenticate the GitHub CLI before running commands that read
GitHub state locally, such as `update`:

```sh
gh auth login
gh auth status
```

## Testing

Run the focused test file after code changes:

```sh
python -m pytest tests/test_update_backlog.py
```

Run the full available test suite before considering a change ready:

```sh
python -m pytest
```

The full suite currently collects the same test file, but keep running both
commands so the habit stays correct as the repo grows.

## Linting and Formatting

The committed tool config lives in `pyproject.toml`.

Check formatting:

```sh
python -m black --check backlog_atlas tests
```

Run the current lightweight linter:

```sh
python -m pyflakes backlog_atlas tests
```

## Local CLI Smoke Checks

After the editable development install, check the CLI entry point:

```sh
backlog-atlas --help
backlog-atlas dump-web --output /tmp/backlog-atlas-preview/
```

To preview the web UI with real or generated data:

```sh
backlog-atlas dump-web --output /tmp/backlog-atlas-preview/
backlog-atlas update --repo https://github.com/owner/name --data-json-path /tmp/backlog-atlas-preview/backlog.json
cd /tmp/backlog-atlas-preview && python3 -m http.server 8000
```

`backlog-atlas update` talks to GitHub through `gh`, so it requires a working
GitHub CLI login and repo access.

## Local Website Preview

The website is a static `index.html` that fetches `backlog.json` from the same
directory. To preview it locally, write the bundled web assets into a temporary
directory:

```sh
backlog-atlas dump-web --output /tmp/backlog-atlas-preview/
```

If you already have a `backlog.json`, copy it next to the generated
`index.html`:

```sh
cp path/to/backlog.json /tmp/backlog-atlas-preview/backlog.json
```

To generate a fresh `backlog.json` from GitHub:

```sh
gh auth status
backlog-atlas update \
  --repo https://github.com/owner/name \
  --data-json-path /tmp/backlog-atlas-preview/backlog.json \
  --snapshot-path /tmp/backlog-atlas-preview/last_snapshot.json \
  --updates-jsonl-path /tmp/backlog-atlas-preview/updates.jsonl
```

Serve the directory over HTTP; opening the file directly will not reliably work
because browsers restrict local `fetch()` calls.

```sh
cd /tmp/backlog-atlas-preview
python3 -m http.server 8000
```

Then open `http://localhost:8000/`.

## Packaging

Build wheel and sdist locally:

```sh
python -m build --wheel --sdist
```

For quick local checks without isolated dependency installation:

```sh
python -m build --no-isolation --wheel --sdist
```

The build should include:

- `LICENSE`
- `backlog_atlas/config.yaml`
- `backlog_atlas/templates/*.yml`
- `backlog_atlas/web/index.html`

## Installation Workflow Development

The generated installation workflow is `backlog_atlas/templates/workflow.yml`;
the uninstall workflow is `backlog_atlas/templates/uninstall_workflow.yml`.
The user-facing install and uninstall flows are documented in
[`USER-GUIDE.md`](./USER-GUIDE.md).

For pre-publish testing, point `--install-from` at a local Backlog Atlas
checkout. If the CLI was installed from a local checkout, including editable
installs with `pip install -e .`, the installer uses that checkout
automatically when `--install-from` is omitted.

```sh
backlog-atlas install \
  --target-root /path/to/target-repo \
  --install-from /path/to/backlog-atlas
```

The source checkout may be dirty. Backlog Atlas builds a wheel from that local
tree, uploads the wheel to `.backlog-atlas/packages/` on the target repo's
`backlog-atlas` branch, and makes the generated workflow install that bundled
wheel. This development install path requires `gh` and write access to the
target repo, even when the workflow and metadata are written into a local target
checkout. The target checkout must have a GitHub remote that Backlog Atlas can
detect. `.github/backlog-atlas.json` records the package version and bundled
wheel path.

## Publishing

Publishing is handled by GitHub Releases and PyPI Trusted Publishing.

Before publishing:

1. Bump `version` in `pyproject.toml`.
2. Run `python -m pytest`.
3. Run `python -m build --wheel --sdist`.
4. Commit and push.
5. Publish a GitHub Release.

PyPI must have a Trusted Publisher configured for:

- repository: `omry/backlog-atlas`
- workflow: `publish.yml`
- environment: `pypi`

PyPI rejects reused versions, so every published release needs a new version.

## Source Control

This repo uses Sapling locally. Use `sl status`, `sl add`, and `sl commit` for
VCS operations unless there is a specific reason to inspect Git metadata.

Do not commit, push, publish, or delete remote branches unless the user
explicitly asks for that action.
