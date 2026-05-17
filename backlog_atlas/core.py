#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from omegaconf import DictConfig, OmegaConf
from omegaconf.errors import OmegaConfBaseException

from . import config as app_config
from .errors import UserError
from .install.cli import (
    add_install_args,
    add_uninstall_args,
    run_install,
    run_uninstall,
)
from .install.commands import read_text, run_gh
from .install.constants import ATLAS_CONFIG_RELATIVE_PATH
from .install.repo import detect_target_root, normalize_github_repo, resolve_repo

PROJECT_DIR = Path(__file__).resolve().parent
WEB_DIR = PROJECT_DIR / "web"
CONFIG_PATH = app_config.PACKAGE_CONFIG_PATH
BacklogConfig = app_config.BacklogConfig
CategoryConfig = app_config.CategoryConfig
_DEFAULT_CATEGORIES = app_config._DEFAULT_CATEGORIES
category_matchers = app_config.category_matchers
load_config = app_config.load_config
load_config_with_source = app_config.load_config_with_source
validate_config_content = app_config.validate_config_content

STATUS_ORDER = ["in progress", "community PR", "blocked", "not started", "done"]


@dataclass
class CategoryClassification:
    category: str
    reason: str


def split_repo(repo: str) -> tuple[str, str]:
    owner, name = repo.split("/", 1)
    return owner, name


def issue_url(cfg: DictConfig, number: str | int) -> str:
    return str(cfg.issue_url_template).format(number=number)


def pr_url(cfg: DictConfig, number: str | int) -> str:
    return str(cfg.pr_url_template).format(number=number)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def ensure_text_file(path: Path) -> None:
    if path.exists():
        return
    write_text(path, "")


def load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(read_text(path))


