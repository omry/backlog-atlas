# Standalone publication checklist

> Temporary pre-publication checklist. Delete this file once the package is
> published and the release process is routine.

Remaining items for publishing and operating Backlog Atlas as a standalone
project.

## Identity & repo

- [x] Pick a real name: Backlog Atlas (`backlog-atlas`).
- [x] Extract to its own repo: `https://github.com/omry/backlog-atlas`.
- [x] Add `LICENSE` (MIT) and any attribution.

## Dependencies & decoupling

- [x] Keep the `omegaconf>=2.3` runtime dependency. It is used for config
  loading in `backlog_atlas/core.py`.
- [ ] Do a final standalone-coupling audit for leftover environment assumptions,
  docs references, generated build artifacts, and local-only setup notes.

## Tooling

- [x] Add committed lint/format config and a development extra for local checks.
  Current local practice is Black style plus `pyflakes`.
- [ ] Add type-checking config once the package is ready for typed CI.
- [ ] Add lint to CI.
- [x] CI runs tests on Python 3.10-3.13 and builds wheel/sdist.
- [x] PyPI publishing workflow using Trusted Publishing from GitHub Releases.
- [ ] Add a changelog or release-note mechanism. `pyproject.toml` is currently
  the version source of truth.

## Tests

- [ ] Verify tests from a fresh clone / clean checkout.
- [x] Document the `gh`-CLI mocking strategy used in tests.

## Docs

- [x] Split user-facing usage into `USER-GUIDE.md`.
- [ ] Add a web UI screenshot.
- [x] Optional design note on the snapshot/diff/update-log model so contributors understand the moving parts.

## Dogfooding

- [x] Run `backlog-atlas install` on this repo itself.
- [x] Verify the generated Pages dashboard from the `backlog-atlas` branch.

## Publication

- [x] Confirm PyPI project availability/ownership for `backlog-atlas`.
- [x] Confirm PyPI Trusted Publisher is configured for repository
  `omry/backlog-atlas`, workflow `publish.yml`, environment `pypi`.
- [ ] Make release a single-step process, with the GitHub Action running the
  required CI checks before publishing.

## Cleanup

- [ ] Delete this file (`STANDALONE-TODO.md`) once the tool is published.
