# Backlog Atlas

Backlog Atlas generates a self-hosted backlog snapshot and static dashboard for
GitHub repository maintainers.

It keeps GitHub Issues as the source of truth, derives backlog state from open
issues and linked pull requests, and publishes the result to a dedicated
`backlog-atlas` branch. The generated branch is machine-owned and can be served
directly with GitHub Pages.

This repo's backlog dashboard: <https://omry.github.io/backlog-atlas/>

## Documentation

- [User Guide](./USER-GUIDE.md) — install Backlog Atlas on a repository, enable
  the web UI, run updates, and uninstall.
- [Maintainer Guide](./MAINTAINERS.md) — local development, testing, packaging,
  and release prep for this package.
- [Design Note](./DESIGN.md) — how snapshots, diffs, and the update log fit
  together.
- [Changelog](./CHANGELOG.md) — user-facing release notes.
- [Standalone TODO](./STANDALONE-TODO.md) — temporary publication checklist.

## What It Produces

The `backlog-atlas` branch contains:

- `backlog.json` — structured backlog data plus the recent activity tail used by
  the web UI.
- `updates.jsonl` — append-only structured activity history.
- `last_snapshot.json` — internal diff state for the next run.
- `index.html` — the static dashboard.

The default branch only needs the installed workflow and metadata:

- `.github/workflows/update-backlog-atlas.yml`
- `.github/backlog-atlas.json`

## Quick Start

```sh
pip install backlog-atlas
cd /path/to/target-repo
backlog-atlas install --dry-run
backlog-atlas install
```

The dry run previews the files and install source before anything is written.
Commit and push the installed workflow and metadata, then enable GitHub Pages
from the `backlog-atlas` branch. See the [User Guide](./USER-GUIDE.md) for the
full local and remote install flows.

## CLI

```sh
# install the workflow and metadata in a repository
backlog-atlas install [flags]

# remove the installed workflow and metadata
backlog-atlas uninstall [flags]

# write the static web UI files for preview or packaging
backlog-atlas dump-web --output PATH

# refresh backlog data; normally run by the installed GitHub Action
backlog-atlas update [flags]
```

## Development Checks

Maintainers can install local check tools with:

```sh
python -m pip install -e ".[dev]"
python -m black --check backlog_atlas tests
python -m pyflakes backlog_atlas tests
python -m pytest
```

See the [Maintainer Guide](./MAINTAINERS.md) for the full development workflow.

## License

MIT.
