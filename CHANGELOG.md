# Changelog

Backlog Atlas uses this file as the release-note source for package changes.
Keep entries user-facing and grouped by released version.

## Unreleased

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
