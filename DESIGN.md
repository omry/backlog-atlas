# Backlog Data Model

Backlog Atlas keeps GitHub Issues as the source of truth. Each update run reads
the current GitHub state, compares it with the previous machine snapshot, and
writes static artifacts for the dashboard.

## Artifacts

The generated `backlog-atlas` branch uses three data files:

- `last_snapshot.json` stores the previous normalized issue state. It is an
  internal diff input for the next update run.
- `updates.jsonl` is the append-only activity log. Each line is one structured
  event from an update run.
- `backlog.json` is the dashboard payload. It contains the current backlog rows
  and a bounded recent activity tail copied from `updates.jsonl`.

The static web UI fetches `backlog.json`. It does not parse `updates.jsonl`
directly, which keeps the dashboard simple and lets the updater control how much
activity history is sent to the browser.

## Update Flow

An update run:

1. Fetches open issues, linked pull requests, labels, and collaborators from
   GitHub.
2. Normalizes that data into current issue records.
3. Loads `last_snapshot.json` when it exists.
4. Diffs the previous and current snapshots to produce new issue, closed issue,
   status change, label change, and pull request link events.
5. Appends those events to `updates.jsonl`.
6. Writes the new `last_snapshot.json`.
7. Writes `backlog.json` for the web UI.

Closed issues are retained in the rendered backlog for a short configurable
window. The snapshot tracks their close dates so they can age out without
reappearing as new changes on later runs.

## Branch Ownership

The `backlog-atlas` branch is machine-owned. Humans should change issues and
pull requests on GitHub, not edit generated files on that branch. Re-running the
workflow should be enough to rebuild the dashboard state from GitHub plus the
previous machine snapshot.