def save_snapshot(snapshot: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def parse_labels(issue: dict[str, Any]) -> list[str]:
    labels = []
    for label in issue.get("labels", []) or []:
        name = label.get("name") if isinstance(label, dict) else str(label)
        if name:
            labels.append(name)
    return labels


def _keyword_matches(title: str, keyword: str) -> bool:
    if keyword == "bug":
        return bool(re.search(r"(?<![A-Za-z0-9_])bug(?![A-Za-z0-9_])", title))
    return keyword in title


def classify_issue_category(
    issue: dict[str, Any],
    label_to_category: dict[str, str],
    category_keywords: dict[str, list[str]],
) -> CategoryClassification:
    labels = parse_labels(issue)
    for raw_label in labels:
        label = raw_label.lower().strip()
        if label in label_to_category:
            category = label_to_category[label]
            return CategoryClassification(
                category=category,
                reason=f'label "{raw_label}" matched categories.{category}.labels',
            )

    # Fallback classification uses the title only — issue bodies contain generic
    # triage wording that makes body-based matching too noisy.
    title = (issue.get("title") or "").lower()
    for category, keywords in category_keywords.items():
        for keyword in keywords:
            if _keyword_matches(title, keyword):
                return CategoryClassification(
                    category=category,
                    reason=(
                        f'title keyword "{keyword}" matched '
                        f"categories.{category}.keywords"
                    ),
                )
    return CategoryClassification(
        category="Enhancement",
        reason="no labels or title keywords matched; defaulted to Enhancement",
    )


def categorize_issue(
    issue: dict[str, Any],
    label_to_category: dict[str, str],
    category_keywords: dict[str, list[str]],
) -> str:
    return classify_issue_category(issue, label_to_category, category_keywords).category


def extract_issue_numbers(text: str, repo: str | None = None) -> list[str]:
    numbers = []
    seen: set[str] = set()

    def add(number: str) -> None:
        if number not in seen:
            seen.add(number)
            numbers.append(number)

    for match in re.finditer(r"(?<![A-Za-z0-9_])#(\d+)", text or ""):
        add(match.group(1))

    if repo:
        url_pattern = rf"https?://github\.com/{re.escape(repo)}/issues/(\d+)"
        for match in re.finditer(url_pattern, text or "", flags=re.IGNORECASE):
            add(match.group(1))

    return numbers


def fetch_collaborators(repo: str) -> set[str]:
    output = run_gh(
        ["api", f"repos/{repo}/collaborators", "--paginate", "--jq", ".[].login"]
    )
    return {line.strip() for line in output.splitlines() if line.strip()}


def fetch_open_issues(repo: str) -> list[dict[str, Any]]:
    owner, name = split_repo(repo)
    issues: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        after_clause = f", after: {json.dumps(cursor)}" if cursor else ""
        query = f"""
query {{
  repository(owner: \"{owner}\", name: \"{name}\") {{
    issues(first: 100, states: OPEN{after_clause}) {{
      nodes {{
        number
        title
        body
        state
        createdAt
        updatedAt
        labels(first: 100) {{ nodes {{ name }} }}
      }}
      pageInfo {{
        hasNextPage
        endCursor
      }}
    }}
  }}
}}
"""
        output = run_gh(["api", "graphql", "-f", f"query={query}"])
        data = json.loads(output)
        issue_connection = data["data"]["repository"]["issues"]
        for node in issue_connection["nodes"]:
            labels = (node.get("labels") or {}).get("nodes") or []
            issues.append(
                {
                    "number": node["number"],
                    "title": node.get("title") or "",
                    "body": node.get("body") or "",
                    "labels": labels,
                    "state": node.get("state") or "OPEN",
                    "createdAt": node.get("createdAt") or "",
                    "updatedAt": node.get("updatedAt") or "",
                }
            )

        if not issue_connection["pageInfo"]["hasNextPage"]:
            break
        cursor = issue_connection["pageInfo"]["endCursor"]

    return issues


def fetch_issue(repo: str, number: int) -> dict[str, Any]:
    owner, name = split_repo(repo)
    query = f"""
query {{
  repository(owner: \"{owner}\", name: \"{name}\") {{
    issue(number: {number}) {{
      number
      title
      body
      state
      createdAt
      updatedAt
      labels(first: 100) {{ nodes {{ name }} }}
    }}
  }}
}}
"""
    output = run_gh(["api", "graphql", "-f", f"query={query}"])
    data = json.loads(output)
    issue = data.get("data", {}).get("repository", {}).get("issue")
    if not issue:
        raise UserError(f"could not find issue #{number} in {repo}")
    labels = (issue.get("labels") or {}).get("nodes") or []
    return {
        "number": issue["number"],
        "title": issue.get("title") or "",
        "body": issue.get("body") or "",
        "labels": labels,
        "state": issue.get("state") or "",
        "createdAt": issue.get("createdAt") or "",
        "updatedAt": issue.get("updatedAt") or "",
    }


def fetch_open_prs(repo: str) -> list[dict[str, Any]]:
    owner, name = split_repo(repo)
    prs: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        after_clause = f", after: {json.dumps(cursor)}" if cursor else ""
        query = f"""
query {{
  repository(owner: \"{owner}\", name: \"{name}\") {{
    pullRequests(first: 100, states: OPEN{after_clause}) {{
      nodes {{
        number
        title
        body
        author {{ login }}
        closingIssuesReferences(first: 50) {{ nodes {{ number }} }}
      }}
      pageInfo {{
        hasNextPage
        endCursor
      }}
    }}
  }}
}}
"""
        output = run_gh(["api", "graphql", "-f", f"query={query}"])
        data = json.loads(output)
        pull_requests = data["data"]["repository"]["pullRequests"]
        for node in pull_requests["nodes"]:
            closing_refs = node.get("closingIssuesReferences", {})
            linked_numbers: list[str] = []

            def walk(value: Any) -> None:
                if isinstance(value, dict):
                    number = value.get("number")
                    if number is not None:
                        linked_numbers.append(str(number))
                    for item in value.values():
                        walk(item)
                elif isinstance(value, list):
                    for item in value:
                        walk(item)

            walk(closing_refs)
            linked_numbers.extend(
                extract_issue_numbers(node.get("body") or "", repo=repo)
            )
            linked_numbers = sorted(set(linked_numbers), key=lambda item: int(item))
            prs.append(
                {
                    "number": str(node["number"]),
                    "title": node.get("title") or "",
                    "body": node.get("body") or "",
                    "author_login": (
                        (node.get("author") or {}).get("login") or ""
                    ).strip(),
                    "linked_issue_numbers": linked_numbers,
                }
            )

        if not pull_requests["pageInfo"]["hasNextPage"]:
            break
        cursor = pull_requests["pageInfo"]["endCursor"]

    return prs


def build_pr_lookup(
    open_prs: list[dict[str, Any]], open_issue_numbers: set[str]
) -> dict[str, list[dict[str, Any]]]:
    lookup: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pr in open_prs:
        linked_numbers = [
            n for n in pr["linked_issue_numbers"] if n in open_issue_numbers
        ]
        pr_record = {
            "number": pr["number"],
            "title": pr.get("title") or "",
            "body": pr.get("body") or "",
            "author_login": pr.get("author_login") or "",
            "linked_issue_numbers": linked_numbers,
        }
        for issue_number in linked_numbers:
            lookup[issue_number].append(pr_record)
    return lookup


def normalize_previous_row(
    row: dict[str, Any],
    label_to_category: dict[str, str],
    category_keywords: dict[str, list[str]],
) -> dict[str, Any]:
    pr_numbers = sorted(row.get("pr_numbers", []), key=lambda value: int(value))
    title = row.get("title") or ""
    labels = row.get("labels", []) or []
    return {
        **row,
        "title": title,
        "category": categorize_issue(
            {"title": title, "labels": [{"name": label} for label in labels]},
            label_to_category,
            category_keywords,
        ),
        "labels": labels,
        "pr_numbers": pr_numbers,
    }


def _display_date(value: str | None) -> str:
    return (value or "")[:10].replace("-", "‑")


def _snapshot_issue_to_previous_row(
    number: str,
    issue: dict[str, Any],
    status: str,
    label_to_category: dict[str, str],
    category_keywords: dict[str, list[str]],
) -> dict[str, Any]:
    labels = list(issue.get("labels", []) or [])
    return normalize_previous_row(
        {
            "number": number,
            "title": issue.get("title") or "",
            "status": status,
            "pr_numbers": [str(value) for value in issue.get("pr_numbers", [])],
            "created": _display_date(issue.get("created_at")),
            "updated": _display_date(issue.get("updated_at")),
            "created_at": issue.get("created_at") or "",
            "updated_at": issue.get("updated_at") or "",
            "labels": labels,
        },
        label_to_category,
        category_keywords,
    )


def previous_rows_from_snapshot(
    snapshot: dict[str, Any] | None,
    label_to_category: dict[str, str],
    category_keywords: dict[str, list[str]],
) -> list[dict[str, Any]]:
    if not snapshot:
        return []

    rows: list[dict[str, Any]] = []
    open_issues = snapshot.get("issues", {}) or {}
    for number, issue in sorted(open_issues.items(), key=lambda item: int(item[0])):
        rows.append(
            _snapshot_issue_to_previous_row(
                number,
                issue,
                issue.get("status") or "not started",
                label_to_category,
                category_keywords,
            )
        )

    recent_done = snapshot.get("recent_done", {}) or {}
    for number, issue in sorted(recent_done.items(), key=lambda item: int(item[0])):
        if number in open_issues:
            continue
        rows.append(
            _snapshot_issue_to_previous_row(
                number,
                issue,
                "done",
                label_to_category,
                category_keywords,
            )
        )

    return rows


def build_current_issue_records(
    cfg: DictConfig,
    open_issues: list[dict[str, Any]],
    collaborators: set[str],
    pr_lookup: dict[str, list[dict[str, Any]]],
    label_to_category: dict[str, str],
    category_keywords: dict[str, list[str]],
) -> list[dict[str, Any]]:
    blocked_labels_set = {lbl.lower().strip() for lbl in cfg.blocked_labels}
    records: list[dict[str, Any]] = []
    for issue in open_issues:
        number = str(issue["number"])
        labels = parse_labels(issue)
        linked_prs = pr_lookup.get(number, [])
        has_open_pr = bool(linked_prs)
        is_maintainer_pr = any(
            pr.get("author_login") in collaborators for pr in linked_prs
        )

        if is_maintainer_pr:
            status = "in progress"
        elif has_open_pr:
            status = "community PR"
        elif {label.lower().strip() for label in labels} & blocked_labels_set:
            status = "blocked"
        else:
            status = "not started"

        pr_numbers = sorted(pr["number"] for pr in linked_prs)
        records.append(
            {
                "number": number,
                "title": issue.get("title") or "",
                "labels": labels,
                "created_at": issue.get("createdAt") or "",
                "updated_at": issue.get("updatedAt") or "",
                "created": (issue.get("createdAt") or "")[:10].replace("-", "‑"),
                "updated": (issue.get("updatedAt") or "")[:10].replace("-", "‑"),
                "category": categorize_issue(
                    issue, label_to_category, category_keywords
                ),
                "status": status,
                "pr_numbers": pr_numbers,
            }
        )

    return records


def build_previous_row_maps(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    rows_by_number: dict[str, dict[str, Any]] = {}
    order_by_status: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        number = row["number"]
        rows_by_number[number] = row
        order_by_status[row["status"]].append(number)
    return rows_by_number, order_by_status


def _is_done_expired(
    row: dict[str, Any], closed_at: dict[str, str], expire_days: int | None
) -> bool:
    if expire_days is None:
        return False
    close_date_str = closed_at.get(row["number"])
    if not close_date_str:
        # Fall back to updated date stored in the row (uses non-breaking hyphens)
        close_date_str = row.get("updated", "").replace("‑", "-")
    if not close_date_str:
        return False
    try:
        return (date.today() - date.fromisoformat(close_date_str)).days > expire_days
    except ValueError:
        return False


def merge_rows_for_render(
    current_records: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    closed_at: dict[str, str] | None = None,
    expire_days: int | None = 14,
) -> list[dict[str, Any]]:
    closed_at = closed_at or {}
    previous_by_number, previous_order = build_previous_row_maps(previous_rows)
    current_by_number = {record["number"]: record for record in current_records}
    current_numbers = set(current_by_number)

    groups: dict[str, list[dict[str, Any]]] = {status: [] for status in STATUS_ORDER}

    for record in current_records:
        previous = previous_by_number.get(record["number"])
        if previous and previous["status"] == record["status"]:
            record["sort_key"] = (
                0,
                previous_order[record["status"]].index(record["number"]),
            )
        else:
            record["sort_key"] = (1, int(record["number"]))
        groups[record["status"]].append(record)

    for status in STATUS_ORDER:
        groups[status].sort(key=lambda item: item["sort_key"])

    done_rows: list[dict[str, Any]] = []
    for row in previous_rows:
        if row["status"] == "done" and row["number"] not in current_numbers:
            if _is_done_expired(row, closed_at, expire_days):
                continue
            row = dict(row)
            row["sort_key"] = (0, previous_order["done"].index(row["number"]))
            done_rows.append(row)

    for row in previous_rows:
        if row["status"] != "done" and row["number"] not in current_numbers:
            current = current_by_number.get(row["number"])
            if current is not None:
                continue
            closed_row = dict(row)
            closed_row["status"] = "done"
            closed_row["sort_key"] = (1, int(closed_row["number"]))
            done_rows.append(closed_row)

    done_rows.sort(key=lambda item: item["sort_key"])

    render_rows: list[dict[str, Any]] = []
    for status in STATUS_ORDER[:-1]:
        render_rows.extend(groups[status])
    render_rows.extend(done_rows)

    return render_rows


def compute_summary_rows(
    cfg: DictConfig,
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    open_rows = [row for row in rows if row["status"] != "done"]
    open_total = len(open_rows)

    category_counts: dict[str, int] = defaultdict(int)
    for row in open_rows:
        category_counts[row["category"]] += 1

    category_rows = []
    for category in cfg.categories.keys():
        count = category_counts.get(category, 0)
        percentage = f"{(count / open_total * 100):.1f}%" if open_total else "0.0%"
        category_rows.append(
            {"category": category, "count": str(count), "percentage": percentage}
        )

    status_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        status_counts[row["status"]] += 1
    status_rows = [
        {"status": status, "count": str(status_counts.get(status, 0))}
        for status in STATUS_ORDER
    ]
    return category_rows, status_rows, open_total


def category_emoji(cfg: DictConfig, category: str) -> str:
    cat_cfg = cfg.categories.get(category)
    return cat_cfg.emoji if cat_cfg is not None else ""


def status_emoji(cfg: DictConfig, status: str) -> str:
    return cfg.status_emojis.get(status, "")


def build_issue_json(cfg: DictConfig, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": int(row["number"]),
        "title": row.get("title", ""),
        "category": row["category"],
        "category_emoji": category_emoji(cfg, row["category"]),
        "status": row["status"],
        "status_emoji": status_emoji(cfg, row["status"]),
        "prs": [
            {"number": int(n), "url": pr_url(cfg, n)} for n in row.get("pr_numbers", [])
        ],
        "created": row.get("created", "").replace("‑", "-"),
        "updated": row.get("updated", "").replace("‑", "-"),
        "labels": list(row.get("labels", [])),
        "url": issue_url(cfg, row["number"]),
    }


def build_data_json(
    cfg: DictConfig,
    render_rows: list[dict[str, Any]],
    generated_on: str,
    generated_at: str,
) -> dict[str, Any]:
    category_rows, status_rows, open_total = compute_summary_rows(cfg, render_rows)
    return {
        "generated_on": generated_on,
        "generated_at": generated_at,
        "repo": cfg.repo,
        "summary": {
            "open_total": open_total,
            "by_category": [
                {
                    "category": r["category"],
                    "emoji": category_emoji(cfg, r["category"]),
                    "count": int(r["count"]),
                    "percentage": float(r["percentage"].rstrip("%")),
                }
                for r in category_rows
            ],
            "by_status": [
                {
                    "status": r["status"],
                    "emoji": status_emoji(cfg, r["status"]),
                    "count": int(r["count"]),
                }
                for r in status_rows
            ],
        },
        "issues": [build_issue_json(cfg, row) for row in render_rows],
    }


def build_run_events(
    cfg: DictConfig,
    generated_at: str,
    new_issues: list[dict[str, Any]],
    status_changes: list[dict[str, Any]],
    label_changes: list[dict[str, Any]],
    closed_issues: list[dict[str, Any]],
    pr_changes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for row in new_issues:
        events.append(
            {
                "ts": generated_at,
                "kind": "new",
                "issue": int(row["number"]),
                "issue_url": issue_url(cfg, row["number"]),
                "title": row.get("title", ""),
            }
        )
    for change in status_changes:
        evt: dict[str, Any] = {
            "ts": generated_at,
            "kind": "status",
            "issue": int(change["number"]),
            "issue_url": issue_url(cfg, change["number"]),
            "title": change.get("title", ""),
            "detail": f"{change['old_status']} → {change['new_status']}",
        }
        prs = change.get("current_pr_numbers") or []
        if prs:
            evt["pr"] = {
                "number": int(prs[0]),
                "url": pr_url(cfg, prs[0]),
            }
        events.append(evt)
    for change in label_changes:
        pieces = []
        if change.get("added"):
            pieces.append("added " + ", ".join(f'"{lb}"' for lb in change["added"]))
        if change.get("removed"):
            pieces.append("removed " + ", ".join(f'"{lb}"' for lb in change["removed"]))
        events.append(
            {
                "ts": generated_at,
                "kind": "label",
                "issue": int(change["number"]),
                "issue_url": issue_url(cfg, change["number"]),
                "title": change.get("title", ""),
                "detail": "; ".join(pieces),
            }
        )
    for row in closed_issues:
        events.append(
            {
                "ts": generated_at,
                "kind": "closed",
                "issue": int(row["number"]),
                "issue_url": issue_url(cfg, row["number"]),
                "title": row.get("title", ""),
            }
        )
    for change in pr_changes:
        if change.get("added_prs"):
            events.append(
                {
                    "ts": generated_at,
                    "kind": "pr",
                    "issue": int(change["number"]),
                    "issue_url": issue_url(cfg, change["number"]),
                    "title": change.get("title", ""),
                    "detail": "linked "
                    + ", ".join(f"#{p}" for p in change["added_prs"]),
                }
            )
        if change.get("removed_prs"):
            events.append(
                {
                    "ts": generated_at,
                    "kind": "pr",
                    "issue": int(change["number"]),
                    "issue_url": issue_url(cfg, change["number"]),
                    "title": change.get("title", ""),
                    "detail": "unlinked "
                    + ", ".join(f"#{p}" for p in change["removed_prs"]),
                }
            )
    return events


def append_events_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    if not events:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for evt in events:
            f.write(json.dumps(evt, ensure_ascii=False) + "\n")


def read_recent_events(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    tail = lines[-limit:] if limit and len(lines) > limit else lines
    events = [json.loads(ln) for ln in tail]
    events.reverse()  # newest first for the UI
    return events


def snapshot_from_open_records(
    repo: str, records: list[dict[str, Any]], generated_at: str
) -> dict[str, Any]:
    return {
        "repo": repo,
        "generated_at": generated_at,
        "issues": {
            record["number"]: {
                "title": record["title"],
                "state": "OPEN",
                "category": record["category"],
                "status": record["status"],
                "labels": sorted(record["labels"]),
                "pr_numbers": sorted(
                    record["pr_numbers"], key=lambda value: int(value)
                ),
                "created_at": record["created_at"],
                "updated_at": record["updated_at"],
            }
            for record in records
            if record["status"] != "done"
        },
    }


def recent_done_from_render_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    done: dict[str, Any] = {}
    for row in rows:
        if row["status"] != "done":
            continue
        done[row["number"]] = {
            "title": row.get("title", ""),
            "state": "CLOSED",
            "category": row["category"],
            "status": "done",
            "labels": sorted(row.get("labels", [])),
            "pr_numbers": sorted(
                row.get("pr_numbers", []), key=lambda value: int(value)
            ),
            "created_at": (
                row.get("created_at") or row.get("created", "").replace("‑", "-")
            ),
            "updated_at": (
                row.get("updated_at") or row.get("updated", "").replace("‑", "-")
            ),
        }
    return done


def compare_snapshots(
    previous_snapshot: dict[str, Any] | None,
    current_snapshot: dict[str, Any],
    current_rows_by_number: dict[str, dict[str, Any]],
    previous_rows_by_number: dict[str, dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    if not previous_snapshot:
        return [], [], [], [], []

    previous_issues = previous_snapshot.get("issues", {})
    current_issues = current_snapshot.get("issues", {})

    new_issues: list[dict[str, Any]] = []
    status_changes: list[dict[str, Any]] = []
    label_changes: list[dict[str, Any]] = []
    closed_issues: list[dict[str, Any]] = []
    pr_changes: list[dict[str, Any]] = []

    for issue_number, current in current_issues.items():
        previous = previous_issues.get(issue_number)
        if previous is None:
            new_issues.append(current_rows_by_number[issue_number])
            continue

        if previous.get("status") != current.get("status"):
            status_changes.append(
                {
                    "number": issue_number,
                    "title": current_rows_by_number[issue_number]["title"],
                    "old_status": previous.get("status", "not started"),
                    "new_status": current.get("status", "not started"),
                    "current_pr_numbers": current_rows_by_number[issue_number][
                        "pr_numbers"
                    ],
                }
            )

        previous_labels = previous.get("labels", [])
        current_labels = current.get("labels", [])
        added_labels = [
            label for label in current_labels if label not in previous_labels
        ]
        removed_labels = [
            label for label in previous_labels if label not in current_labels
        ]
        if added_labels or removed_labels:
            label_changes.append(
                {
                    "number": issue_number,
                    "title": current_rows_by_number[issue_number]["title"],
                    "added": added_labels,
                    "removed": removed_labels,
                }
            )

        previous_prs = set(previous.get("pr_numbers", []))
        current_prs = set(current.get("pr_numbers", []))
        added_prs = sorted(current_prs - previous_prs, key=int)
        removed_prs = sorted(previous_prs - current_prs, key=int)
        if added_prs or removed_prs:
            pr_changes.append(
                {
                    "number": issue_number,
                    "title": current_rows_by_number[issue_number]["title"],
                    "added_prs": added_prs,
                    "removed_prs": removed_prs,
                }
            )

    for issue_number, previous in previous_issues.items():
        if issue_number not in current_issues:
            previous_row = previous_rows_by_number.get(issue_number)
            if previous_row is None or previous_row.get("status") == "done":
                continue
            closed_issues.append(previous_row)

    return new_issues, status_changes, label_changes, closed_issues, pr_changes


def build_commit_message(
    new_issues: list[dict[str, Any]],
    status_changes: list[dict[str, Any]],
    label_changes: list[dict[str, Any]],
    closed_issues: list[dict[str, Any]],
    pr_changes: list[dict[str, Any]],
    open_count: int,
) -> str:
    parts: list[str] = []

    if new_issues:
        nums = ", ".join(str(r["number"]) for r in new_issues[:3])
        suffix = f" +{len(new_issues) - 3} more" if len(new_issues) > 3 else ""
        parts.append(f"new {nums}{suffix}")

    if closed_issues:
        nums = ", ".join(str(r["number"]) for r in closed_issues[:3])
        suffix = f" +{len(closed_issues) - 3} more" if len(closed_issues) > 3 else ""
        parts.append(f"closed {nums}{suffix}")

    for c in status_changes[:3]:
        parts.append(f"{c['number']} {c['old_status']} → {c['new_status']}")
    if len(status_changes) > 3:
        parts.append(f"+{len(status_changes) - 3} more status changes")

    for c in pr_changes[:3]:
        if c["added_prs"]:
            prs = ", ".join(str(p) for p in c["added_prs"])
            parts.append(f"link {prs} to {c['number']}")
        if c["removed_prs"]:
            prs = ", ".join(str(p) for p in c["removed_prs"])
            parts.append(f"unlink {prs} from {c['number']}")
    if len(pr_changes) > 3:
        parts.append(f"+{len(pr_changes) - 3} more PR changes")

    for c in label_changes[:2]:
        pieces = []
        if c.get("added"):
            pieces.append("+" + ", ".join(c["added"]))
        if c.get("removed"):
            pieces.append("-" + ", ".join(c["removed"]))
        parts.append(f"{c['number']} labels: {'; '.join(pieces)}")
    if len(label_changes) > 2:
        parts.append(f"+{len(label_changes) - 2} more label changes")

    if not parts:
        return f"backlog: sync ({open_count} open) [skip ci]"

    return "backlog: " + "; ".join(parts) + " [skip ci]"


def parse_issue_number_arg(value: str) -> int:
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    if not text.isdigit() or int(text) <= 0:
        raise argparse.ArgumentTypeError("issue number must be a positive integer")
    return int(text)


def _add_update_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        help=(
            "Repository URL. GitHub URLs are supported today; owner/name is "
            "accepted as GitHub shorthand. Defaults to Git or Sapling remote detection."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files",
    )
    parser.add_argument(
        "--snapshot-path",
        help="Path to snapshot JSON file. Defaults to the state/ directory next to this script.",
    )
    parser.add_argument(
        "--commit-msg-path",
        help="Write the descriptive commit message to this file.",
    )
    parser.add_argument(
        "--data-json-path",
        help="Override the path where backlog.json is written.",
    )
    parser.add_argument(
        "--updates-jsonl-path",
        help="Override the path of the append-only structured updates log (updates.jsonl).",
    )


def _add_classify_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "issue_number",
        type=parse_issue_number_arg,
        help="GitHub issue number to classify.",
    )
    parser.add_argument(
        "--repo",
        help=(
            "Repository URL. GitHub URLs are supported; owner/name is accepted "
            "as shorthand. When provided, classify uses the remote config from "
            "the repository default branch."
        ),
    )


def _add_dump_atlas_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        required=True,
        help="YAML multi-repo atlas config to compile into atlas.json.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help=(
            "Output path. If it ends with .json, writes there. "
            "Otherwise writes atlas.json inside the directory."
        ),
    )


def _add_atlas_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        help=(
            f"Atlas YAML config path. Defaults to {ATLAS_CONFIG_RELATIVE_PATH} "
            "in the detected checkout."
        ),
    )


def _add_atlas_args(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="atlas_cmd", required=True)

    p_list = sub.add_parser("list", help="List repos tracked by atlas.yaml.")
    _add_atlas_config_arg(p_list)

    p_add = sub.add_parser("add", help="Add a repo to atlas.yaml.")
    p_add.add_argument(
        "repo",
        help="GitHub repository URL or owner/name shorthand to add.",
    )
    p_add.add_argument(
        "--backlog-url",
        help=(
            "Published backlog.json URL. Defaults to "
            "https://OWNER.github.io/REPO/backlog.json."
        ),
    )
    _add_atlas_config_arg(p_add)

    p_remove = sub.add_parser("remove", help="Remove a repo from atlas.yaml.")
    p_remove.add_argument(
        "repo",
        help="GitHub repository URL or owner/name shorthand to remove.",
    )
    _add_atlas_config_arg(p_remove)


def remote_config_source(repo: str, branch: str) -> str:
    return f"https://github.com/{repo}@{branch}:{app_config.APP_CONFIG_RELATIVE_PATH}"


def load_remote_config(repo: str) -> tuple[DictConfig, str]:
    from .install import github as install_github

    branch = install_github.github_default_branch(repo)
    source = remote_config_source(repo, branch)
    content = install_github.remote_config_text(repo, branch)
    if content is None:
        raise UserError(
            "remote Backlog Atlas config was not found:\n"
            f"  {source}\n\n"
            "Remote classification uses the config committed to the repository "
            "default branch. Run `backlog-atlas install` or merge "
            f"`{app_config.APP_CONFIG_RELATIVE_PATH}`, then rerun classify."
        )
    return validate_config_content(content, source), source


def print_classification(
    mode: str,
    repo: str,
    config_source: str,
    issue: dict[str, Any],
    classification: CategoryClassification,
) -> None:
    labels = parse_labels(issue)
    print(f"Mode: {mode}")
    print(f"Repo: {repo}")
    print(f"Config: {config_source}")
    print(f"Issue: #{issue['number']} {issue.get('title') or ''}")
    print(f"Labels: {', '.join(labels) if labels else '(none)'}")
    print(f"Category: {classification.category}")
    print(f"Reason: {classification.reason}")


def run_classify(args: argparse.Namespace) -> int:
    if args.repo:
        mode = "remote"
        repo = resolve_repo(args.repo)
        cfg, config_source = load_remote_config(repo)
    else:
        mode = "checkout"
        target_root = detect_target_root()
        repo = resolve_repo(None, target_root)
        loaded_config = load_config_with_source(target_root)
        cfg = loaded_config.config
        config_source = loaded_config.source

    cfg.repo = repo
    issue = fetch_issue(repo, args.issue_number)
    label_to_category, category_keywords = category_matchers(cfg)
    classification = classify_issue_category(
        issue, label_to_category, category_keywords
    )
    print_classification(mode, repo, config_source, issue, classification)
    return 0


def run_update(args: argparse.Namespace) -> int:
    target_root = detect_target_root()
    loaded_config = load_config_with_source(target_root)
    cfg = loaded_config.config
    repo = resolve_repo(args.repo)
    cfg.repo = repo
    generated_on = today()
    generated_at = iso_now()

    state_dir = target_root / ".backlog-atlas"
    snapshot_path = (
        Path(args.snapshot_path)
        if args.snapshot_path
        else state_dir / "last_snapshot.json"
    )
    data_json_path = (
        Path(args.data_json_path)
        if args.data_json_path
        else state_dir / cfg.data_json_filename
    )
    updates_jsonl_path = (
        Path(args.updates_jsonl_path)
        if args.updates_jsonl_path
        else state_dir / cfg.updates_jsonl_filename
    )
    label_to_category, category_keywords = category_matchers(cfg)

    previous_snapshot = load_json_file(snapshot_path)
    if previous_snapshot and previous_snapshot.get("repo") not in {None, repo}:
        previous_snapshot = None
    previous_rows = previous_rows_from_snapshot(
        previous_snapshot, label_to_category, category_keywords
    )
    previous_rows_by_number = {row["number"]: row for row in previous_rows}

    collaborators = fetch_collaborators(repo)
    open_issues = fetch_open_issues(repo)
    open_issue_numbers = {str(issue["number"]) for issue in open_issues}
    open_prs = fetch_open_prs(repo)
    pr_lookup = build_pr_lookup(open_prs, open_issue_numbers)
    current_records = build_current_issue_records(
        cfg,
        open_issues,
        collaborators,
        pr_lookup,
        label_to_category,
        category_keywords,
    )
    current_snapshot = snapshot_from_open_records(repo, current_records, generated_at)

    prev_open = set((previous_snapshot or {}).get("issues", {}).keys())
    curr_open = set(current_snapshot["issues"].keys())
    run_date = generated_at[:10]
    closed_at: dict[str, str] = dict((previous_snapshot or {}).get("closed_at", {}))
    for num in prev_open - curr_open:
        closed_at.setdefault(num, run_date)

    render_rows = merge_rows_for_render(
        current_records, previous_rows, closed_at, expire_days=cfg.done_expire_days
    )
    rendered_done_numbers = {
        row["number"] for row in render_rows if row["status"] == "done"
    }
    current_snapshot["closed_at"] = {
        num: dt for num, dt in closed_at.items() if num in rendered_done_numbers
    }
    current_snapshot["recent_done"] = recent_done_from_render_rows(render_rows)
    new_issues, status_changes, label_changes, closed_issues, pr_changes = (
        compare_snapshots(
            previous_snapshot,
            current_snapshot,
            {record["number"]: record for record in current_records},
            previous_rows_by_number,
        )
    )

    run_events = build_run_events(
        cfg,
        generated_at,
        new_issues,
        status_changes,
        label_changes,
        closed_issues,
        pr_changes,
    )

    if not args.dry_run and run_events:
        append_events_jsonl(updates_jsonl_path, run_events)

    recent_events = read_recent_events(updates_jsonl_path, cfg.data_updates_limit)
    if args.dry_run and run_events:
        # Dry-run still wants to preview the updates that would be embedded.
        recent_events = list(reversed(run_events)) + recent_events
    if args.dry_run:
        recent_events = recent_events[: cfg.data_updates_limit]

    data_obj = build_data_json(cfg, render_rows, generated_on, generated_at)
    data_obj["updates"] = recent_events
    data_json_content = json.dumps(data_obj, indent=2, ensure_ascii=False) + "\n"
    data_json_changed = (
        not data_json_path.exists() or read_text(data_json_path) != data_json_content
    )

    if args.dry_run:
        print(f"Resolved GitHub repo: {repo}")
        print(f"Config: {loaded_config.source}")
        print(
            f"{cfg.data_json_filename} would {'change' if data_json_changed else 'remain unchanged'}"
        )
        print(
            f"{cfg.updates_jsonl_filename} would append {len(run_events)} event(s)"
            if run_events
            else f"{cfg.updates_jsonl_filename} would not change"
        )
        print(f"Snapshot would contain {len(current_snapshot['issues'])} open issues")
        return 0

    if data_json_changed:
        write_text(data_json_path, data_json_content)

    ensure_text_file(updates_jsonl_path)

    save_snapshot(current_snapshot, snapshot_path)
    print(
        (
            f"Updated {cfg.data_json_filename}"
            if data_json_changed
            else f"{cfg.data_json_filename} already up to date"
        ),
        file=sys.stdout,
    )
    if run_events:
        print(
            f"Appended {len(run_events)} event(s) to {cfg.updates_jsonl_filename}",
            file=sys.stdout,
        )
    else:
        print("No backlog updates needed", file=sys.stdout)
    print(
        f"Saved snapshot for {repo} with {len(current_snapshot['issues'])} open issues",
        file=sys.stdout,
    )
    if args.commit_msg_path:
        commit_msg = build_commit_message(
            new_issues,
            status_changes,
            label_changes,
            closed_issues,
            pr_changes,
            len(current_snapshot["issues"]),
        )
        Path(args.commit_msg_path).write_text(commit_msg, encoding="utf-8")
        print(f"Commit message: {commit_msg}", file=sys.stdout)
    return 0


def _is_yaml_error(error: Exception) -> bool:
    return type(error).__module__.split(".", 1)[0] == "yaml"


def atlas_config_error(source: Path, message: str) -> UserError:
    return UserError(
        f"Backlog Atlas multi-repo config is invalid:\n  {source}\n\n{message}"
    )


def atlas_config_path(config: str | None) -> Path:
    if config:
        return Path(config)
    return detect_target_root() / ATLAS_CONFIG_RELATIVE_PATH


def load_mutable_atlas_config(path: Path, create: bool = False) -> DictConfig | None:
    if not path.exists():
        if not create:
            return None
        return OmegaConf.create({"repos": []})
    try:
        raw = OmegaConf.load(path)
    except (OSError, OmegaConfBaseException, ValueError, TypeError) as e:
        raise atlas_config_error(path, str(e)) from e
    except Exception as e:
        if _is_yaml_error(e):
            raise atlas_config_error(path, str(e)) from e
        raise
    if not isinstance(raw, DictConfig):
        raise atlas_config_error(path, "top-level YAML value must be a mapping")
    repos = raw.get("repos")
    if repos is None:
        raw.repos = []
    elif not OmegaConf.is_list(repos):
        raise atlas_config_error(path, "`repos` must be a list")
    return raw


def atlas_repo_entries(config: DictConfig, path: Path) -> list[dict[str, str]]:
    data = OmegaConf.to_container(config, resolve=False)
    if not isinstance(data, dict):
        raise atlas_config_error(path, "top-level YAML value must be a mapping")
    repos = data.get("repos") or []
    if not isinstance(repos, list):
        raise atlas_config_error(path, "`repos` must be a list")

    entries = []
    for index, entry in enumerate(repos, start=1):
        if not isinstance(entry, dict):
            raise atlas_config_error(path, f"`repos[{index}]` must be a mapping")
        repo = entry.get("repo")
        backlog_url = entry.get("backlog_url") or entry.get("url")
        if not isinstance(repo, str) or not repo.strip():
            raise atlas_config_error(
                path,
                f"`repos[{index}].repo` must be a non-empty owner/name string",
            )
        if not isinstance(backlog_url, str) or not backlog_url.strip():
            raise atlas_config_error(
                path,
                f"`repos[{index}].backlog_url` must be a non-empty string",
            )
        entries.append({"repo": repo, "backlog_url": backlog_url})
    return entries


def default_atlas_backlog_url(repo: str) -> str:
    owner, name = repo.split("/", 1)
    return f"https://{owner}.github.io/{name}/backlog.json"


def save_atlas_config(path: Path, config: DictConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    OmegaConf.save(config=config, f=path, resolve=False)


def normalize_atlas_repo_arg(repo_or_url: str) -> str:
    repo = normalize_github_repo(repo_or_url)
    if repo:
        return repo
    raise UserError(
        "unsupported repo value; expected a GitHub repository URL like "
        "https://github.com/owner/name or the shorthand owner/name"
    )


def run_atlas_list(args: argparse.Namespace) -> int:
    path = atlas_config_path(args.config)
    config = load_mutable_atlas_config(path)
    if config is None:
        print(f"No tracked repos (atlas config not found: {path})")
        return 0
    entries = atlas_repo_entries(config, path)
    if not entries:
        print(f"No tracked repos in {path}")
        return 0
    print(f"Tracked repos in {path}:")
    for entry in entries:
        print(f"- {entry['repo']}  {entry['backlog_url']}")
    return 0


def run_atlas_add(args: argparse.Namespace) -> int:
    path = atlas_config_path(args.config)
    config = load_mutable_atlas_config(path, create=True)
    assert config is not None
    repo = normalize_atlas_repo_arg(args.repo)
    entries = atlas_repo_entries(config, path)
    if any(normalize_github_repo(entry["repo"]) == repo for entry in entries):
        raise UserError(f"{repo} is already tracked in {path}")

    config.repos.append(
        {
            "repo": repo,
            "backlog_url": args.backlog_url or default_atlas_backlog_url(repo),
        }
    )
    save_atlas_config(path, config)
    print(f"Added {repo} to {path}")
    return 0


def run_atlas_remove(args: argparse.Namespace) -> int:
    path = atlas_config_path(args.config)
    config = load_mutable_atlas_config(path)
    if config is None:
        raise UserError(f"atlas config was not found: {path}")
    repo = normalize_atlas_repo_arg(args.repo)
    data = OmegaConf.to_container(config, resolve=False)
    if not isinstance(data, dict):
        raise atlas_config_error(path, "top-level YAML value must be a mapping")
    repos = data.get("repos") or []
    if not isinstance(repos, list):
        raise atlas_config_error(path, "`repos` must be a list")

    remaining = []
    removed = False
    for entry in repos:
        if not isinstance(entry, dict):
            raise atlas_config_error(path, "`repos` entries must be mappings")
        if normalize_github_repo(str(entry.get("repo") or "")) == repo:
            removed = True
            continue
        remaining.append(entry)
    if not removed:
        raise UserError(f"{repo} is not tracked in {path}")

    if remaining:
        config.repos = remaining
        save_atlas_config(path, config)
        print(f"Removed {repo} from {path}")
    else:
        path.unlink()
        print(f"Removed {repo} from {path}")
        print(f"Removed empty atlas config {path}")
    return 0


def run_atlas(args: argparse.Namespace) -> int:
    if args.atlas_cmd == "list":
        return run_atlas_list(args)
    if args.atlas_cmd == "add":
        return run_atlas_add(args)
    if args.atlas_cmd == "remove":
        return run_atlas_remove(args)
    raise RuntimeError(f"unsupported atlas command: {args.atlas_cmd}")


def load_atlas_manifest_config(path: Path) -> dict[str, Any]:
    try:
        raw = OmegaConf.load(path)
        data = OmegaConf.to_container(raw, resolve=True)
    except (OSError, OmegaConfBaseException, ValueError, TypeError) as e:
        raise atlas_config_error(path, str(e)) from e
    except Exception as e:
        if _is_yaml_error(e):
            raise atlas_config_error(path, str(e)) from e
        raise

    if not isinstance(data, dict):
        raise atlas_config_error(path, "top-level YAML value must be a mapping")

    repos = data.get("repos")
    if not isinstance(repos, list) or not repos:
        raise atlas_config_error(path, "`repos` must contain at least one repo entry")

    manifest: dict[str, Any] = {"repos": []}
    title = data.get("title")
    if title is not None:
        if not isinstance(title, str) or not title.strip():
            raise atlas_config_error(path, "`title` must be a non-empty string")
        manifest["title"] = title

    for index, entry in enumerate(repos, start=1):
        if not isinstance(entry, dict):
            raise atlas_config_error(path, f"`repos[{index}]` must be a mapping")
        repo = entry.get("repo")
        backlog_url = entry.get("backlog_url") or entry.get("url")
        if not isinstance(repo, str) or not repo.strip():
            raise atlas_config_error(
                path,
                f"`repos[{index}].repo` must be a non-empty owner/name string",
            )
        if not isinstance(backlog_url, str) or not backlog_url.strip():
            raise atlas_config_error(
                path,
                f"`repos[{index}].backlog_url` must be a non-empty string",
            )
        manifest["repos"].append({"repo": repo, "backlog_url": backlog_url})

    return manifest


def atlas_manifest_output_path(output: str) -> Path:
    path = Path(output)
    if path.suffix == ".json":
        return path
    return path / "atlas.json"


def run_dump_atlas(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    manifest = load_atlas_manifest_config(config_path)
    output_path = atlas_manifest_output_path(args.output)
    write_text(output_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Wrote atlas manifest to {output_path}", file=sys.stdout)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="backlog-atlas")
    sub = parser.add_subparsers(dest="cmd")

    p_update = sub.add_parser(
        "update",
        help="Regenerate backlog.json and updates.jsonl from GitHub state.",
    )
    _add_update_args(p_update)

    p_classify = sub.add_parser(
        "classify",
        help="Explain how one GitHub issue is classified by Backlog Atlas config.",
    )
    _add_classify_args(p_classify)

    p_install = sub.add_parser(
        "install",
        help="Write the GitHub Actions workflow for Backlog Atlas.",
    )
    add_install_args(p_install)
    p_uninstall = sub.add_parser(
        "uninstall",
        help="Write a one-shot workflow that uninstalls Backlog Atlas.",
    )
    add_uninstall_args(p_uninstall)

    p_dump_web = sub.add_parser(
        "dump-web",
        help="Write the bundled web UI files to a target directory or single file.",
    )
    p_dump_web.add_argument(
        "--output",
        required=True,
        help=(
            "Output path. If it ends with .html, only index.html is written there. "
            "Otherwise treated as a directory and all bundled web files are copied in."
        ),
    )
    p_dump_atlas = sub.add_parser(
        "dump-atlas",
        help="Compile YAML multi-repo atlas config into browser atlas.json.",
    )
    _add_dump_atlas_args(p_dump_atlas)
    p_atlas = sub.add_parser(
        "atlas",
        help="Manage repos tracked by the multi-repo atlas config.",
    )
    _add_atlas_args(p_atlas)

    args = parser.parse_args()

    try:
        if args.cmd == "update":
            return run_update(args)
        if args.cmd == "classify":
            return run_classify(args)
        if args.cmd == "install":
            return run_install(args)
        if args.cmd == "uninstall":
            return run_uninstall(args)
        if args.cmd == "dump-web":
            return run_dump_web(args)
        if args.cmd == "dump-atlas":
            return run_dump_atlas(args)
        if args.cmd == "atlas":
            return run_atlas(args)
    except UserError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.exit_code
    parser.print_help()
    return 2


def run_dump_web(args: argparse.Namespace) -> int:
    out = Path(args.output)
    if out.suffix == ".html":
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes((WEB_DIR / "index.html").read_bytes())
        print(f"✓ wrote {out}")
        return 0
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in WEB_DIR.iterdir():
        if src.is_file():
            (out / src.name).write_bytes(src.read_bytes())
            count += 1
    print(f"✓ wrote {count} file(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
