# Backlog Atlas User Guide

This guide is for repository maintainers who want to install and operate
Backlog Atlas on a GitHub repository.

Backlog Atlas creates a dedicated `backlog-atlas` branch containing a static
dashboard and machine-readable backlog state. Your default branch only gets the
workflow that keeps that branch updated, editable config, and an install
manifest used for cleanup.

## Requirements

- A GitHub repository with Issues enabled.
- GitHub Actions enabled for the repository.
- Permission to write workflow files on the default branch.
- The GitHub CLI (`gh`) only for remote installs, bundled-wheel development
  installs, or local `backlog-atlas update` runs.

Normal local installs do not need `gh`; the generated GitHub Actions workflow
uses GitHub's `GITHUB_TOKEN` when it runs in the target repository.

## Install the CLI

Install Backlog Atlas in the environment where you will run the setup command:

```sh
pip install backlog-atlas
```

## Install on a Repository

Backlog Atlas has two install modes. Pick one:

- Local install writes files into a checkout you already have on disk. Use
  `backlog-atlas install` from that checkout, or pass `--target-root`.
- Remote install writes files through GitHub. Use `--repo`.

`--target-root` and `--repo` are mutually exclusive for install.

### Local Install

Use this when you already have the target repository checked out locally.

```sh
cd /path/to/target-repo
backlog-atlas install --dry-run
backlog-atlas install
```

To run the same local install from another directory, pass the checkout path:

```sh
backlog-atlas install --target-root /path/to/target-repo
```

This writes:

- `.github/workflows/update-backlog-atlas.yml` — the GitHub Actions workflow
  that updates the `backlog-atlas` branch when issues or pull requests change.
- `.github/backlog-atlas/manifest.json` — the cleanup manifest listing
  installed files, install source, Backlog Atlas version, and whether normal
  uninstall or only clean uninstall removes each file.
- `.github/backlog-atlas/config.yaml` — editable repository configuration. It is
  created only if missing; reinstall and upgrade preserve local edits.

Local install requires a clean Git or Sapling working tree. It stages/adds the
managed install files, creates a local commit containing only those files, and
prints review and push commands.

Use `--force` to install into a dirty working tree. This skips the cleanliness
check and rewrites/re-adds the managed install files, but Backlog Atlas still
commits only its own install files.

`--target-root` is for local installs only. Do not combine it with `--repo`.
The checkout's Git or Sapling remote must point at GitHub so Backlog Atlas can
detect the target repository.

### Remote Install

Use this when you want Backlog Atlas to write the install files through GitHub
instead of a local checkout.

```sh
gh auth login
backlog-atlas install --repo https://github.com/owner/name --dry-run
backlog-atlas install --repo https://github.com/owner/name
```

Remote installs use `gh`, require write access, and default to opening an
install pull request. To commit directly to the default branch:

```sh
backlog-atlas install --repo https://github.com/owner/name --delivery push
```

Install dry runs print the target repository, install source, and files that
would be written. Remote dry runs also show whether the install would use a pull
request or direct push. Remote dry runs call GitHub read-only to verify the
repository exists and the current `gh` authentication appears to have write
access. They do not write files, create branches, commit, or open pull requests.
If a remote config already exists, install validates it before writing anything.

## What the Workflow Does

After the install commit lands on the default branch, the generated workflow:

1. Creates the `backlog-atlas` branch if it does not exist.
2. Fetches open issues, linked pull requests, labels, and collaborator status.
3. Writes backlog state to the `backlog-atlas` branch.
4. Copies the bundled static web UI to that branch.
5. Commits only machine/frontend artifacts to the `backlog-atlas` branch.

The generated branch contains:

- `backlog.json` — structured backlog data plus the recent activity tail used by
  the web UI.
- `updates.jsonl` — append-only structured activity history.
- `last_snapshot.json` — internal diff state for the next run.
- `index.html` — the static dashboard.
- `.backlog-atlas/` — internal state and, for development installs, bundled
  wheels.

The branch is intentionally machine-owned. It is not meant for hand editing.

The workflow reads `.github/backlog-atlas/config.yaml` from the default branch.
Edit that file in the repository checkout to customize classification labels,
title keywords, and retention settings.

## Enable the Web UI

Use GitHub Pages to serve the dashboard:

1. Open the repository's Pages settings.
2. Set the source branch to `backlog-atlas`.
3. Set the folder to `/`.

The page loads `backlog.json` from the same branch and renders the dashboard.

## Run an Update Locally

Most repositories should let the workflow handle updates. For local debugging:

```sh
gh auth status
backlog-atlas update --repo https://github.com/owner/name
```

Useful flags:

- `--dry-run` — preview changes without writing files.
- `--data-json-path PATH` — write `backlog.json` somewhere else.
- `--updates-jsonl-path PATH` — write/read the structured update log somewhere
  else.
- `--snapshot-path PATH` — write/read diff state somewhere else.

By default, local output goes under `.backlog-atlas/` in the detected checkout.

