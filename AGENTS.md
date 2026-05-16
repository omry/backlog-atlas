# AGENTS.md

Repo-specific directives for coding agents working in Backlog Atlas.

## Behavioral defaults

These guidelines are intended to reduce common LLM coding mistakes. Apply them
alongside the repo-specific rules below. They bias toward caution over speed,
and for truly trivial tasks you may use judgment.

### Think before coding

- Do not assume.
- Do not hide confusion.
- Surface tradeoffs.
- State assumptions explicitly when they matter to the implementation.
- If multiple reasonable interpretations exist, present them instead of silently
  picking one.
- If a simpler approach exists, say so.
- Push back when warranted.
- If something material is unclear or risky, stop, name what is confusing, and
  ask instead of guessing.

### Simplicity first

- Solve the requested problem with the minimum code necessary.
- No features beyond what was asked.
- No abstractions for single-use code.
- No flexibility or configurability that was not requested.
- No error handling for scenarios that are effectively impossible in context.
- If a solution feels overbuilt for the task, simplify it before considering it
  done.
- If you write 200 lines and the same result could be achieved in 50, rewrite
  it.
- Ask: would a senior engineer say this is overcomplicated? If yes, simplify.

### Surgical changes

- Touch only what is needed for the request.
- Do not "clean up" adjacent code, comments, formatting, or structure unless
  the change requires it.
- Match the existing style and patterns of the codebase unless the user asks for
  a broader refactor.
- If you notice unrelated dead code or issues nearby, mention them instead of
  fixing them opportunistically.
- Remove imports, variables, functions, or other artifacts that your change
  makes unused.
- Do not delete unrelated pre-existing dead code unless asked.
- Every changed line should trace directly to the user's request.

### Prefer focused tools over ad hoc shell

Use repository-aware file inspection and edit tools for file operations. Reserve
shell commands for things that genuinely require shell execution: `sl`
(Sapling) commands, `gh`, dependency installation, or `pytest` / `python` for
tests and package tooling.

- Use `rg` for text search and `rg --files` for file discovery.
- Avoid inline Python snippets (`python -c ...`) when a dedicated tool or
  standard CLI utility is sufficient.
- Use structured tools such as `jq` to parse JSON shell output instead of
  piping to Python.

### Goal-driven execution

- Translate requests into concrete success criteria that can be verified.
- For bug fixes, prefer reproducing the issue with a test or other reliable
  check before fixing it.
- For refactors, prefer checks that demonstrate behavior is preserved before and
  after.
- For multi-step tasks, keep a brief plan in mind and verify each step before
  calling the work complete.
- Favor specific goals over vague ones:
  - "Add validation" -> write tests for invalid inputs, then make them pass.
  - "Fix the bug" -> reproduce it with a test or reliable check, then make it
    pass.
  - "Refactor X" -> verify behavior before and after the refactor.

## Documentation map

- Main README: [`README.md`](./README.md)
- User guide: [`USER-GUIDE.md`](./USER-GUIDE.md)
- Product strategy: [`PRODUCT-STRATEGY.md`](./PRODUCT-STRATEGY.md)
- Standalone publication checklist: [`STANDALONE-TODO.md`](./STANDALONE-TODO.md)
- CLI and core logic: [`backlog_atlas/__init__.py`](./backlog_atlas/__init__.py)
- Default configuration: [`backlog_atlas/config.yaml`](./backlog_atlas/config.yaml)
- Workflow template: [`backlog_atlas/templates/workflow.yml`](./backlog_atlas/templates/workflow.yml)
- Static web UI: [`backlog_atlas/web/index.html`](./backlog_atlas/web/index.html)
- Tests: [`tests/test_update_backlog.py`](./tests/test_update_backlog.py)

## Reproduction files

When asked to create a reproduction for an issue, place files under `temp/`:

- Single-file repro: `temp/<issue_number>.py`
- Multi-file repro: `temp/<issue_number>/`

## Stop and ask

- If a tracked repo file appears unexpectedly renamed, moved, regenerated,
  deleted, or otherwise changed, stop and ask before reverting, recreating,
  reclassifying, or staging over that change.
- Do not change release automation, workflow triggers, publishing behavior,
  package identity, or generated file formats unless the request explicitly
  includes that scope.
- Do not treat the future hosted service as existing product behavior. Keep
  hosted/cloud wording clearly framed as strategy or future direction unless the
  user asks to implement cloud code.

## Verification

- For any new or changed functionality, test it in two layers when practical:
  - run focused tests with `pytest tests/test_update_backlog.py`
  - run the broader available checks, currently the full `pytest` suite
- If the broader suite disagrees with the focused tests, trust the broader
  result and do not call the change verified.
- If live verification is blocked by the current environment, request escalation
  if that would unblock it. If not, stop and ask for guidance.
- For docs-only changes, tests are optional; say explicitly when no tests were
  run.

## Linting and formatting

The committed local check configuration lives in `pyproject.toml`. Install the
development tools with `python -m pip install -e ".[dev]"`, then:

- Keep Python formatted with `black` style.
- Keep imports compatible with `isort`'s default style.
- Run `python -m black --check backlog_atlas tests` for formatting.
- Run `python -m pyflakes backlog_atlas tests` for lightweight linting.
- Run `python -m mypy` for type checking.
- Run `pytest tests/test_update_backlog.py` after code changes.
- If adding lint or type-check tooling, document the commands in `README.md` and
  update this file.

## Environment and hooks

- Run commands from an activated environment with the package installed in
  editable development mode, as documented in `MAINTAINERS.md`.
- When validating contributor setup, shell initialization, or hook behavior,
  verify it from the same environment a developer would actually use, such as a
  normal shell session or `sl commit`, not only from a temporary sandbox-only
  environment.
- Prefer hooks that do not depend on nontrivial user-environment tooling.
- If an environment override is required for one command, explain why it must be
  part of that same process invocation.
- If a small system tool would materially simplify the workflow, it is fine to
  suggest it or ask the user to install it.

## Sapling and escalation

This repo uses Sapling (`sl`) for source control, not `git` directly. Use `sl`
for all VCS operations (status, log, commit, amend, etc.).

- Keep escalated `sl` commands minimal and single-purpose.
- Do not bundle staging, environment bootstrapping, dependency installation, and
  commit creation into one escalated shell command unless there is no practical
  alternative.
- If an `sl` operation requires escalation, ask only for the specific action
  that needs it.

## Release and publishing

- Do not commit, push, merge, publish, or otherwise send changes outside the
  local working tree unless the user explicitly asks for that outward action.
- If a change alters release automation, workflow triggers, installation
  behavior, package metadata, generated artifact names, or other externally
  visible project mechanics, require an explicit user review checkpoint before
  any commit, push, merge, publish, or deployment action.
- The user handles releases. Do not edit version numbers, create release files,
  assemble release notes, publish to PyPI, or otherwise perform release-cut
  steps unless explicitly asked.
- Do not improvise a manual release flow or treat GitHub Release text as the
  source of truth unless release docs are added and say so.

## Reviews

- When asked to review a commit, pull request, or diff, cover correctness,
  completeness, documentation, and internal consistency.
- For product-user-visible changes, verify that docs and examples match the
  implementation.
