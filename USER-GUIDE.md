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
backlog-atlas install --repo https://github.com/owner/name --delivery pr --dry-run
backlog-atlas install --repo https://github.com/owner/name --delivery pr
```

Remote installs use `gh`, require write access, and require an explicit
delivery mode. Use `--delivery pr` to open an install pull request, or commit
directly to the default branch with:

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
- `favicon.svg` — the dashboard icon.
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

For a lightweight multi-repo dashboard, track repos in
`.github/backlog-atlas/atlas.yaml`. The installed workflow compiles this YAML to
`atlas.json` next to `index.html`; the browser loads each listed `backlog.json`
and merges the datasets locally.

Use the CLI for simple published URLs:

```sh
backlog-atlas atlas add omry/omegaconf
backlog-atlas atlas add facebookresearch/hydra
backlog-atlas atlas list
backlog-atlas atlas remove facebookresearch/hydra
```

To install or upgrade every repo listed in `atlas.yaml`, run a batch install:

```sh
backlog-atlas atlas install --delivery pr --dry-run
backlog-atlas atlas install --delivery pr
```

Use `--delivery push` to push install commits directly to each repo's default
branch. Batch push validates write access and config for every target repo
before writing anything, then asks for confirmation unless `--yes` is passed.

```sh
backlog-atlas atlas install --delivery push
```

For local checkouts, point the batch at a directory containing checkouts named
after each repository, or pass explicit checkout mappings:

```sh
backlog-atlas atlas install --local --checkout-root ~/dev --dry-run
backlog-atlas atlas install --local --checkout omry/omegaconf=~/src/omegaconf
```

Batch install supports `--only`, `--exclude`, `--install-from`,
`--continue-on-error`, and local `--force`. Without `--continue-on-error`, it
stops on the first install failure and reports which repos were not attempted.

Without `--backlog-url`, `atlas add` defaults to
`https://raw.githubusercontent.com/OWNER/REPO/backlog-atlas/backlog.json`, which
is readable by browsers from other GitHub Pages sites. `atlas add` validates
that GitHub can see the repository and that Backlog Atlas is installed there
before updating `atlas.yaml`.

Edit the YAML directly when you want OmegaConf interpolation or separate local
and published URLs:

```yaml
title: OmegaConf + Hydra Backlog
target: ${oc.env:BACKLOG_ATLAS_TARGET,published}
raw_base: https://raw.githubusercontent.com

urls:
  published:
    omegaconf: ${raw_base}/omry/omegaconf/backlog-atlas/backlog.json
    hydra: ${raw_base}/facebookresearch/hydra/backlog-atlas/backlog.json
  local:
    omegaconf: ./omegaconf/backlog.json
    hydra: ./hydra/backlog.json

repos:
  - repo: omry/omegaconf
    backlog_url: ${urls.${target}.omegaconf}
  - repo: facebookresearch/hydra
    backlog_url: ${urls.${target}.hydra}
```

```sh
backlog-atlas dump-web --output /tmp/backlog-atlas-preview/
BACKLOG_ATLAS_TARGET=local backlog-atlas dump-atlas \
  --config .github/backlog-atlas/atlas.yaml \
  --output /tmp/backlog-atlas-preview/
```

The YAML is read with OmegaConf, so interpolations such as
`${urls.${target}.omegaconf}` are resolved before writing the materialized
browser JSON. `BACKLOG_ATLAS_TARGET=local` lets you test local files before
publishing; leaving it unset emits the published URLs. Conventional GitHub Pages
URLs such as `https://OWNER.github.io/REPO/backlog.json` are rewritten to the
matching `raw.githubusercontent.com` URL while compiling `atlas.json`, because
GitHub Pages does not reliably allow cross-origin browser reads of JSON data.

After `atlas.yaml` is committed, the installed workflow publishes `atlas.json`
on the next run. If `atlas.yaml` is removed, the workflow removes stale
`atlas.json` and the UI returns to single-repo mode.

To generate local datasets for the preview, run `backlog-atlas update` from each
repository checkout and point its output at the matching preview subdirectory:

```sh
mkdir -p /tmp/backlog-atlas-preview/omegaconf
cd /path/to/omegaconf
backlog-atlas update \
  --repo https://github.com/omry/omegaconf \
  --data-json-path /tmp/backlog-atlas-preview/omegaconf/backlog.json \
  --snapshot-path /tmp/backlog-atlas-preview/omegaconf/last_snapshot.json \
  --updates-jsonl-path /tmp/backlog-atlas-preview/omegaconf/updates.jsonl
```

Repeat that for each repo listed in `atlas.yaml`, then serve the preview:

```sh
cd /tmp/backlog-atlas-preview
python3 -m http.server 8000
```

If generated `atlas.json` is not present, the UI falls back to the single-repo
`backlog.json` behavior. If `atlas.json` exists but is invalid, or one of its
listed datasets cannot be loaded, the page shows a load error instead of
silently switching modes. Browser federation is intended for public or otherwise
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
backlog-atlas install --repo https://github.com/owner/name --delivery pr --dry-run
backlog-atlas install --repo https://github.com/owner/name --delivery pr
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
