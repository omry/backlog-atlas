# Maintainer Guide

This guide is for local development and release prep for Backlog Atlas.

## Repository Shape

Backlog Atlas is a small Python package with three main surfaces:

- a CLI that fetches GitHub issue and pull request state, derives backlog
  records, and writes Markdown/JSON artifacts
- bundled templates and static web assets used by installed target repos
- tests and release automation for validating and publishing the package

Generated backlog output is intended to live on a target repository's
`backlog-atlas` branch, not on `main`.

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

Then install the package in editable mode:

```sh
python -m pip install -e .
```

Install development tools used by the local checks:

```sh
python -m pip install pytest build
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

## Local CLI Smoke Checks

After `python -m pip install -e .`, check the CLI entry point:

```sh
backlog-atlas --help
backlog-atlas dump-web --output /tmp/backlog-atlas-preview/
```

To preview the web UI with real or generated data:

```sh
backlog-atlas dump-web --output /tmp/backlog-atlas-preview/
backlog-atlas update --repo owner/name --data-json-path /tmp/backlog-atlas-preview/backlog.json
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
  --repo owner/name \
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
- `backlog_atlas/templates/*.tmpl`
- `backlog_atlas/web/index.html`

## Installation Workflow

The generated installation workflow is `backlog_atlas/templates/workflow.yml.tmpl`.
It creates and updates artifacts on the `backlog-atlas` branch.

Local install dry run pattern for a target repo:

```sh
backlog-atlas install --repo owner/name --target-root /path/to/repo --skip-branch --pip-spec .
```

Use `--skip-branch` when you only want to inspect the workflow file that would
be written locally. Omit it only when you intend to create the GitHub branch via
the API.

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