## Classify One Issue

To test config edits from a checkout, run:

```sh
backlog-atlas classify 123
```

Checkout mode uses `.github/backlog-atlas/config.yaml` from the working tree,
including uncommitted edits.

To classify with the config already committed to a remote repository's default
branch, pass `--repo`:

```sh
backlog-atlas classify 123 --repo https://github.com/owner/name
```

Remote mode intentionally uses only the remote config. It does not inspect local
config files.

## Preview Locally

To preview the web UI on your machine:

```sh
backlog-atlas dump-web --output /tmp/backlog-atlas-preview/
backlog-atlas update \
  --repo https://github.com/owner/name \
  --data-json-path /tmp/backlog-atlas-preview/backlog.json \
  --snapshot-path /tmp/backlog-atlas-preview/last_snapshot.json \
  --updates-jsonl-path /tmp/backlog-atlas-preview/updates.jsonl
cd /tmp/backlog-atlas-preview
python3 -m http.server 8000
```

Then open `http://localhost:8000/`.

## Browser-Federated Multi-Repo Preview

For a lightweight multi-repo dashboard, place an `atlas.json` file next to
`index.html`. The browser loads each listed `backlog.json` and merges the
datasets locally:

```json
{
  "title": "Team Backlog",
  "repos": [
    {
      "repo": "owner/service-a",
      "backlog_url": "https://owner.github.io/service-a/backlog.json"
    },
    {
      "repo": "owner/service-b",
      "backlog_url": "https://owner.github.io/service-b/backlog.json"
    }
  ]
}
```

If `atlas.json` is not present, the UI falls back to the single-repo
`backlog.json` behavior. Browser federation is intended for public or otherwise
browser-readable datasets; it does not add credentials or server-side
aggregation.

## Uninstall

From a local checkout of the target repository:

```sh
backlog-atlas uninstall --repo https://github.com/owner/name --target-root /path/to/target-repo
```

This writes a one-shot workflow to
`.github/workflows/update-backlog-atlas.yml`, creates a local uninstall commit,
and prints review and push commands. When the workflow runs, it removes Backlog
Atlas install hooks and manifests from the default branch.

Uninstall follows Debian-style remove/purge semantics:

- Normal uninstall removes the installed workflow, install manifest, and
  bundled install packages from `.backlog-atlas/packages/`.
- Normal uninstall preserves the `backlog-atlas` branch, generated dashboard
  history, and Backlog Atlas config.
- Normal uninstall is idempotent: if default-branch install files were already
  removed manually, it still writes the one-shot cleanup workflow so generated
  branch packages can be removed.
- Clean uninstall also deletes the `backlog-atlas` branch and Backlog Atlas
  config. It can be run later even if normal uninstall already removed the
  workflow.

To clean uninstall:

```sh
backlog-atlas uninstall \
  --repo https://github.com/owner/name \
  --target-root /path/to/target-repo \
  --clean
```

Like install, uninstall requires a clean working tree by default. `--force`
skips that check while still committing only Backlog Atlas-owned files.

## Install Source

By default, Backlog Atlas makes the generated workflow install from the same
kind of source as the CLI you are running:

- If the CLI was installed from PyPI, the workflow uses the exact pinned PyPI
  version, such as `backlog-atlas==1.2.3`.
- If the CLI was installed from a local checkout, including editable installs,
  Backlog Atlas builds a wheel from that checkout and bundles it on the target
  repo's `backlog-atlas` branch. The bundled wheel filename includes the
  checkout commit hash and ends in `.dirty` when the checkout has uncommitted
  changes.

For pre-publish testing, `--install-from` can override this and point at a
specific local Backlog Atlas checkout:

```sh
backlog-atlas install \
  --target-root /path/to/target-repo \
  --install-from /path/to/backlog-atlas
```

Bundled-wheel installs require `gh` and write access to the target repository.

## Upgrade

To upgrade an installed repository, upgrade the `backlog-atlas` CLI in the
environment where you run setup, then rerun the same install mode you used
before.

For a normal PyPI install:

```sh
python -m pip install --upgrade backlog-atlas
```

Then preview and apply the install update.

For local install:

```sh
cd /path/to/target-repo
backlog-atlas install --dry-run
backlog-atlas install
```

For remote install:

```sh
backlog-atlas install --repo https://github.com/owner/name --dry-run
backlog-atlas install --repo https://github.com/owner/name
```

This updates the installed workflow and `.github/backlog-atlas/manifest.json` so
future workflow runs use the upgraded Backlog Atlas source and cleanup uses the
current install manifest. It creates `.github/backlog-atlas/config.yaml` if the
repo does not have one yet. If the
generated `backlog-atlas` branch already exists, the next workflow run updates
its machine-generated files in place.

Install first removes previous Backlog Atlas install hooks/manifests while
preserving config and generated dashboard history. When the previous install
manifest lists bundled wheels, it writes a temporary cleanup workflow that
removes those old wheels only after the new install lands.
