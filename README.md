# Backlog Atlas

Generates a self-hosted backlog snapshot and dashboard for maintainers.

Backlog Atlas keeps the issue tracker as the source of truth and publishes a
derived view of one repository's open issues, linked pull requests, status, and
recent backlog activity.

## What it produces

Outputs land on a dedicated `backlog-atlas` branch (kept off `main` so issue churn doesn't pollute the main history):

- `BACKLOG.md` — categorized table of open issues + recently-done.
- `BACKLOG-UPDATES.md` — append-only human changelog of new/closed/status/label events.
- `backlog.json` — same data as `BACKLOG.md` but structured, consumed by the web UI.
- `updates.jsonl` — append-only structured event log (machine-readable changelog). Bootstrapped from `BACKLOG-UPDATES.md` on first run.
- `last_snapshot.json` — internal state used to diff against the next run.
- `events.jsonl` — log of GitHub issue/PR events queued for the next debounced run.
- `index.html` — bundled with the package; copied to the `backlog-atlas` branch by the workflow so a static page can be served via GitHub Pages.

## Install

```
pip install .
# or, once published:
# pip install backlog-atlas
```

Backlog Atlas shells out to the GitHub CLI for local GitHub reads. Install and
authenticate `gh` before running `backlog-atlas update` locally:

```
gh auth login
gh auth status
```

## CLI

```
backlog-atlas update [flags]        # regenerate outputs from current GitHub state
backlog-atlas install [flags]       # write the Backlog Atlas workflow YAML
backlog-atlas uninstall [flags]     # write a one-shot uninstall workflow
backlog-atlas dump-web --output X   # write the bundled index.html (or full web/ dir)
```

### `update`

Fetches issues/PRs from GitHub via `gh` and rewrites the backlog files. Useful flags:

- `--repo owner/name` — override repo detection (defaults to `sl`/`git` remote).
- `--dry-run` — print what would change without writing.
- `--snapshot-path` / `--event-log-path` / `--commit-msg-path` — workflow-driven I/O paths.
- `--data-json-path` / `--updates-jsonl-path` — override default output locations.

Defaults write everything under `<target-repo>/.backlog-atlas/` so the file system isn't littered.

### `install`

```
backlog-atlas install [--install-from <backlog-atlas==X.Y.Z-or-local-checkout>]
backlog-atlas install --repo <owner/name-or-github-url> [--delivery pr|push]
```

Inside a local Sapling or Git checkout, `install` requires a clean target working tree, writes `.github/workflows/update-backlog-atlas.yml` plus `.github/backlog-atlas.json` install metadata, adds/stages both files, and prints commit/push commands. With `--repo` and no local target, it installs remotely through `gh`; remote installs default to `--delivery pr`, or use `--delivery push` to write to the default branch directly. The generated workflow creates the `backlog-atlas` branch on its first run, installs Backlog Atlas, and runs `backlog-atlas update` + `backlog-atlas dump-web`. By default, the workflow installs the current Backlog Atlas package version from PyPI, pinned as `backlog-atlas==X.Y.Z`. Use `--install-from /path/to/backlog-atlas-checkout` for pre-publish testing; the checkout is built into a wheel, uploaded to the target repo's `backlog-atlas` branch, and installed from there. That development install path requires `gh` and write access to the target repo.

### `uninstall`

Writes a one-shot workflow to `.github/workflows/update-backlog-atlas.yml`. After you commit and push it, GitHub Actions logs that Backlog Atlas was uninstalled, keeps the `backlog-atlas` branch by default, and removes the workflow and install metadata from `main`.

Use `--delete-branch` to make the one-shot workflow delete the `backlog-atlas` branch too:

```
backlog-atlas uninstall --repo owner/name --delete-branch
```

## Web UI

The page is served from the `backlog-atlas` branch via GitHub Pages: enable Pages → branch `backlog-atlas` / `/`. It fetches `backlog.json` and renders an interactive view with search, category/status filters, sortable columns, dark/light themes, and a fixed bottom activity panel.

For local preview:

```
backlog-atlas dump-web --output ./preview/
backlog-atlas update --data-json-path ./preview/backlog.json
cd preview && python3 -m http.server 8000
# open http://localhost:8000/
```

## Tests

```
pytest tests/test_update_backlog.py
```

## Maintainers

See [`MAINTAINERS.md`](./MAINTAINERS.md) for local development, testing,
packaging, and publishing notes.

## Publishing

Publishing uses PyPI Trusted Publishing from `.github/workflows/publish.yml`.
Configure the PyPI publisher for:

- repository: `omry/backlog-atlas`
- workflow: `publish.yml`
- environment: `pypi`

The workflow builds and publishes when a GitHub Release is published.

## License

MIT.

## Layout

```
.
├── pyproject.toml
├── README.md
├── MAINTAINERS.md
├── backlog_atlas/
│   ├── __init__.py             # CLI + all logic (single-module package for now)
│   ├── config.yaml             # default category/keyword/emoji config
│   ├── templates/
│   │   ├── backlog.md.tmpl
│   │   ├── backlog_updates_entry.md.tmpl
│   │   ├── workflow.yml.tmpl   # GitHub Actions workflow template installed by `install`
│   │   └── uninstall_workflow.yml.tmpl
│   └── web/
│       └── index.html          # bundled static UI
└── tests/
    └── test_update_backlog.py
```
