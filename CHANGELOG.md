# Changelog

Backlog Atlas uses this file as the release-note source for package changes.
Keep entries user-facing and grouped by released version.

## Unreleased

- Nothing yet.

## 0.15

- Hardened release publishing so it requires a clean checkout, checks the
  remote default branch before editing release files, and restores release
  files if pre-commit checks fail.

## 0.14

- Batched remote install updates into a single commit, so install pull requests
  no longer show one commit per generated file.
- Added `backlog-atlas atlas install` to batch install or upgrade every repo in
  an atlas config, with all-target preflight validation before writes.
- Required remote installs to pass `--delivery pr` or `--delivery push`
  explicitly instead of defaulting to pull request delivery.
- Skipped creating remote install commits or pull requests when the generated
  install files are already up to date.

## 0.13

- Added browser-based multi-repository dashboards driven by an atlas manifest,
  including `atlas.yaml` compilation and CLI helpers for managing tracked repos.
- Added issue classification preview output so maintainers can inspect how
  labels, keywords, and config rules classify an issue.
- Improved install lifecycle metadata with manifest-driven cleanup, editable
  configuration deployment, remote config validation, and safer upgrade cleanup.
- Simplified install next steps, required local checkouts to be current with the
  default branch before install, and made GitHub CLI follow-up commands work
  from Sapling checkouts.
- Made `backlog-atlas install` quiet by default; pass `--verbose` to show
  progress logs and generated next-step commands.
- Simplified the web dashboard by removing the side legend pane.
- Added local release tooling, changelog support, and CI publish checks for
  formatting, linting, typing, tests, and package builds.

## 0.11

- Published Backlog Atlas as a standalone PyPI package.
- Added local and remote install flows with dry-run output.
- Added bundled-wheel installs for local checkout development.
- Improved generated install metadata, workflow templates, and install
  next-step output.
- Split user and maintainer documentation.
