# Backlog Atlas product strategy

Status: public draft

Backlog Atlas helps maintainers understand and communicate the state of their
issue backlog without adopting a heavyweight project-management system.

The near-term open source product is a per-repository publisher plus static
dashboards that can read published snapshots. The immediate multi-repository
use case is still self-hosted: related repositories can each publish their own
backlog data, and one static dashboard can combine those snapshots. The
longer-term hosted product is a managed, multi-repository dashboard where users
connect their code host, choose repositories, and get an aggregated backlog view
with little setup.

## Problem

Software backlogs are usually distributed across issues, pull requests, labels,
and maintainer memory. This works while a project is small, but it becomes hard
to answer basic questions as repositories grow:

- What is open, blocked, in progress, or likely handled by an open PR?
- Which parts of the backlog are bugs, enhancements, docs, or build work?
- What changed recently?
- Which repositories need attention first?
- How can this be shared with contributors without giving them access to
  private maintainer tooling?

Existing issue trackers are good source-of-truth systems, but they are often
repo-local and event-oriented. Backlog Atlas is a lightweight derived view: it
turns issue and PR state into a browsable backlog snapshot.

## Product shape

Backlog Atlas has two natural layers.

### Backlog Atlas OSS

The open source package gives each repository a self-contained backlog
snapshot. It installs a repository workflow that listens to issue and pull
request events, generates backlog artifacts, and commits those artifacts to a
dedicated `backlog-atlas` branch.

The repository publisher is intentionally local: each repository owns its own
workflow, generated JSON, changelog, and state. The static dashboard can then
read one or more published snapshots directly from those repositories and
combine them in the browser.

A concrete early use case is a maintainer who wants OmegaConf and Hydra in the
same dashboard before any hosted service exists. Both repositories can publish
their own `backlog.json` files, and a static dashboard can fetch those files,
annotate issues by repository, and present a combined view.

The OSS package should remain useful by itself:

- no hosted account
- no central database
- no required service
- per-repository publishers
- optional manually configured multi-repository static dashboard
- static JSON and HTML artifacts
- transparent generated files that can be inspected, linked, or archived

This is enough for many public open source projects and small related-repo
ecosystems.

### Backlog Atlas Cloud

The hosted product removes setup friction and provides the multi-repository
experience:

1. Create an account.
2. Connect a code host or organization.
3. Add the repositories you care about.
4. Use a combined dashboard.

The cloud product can provide features that are awkward in a static-only model:

- private repository support
- centralized provider integrations
- multi-repository dashboards
- historical trends and retention
- saved filters and team views
- notifications for stale or growing backlog areas
- richer analytics across repositories
- organization-level onboarding and permission checks

The cloud product should be additive, not a replacement for the OSS mode.

## Positioning

Backlog Atlas is not a replacement for issues, pull requests, or project boards.
It is a visibility layer over them.

Its job is to make backlog state easier to scan, share, and compare. The source
of truth remains the code host. Backlog Atlas publishes and aggregates derived
snapshots.

Initial implementation can focus on GitHub, but the product name and data model
should stay provider-neutral. Future providers may include GitLab, Bitbucket, or
other issue trackers.

## Architecture principles

- Repository-owned facts: each repository can publish its own backlog snapshot.
- Static aggregation before cloud: the OSS dashboard should be able to combine
  manually configured public snapshots without a server.
- Provider-neutral schema: snapshots should describe issues, PRs, labels,
  status, categories, and timestamps without assuming one provider forever.
- Static-first OSS: the open source path should work without a server.
- Service for convenience: hosted mode should earn its place through easier
  setup, private repo support, history, teams, and notifications.
- Portable data: users should be able to fetch, inspect, and export the data
  Backlog Atlas produces.

## Monetization

The hosted product can be commercially sustainable without weakening the open
source package. Good paid surfaces are convenience, scale, private data, and
history rather than gating the core snapshot format.

Potential hosted tiers:

- Free: public repositories, limited repository count, current dashboard.
- Pro: private repositories, more repositories, saved views, longer history.
- Team: shared dashboards, notifications, analytics, organization installs.
- Enterprise: SSO, audit logs, data retention controls, support, SLA.

This keeps the open source version complete while giving teams a reason to pay
for the managed experience.

## Near-term roadmap

1. Harden the single-repository OSS publisher workflow and documentation.
2. Stabilize the generated JSON schema.
3. Document how to self-host the single-repository dashboard.
4. Add a manually configured static multi-repository dashboard for related
   public repositories such as OmegaConf and Hydra.
5. Keep the schema and terminology ready for a future multi-repository hosted
   dashboard.

## Open questions

- What provider-neutral fields must be in the first stable snapshot schema?
- What is the smallest useful configuration format for a static
  multi-repository dashboard?
- How much history should the OSS publisher retain by default?
- What is the right hosted authentication model for private repositories?
- Which hosted feature creates the clearest first paid value: private repos,
  history, alerts, or team dashboards?
