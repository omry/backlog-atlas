"""Unit tests for Backlog Atlas."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import backlog_atlas.core as ub  # noqa: E402
import backlog_atlas.install.artifacts as install_artifacts  # noqa: E402
import backlog_atlas.install.commands as install_commands  # noqa: E402
import backlog_atlas.install.github as install_github  # noqa: E402
import backlog_atlas.install.local as install_local  # noqa: E402
import backlog_atlas.install.repo as install_repo  # noqa: E402
import backlog_atlas.install.sources as install_sources  # noqa: E402
from backlog_atlas.install.models import InstallSource  # noqa: E402

# Helpers derived from _DEFAULT_CATEGORIES for tests
_L2C = {label: cat for cat, c in ub._DEFAULT_CATEGORIES.items() for label in c.labels}
_KW = {cat: c.keywords for cat, c in ub._DEFAULT_CATEGORIES.items()}


def _cfg(repo: str = "o/r") -> Any:
    cfg = ub.load_config()
    cfg.repo = repo
    return cfg


# ---------------------------------------------------------------------------
# try_command
# ---------------------------------------------------------------------------


def test_try_command_missing_binary():
    assert install_commands.try_command(["nonexistent_binary_xyz"]) is None


def test_try_command_nonzero_exit():
    assert install_commands.try_command(["false"]) is None


def test_try_command_success():
    result = install_commands.try_command(["echo", "hello"])
    assert result is not None
    assert "hello" in result


# ---------------------------------------------------------------------------
# categorize_issue
# ---------------------------------------------------------------------------


def _issue(labels: list[str], title: str = "", body: str = "") -> dict[str, Any]:
    return {
        "title": title,
        "body": body,
        "labels": [{"name": name} for name in labels],
    }


def test_categorize_bug_label():
    assert ub.categorize_issue(_issue(["bug"]), _L2C, _KW) == "Bug"


def test_categorize_enhancement_label():
    assert ub.categorize_issue(_issue(["enhancement"]), _L2C, _KW) == "Enhancement"


def test_categorize_refactor_label():
    assert ub.categorize_issue(_issue(["refactor"]), _L2C, _KW) == "Refactor"


def test_categorize_documentation_label():
    assert ub.categorize_issue(_issue(["documentation"]), _L2C, _KW) == "Documentation"


def test_categorize_question_label():
    assert ub.categorize_issue(_issue(["question"]), _L2C, _KW) == "Question"


def test_categorize_bug_keyword_in_title():
    assert (
        ub.categorize_issue(_issue([], title="crash when using merge"), _L2C, _KW)
        == "Bug"
    )


def test_categorize_enhancement_fallback():
    assert ub.categorize_issue(_issue([]), _L2C, _KW) == "Enhancement"


def test_categorize_bug_label_beats_enhancement_keyword():
    assert ub.categorize_issue(_issue(["bug"], title="add feature"), _L2C, _KW) == "Bug"


# ---------------------------------------------------------------------------
# status determination via build_current_issue_records
# ---------------------------------------------------------------------------


def _open_issue(number: int, labels: list[str] = []) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"Issue {number}",
        "body": "",
        "labels": [{"name": name} for name in labels],
        "state": "OPEN",
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-01T00:00:00Z",
    }


def _pr(number: str, author: str, linked: list[str]) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"PR {number}",
        "body": "",
        "author_login": author,
        "linked_issue_numbers": linked,
    }


def test_status_not_started():
    issues = [_open_issue(1)]
    pr_lookup: dict[str, Any] = {}
    records = ub.build_current_issue_records(
        _cfg(), issues, set(), pr_lookup, _L2C, _KW
    )
    assert records[0]["status"] == "not started"


def test_status_in_progress_maintainer_pr():
    issues = [_open_issue(1)]
    collaborators = {"maintainer"}
    pr_lookup = ub.build_pr_lookup([_pr("10", "maintainer", ["1"])], {"1"})
    records = ub.build_current_issue_records(
        _cfg(), issues, collaborators, pr_lookup, _L2C, _KW
    )
    assert records[0]["status"] == "in progress"


def test_status_community_pr():
    issues = [_open_issue(1)]
    pr_lookup = ub.build_pr_lookup([_pr("10", "community_user", ["1"])], {"1"})
    records = ub.build_current_issue_records(
        _cfg(), issues, set(), pr_lookup, _L2C, _KW
    )
    assert records[0]["status"] == "community PR"


def test_status_blocked_awaiting_response():
    issues = [_open_issue(1, labels=["awaiting response"])]
    records = ub.build_current_issue_records(_cfg(), issues, set(), {}, _L2C, _KW)
    assert records[0]["status"] == "blocked"


def test_status_in_progress_beats_blocked():
    issues = [_open_issue(1, labels=["awaiting response"])]
    collaborators = {"maintainer"}
    pr_lookup = ub.build_pr_lookup([_pr("10", "maintainer", ["1"])], {"1"})
    records = ub.build_current_issue_records(
        _cfg(), issues, collaborators, pr_lookup, _L2C, _KW
    )
    assert records[0]["status"] == "in progress"


# ---------------------------------------------------------------------------
# compare_snapshots
# ---------------------------------------------------------------------------


def _snapshot(issues: dict[str, Any]) -> dict[str, Any]:
    return {"repo": "o/r", "generated_at": "2024-01-01T00:00:00Z", "issues": issues}


def _record(
    number: str, status: str = "not started", labels: list[str] = []
) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"Issue {number}",
        "status": status,
        "category": "Enhancement",
        "labels": labels,
        "pr_numbers": [],
        "created": "2024-01-01",
        "updated": "2024-01-01",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }


def test_compare_no_previous_snapshot():
    current = _snapshot(
        {
            "1": {
                "title": "t",
                "status": "not started",
                "labels": [],
                "category": "Enhancement",
            }
        }
    )
    new, status, labels, closed, prs = ub.compare_snapshots(
        None, current, {"1": _record("1")}, {}
    )
    assert new == [] and status == [] and labels == [] and closed == [] and prs == []


def test_compare_detects_new_issue():
    prev = _snapshot({})
    curr = _snapshot(
        {
            "1": {
                "title": "t",
                "status": "not started",
                "labels": [],
                "category": "Enhancement",
            }
        }
    )
    new, _, _, _, _ = ub.compare_snapshots(prev, curr, {"1": _record("1")}, {})
    assert len(new) == 1 and new[0]["number"] == "1"


def test_compare_detects_status_change():
    prev = _snapshot(
        {
            "1": {
                "title": "t",
                "status": "not started",
                "labels": [],
                "category": "Enhancement",
            }
        }
    )
    curr = _snapshot(
        {
            "1": {
                "title": "t",
                "status": "in progress",
                "labels": [],
                "category": "Enhancement",
            }
        }
    )
    _, status, _, _, _ = ub.compare_snapshots(
        prev, curr, {"1": _record("1", "in progress")}, {}
    )
    assert len(status) == 1 and status[0]["new_status"] == "in progress"


def test_compare_detects_closed():
    prev = _snapshot(
        {
            "1": {
                "title": "t",
                "status": "not started",
                "labels": [],
                "category": "Enhancement",
            }
        }
    )
    curr = _snapshot({})
    _, _, _, closed, _ = ub.compare_snapshots(prev, curr, {}, {"1": _record("1")})
    assert len(closed) == 1


# ---------------------------------------------------------------------------
# commit message generation
# ---------------------------------------------------------------------------


def test_commit_message_uses_plain_numbers_not_github_refs():
    message = ub.build_commit_message(
        new_issues=[{"number": "1"}],
        status_changes=[
            {
                "number": "2",
                "old_status": "not started",
                "new_status": "in progress",
            }
        ],
        label_changes=[
            {
                "number": "3",
                "added": ["bug"],
                "removed": ["question"],
            }
        ],
        closed_issues=[{"number": "4"}],
        pr_changes=[
            {
                "number": "5",
                "added_prs": ["10"],
                "removed_prs": ["11"],
            }
        ],
        open_count=9,
    )

    assert "#" not in message
    assert message == (
        "backlog: new 1; closed 4; 2 not started → in progress; "
        "link 10 to 5; unlink 11 from 5; 3 labels: +bug; -question [skip ci]"
    )


# ---------------------------------------------------------------------------
# save_snapshot / load_json_file with custom path
# ---------------------------------------------------------------------------


def test_save_and_load_snapshot_custom_path(tmp_path: Path):
    snap = {"repo": "o/r", "generated_at": "2024-01-01T00:00:00Z", "issues": {}}
    path = tmp_path / "snap.json"
    ub.save_snapshot(snap, path)
    loaded = ub.load_json_file(path)
    assert loaded == snap


def test_save_snapshot_creates_parent_dirs(tmp_path: Path):
    snap = {"repo": "o/r", "issues": {}}
    path = tmp_path / "deep" / "dir" / "snap.json"
    ub.save_snapshot(snap, path)
    assert path.exists()


# ---------------------------------------------------------------------------
# normalize_previous_row — category derived from title/labels, not HTML
# ---------------------------------------------------------------------------


def _prev_row(
    number: str, title: str, status: str = "done", labels: list[str] = []
) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "status": status,
        "pr_numbers": [],
        "created": "2024‑01‑01",
        "updated": "2024‑01‑01",
        "labels": labels,
    }


def test_normalize_previous_row_derives_category_from_title():
    row = ub.normalize_previous_row(
        _prev_row("803", "[Question] Why hide this?"), _L2C, _KW
    )
    assert row["category"] == "Question"


def test_normalize_previous_row_derives_category_from_label():
    row = ub.normalize_previous_row(
        _prev_row("1", "Something", labels=["bug"]), _L2C, _KW
    )
    assert row["category"] == "Bug"


def test_normalize_previous_row_ignores_stale_category_field():
    raw = {
        **_prev_row("1", "Add a feature"),
        "category": '<span title="<span>garbage</span>">✨</span>',
    }
    row = ub.normalize_previous_row(raw, _L2C, _KW)
    assert row["category"] == "Enhancement"


def test_previous_rows_from_snapshot_includes_recent_done():
    snapshot = {
        "repo": "o/r",
        "issues": {
            "1": {
                "title": "Open bug",
                "status": "blocked",
                "labels": ["bug"],
                "pr_numbers": ["10"],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
            }
        },
        "recent_done": {
            "2": {
                "title": "Closed question",
                "labels": ["question"],
                "pr_numbers": [],
                "created_at": "2024-01-03T00:00:00Z",
                "updated_at": "2024-01-04T00:00:00Z",
            }
        },
    }

    rows = ub.previous_rows_from_snapshot(snapshot, _L2C, _KW)

    assert [(row["number"], row["status"], row["category"]) for row in rows] == [
        ("1", "blocked", "Bug"),
        ("2", "done", "Question"),
    ]


# ---------------------------------------------------------------------------
# _is_done_expired
# ---------------------------------------------------------------------------


def test_is_done_expired_not_expired_via_closed_at():
    from datetime import date, timedelta

    recent = (date.today() - timedelta(days=5)).isoformat()
    row = _prev_row("1", "t")
    assert not ub._is_done_expired(row, {"1": recent}, 14)


def test_is_done_expired_expired_via_closed_at():
    from datetime import date, timedelta

    old = (date.today() - timedelta(days=15)).isoformat()
    row = _prev_row("1", "t")
    assert ub._is_done_expired(row, {"1": old}, 14)


def test_is_done_expired_boundary_exactly_14_days():
    from datetime import date, timedelta

    boundary = (date.today() - timedelta(days=14)).isoformat()
    row = _prev_row("1", "t")
    assert not ub._is_done_expired(row, {"1": boundary}, 14)


def test_is_done_expired_fallback_to_updated_field():
    from datetime import date, timedelta

    old = (date.today() - timedelta(days=20)).isoformat().replace("-", "‑")
    row = {**_prev_row("1", "t"), "updated": old}
    assert ub._is_done_expired(row, {}, 14)


def test_is_done_expired_no_date_not_expired():
    row = {**_prev_row("1", "t"), "updated": ""}
    assert not ub._is_done_expired(row, {}, 14)


def test_is_done_expired_none_expire_days_never_expires():
    from datetime import date, timedelta

    old = (date.today() - timedelta(days=999)).isoformat()
    row = _prev_row("1", "t")
    assert not ub._is_done_expired(row, {"1": old}, None)


# ---------------------------------------------------------------------------
# merge_rows_for_render — done expiry
# ---------------------------------------------------------------------------


def _done_prev_row(number: str, days_old: int) -> dict[str, Any]:
    from datetime import date, timedelta

    updated = (date.today() - timedelta(days=days_old)).isoformat().replace("-", "‑")
    row = _prev_row(number, f"Issue {number}", status="done")
    row["updated"] = updated
    row["category"] = "Enhancement"
    return row


def test_merge_keeps_fresh_done_row():
    prev = [_done_prev_row("1", days_old=5)]
    rows = ub.merge_rows_for_render([], prev)
    assert any(r["number"] == "1" for r in rows)


def test_merge_expires_old_done_row():
    prev = [_done_prev_row("1", days_old=20)]
    rows = ub.merge_rows_for_render([], prev)
    assert not any(r["number"] == "1" for r in rows)


def test_merge_closed_at_overrides_updated_field():
    from datetime import date, timedelta

    # updated says old, but closed_at says recent → should keep
    prev = [_done_prev_row("1", days_old=20)]
    recent = (date.today() - timedelta(days=3)).isoformat()
    rows = ub.merge_rows_for_render([], prev, closed_at={"1": recent})
    assert any(r["number"] == "1" for r in rows)


# ---------------------------------------------------------------------------
# closed_at snapshot tracking and pruning via main()
# ---------------------------------------------------------------------------


def test_initial_update_creates_empty_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    snapshot_path = tmp_path / "last_snapshot.json"

    monkeypatch.setattr(ub, "fetch_collaborators", lambda repo: set())
    monkeypatch.setattr(ub, "fetch_open_issues", lambda repo: [])
    monkeypatch.setattr(ub, "fetch_open_prs", lambda repo: [])
    monkeypatch.setattr(ub, "detect_target_root", lambda *a, **kw: tmp_path)

    with patch.object(ub, "resolve_repo", return_value="o/r"):
        sys.argv = [
            "backlog-atlas",
            "update",
            "--snapshot-path",
            str(snapshot_path),
        ]
        ub.main()

    assert not (tmp_path / "BACKLOG.md").exists()
    assert not (tmp_path / "BACKLOG-UPDATES.md").exists()
    assert (tmp_path / ".backlog-atlas" / "backlog.json").exists()
    assert (tmp_path / ".backlog-atlas" / "updates.jsonl").read_text(
        encoding="utf-8"
    ) == ""


def test_dry_run_does_not_write_updates_jsonl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    updates_jsonl = tmp_path / "updates.jsonl"
    snapshot_path = tmp_path / "last_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "repo": "o/r",
                "generated_at": "2024-01-01T00:00:00Z",
                "issues": {
                    "1": {
                        "title": "Issue 1",
                        "status": "not started",
                        "labels": [],
                        "category": "Enhancement",
                        "pr_numbers": [],
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ub, "fetch_collaborators", lambda repo: set())
    monkeypatch.setattr(ub, "fetch_open_issues", lambda repo: [])
    monkeypatch.setattr(ub, "fetch_open_prs", lambda repo: [])
    monkeypatch.setattr(ub, "detect_target_root", lambda *a, **kw: tmp_path)

    with patch.object(ub, "resolve_repo", return_value="o/r"):
        sys.argv = [
            "backlog-atlas",
            "update",
            "--dry-run",
            "--snapshot-path",
            str(snapshot_path),
            "--updates-jsonl-path",
            str(updates_jsonl),
        ]
        ub.main()

    assert not updates_jsonl.exists()
    assert "Config: packaged defaults" in capsys.readouterr().out


def test_update_uses_checkout_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = tmp_path / ".github" / "backlog-atlas" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "categories:\n" "  Custom:\n" "    labels: [custom]\n" "    keywords: []\n",
        encoding="utf-8",
    )
    data_json = tmp_path / "backlog.json"
    snapshot_path = tmp_path / "last_snapshot.json"
    updates_jsonl = tmp_path / "updates.jsonl"

    monkeypatch.setattr(ub, "fetch_collaborators", lambda repo: set())
    monkeypatch.setattr(
        ub,
        "fetch_open_issues",
        lambda repo: [
            {
                "number": 1,
                "title": "Custom issue",
                "body": "",
                "labels": [{"name": "custom"}],
                "state": "OPEN",
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-01T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(ub, "fetch_open_prs", lambda repo: [])
    monkeypatch.setattr(ub, "detect_target_root", lambda *a, **kw: tmp_path)

    with patch.object(ub, "resolve_repo", return_value="o/r"):
        sys.argv = [
            "backlog-atlas",
            "update",
            "--snapshot-path",
            str(snapshot_path),
            "--data-json-path",
            str(data_json),
            "--updates-jsonl-path",
            str(updates_jsonl),
        ]
        assert ub.main() == 0

    data = json.loads(data_json.read_text(encoding="utf-8"))
    assert {"category": "Custom", "emoji": "", "count": 1, "percentage": 100.0} in data[
        "summary"
    ]["by_category"]
    assert data["issues"][0]["category"] == "Custom"


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------


def test_classify_checkout_uses_local_config_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    config = tmp_path / ".github" / "backlog-atlas" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "categories:\n" "  Custom:\n" "    labels: [custom]\n" "    keywords: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ub, "detect_target_root", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(ub, "resolve_repo", lambda explicit, cwd=None: "o/r")
    monkeypatch.setattr(
        ub,
        "fetch_issue",
        lambda repo, number: {
            "number": number,
            "title": "Custom classification",
            "labels": [{"name": "custom"}],
        },
    )

    sys.argv = ["backlog-atlas", "classify", "123"]

    rc = ub.main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "Mode: checkout" in out
    assert "Repo: o/r" in out
    assert "Config: .github/backlog-atlas/config.yaml" in out
    assert "Issue: #123 Custom classification" in out
    assert "Category: Custom" in out
    assert 'Reason: label "custom" matched categories.Custom.labels' in out


def test_classify_remote_uses_remote_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(install_github, "github_default_branch", lambda repo: "main")
    monkeypatch.setattr(
        install_github,
        "remote_config_text",
        lambda repo, branch: (
            "categories:\n" "  Remote:\n" "    labels: [remote]\n" "    keywords: []\n"
        ),
    )
    monkeypatch.setattr(
        ub,
        "fetch_issue",
        lambda repo, number: {
            "number": number,
            "title": "Remote classification",
            "labels": [{"name": "remote"}],
        },
    )

    sys.argv = [
        "backlog-atlas",
        "classify",
        "#123",
        "--repo",
        "https://github.com/o/r",
    ]

    rc = ub.main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "Mode: remote" in out
    assert "Repo: o/r" in out
    assert (
        "Config: https://github.com/o/r@main:.github/backlog-atlas/config.yaml" in out
    )
    assert "Category: Remote" in out


def test_classify_remote_rejects_missing_remote_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(install_github, "github_default_branch", lambda repo: "main")
    monkeypatch.setattr(install_github, "remote_config_text", lambda repo, branch: None)
    monkeypatch.setattr(
        ub,
        "fetch_issue",
        lambda repo, number: pytest.fail("should not fetch issue without config"),
    )

    sys.argv = [
        "backlog-atlas",
        "classify",
        "123",
        "--repo",
        "https://github.com/o/r",
    ]

    rc = ub.main()

    assert rc == 1
    err = capsys.readouterr().err
    assert "remote Backlog Atlas config was not found" in err
    assert "Remote classification uses the config committed" in err


# ---------------------------------------------------------------------------
# install / uninstall
# ---------------------------------------------------------------------------


def _stub_local_install(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    calls: list[tuple[Any, ...]] = []

    def fake_clean(target_root: Path, vcs: str) -> bool:
        calls.append(("clean", target_root, vcs))
        return True

    def fake_add(target_root: Path, artifact_paths: list[Path], vcs: str) -> None:
        calls.append(("add", target_root, artifact_paths, vcs))

    def fake_commit(
        target_root: Path, artifact_paths: list[Path], vcs: str, message: str
    ) -> None:
        calls.append(("commit", target_root, artifact_paths, vcs, message))

    monkeypatch.setattr(install_repo, "detect_local_vcs", lambda target_root: "git")
    monkeypatch.setattr(install_repo, "detect_repo_from_sl", lambda cwd=None: "o/r")
    monkeypatch.setattr(install_repo, "detect_repo_from_git", lambda cwd=None: None)
    monkeypatch.setattr(install_local, "ensure_worktree_clean", fake_clean)
    monkeypatch.setattr(install_local, "add_local_install_files", fake_add)
    monkeypatch.setattr(install_local, "commit_local_files", fake_commit)
    monkeypatch.setattr(
        install_repo, "is_on_default_branch", lambda target_root, vcs: None
    )
    _stub_installed_pypi(monkeypatch)
    return calls


def _stub_installed_pypi(
    monkeypatch: pytest.MonkeyPatch, version: str = "1.2.3"
) -> None:
    monkeypatch.setattr(install_sources, "installed_local_source_root", lambda: None)
    monkeypatch.setattr(install_sources, "installed_version", lambda: version)


def _make_backlog_atlas_checkout(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "pyproject.toml").write_text(
        "[project]\nname = 'backlog-atlas'\nversion = '2.3.4'\n",
        encoding="utf-8",
    )
    return source_root


def test_workflow_template_substitutes_install_source():
    out = install_artifacts.load_workflow_template("git+https://example.com/x.git")
    assert "__BACKLOG_ATLAS_PIP__" not in out
    assert "BACKLOG_ATLAS_PIP: git+https://example.com/x.git" in out
    assert "BACKLOG_ATLAS_BRANCH: backlog-atlas" in out
    assert 'pip install "$BACKLOG_ATLAS_PIP"' in out
    assert "backlog-atlas update" in out
    assert "backlog-atlas dump-web" in out
    assert "backlog-atlas dump-atlas" in out
    assert "ensure-backlog-branch:" in out
    assert "needs: ensure-backlog-branch" in out
    assert ".backlog-atlas/.keep" in out
    assert "git rm --ignore-unmatch BACKLOG.md BACKLOG-UPDATES.md" in out
    assert "git add BACKLOG.md" not in out
    assert "git rm --ignore-unmatch atlas.json" in out
    assert "cp BACKLOG.md" not in out
    assert "Seed backlog files for tool" not in out
    assert "log-event:" not in out
    assert "events.jsonl" not in out
    assert "--event-log-path" not in out
    assert 'git push "$remote_url" HEAD:"$BACKLOG_ATLAS_BRANCH"' in out
    assert "ref: ${{ env.BACKLOG_ATLAS_BRANCH }}" in out
    assert "ref: ${{ github.event.repository.default_branch }}" in out
    assert "ref: main" not in out
    assert 'origin "$BACKLOG_ATLAS_BRANCH"' in out
    assert "backlog-atlas-branch" in out
    assert "path: backlog-branch" not in out
    assert "cd backlog-branch" not in out
    assert "origin backlog\n" not in out
    # GitHub Actions ${{ }} expressions must be preserved verbatim.
    assert "${{ github.event_name }}" in out
    assert "${{ github.event.action }}" in out


def test_web_ui_supports_browser_federated_manifest():
    content = (
        Path(__file__).resolve().parent.parent / "backlog_atlas" / "web" / "index.html"
    ).read_text(encoding="utf-8")

    assert 'fetch("atlas.json")' in content
    assert "manifestResponse.status === 404" in content
    assert "Could not load Backlog Atlas data" in content
    assert "atlas.json must include at least one repo entry" in content
    assert "Falling back to backlog.json after atlas.json load failed" not in content
    assert "backlog_url" in content
    assert 'id="repo-pills"' in content
    assert 'data-key="repo"' in content
    assert "loadBacklogData" in content


def test_dump_atlas_resolves_yaml_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    config = tmp_path / "atlas.yaml"
    config.write_text(
        "\n".join(
            [
                "title: ${project} Backlog",
                "project: OmegaConf + Hydra",
                "base_url: https://example.com/backlogs",
                "repos:",
                "  - repo: omry/omegaconf",
                "    backlog_url: ${base_url}/omegaconf/backlog.json",
                "  - repo: facebookresearch/hydra",
                "    url: ${base_url}/hydra/backlog.json",
                "",
            ]
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "site"
    sys.argv = [
        "backlog-atlas",
        "dump-atlas",
        "--config",
        str(config),
        "--output",
        str(out_dir),
    ]

    assert ub.main() == 0

    assert json.loads((out_dir / "atlas.json").read_text(encoding="utf-8")) == {
        "repos": [
            {
                "repo": "omry/omegaconf",
                "backlog_url": "https://example.com/backlogs/omegaconf/backlog.json",
            },
            {
                "repo": "facebookresearch/hydra",
                "backlog_url": "https://example.com/backlogs/hydra/backlog.json",
            },
        ],
        "title": "OmegaConf + Hydra Backlog",
    }
    assert (
        f"Wrote atlas manifest to {out_dir / 'atlas.json'}" in capsys.readouterr().out
    )


def test_dump_atlas_rejects_invalid_yaml_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    config = tmp_path / "atlas.yaml"
    config.write_text("repos: []\n", encoding="utf-8")
    sys.argv = [
        "backlog-atlas",
        "dump-atlas",
        "--config",
        str(config),
        "--output",
        str(tmp_path / "site"),
    ]

    assert ub.main() == 1

    err = capsys.readouterr().err
    assert "Backlog Atlas multi-repo config is invalid" in err
    assert "`repos` must contain at least one repo entry" in err


def test_atlas_cli_add_list_and_remove_repos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(
        install_github, "verify_backlog_atlas_installed", lambda repo: "main"
    )
    config = tmp_path / "atlas.yaml"

    sys.argv = [
        "backlog-atlas",
        "atlas",
        "add",
        "https://github.com/omry/omegaconf",
        "--config",
        str(config),
    ]
    assert ub.main() == 0

    sys.argv = [
        "backlog-atlas",
        "atlas",
        "add",
        "facebookresearch/hydra",
        "--backlog-url",
        "https://example.com/hydra/backlog.json",
        "--config",
        str(config),
    ]
    assert ub.main() == 0

    assert ub.load_atlas_manifest_config(config) == {
        "repos": [
            {
                "repo": "omry/omegaconf",
                "backlog_url": "https://omry.github.io/omegaconf/backlog.json",
            },
            {
                "repo": "facebookresearch/hydra",
                "backlog_url": "https://example.com/hydra/backlog.json",
            },
        ]
    }

    sys.argv = [
        "backlog-atlas",
        "atlas",
        "list",
        "--config",
        str(config),
    ]
    assert ub.main() == 0
    out = capsys.readouterr().out
    assert "omry/omegaconf" in out
    assert "facebookresearch/hydra" in out

    sys.argv = [
        "backlog-atlas",
        "atlas",
        "remove",
        "omry/omegaconf",
        "--config",
        str(config),
    ]
    assert ub.main() == 0
    assert ub.load_atlas_manifest_config(config) == {
        "repos": [
            {
                "repo": "facebookresearch/hydra",
                "backlog_url": "https://example.com/hydra/backlog.json",
            }
        ]
    }

    sys.argv = [
        "backlog-atlas",
        "atlas",
        "remove",
        "facebookresearch/hydra",
        "--config",
        str(config),
    ]
    assert ub.main() == 0
    assert not config.exists()


def test_atlas_cli_rejects_duplicate_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    calls = []

    def fake_verify(repo: str) -> str:
        calls.append(repo)
        return "main"

    monkeypatch.setattr(install_github, "verify_backlog_atlas_installed", fake_verify)
    config = tmp_path / "atlas.yaml"
    sys.argv = [
        "backlog-atlas",
        "atlas",
        "add",
        "omry/omegaconf",
        "--config",
        str(config),
    ]
    assert ub.main() == 0

    sys.argv = [
        "backlog-atlas",
        "atlas",
        "add",
        "https://github.com/omry/omegaconf",
        "--config",
        str(config),
    ]
    assert ub.main() == 1

    assert "omry/omegaconf is already tracked" in capsys.readouterr().err
    assert calls == ["omry/omegaconf"]


def test_atlas_cli_add_validates_full_github_url_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls = []

    def fake_verify(repo: str) -> str:
        calls.append(repo)
        return "main"

    monkeypatch.setattr(install_github, "verify_backlog_atlas_installed", fake_verify)
    config = tmp_path / "atlas.yaml"
    sys.argv = [
        "backlog-atlas",
        "atlas",
        "add",
        "https://github.com/omry/omegaconf.git",
        "--config",
        str(config),
    ]

    assert ub.main() == 0

    assert calls == ["omry/omegaconf"]


def test_atlas_cli_add_rejects_repo_without_backlog_atlas_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    config = tmp_path / "atlas.yaml"

    def fail_verify(repo: str) -> str:
        raise install_github.UserError(
            f"{repo} does not appear to have Backlog Atlas installed"
        )

    monkeypatch.setattr(install_github, "verify_backlog_atlas_installed", fail_verify)
    sys.argv = [
        "backlog-atlas",
        "atlas",
        "add",
        "omry/omegaconf",
        "--config",
        str(config),
    ]

    assert ub.main() == 1

    assert not config.exists()
    assert "does not appear to have Backlog Atlas installed" in capsys.readouterr().err


def test_verify_backlog_atlas_installed_checks_repo_and_manifest(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run_gh(args: list[str], input_text: str | None = None) -> str:
        assert input_text is None
        assert args == ["api", "repos/o/r"]
        return json.dumps({"default_branch": "develop"})

    monkeypatch.setattr(install_github, "run_gh", fake_run_gh)
    monkeypatch.setattr(
        install_github,
        "github_file_text",
        lambda repo, branch, path: json.dumps({"tool": "backlog-atlas", "files": []}),
    )

    assert install_github.verify_backlog_atlas_installed("o/r") == "develop"


def test_verify_backlog_atlas_installed_rejects_missing_repo(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run_gh(args: list[str], input_text: str | None = None) -> str:
        raise install_github.UserError(
            "gh api repos/o/missing failed: gh: Not Found (HTTP 404)"
        )

    monkeypatch.setattr(install_github, "run_gh", fake_run_gh)

    with pytest.raises(install_github.UserError) as exc:
        install_github.verify_backlog_atlas_installed("o/missing")

    assert "GitHub could not find o/missing" in str(exc.value)


def test_verify_backlog_atlas_installed_rejects_missing_install_manifest(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        install_github,
        "run_gh",
        lambda args, input_text=None: json.dumps({"default_branch": "main"}),
    )
    monkeypatch.setattr(
        install_github,
        "github_file_text",
        lambda repo, branch, path: None,
    )

    with pytest.raises(install_github.UserError) as exc:
        install_github.verify_backlog_atlas_installed("o/r")

    message = str(exc.value)
    assert "does not appear to have Backlog Atlas installed" in message
    assert "https://github.com/o/r@main:.github/backlog-atlas/manifest.json" in message


def test_install_help_prefers_repository_url(capsys: pytest.CaptureFixture[str]):
    sys.argv = ["backlog-atlas", "install", "--help"]

    with pytest.raises(SystemExit) as exc:
        ub.main()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    normalized = " ".join(out.split())
    assert "Repository URL" in normalized
    assert "owner/name is accepted as GitHub shorthand" in normalized
    assert "Installs remotely" in normalized
    assert "cannot be combined with --target-root" in normalized
    assert "Target working tree root for local install" in normalized
    assert "Cannot be combined with --repo" in normalized
    assert "proceed even when the target working tree is dirty" in normalized
    assert "GitHub repo owner/name" not in normalized


def test_install_rejects_repo_with_target_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "https://github.com/o/r",
        "--target-root",
        str(tmp_path),
    ]

    rc = ub.main()

    assert rc == 1
    err = capsys.readouterr().err
    assert "--repo and --target-root are mutually exclusive" in err
    assert "use --repo for remote install" in err
    assert "--target-root for local checkout install" in err


def test_install_rejects_unsupported_repo_value(
    capsys: pytest.CaptureFixture[str],
):
    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "https://example.com/o/r",
    ]

    rc = ub.main()

    assert rc == 1
    err = capsys.readouterr().err
    assert "unsupported --repo value" in err
    assert "https://github.com/owner/name" in err
    assert "owner/name" in err


def test_install_writes_workflow_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls = _stub_local_install(monkeypatch)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
        "--install-from",
        "backlog-atlas==2.0.0",
    ]
    rc = ub.main()
    assert rc == 0
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    manifest = tmp_path / ".github" / "backlog-atlas" / "manifest.json"
    config = tmp_path / ".github" / "backlog-atlas" / "config.yaml"
    assert wf.exists()
    assert manifest.exists()
    assert config.exists()
    content = wf.read_text(encoding="utf-8")
    assert "BACKLOG_ATLAS_PIP: backlog-atlas==2.0.0" in content
    assert "${{ github.event_name }}" in content
    manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_obj["tool"] == "backlog-atlas"
    assert manifest_obj["install"] == {
        "installed_version": "2.0.0",
        "install_source": "backlog-atlas==2.0.0",
        "source_type": "pypi",
        "workflow_path": ".github/workflows/update-backlog-atlas.yml",
    }
    assert {entry["path"]: entry["remove"] for entry in manifest_obj["files"]} == {
        ".github/workflows/update-backlog-atlas.yml": "uninstall",
        ".github/backlog-atlas/manifest.json": "uninstall",
        ".github/backlog-atlas/config.yaml": "clean",
        ".github/backlog-atlas/atlas.yaml": "clean",
    }
    assert calls == [
        ("clean", tmp_path, "git"),
        ("add", tmp_path, [wf, manifest, config], "git"),
        (
            "commit",
            tmp_path,
            [wf, manifest, config],
            "git",
            "backlog: install Backlog Atlas 2.0.0 workflow",
        ),
    ]


def test_install_defaults_to_pypi_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _stub_local_install(monkeypatch)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
    ]
    rc = ub.main()
    assert rc == 0
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    manifest = tmp_path / ".github" / "backlog-atlas" / "manifest.json"
    config = tmp_path / ".github" / "backlog-atlas" / "config.yaml"
    assert "BACKLOG_ATLAS_PIP: backlog-atlas==1.2.3" in wf.read_text(encoding="utf-8")
    assert config.exists()
    manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_obj["install"]["install_source"] == "backlog-atlas==1.2.3"
    assert manifest_obj["install"]["installed_version"] == "1.2.3"
    assert manifest_obj["install"]["source_type"] == "pypi"


def test_install_leaves_unmatched_existing_workflow_and_metadata_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    metadata = tmp_path / ".github" / "backlog-atlas.json"
    manifest = tmp_path / ".github" / "backlog-atlas" / "manifest.json"
    config = tmp_path / ".github" / "backlog-atlas" / "config.yaml"
    wf.parent.mkdir(parents=True)
    wf.write_text("# preexisting\n", encoding="utf-8")
    calls = _stub_local_install(monkeypatch)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
    ]
    rc = ub.main()
    assert rc == 0
    # Existing workflow not overwritten
    assert wf.read_text(encoding="utf-8") == "# preexisting\n"
    assert not metadata.exists()
    assert not manifest.exists()
    assert not config.exists()
    assert calls == [("clean", tmp_path, "git")]


def test_install_local_bundled_source_does_not_upload_when_workflow_blocks_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text("# preexisting\n", encoding="utf-8")
    monkeypatch.setattr(install_repo, "detect_local_vcs", lambda target_root: "git")
    monkeypatch.setattr(
        install_local,
        "ensure_worktree_clean",
        lambda target_root, vcs: True,
    )
    monkeypatch.setattr(
        install_github,
        "ensure_backlog_branch_with_bundle",
        lambda repo, source: pytest.fail("should not upload bundled wheel"),
    )

    rc = install_local.run_local_install(
        "o/r",
        tmp_path,
        InstallSource(
            pip_spec="backlog-atlas-branch/.backlog-atlas/packages/current.whl",
            version="2.0.0",
            source_type="bundled-wheel",
            bundled_wheel_path=".backlog-atlas/packages/current.whl",
            bundled_wheel_content=b"wheel bytes",
        ),
    )

    assert rc == 0
    assert wf.read_text(encoding="utf-8") == "# preexisting\n"
    assert not (tmp_path / ".github" / "backlog-atlas.json").exists()
    assert not (tmp_path / ".github" / "backlog-atlas" / "manifest.json").exists()


def test_install_cleanup_preserves_unmanaged_metadata_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    metadata = tmp_path / ".github" / "backlog-atlas.json"
    manifest = tmp_path / ".github" / "backlog-atlas" / "manifest.json"
    wf.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)
    wf.write_text("# preexisting\n", encoding="utf-8")
    metadata.write_text('{"tool": "someone-else"}\n', encoding="utf-8")
    manifest.write_text('{"tool": "someone-else"}\n', encoding="utf-8")
    calls = _stub_local_install(monkeypatch)

    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
    ]

    rc = ub.main()

    assert rc == 0
    assert wf.read_text(encoding="utf-8") == "# preexisting\n"
    assert metadata.read_text(encoding="utf-8") == '{"tool": "someone-else"}\n'
    assert manifest.read_text(encoding="utf-8") == '{"tool": "someone-else"}\n'
    assert calls == [("clean", tmp_path, "git")]


def test_install_rejects_invalid_existing_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    config = tmp_path / ".github" / "backlog-atlas" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("done_expire_days: not-a-number\n", encoding="utf-8")
    calls = _stub_local_install(monkeypatch)

    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
    ]

    rc = ub.main()

    assert rc == 1
    err = capsys.readouterr().err
    assert "existing Backlog Atlas config is invalid" in err
    assert str(config) in err
    assert calls == []
    assert not (tmp_path / ".github" / "workflows").exists()


def test_install_writes_manifest_when_existing_workflow_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    manifest = tmp_path / ".github" / "backlog-atlas" / "manifest.json"
    config = tmp_path / ".github" / "backlog-atlas" / "config.yaml"
    wf.parent.mkdir(parents=True)
    wf.write_text(
        install_artifacts.load_workflow_template("backlog-atlas==1.2.3"),
        encoding="utf-8",
    )
    calls = _stub_local_install(monkeypatch)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
    ]
    rc = ub.main()
    assert rc == 0
    assert manifest.exists()
    assert config.exists()
    assert calls == [
        ("clean", tmp_path, "git"),
        ("add", tmp_path, [wf, manifest, config], "git"),
        (
            "commit",
            tmp_path,
            [wf, manifest, config],
            "git",
            "backlog: install Backlog Atlas 1.2.3 workflow",
        ),
    ]


def test_install_force_reinstalls_when_already_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    metadata = tmp_path / ".github" / "backlog-atlas.json"
    manifest = tmp_path / ".github" / "backlog-atlas" / "manifest.json"
    config = tmp_path / ".github" / "backlog-atlas" / "config.yaml"
    wf.parent.mkdir(parents=True)
    wf.write_text(
        install_artifacts.load_workflow_template("backlog-atlas==1.2.3"),
        encoding="utf-8",
    )
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text('{"tool": "backlog-atlas"}\n', encoding="utf-8")
    calls = _stub_local_install(monkeypatch)

    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
        "--force",
    ]

    rc = ub.main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "Skipping working tree cleanliness check" in out
    assert "Nothing to do" not in out
    assert f"wrote workflow to {wf}" in out
    assert f"wrote install manifest to {manifest}" in out
    assert f"wrote editable config to {config}" in out
    assert not metadata.exists()
    assert calls == [
        ("add", tmp_path, [wf, manifest, config, metadata], "git"),
        (
            "commit",
            tmp_path,
            [wf, manifest, config, metadata],
            "git",
            "backlog: install Backlog Atlas 1.2.3 workflow",
        ),
    ]


def test_install_removes_previous_install_artifacts_before_reinstalling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    metadata = tmp_path / ".github" / "backlog-atlas.json"
    old_manifest = tmp_path / ".github" / "backlog-atlas" / "manifest.json"
    app_config = tmp_path / ".github" / "backlog-atlas" / "config.yaml"
    wf.parent.mkdir(parents=True)
    old_manifest.parent.mkdir(parents=True)
    wf.write_text(
        install_artifacts.load_workflow_template("backlog-atlas==0.9.0"),
        encoding="utf-8",
    )
    metadata.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tool": "backlog-atlas",
                "source_type": "bundled-wheel",
                "bundled_wheel_path": ".backlog-atlas/packages/old.whl",
            }
        ),
        encoding="utf-8",
    )
    old_manifest.write_text(
        json.dumps({"tool": "backlog-atlas", "schema_version": 1}),
        encoding="utf-8",
    )
    app_config.write_text("done_expire_days: 30\n", encoding="utf-8")
    calls = _stub_local_install(monkeypatch)

    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
    ]

    rc = ub.main()

    assert rc == 0
    assert wf.exists()
    assert not metadata.exists()
    manifest_obj = json.loads(old_manifest.read_text(encoding="utf-8"))
    assert manifest_obj["tool"] == "backlog-atlas"
    assert manifest_obj["files"]
    assert app_config.exists()
    assert app_config.read_text(encoding="utf-8") == "done_expire_days: 30\n"
    assert calls == [
        ("clean", tmp_path, "git"),
        ("add", tmp_path, [wf, old_manifest, metadata], "git"),
        (
            "commit",
            tmp_path,
            [wf, old_manifest, metadata],
            "git",
            "backlog: install Backlog Atlas 1.2.3 workflow",
        ),
    ]


def test_install_pypi_upgrade_from_bundled_wheel_writes_cleanup_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    metadata = tmp_path / ".github" / "backlog-atlas.json"
    cleanup_wf = (
        tmp_path
        / ".github"
        / "workflows"
        / "temporary-backlog-atlas-upgrade-cleanup.yml"
    )
    wf.parent.mkdir(parents=True)
    wf.write_text(
        install_artifacts.load_workflow_template(
            "backlog-atlas-branch/.backlog-atlas/packages/old.whl"
        ),
        encoding="utf-8",
    )
    metadata.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tool": "backlog-atlas",
                "source_type": "bundled-wheel",
                "bundled_wheel_path": ".backlog-atlas/packages/old.whl",
            }
        ),
        encoding="utf-8",
    )
    old_manifest = tmp_path / ".github" / "backlog-atlas" / "manifest.json"
    old_manifest.parent.mkdir(parents=True)
    old_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tool": "backlog-atlas",
                "files": [
                    {
                        "path": ".backlog-atlas/packages/old.whl",
                        "branch": "backlog-atlas",
                        "remove": "uninstall",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = _stub_local_install(monkeypatch)

    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
        "--install-from",
        "backlog-atlas==2.0.0",
    ]

    rc = ub.main()

    assert rc == 0
    cleanup_content = cleanup_wf.read_text(encoding="utf-8")
    manifest = tmp_path / ".github" / "backlog-atlas" / "manifest.json"
    config = tmp_path / ".github" / "backlog-atlas" / "config.yaml"
    manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
    assert ".github/workflows/temporary-backlog-atlas-upgrade-cleanup.yml" in {
        entry["path"] for entry in manifest_obj["files"]
    }
    assert not metadata.exists()
    assert "BACKLOG_ATLAS_KEEP_PACKAGE" not in cleanup_content
    assert ".backlog-atlas/packages/old.whl" in cleanup_content
    assert "find .backlog-atlas/packages" not in cleanup_content
    assert config.exists()
    assert calls == [
        ("clean", tmp_path, "git"),
        ("add", tmp_path, [wf, manifest, config, cleanup_wf, metadata], "git"),
        (
            "commit",
            tmp_path,
            [wf, manifest, config, cleanup_wf, metadata],
            "git",
            "backlog: install Backlog Atlas 2.0.0 workflow",
        ),
    ]


def test_remove_install_artifacts_ignores_unsafe_manifest_paths(tmp_path: Path):
    target_root = tmp_path / "repo"
    manifest = target_root / ".github" / "backlog-atlas" / "manifest.json"
    outside = tmp_path / "outside.txt"
    absolute = tmp_path / "absolute.txt"
    unmanaged_workflow = target_root / ".github" / "workflows" / "ci.yml"
    manifest.parent.mkdir(parents=True)
    unmanaged_workflow.parent.mkdir(parents=True)
    outside.write_text("keep\n", encoding="utf-8")
    absolute.write_text("keep\n", encoding="utf-8")
    unmanaged_workflow.write_text("name: CI\n", encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tool": "backlog-atlas",
                "files": [
                    {
                        "path": "../outside.txt",
                        "branch": "default",
                        "remove": "uninstall",
                    },
                    {
                        "path": str(absolute),
                        "branch": "default",
                        "remove": "uninstall",
                    },
                    {
                        "path": ".github/workflows/ci.yml",
                        "branch": "default",
                        "remove": "uninstall",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    removed = install_artifacts.remove_install_artifacts(target_root)

    assert removed == []
    assert outside.exists()
    assert absolute.exists()
    assert unmanaged_workflow.exists()


def test_install_updates_managed_existing_workflow_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    manifest = tmp_path / ".github" / "backlog-atlas" / "manifest.json"
    config = tmp_path / ".github" / "backlog-atlas" / "config.yaml"
    wf.parent.mkdir(parents=True)
    old_workflow = install_artifacts.load_workflow_template(
        "backlog-atlas==1.2.3"
    ).replace("ref: ${{ github.event.repository.default_branch }}", "ref: main")
    wf.write_text(old_workflow, encoding="utf-8")
    calls = _stub_local_install(monkeypatch)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
    ]
    rc = ub.main()
    assert rc == 0
    assert "ref: main" not in wf.read_text(encoding="utf-8")
    assert manifest.exists()
    assert config.exists()
    assert calls == [
        ("clean", tmp_path, "git"),
        ("add", tmp_path, [wf, manifest, config], "git"),
        (
            "commit",
            tmp_path,
            [wf, manifest, config],
            "git",
            "backlog: install Backlog Atlas 1.2.3 workflow",
        ),
    ]


def test_install_local_checkout_detects_repo_and_adds_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls = _stub_local_install(monkeypatch)
    monkeypatch.setattr(install_repo, "detect_target_root", lambda: tmp_path)
    monkeypatch.setattr(install_repo, "detect_repo_from_sl", lambda cwd=None: "o/r")
    monkeypatch.setattr(install_repo, "detect_repo_from_git", lambda cwd=None: None)
    sys.argv = ["backlog-atlas", "install"]
    rc = ub.main()
    assert rc == 0
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    manifest = tmp_path / ".github" / "backlog-atlas" / "manifest.json"
    config = tmp_path / ".github" / "backlog-atlas" / "config.yaml"
    assert wf.exists()
    assert manifest.exists()
    assert config.exists()
    assert calls == [
        ("clean", tmp_path, "git"),
        ("add", tmp_path, [wf, manifest, config], "git"),
        (
            "commit",
            tmp_path,
            [wf, manifest, config],
            "git",
            "backlog: install Backlog Atlas 1.2.3 workflow",
        ),
    ]


def test_install_dirty_worktree_returns_error_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(install_repo, "detect_local_vcs", lambda target_root: "git")
    monkeypatch.setattr(
        install_local,
        "run_command",
        lambda args, cwd=None: " M existing.py\n",
    )
    monkeypatch.setattr(
        install_github,
        "ensure_backlog_branch_with_bundle",
        lambda repo, install_source: pytest.fail("should not touch GitHub"),
    )

    rc = install_local.run_local_install(
        "o/r",
        tmp_path,
        InstallSource(
            pip_spec="backlog-atlas==1.2.3",
            version="1.2.3",
            source_type="pypi",
        ),
    )

    assert rc == 1
    assert "has uncommitted changes" in capsys.readouterr().err
    assert not (tmp_path / ".github").exists()


def test_install_force_skips_dirty_worktree_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(install_repo, "detect_local_vcs", lambda target_root: "git")
    monkeypatch.setattr(install_repo, "detect_repo_from_sl", lambda cwd=None: "o/r")
    monkeypatch.setattr(install_repo, "detect_repo_from_git", lambda cwd=None: None)
    _stub_installed_pypi(monkeypatch)
    monkeypatch.setattr(
        install_local,
        "ensure_worktree_clean",
        lambda target_root, vcs: pytest.fail("should not check worktree cleanliness"),
    )
    monkeypatch.setattr(
        install_repo, "is_on_default_branch", lambda target_root, vcs: None
    )
    add_calls: list[tuple[Path, list[Path], str]] = []
    commit_calls: list[tuple[Path, list[Path], str, str]] = []
    monkeypatch.setattr(
        install_local,
        "add_local_install_files",
        lambda target_root, artifact_paths, vcs: add_calls.append(
            (target_root, artifact_paths, vcs)
        ),
    )
    monkeypatch.setattr(
        install_local,
        "commit_local_files",
        lambda target_root, artifact_paths, vcs, message: commit_calls.append(
            (target_root, artifact_paths, vcs, message)
        ),
    )

    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
        "--force",
    ]

    rc = ub.main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "Skipping working tree cleanliness check" in out
    assert (tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml").exists()
    assert (tmp_path / ".github" / "backlog-atlas" / "manifest.json").exists()
    assert add_calls
    assert commit_calls


def test_install_local_bundled_upload_failure_leaves_checkout_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    metadata = tmp_path / ".github" / "backlog-atlas.json"
    old_manifest = tmp_path / ".github" / "backlog-atlas" / "manifest.json"
    cleanup_wf = (
        tmp_path
        / ".github"
        / "workflows"
        / "temporary-backlog-atlas-upgrade-cleanup.yml"
    )
    wf.parent.mkdir(parents=True)
    old_manifest.parent.mkdir(parents=True)
    old_workflow_content = install_artifacts.load_workflow_template(
        "backlog-atlas==0.9.0"
    )
    old_metadata_content = json.dumps({"tool": "backlog-atlas"}) + "\n"
    old_manifest_content = json.dumps({"tool": "backlog-atlas"}) + "\n"
    wf.write_text(old_workflow_content, encoding="utf-8")
    metadata.write_text(old_metadata_content, encoding="utf-8")
    old_manifest.write_text(old_manifest_content, encoding="utf-8")
    monkeypatch.setattr(install_repo, "detect_local_vcs", lambda target_root: "git")
    monkeypatch.setattr(
        install_local,
        "ensure_worktree_clean",
        lambda target_root, vcs: True,
    )
    monkeypatch.setattr(
        install_local,
        "add_local_install_files",
        lambda *args: pytest.fail("should not add files"),
    )
    monkeypatch.setattr(
        install_local,
        "commit_local_files",
        lambda *args: pytest.fail("should not commit files"),
    )

    def fail_bundle(repo: str, install_source: InstallSource) -> None:
        raise install_github.UserError("bundle failed")

    monkeypatch.setattr(
        install_github,
        "ensure_backlog_branch_with_bundle",
        fail_bundle,
    )

    with pytest.raises(install_github.UserError):
        install_local.run_local_install(
            "o/r",
            tmp_path,
            InstallSource(
                pip_spec="backlog-atlas-branch/.backlog-atlas/packages/new.whl",
                version="2.0.0",
                source_type="bundled-wheel",
                bundled_wheel_path=".backlog-atlas/packages/new.whl",
                bundled_wheel_content=b"wheel bytes",
            ),
        )

    assert wf.read_text(encoding="utf-8") == old_workflow_content
    assert metadata.read_text(encoding="utf-8") == old_metadata_content
    assert old_manifest.read_text(encoding="utf-8") == old_manifest_content
    assert not cleanup_wf.exists()


def test_commit_local_files_scopes_commit_to_artifact_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[tuple[list[str], Path | None]] = []
    paths = [
        tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml",
        tmp_path / ".github" / "backlog-atlas" / "manifest.json",
    ]

    def fake_run_command(args: list[str], cwd: Path | None = None) -> str:
        calls.append((args, cwd))
        return ""

    monkeypatch.setattr(
        install_local,
        "run_command",
        fake_run_command,
    )

    install_local.commit_local_files(tmp_path, paths, "git", "message")
    install_local.commit_local_files(tmp_path, paths, "sl", "message")

    assert calls == [
        (
            [
                "git",
                "commit",
                "-m",
                "message",
                "--only",
                "--",
                ".github/workflows/update-backlog-atlas.yml",
                ".github/backlog-atlas/manifest.json",
            ],
            tmp_path,
        ),
        (
            [
                "sl",
                "commit",
                "-m",
                "message",
                ".github/workflows/update-backlog-atlas.yml",
                ".github/backlog-atlas/manifest.json",
            ],
            tmp_path,
        ),
    ]


def test_install_local_dry_run_prints_plan_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(install_repo, "detect_local_vcs", lambda target_root: "git")
    monkeypatch.setattr(install_repo, "detect_repo_from_sl", lambda cwd=None: "o/r")
    monkeypatch.setattr(install_repo, "detect_repo_from_git", lambda cwd=None: None)
    _stub_installed_pypi(monkeypatch)
    monkeypatch.setattr(
        install_local,
        "ensure_worktree_clean",
        lambda target_root, vcs: pytest.fail("should not check worktree cleanliness"),
    )
    monkeypatch.setattr(
        install_local,
        "add_local_install_files",
        lambda target_root, artifact_paths, vcs: pytest.fail("should not add files"),
    )
    monkeypatch.setattr(
        install_github,
        "ensure_backlog_branch_with_bundle",
        lambda repo, install_source: pytest.fail("should not touch GitHub"),
    )

    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
        "--dry-run",
    ]

    rc = ub.main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "Dry run: would install Backlog Atlas locally" in out
    assert "No files would be written and no GitHub calls would be made." in out
    assert "Target repo: o/r" in out
    assert "Workflow would install Backlog Atlas from: backlog-atlas==1.2.3" in out
    assert str(tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml") in out
    assert str(tmp_path / ".github" / "backlog-atlas" / "manifest.json") in out
    assert not (tmp_path / ".github").exists()


def test_install_local_dry_run_with_force_prints_plan_without_clean_requirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(install_repo, "detect_local_vcs", lambda target_root: "git")
    monkeypatch.setattr(install_repo, "detect_repo_from_sl", lambda cwd=None: "o/r")
    monkeypatch.setattr(install_repo, "detect_repo_from_git", lambda cwd=None: None)
    _stub_installed_pypi(monkeypatch)
    monkeypatch.setattr(
        install_local,
        "ensure_worktree_clean",
        lambda target_root, vcs: pytest.fail("should not check worktree cleanliness"),
    )

    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
        "--dry-run",
        "--force",
    ]

    rc = ub.main()

    assert rc == 0
    out = capsys.readouterr().out
    assert (
        "Would skip the clean working tree requirement because --force was provided."
        in out
    )
    assert "Would require a clean working tree." not in out
    assert not (tmp_path / ".github").exists()


def test_install_local_checkout_rejects_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    _stub_local_install(monkeypatch)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
        "--delivery",
        "push",
    ]
    rc = ub.main()
    assert rc == 1
    assert "--delivery only applies to remote" in capsys.readouterr().err


def test_install_remote_rejects_force(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(
        install_sources,
        "resolve_install_source",
        lambda install_from, dry_run=False: pytest.fail(
            "should reject before resolving install source"
        ),
    )

    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "https://github.com/o/r",
        "--force",
    ]

    rc = ub.main()

    assert rc == 1
    err = capsys.readouterr().err
    assert "--force only applies to local installs" in err


def test_resolve_install_source_from_local_checkout_builds_bundled_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    source_root = _make_backlog_atlas_checkout(tmp_path)
    monkeypatch.setattr(
        install_sources,
        "build_local_wheel",
        lambda path: (
            "backlog_atlas-2.3.4-0.gabc123def456.dirty-py3-none-any.whl",
            b"wheel bytes",
        ),
    )

    source = install_sources.resolve_install_source(str(source_root))

    assert capsys.readouterr().out == ""
    assert source == InstallSource(
        pip_spec=(
            "backlog-atlas-branch/.backlog-atlas/packages/"
            "backlog_atlas-2.3.4-0.gabc123def456.dirty-py3-none-any.whl"
        ),
        version="2.3.4",
        source_type="bundled-wheel",
        bundled_wheel_path=(
            ".backlog-atlas/packages/"
            "backlog_atlas-2.3.4-0.gabc123def456.dirty-py3-none-any.whl"
        ),
        bundled_wheel_content=b"wheel bytes",
    )


def test_build_local_wheel_explains_missing_build_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_root = _make_backlog_atlas_checkout(tmp_path)

    def fake_run_command(args: list[str], cwd: Path | None = None) -> str:
        raise install_sources.UserError(
            f"{args[0]} -m build failed: {args[0]}: No module named build"
        )

    monkeypatch.setattr(install_sources, "run_command", fake_run_command)

    with pytest.raises(install_sources.UserError) as exc:
        install_sources.build_local_wheel(source_root)

    message = str(exc.value)
    assert "installed from a local checkout" in message
    assert "needs to build a bundled wheel" in message
    assert "missing the 'build' package" in message
    assert "-m pip install build" in message


def test_build_local_wheel_storage_name_includes_dirty_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    source_root = _make_backlog_atlas_checkout(tmp_path)

    def fake_try_command(args: list[str], cwd: Path | None = None) -> str | None:
        assert cwd == source_root
        if args[:2] == ["git", "rev-parse"]:
            return "abc123def456\n"
        if args[:2] == ["git", "status"]:
            return " M backlog_atlas/core.py\n"
        return None

    def fake_run_command(args: list[str], cwd: Path | None = None) -> str:
        assert cwd == source_root
        out_dir = Path(args[args.index("--outdir") + 1])
        (out_dir / "backlog_atlas-2.3.4-py3-none-any.whl").write_bytes(b"wheel bytes")
        return ""

    monkeypatch.setattr(install_sources, "try_command", fake_try_command)
    monkeypatch.setattr(install_sources, "run_command", fake_run_command)

    wheel_name, wheel_content = install_sources.build_local_wheel(source_root)

    assert wheel_name == ("backlog_atlas-2.3.4-0.gabc123def456.dirty-py3-none-any.whl")
    assert wheel_content == b"wheel bytes"
    assert (
        "Built wheel backlog_atlas-2.3.4-0.gabc123def456.dirty-py3-none-any.whl"
        in capsys.readouterr().out
    )


def test_installed_local_source_root_reads_direct_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_root = tmp_path / "source"
    source_root.mkdir()

    class FakeDistribution:
        def read_text(self, name: str) -> str | None:
            assert name == "direct_url.json"
            return json.dumps(
                {
                    "dir_info": {"editable": True},
                    "url": source_root.as_uri(),
                }
            )

    monkeypatch.setattr(
        install_sources,
        "package_distribution",
        lambda name: FakeDistribution(),
    )

    assert install_sources.installed_local_source_root() == source_root


def test_resolve_install_source_defaults_to_installed_local_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_root = _make_backlog_atlas_checkout(tmp_path)
    monkeypatch.setattr(
        install_sources, "installed_local_source_root", lambda: source_root
    )
    monkeypatch.setattr(
        install_sources,
        "build_local_wheel",
        lambda path: (
            "backlog_atlas-2.3.4-0.gabc123def456.dirty-py3-none-any.whl",
            b"wheel bytes",
        ),
    )

    source = install_sources.resolve_install_source(None)

    assert source == InstallSource(
        pip_spec=(
            "backlog-atlas-branch/.backlog-atlas/packages/"
            "backlog_atlas-2.3.4-0.gabc123def456.dirty-py3-none-any.whl"
        ),
        version="2.3.4",
        source_type="bundled-wheel",
        bundled_wheel_path=(
            ".backlog-atlas/packages/"
            "backlog_atlas-2.3.4-0.gabc123def456.dirty-py3-none-any.whl"
        ),
        bundled_wheel_content=b"wheel bytes",
    )


def test_resolve_install_source_local_source_dry_run_does_not_build_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_root = _make_backlog_atlas_checkout(tmp_path)
    monkeypatch.setattr(
        install_sources, "installed_local_source_root", lambda: source_root
    )
    monkeypatch.setattr(
        install_sources,
        "build_local_wheel",
        lambda path: pytest.fail("should not build wheel for dry run"),
    )

    source = install_sources.resolve_install_source(None, dry_run=True)

    assert source == InstallSource(
        pip_spec="backlog-atlas-branch/.backlog-atlas/packages/<built-wheel>",
        version="2.3.4",
        source_type="bundled-wheel",
        bundled_wheel_path=".backlog-atlas/packages/<built-wheel>",
    )


def test_local_source_dry_run_wheel_name_includes_dirty_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_root = _make_backlog_atlas_checkout(tmp_path)

    def fake_try_command(args: list[str], cwd: Path | None = None) -> str | None:
        assert cwd == source_root
        if args[:2] == ["git", "rev-parse"]:
            return "abc123def456\n"
        if args[:2] == ["git", "status"]:
            return " M backlog_atlas/core.py\n"
        return None

    monkeypatch.setattr(install_sources, "try_command", fake_try_command)
    monkeypatch.setattr(
        install_sources,
        "build_local_wheel",
        lambda path: pytest.fail("should not build wheel for dry run"),
    )

    source = install_sources.resolve_install_source(str(source_root), dry_run=True)

    assert source == InstallSource(
        pip_spec=(
            "backlog-atlas-branch/.backlog-atlas/packages/"
            "backlog_atlas-2.3.4-0.gabc123def456.dirty-py3-none-any.whl"
        ),
        version="2.3.4",
        source_type="bundled-wheel",
        bundled_wheel_path=(
            ".backlog-atlas/packages/"
            "backlog_atlas-2.3.4-0.gabc123def456.dirty-py3-none-any.whl"
        ),
    )


def test_wheel_storage_name_adds_checkout_build_tag():
    assert (
        install_sources.wheel_storage_name(
            "backlog_atlas-0.1.0-py3-none-any.whl", "0.gabc123def456.dirty"
        )
        == "backlog_atlas-0.1.0-0.gabc123def456.dirty-py3-none-any.whl"
    )


def test_checkout_wheel_build_tag_falls_back_to_sapling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_root = _make_backlog_atlas_checkout(tmp_path)

    def fake_try_command(args: list[str], cwd: Path | None = None) -> str | None:
        assert cwd == source_root
        if args[:2] == ["git", "rev-parse"]:
            return None
        if args[:2] == ["sl", "log"]:
            return "b76abe8f192e\n"
        if args[:2] == ["sl", "status"]:
            return ""
        return None

    monkeypatch.setattr(install_sources, "try_command", fake_try_command)

    assert install_sources.checkout_wheel_build_tag(source_root) == "0.gb76abe8f192e"


def test_install_rejects_floating_install_source(
    capsys: pytest.CaptureFixture[str],
):
    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "o/r",
        "--install-from",
        "git+https://example.com/x.git@main",
    ]
    rc = ub.main()
    assert rc == 1
    assert "must be a pinned PyPI spec" in capsys.readouterr().err


def test_install_local_target_bundles_local_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    calls = _stub_local_install(monkeypatch)
    source_root = _make_backlog_atlas_checkout(tmp_path)
    target_root = tmp_path / "target"
    bundle_calls: list[tuple[str, InstallSource]] = []
    monkeypatch.setattr(
        install_sources,
        "build_local_wheel",
        lambda path: (
            "backlog_atlas-2.3.4-0.gabc123def456.dirty-py3-none-any.whl",
            b"wheel bytes",
        ),
    )
    monkeypatch.setattr(
        install_github,
        "ensure_backlog_branch_with_bundle",
        lambda repo, source: bundle_calls.append((repo, source)),
    )
    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(target_root),
        "--install-from",
        str(source_root),
    ]
    rc = ub.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "created install commit" in out
    assert bundle_calls[0][0] == "o/r"
    install_source = bundle_calls[0][1]
    assert install_source.source_type == "bundled-wheel"
    assert install_source.bundled_wheel_content == b"wheel bytes"
    assert install_source.bundled_wheel_path == (
        ".backlog-atlas/packages/"
        "backlog_atlas-2.3.4-0.gabc123def456.dirty-py3-none-any.whl"
    )
    wf = target_root / ".github" / "workflows" / "update-backlog-atlas.yml"
    manifest = target_root / ".github" / "backlog-atlas" / "manifest.json"
    config = target_root / ".github" / "backlog-atlas" / "config.yaml"
    cleanup_wf = (
        target_root
        / ".github"
        / "workflows"
        / "temporary-backlog-atlas-upgrade-cleanup.yml"
    )
    assert not cleanup_wf.exists()
    manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
    assert {
        "path": install_source.bundled_wheel_path,
        "branch": "backlog-atlas",
        "remove": "uninstall",
    } in manifest_obj["files"]
    assert config.exists()
    assert calls == [
        ("clean", target_root, "git"),
        ("add", target_root, [wf, manifest, config], "git"),
        (
            "commit",
            target_root,
            [wf, manifest, config],
            "git",
            "backlog: install Backlog Atlas workflow from "
            "backlog_atlas-2.3.4-0.gabc123def456.dirty-py3-none-any.whl",
        ),
    ]


def test_install_local_checkout_guides_default_branch_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    _stub_local_install(monkeypatch)
    monkeypatch.setattr(
        install_repo, "is_on_default_branch", lambda target_root, vcs: True
    )
    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
    ]
    rc = ub.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert f"Checking working tree at {tmp_path}" in out
    assert "Working tree is clean" in out
    assert "Checked install workflow and manifest" in out
    assert "created install commit" in out
    assert f"cd {tmp_path}" in out
    assert "# Review the install commit." in out
    assert "git show --stat HEAD" in out
    assert "# Push when ready." in out
    assert "git push" in out
    assert "git push -u origin HEAD" not in out
    assert "gh workflow run 'Update Backlog Atlas' --repo o/r" in out
    assert "https://github.com/o/r/settings/pages" in out
    assert "\n# Review the install commit.\n" in out
    assert "\ngit push\n\n# Trigger the first Backlog Atlas run.\n" in out
    assert "\n\n# Enable Pages from the backlog-atlas branch, folder /.\n" in out


def test_install_local_checkout_omits_cd_when_already_in_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    _stub_local_install(monkeypatch)
    monkeypatch.chdir(tmp_path)

    sys.argv = ["backlog-atlas", "install", "--target-root", str(tmp_path)]
    rc = ub.main()

    assert rc == 0
    out = capsys.readouterr().out
    assert f"cd {tmp_path}" not in out
    assert "# Review the install commit." in out


def test_install_local_next_steps_are_colorized_when_forced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(
        install_repo, "is_on_default_branch", lambda target_root, vcs: True
    )

    install_local.print_local_install_next_steps(
        "o/r",
        tmp_path,
        "git",
    )

    out = capsys.readouterr().out
    assert "\033[" in out
    plain = install_commands.strip_ansi(out)
    assert "# Review the install commit." in plain
    assert "git show --stat HEAD" in plain
    assert "# Push when ready." in plain


def test_install_local_checkout_guides_pr_from_non_default_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    _stub_local_install(monkeypatch)
    monkeypatch.setattr(
        install_repo, "is_on_default_branch", lambda target_root, vcs: False
    )
    sys.argv = [
        "backlog-atlas",
        "install",
        "--target-root",
        str(tmp_path),
    ]
    rc = ub.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "created install commit" in out
    assert "git show --stat HEAD" in out
    assert "git push -u origin HEAD" in out
    assert "# Open or merge a PR for this install commit before continuing." in out
    assert "gh workflow run 'Update Backlog Atlas' --repo o/r" in out


def test_install_remote_defaults_to_pr_delivery_for_github_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    captured: dict[str, str] = {}

    def fake_remote_install(
        repo: str, install_source: InstallSource, delivery: str
    ) -> None:
        captured.update(
            {
                "repo": repo,
                "install_from": install_source.pip_spec,
                "version": install_source.version,
                "source_type": install_source.source_type,
                "delivery": delivery,
            }
        )

    _stub_installed_pypi(monkeypatch)
    monkeypatch.setattr(install_github, "install_remote_workflow", fake_remote_install)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "https://github.com/o/r.git",
        "--install-from",
        "backlog-atlas==2.0.0",
    ]
    rc = ub.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "opened or updated Backlog Atlas install PR for o/r" in out
    assert "installs Backlog Atlas 2.0.0 from backlog-atlas==2.0.0" in out
    assert captured == {
        "repo": "o/r",
        "install_from": "backlog-atlas==2.0.0",
        "version": "2.0.0",
        "source_type": "pypi",
        "delivery": "pr",
    }


def test_install_remote_supports_push_delivery_for_ssh_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    captured: dict[str, str] = {}

    def fake_remote_install(
        repo: str, install_source: InstallSource, delivery: str
    ) -> None:
        captured.update(
            {
                "repo": repo,
                "install_from": install_source.pip_spec,
                "version": install_source.version,
                "source_type": install_source.source_type,
                "delivery": delivery,
            }
        )

    _stub_installed_pypi(monkeypatch)
    monkeypatch.setattr(install_github, "install_remote_workflow", fake_remote_install)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "git@github.com:o/r.git",
        "--delivery",
        "push",
    ]
    rc = ub.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "pushed Backlog Atlas workflow to o/r" in out
    assert "installs Backlog Atlas 1.2.3 from backlog-atlas==1.2.3" in out
    assert captured == {
        "repo": "o/r",
        "install_from": "backlog-atlas==1.2.3",
        "version": "1.2.3",
        "source_type": "pypi",
        "delivery": "push",
    }


def test_install_remote_dry_run_verifies_repo_without_writing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    calls: list[list[str]] = []
    _stub_installed_pypi(monkeypatch)

    def fake_run_gh(args: list[str], input_text: str | None = None) -> str:
        calls.append(args)
        assert input_text is None
        assert args == ["api", "repos/o/r"]
        return json.dumps(
            {
                "default_branch": "main",
                "permissions": {"admin": False, "maintain": False, "push": True},
            }
        )

    monkeypatch.setattr(install_github, "run_gh", fake_run_gh)
    monkeypatch.setattr(
        install_github,
        "install_remote_workflow",
        lambda repo, install_source, delivery: pytest.fail(
            "should not install remotely"
        ),
    )
    monkeypatch.setattr(
        install_github,
        "remote_installed_bundled_package_paths",
        lambda repo, branch: [],
    )
    monkeypatch.setattr(
        install_github,
        "validate_remote_config",
        lambda repo, branch: False,
    )

    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "https://github.com/o/r",
        "--dry-run",
    ]

    rc = ub.main()

    assert rc == 0
    out = capsys.readouterr().out
    assert calls == [["api", "repos/o/r"]]
    assert "Dry run: would install Backlog Atlas remotely" in out
    assert "Verified GitHub repository exists and current gh auth can write." in out
    assert "No files, branches, commits, or pull requests would be created." in out
    assert "Target repo: o/r" in out
    assert "Default branch: main" in out
    assert "Delivery: pull request" in out
    assert "Workflow would install Backlog Atlas from: backlog-atlas==1.2.3" in out
    assert "Would create or update temporary_backlog_atlas_install_pr from main" in out
    assert ".github/workflows/update-backlog-atlas.yml" in out
    assert ".github/backlog-atlas/manifest.json" in out
    assert ".github/backlog-atlas/config.yaml" in out
    assert ".github/backlog-atlas.json" not in out


def test_install_remote_dry_run_rejects_missing_write_access(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    _stub_installed_pypi(monkeypatch)
    monkeypatch.setattr(
        install_github,
        "run_gh",
        lambda args, input_text=None: json.dumps(
            {
                "default_branch": "main",
                "permissions": {"admin": False, "maintain": False, "push": False},
            }
        ),
    )
    monkeypatch.setattr(
        install_github,
        "install_remote_workflow",
        lambda repo, install_source, delivery: pytest.fail(
            "should not install remotely"
        ),
    )
    monkeypatch.setattr(
        install_github,
        "remote_installed_bundled_package_paths",
        lambda repo, branch: [],
    )
    monkeypatch.setattr(
        install_github,
        "validate_remote_config",
        lambda repo, branch: False,
    )

    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "https://github.com/o/r",
        "--dry-run",
    ]

    rc = ub.main()

    assert rc == 1
    err = capsys.readouterr().err
    assert "o/r exists" in err
    assert "does not appear to have write access" in err


def test_install_remote_dry_run_explains_missing_repo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    _stub_installed_pypi(monkeypatch)

    def fake_run_gh(args: list[str], input_text: str | None = None) -> str:
        raise install_github.UserError(
            "gh api repos/owner/name failed: gh: Not Found (HTTP 404)"
        )

    monkeypatch.setattr(install_github, "run_gh", fake_run_gh)
    monkeypatch.setattr(
        install_github,
        "install_remote_workflow",
        lambda repo, install_source, delivery: pytest.fail(
            "should not install remotely"
        ),
    )
    monkeypatch.setattr(
        install_github,
        "remote_installed_bundled_package_paths",
        lambda repo, branch: [],
    )
    monkeypatch.setattr(
        install_github,
        "validate_remote_config",
        lambda repo, branch: False,
    )

    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "https://github.com/owner/name",
        "--dry-run",
    ]

    rc = ub.main()

    assert rc == 1
    err = capsys.readouterr().err
    assert "GitHub could not find owner/name" in err
    assert "Check the repository URL" in err
    assert "current gh authentication can access it" in err


def test_install_remote_config_validation_rejects_invalid_config(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        install_github,
        "remote_config_text",
        lambda repo, branch: "done_expire_days: not-a-number\n",
    )

    with pytest.raises(install_github.UserError) as exc:
        install_github.validate_remote_config("o/r", "main")

    message = str(exc.value)
    assert "existing Backlog Atlas config is invalid" in message
    assert "https://github.com/o/r@main:.github/backlog-atlas/config.yaml" in message


def test_install_remote_config_validation_rejects_unparsable_yaml(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        install_github,
        "remote_config_text",
        lambda repo, branch: "categories:\n  Broken: [\n",
    )

    with pytest.raises(install_github.UserError) as exc:
        install_github.validate_remote_config("o/r", "main")

    message = str(exc.value)
    assert "existing Backlog Atlas config is invalid" in message
    assert "https://github.com/o/r@main:.github/backlog-atlas/config.yaml" in message


def test_install_remote_config_validation_rejects_unreadable_config(
    monkeypatch: pytest.MonkeyPatch,
):
    payload = {
        "encoding": "base64",
        "content": "not valid base64",
    }
    monkeypatch.setattr(
        install_github,
        "try_gh",
        lambda args: json.dumps(payload),
    )

    with pytest.raises(install_github.UserError) as exc:
        install_github.validate_remote_config("o/r", "main")

    message = str(exc.value)
    assert "remote Backlog Atlas config is not readable" in message
    assert "https://github.com/o/r@main:.github/backlog-atlas/config.yaml" in message


def test_install_remote_validates_config_before_bundling(
    monkeypatch: pytest.MonkeyPatch,
):
    source = InstallSource(
        pip_spec="backlog-atlas-branch/.backlog-atlas/packages/current.whl",
        version="2.0.0",
        source_type="bundled-wheel",
        bundled_wheel_path=".backlog-atlas/packages/current.whl",
        bundled_wheel_content=b"wheel bytes",
    )

    monkeypatch.setattr(install_github, "github_default_branch", lambda repo: "main")

    def fail_config(repo: str, branch: str) -> bool:
        raise install_github.UserError("bad")

    monkeypatch.setattr(install_github, "validate_remote_config", fail_config)
    monkeypatch.setattr(
        install_github,
        "ensure_backlog_branch_with_bundle",
        lambda repo, install_source: pytest.fail("should validate before bundling"),
    )

    with pytest.raises(install_github.UserError, match="bad"):
        install_github.install_remote_workflow("o/r", source, "pr")


def test_install_remote_dry_run_local_source_does_not_build_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    source_root = _make_backlog_atlas_checkout(tmp_path)
    monkeypatch.setattr(
        install_sources,
        "build_local_wheel",
        lambda source_root: pytest.fail("should not build wheel for dry run"),
    )
    monkeypatch.setattr(
        install_github,
        "run_gh",
        lambda args, input_text=None: json.dumps(
            {
                "default_branch": "main",
                "permissions": {"admin": False, "maintain": False, "push": True},
            }
        ),
    )
    monkeypatch.setattr(
        install_github,
        "install_remote_workflow",
        lambda repo, install_source, delivery: pytest.fail(
            "should not install remotely"
        ),
    )
    monkeypatch.setattr(
        install_github,
        "remote_installed_bundled_package_paths",
        lambda repo, branch: [],
    )
    monkeypatch.setattr(
        install_github,
        "validate_remote_config",
        lambda repo, branch: False,
    )

    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "https://github.com/o/r",
        "--install-from",
        str(source_root),
        "--dry-run",
    ]

    rc = ub.main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "Workflow would install Backlog Atlas from: " in out
    assert "backlog-atlas-branch/.backlog-atlas/packages/<built-wheel>" in out
    assert "Would build and upload bundled wheel to backlog-atlas" in out
    assert ".backlog-atlas/packages/<built-wheel>" in out
    assert "temporary-backlog-atlas-upgrade-cleanup.yml" not in out
    assert "removes old bundled wheels after the install lands" not in out


def test_install_remote_bundles_local_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_root = _make_backlog_atlas_checkout(tmp_path)
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        install_sources,
        "build_local_wheel",
        lambda path: ("backlog_atlas-2.3.4-py3-none-any.whl", b"wheel bytes"),
    )

    def fake_remote_install(
        repo: str, install_source: InstallSource, delivery: str
    ) -> None:
        captured.update(
            {
                "repo": repo,
                "install_from": install_source.pip_spec,
                "version": install_source.version,
                "source_type": install_source.source_type,
                "bundled_wheel_path": install_source.bundled_wheel_path or "",
                "delivery": delivery,
            }
        )

    monkeypatch.setattr(install_github, "install_remote_workflow", fake_remote_install)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "https://github.com/o/r.git",
        "--install-from",
        str(source_root),
    ]
    rc = ub.main()
    assert rc == 0
    assert captured == {
        "repo": "o/r",
        "install_from": (
            "backlog-atlas-branch/.backlog-atlas/packages/"
            "backlog_atlas-2.3.4-py3-none-any.whl"
        ),
        "version": "2.3.4",
        "source_type": "bundled-wheel",
        "bundled_wheel_path": (
            ".backlog-atlas/packages/backlog_atlas-2.3.4-py3-none-any.whl"
        ),
        "delivery": "pr",
    }


def test_install_remote_pr_writes_workflow_and_manifest(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    calls: list[tuple[Any, ...]] = []

    def fake_delete_file(repo: str, branch: str, path: str, message: str) -> bool:
        calls.append(("delete", repo, branch, path, message))
        return True

    monkeypatch.setattr(install_github, "github_default_branch", lambda repo: "develop")
    monkeypatch.setattr(
        install_github,
        "ensure_github_branch",
        lambda repo, branch, source_branch: calls.append(
            ("branch", repo, branch, source_branch)
        ),
    )

    def fake_put(repo: str, branch: str, path: str, content: str, message: str) -> None:
        calls.append(("put", repo, branch, path, content, message))

    monkeypatch.setattr(install_github, "put_github_file", fake_put)
    monkeypatch.setattr(
        install_github,
        "delete_github_file",
        fake_delete_file,
    )
    monkeypatch.setattr(
        install_github,
        "ensure_github_pr",
        lambda repo, branch, base_branch, install_source: calls.append(
            ("pr", repo, branch, base_branch, install_source)
        ),
    )
    monkeypatch.setattr(
        install_github,
        "remote_installed_bundled_package_paths",
        lambda repo, branch: [],
    )
    monkeypatch.setattr(
        install_github,
        "validate_remote_config",
        lambda repo, branch: False,
    )

    install_github.install_remote_workflow(
        "o/r",
        InstallSource(
            pip_spec="backlog-atlas==1.2.3",
            version="1.2.3",
            source_type="pypi",
        ),
        "pr",
    )

    out = capsys.readouterr().out
    assert "Preparing remote install for o/r" in out
    assert "Resolving default branch" in out
    assert "Default branch is develop" in out
    assert (
        "Ensuring install branch temporary_backlog_atlas_install_pr from develop" in out
    )
    assert "Writing workflow to temporary_backlog_atlas_install_pr" in out
    assert "Writing install manifest to temporary_backlog_atlas_install_pr" in out
    assert "Writing editable config to temporary_backlog_atlas_install_pr" in out
    assert (
        "Removed old upgrade cleanup workflow from temporary_backlog_atlas_install_pr"
        in out
    )
    assert calls[0] == (
        "branch",
        "o/r",
        "temporary_backlog_atlas_install_pr",
        "develop",
    )
    assert calls[5] == (
        "delete",
        "o/r",
        "temporary_backlog_atlas_install_pr",
        ".github/workflows/temporary-backlog-atlas-upgrade-cleanup.yml",
        "backlog: remove temporary Backlog Atlas upgrade cleanup workflow",
    )
    put_calls = [call for call in calls if call[0] == "put"]
    assert [call[3] for call in put_calls] == [
        ".github/workflows/update-backlog-atlas.yml",
        ".github/backlog-atlas/manifest.json",
        ".github/backlog-atlas/config.yaml",
    ]
    manifest = json.loads(put_calls[1][4])
    assert manifest["tool"] == "backlog-atlas"
    assert manifest["install"]["installed_version"] == "1.2.3"
    assert manifest["install"]["install_source"] == "backlog-atlas==1.2.3"
    assert manifest["install"]["source_type"] == "pypi"
    assert ".github/backlog-atlas/manifest.json" in {
        entry["path"] for entry in manifest["files"]
    }
    assert "ref: ${{ github.event.repository.default_branch }}" in put_calls[0][4]
    assert "ref: main" not in put_calls[0][4]
    assert put_calls[0][5] == "backlog: install Backlog Atlas 1.2.3 workflow"
    assert put_calls[1][5] == "backlog: install Backlog Atlas 1.2.3 workflow"
    assert put_calls[2][5] == "backlog: install Backlog Atlas 1.2.3 workflow"
    assert calls[-1][:4] == (
        "pr",
        "o/r",
        "temporary_backlog_atlas_install_pr",
        "develop",
    )
    assert calls[-1][4].version == "1.2.3"


def test_install_remote_pr_skips_upgrade_cleanup_for_fresh_bundled_wheel(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[Any, ...]] = []
    source = InstallSource(
        pip_spec="backlog-atlas-branch/.backlog-atlas/packages/current.whl",
        version="2.0.0",
        source_type="bundled-wheel",
        bundled_wheel_path=".backlog-atlas/packages/current.whl",
        bundled_wheel_content=b"wheel bytes",
    )

    monkeypatch.setattr(install_github, "github_default_branch", lambda repo: "main")
    monkeypatch.setattr(
        install_github,
        "ensure_backlog_branch_with_bundle",
        lambda repo, install_source: calls.append(("bundle", repo, install_source)),
    )
    monkeypatch.setattr(
        install_github,
        "ensure_github_branch",
        lambda repo, branch, source_branch: calls.append(
            ("branch", repo, branch, source_branch)
        ),
    )
    monkeypatch.setattr(install_github, "delete_github_file", lambda *args: False)
    monkeypatch.setattr(
        install_github,
        "put_github_file",
        lambda repo, branch, path, content, message: calls.append(
            ("put", repo, branch, path, content, message)
        ),
    )
    monkeypatch.setattr(
        install_github,
        "ensure_github_pr",
        lambda repo, branch, base_branch, install_source: calls.append(
            ("pr", repo, branch, base_branch, install_source)
        ),
    )
    monkeypatch.setattr(
        install_github,
        "remote_installed_bundled_package_paths",
        lambda repo, branch: [],
    )
    monkeypatch.setattr(
        install_github,
        "validate_remote_config",
        lambda repo, branch: True,
    )

    install_github.install_remote_workflow("o/r", source, "pr")

    put_calls = [call for call in calls if call[0] == "put"]
    assert [call[3] for call in put_calls] == [
        ".github/workflows/update-backlog-atlas.yml",
        ".github/backlog-atlas/manifest.json",
    ]
    manifest = json.loads(put_calls[1][4])
    assert {
        "path": ".backlog-atlas/packages/current.whl",
        "branch": "backlog-atlas",
        "remove": "uninstall",
    } in manifest["files"]
    assert not [
        entry
        for entry in manifest["files"]
        if entry["path"]
        == ".github/workflows/temporary-backlog-atlas-upgrade-cleanup.yml"
    ]


def test_install_remote_pr_writes_cleanup_when_previous_install_was_bundled(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[Any, ...]] = []
    source = InstallSource(
        pip_spec="backlog-atlas==2.0.0",
        version="2.0.0",
        source_type="pypi",
    )

    monkeypatch.setattr(install_github, "github_default_branch", lambda repo: "main")
    monkeypatch.setattr(
        install_github,
        "ensure_github_branch",
        lambda repo, branch, source_branch: calls.append(
            ("branch", repo, branch, source_branch)
        ),
    )
    monkeypatch.setattr(install_github, "delete_github_file", lambda *args: False)
    monkeypatch.setattr(
        install_github,
        "put_github_file",
        lambda repo, branch, path, content, message: calls.append(
            ("put", repo, branch, path, content, message)
        ),
    )
    monkeypatch.setattr(
        install_github,
        "ensure_github_pr",
        lambda repo, branch, base_branch, install_source: calls.append(
            ("pr", repo, branch, base_branch, install_source)
        ),
    )
    monkeypatch.setattr(
        install_github,
        "remote_installed_bundled_package_paths",
        lambda repo, branch: [".backlog-atlas/packages/old.whl"],
    )
    monkeypatch.setattr(
        install_github,
        "validate_remote_config",
        lambda repo, branch: True,
    )

    install_github.install_remote_workflow("o/r", source, "pr")

    put_calls = [call for call in calls if call[0] == "put"]
    assert [call[3] for call in put_calls] == [
        ".github/workflows/update-backlog-atlas.yml",
        ".github/backlog-atlas/manifest.json",
        ".github/workflows/temporary-backlog-atlas-upgrade-cleanup.yml",
    ]
    manifest = json.loads(put_calls[1][4])
    assert not [
        entry for entry in manifest["files"] if entry.get("branch") == "backlog-atlas"
    ]
    cleanup_content = put_calls[2][4]
    assert "BACKLOG_ATLAS_KEEP_PACKAGE" not in cleanup_content
    assert ".backlog-atlas/packages/old.whl" in cleanup_content
    assert "find .backlog-atlas/packages" not in cleanup_content


def test_install_remote_push_skips_upgrade_cleanup_without_old_packages(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[Any, ...]] = []
    source = InstallSource(
        pip_spec="backlog-atlas-branch/.backlog-atlas/packages/current.whl",
        version="2.0.0",
        source_type="bundled-wheel",
        bundled_wheel_path=".backlog-atlas/packages/current.whl",
        bundled_wheel_content=b"wheel bytes",
    )

    monkeypatch.setattr(install_github, "github_default_branch", lambda repo: "main")
    monkeypatch.setattr(
        install_github,
        "ensure_backlog_branch_with_bundle",
        lambda repo, install_source: calls.append(("bundle", repo, install_source)),
    )
    monkeypatch.setattr(install_github, "delete_github_file", lambda *args: False)
    monkeypatch.setattr(
        install_github,
        "put_github_file",
        lambda repo, branch, path, content, message: calls.append(
            ("put", repo, branch, path, content, message)
        ),
    )
    monkeypatch.setattr(
        install_github,
        "remote_installed_bundled_package_paths",
        lambda repo, branch: [],
    )
    monkeypatch.setattr(
        install_github,
        "validate_remote_config",
        lambda repo, branch: True,
    )

    install_github.install_remote_workflow("o/r", source, "push")

    put_calls = [call for call in calls if call[0] == "put"]
    assert [call[3] for call in put_calls] == [
        ".github/workflows/update-backlog-atlas.yml",
        ".github/backlog-atlas/manifest.json",
    ]


def test_install_remote_push_removes_stale_cleanup_before_updating_workflow(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[Any, ...]] = []
    source = InstallSource(
        pip_spec="backlog-atlas-branch/.backlog-atlas/packages/current.whl",
        version="2.0.0",
        source_type="bundled-wheel",
        bundled_wheel_path=".backlog-atlas/packages/current.whl",
        bundled_wheel_content=b"wheel bytes",
    )

    def fake_delete(repo: str, branch: str, path: str, message: str) -> bool:
        calls.append(("delete", repo, branch, path, message))
        return path == ".github/workflows/temporary-backlog-atlas-upgrade-cleanup.yml"

    monkeypatch.setattr(install_github, "github_default_branch", lambda repo: "main")
    monkeypatch.setattr(
        install_github, "ensure_backlog_branch_with_bundle", lambda *args: None
    )
    monkeypatch.setattr(install_github, "delete_github_file", fake_delete)
    monkeypatch.setattr(
        install_github,
        "put_github_file",
        lambda repo, branch, path, content, message: calls.append(
            ("put", repo, branch, path, content, message)
        ),
    )
    monkeypatch.setattr(
        install_github,
        "remote_installed_bundled_package_paths",
        lambda repo, branch: [],
    )
    monkeypatch.setattr(
        install_github,
        "validate_remote_config",
        lambda repo, branch: True,
    )

    install_github.install_remote_workflow("o/r", source, "push")

    assert calls[0] == (
        "delete",
        "o/r",
        "main",
        ".github/workflows/temporary-backlog-atlas-upgrade-cleanup.yml",
        "backlog: remove stale temporary Backlog Atlas upgrade cleanup workflow",
    )
    put_calls = [call for call in calls if call[0] == "put"]
    assert [call[3] for call in put_calls][:3] == [
        ".github/workflows/update-backlog-atlas.yml",
        ".github/backlog-atlas/manifest.json",
    ]


def test_upgrade_cleanup_template_keeps_current_wheel_and_self_deletes():
    content = install_artifacts.load_upgrade_cleanup_workflow_template(
        [".backlog-atlas/packages/old.whl"]
    )

    assert "name: Backlog Atlas Upgrade Cleanup" in content
    assert "BACKLOG_ATLAS_KEEP_PACKAGE" not in content
    assert ".backlog-atlas/packages/old.whl" in content
    assert "find .backlog-atlas/packages" not in content
    assert "backlog-atlas-remove-packages" in content
    assert 'git rm --ignore-unmatch "$BACKLOG_ATLAS_CLEANUP_WORKFLOW"' in content
    assert "backlog: remove temporary upgrade cleanup workflow [skip ci]" in content


def test_upgrade_cleanup_template_handles_empty_package_cleanup_list():
    content = install_artifacts.load_upgrade_cleanup_workflow_template()

    assert "BACKLOG_ATLAS_REMOVE_PACKAGES_JSON: '[]'" in content
    assert "No old bundled install packages were listed" in content


def test_install_pr_text_includes_version_and_source(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []
    source = InstallSource(
        pip_spec="backlog-atlas==2.0.0",
        version="2.0.0",
        source_type="pypi",
    )

    def fake_run_gh(args: list[str], input_text: str | None = None) -> str:
        calls.append(args)
        if args[:2] == ["pr", "list"]:
            return "[]"
        return ""

    monkeypatch.setattr(install_github, "run_gh", fake_run_gh)

    install_github.ensure_github_pr("o/r", "install-branch", "main", source)

    create_call = calls[-1]
    assert create_call[:2] == ["pr", "create"]
    assert "Install Backlog Atlas 2.0.0" in create_call
    body = create_call[create_call.index("--body") + 1]
    assert "Installs Backlog Atlas 2.0.0 from backlog-atlas==2.0.0" in body
    assert "Install source: `backlog-atlas==2.0.0`" in body


def test_install_pr_text_identifies_bundled_wheel_source(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []
    source = InstallSource(
        pip_spec="backlog-atlas-branch/.backlog-atlas/packages/pkg.whl",
        version="2.0.0",
        source_type="bundled-wheel",
        bundled_wheel_path=".backlog-atlas/packages/pkg.whl",
        bundled_wheel_content=b"wheel bytes",
    )

    def fake_run_gh(args: list[str], input_text: str | None = None) -> str:
        calls.append(args)
        if args[:2] == ["pr", "list"]:
            return "[]"
        return ""

    monkeypatch.setattr(install_github, "run_gh", fake_run_gh)

    install_github.ensure_github_pr("o/r", "install-branch", "main", source)

    create_call = calls[-1]
    assert create_call[:2] == ["pr", "create"]
    assert "Install Backlog Atlas from pkg.whl" in create_call
    body = create_call[create_call.index("--body") + 1]
    assert (
        "Installs Backlog Atlas 2.0.0 from bundled wheel "
        ".backlog-atlas/packages/pkg.whl"
    ) in body


def test_install_pr_text_is_updated_for_existing_pr(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []
    source = InstallSource(
        pip_spec="backlog-atlas==2.0.0",
        version="2.0.0",
        source_type="pypi",
    )

    def fake_run_gh(args: list[str], input_text: str | None = None) -> str:
        calls.append(args)
        if args[:2] == ["pr", "list"]:
            return json.dumps([{"number": 7}])
        return ""

    monkeypatch.setattr(install_github, "run_gh", fake_run_gh)

    install_github.ensure_github_pr("o/r", "install-branch", "main", source)

    edit_call = calls[-1]
    assert edit_call[:3] == ["pr", "edit", "7"]
    assert "Install Backlog Atlas 2.0.0" in edit_call
    body = edit_call[edit_call.index("--body") + 1]
    assert "Installs Backlog Atlas 2.0.0 from backlog-atlas==2.0.0" in body
    assert "Install source: `backlog-atlas==2.0.0`" in body


def test_bundled_wheel_is_published_to_backlog_branch(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[Any, ...]] = []
    source = InstallSource(
        pip_spec="backlog-atlas-branch/.backlog-atlas/packages/pkg.whl",
        version="2.3.4",
        source_type="bundled-wheel",
        bundled_wheel_path=".backlog-atlas/packages/pkg.whl",
        bundled_wheel_content=b"wheel bytes",
    )
    monkeypatch.setattr(
        install_github, "github_ref_sha", lambda repo, branch: "branch-sha"
    )
    monkeypatch.setattr(
        install_github,
        "put_github_file_bytes",
        lambda repo, branch, path, content, message: calls.append(
            ("put-bytes", repo, branch, path, content, message)
        ),
    )

    install_github.ensure_backlog_branch_with_bundle("o/r", source)

    assert calls == [
        (
            "put-bytes",
            "o/r",
            "backlog-atlas",
            ".backlog-atlas/packages/pkg.whl",
            b"wheel bytes",
            "backlog: bundle pkg.whl",
        )
    ]


def test_bundled_wheel_initializes_backlog_branch_without_markdown(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[Any, ...]] = []
    source = InstallSource(
        pip_spec="backlog-atlas-branch/.backlog-atlas/packages/pkg.whl",
        version="2.3.4",
        source_type="bundled-wheel",
        bundled_wheel_path=".backlog-atlas/packages/pkg.whl",
        bundled_wheel_content=b"wheel bytes",
    )
    monkeypatch.setattr(install_github, "github_ref_sha", lambda repo, branch: None)

    def fake_create_tree(repo: str, entries: dict[str, bytes]) -> str:
        calls.append(("tree", repo, entries))
        return "tree-sha"

    def fake_create_commit(repo: str, message: str, tree_sha: str) -> str:
        calls.append(("commit", repo, message, tree_sha))
        return "commit-sha"

    monkeypatch.setattr(install_github, "create_tree", fake_create_tree)
    monkeypatch.setattr(install_github, "create_commit", fake_create_commit)
    monkeypatch.setattr(
        install_github,
        "create_branch_ref",
        lambda repo, branch, commit_sha: calls.append(
            ("ref", repo, branch, commit_sha)
        ),
    )

    install_github.ensure_backlog_branch_with_bundle("o/r", source)

    assert calls == [
        ("tree", "o/r", {".backlog-atlas/packages/pkg.whl": b"wheel bytes"}),
        ("commit", "o/r", "backlog: initialize backlog-atlas branch", "tree-sha"),
        ("ref", "o/r", "backlog-atlas", "commit-sha"),
    ]


def test_uninstall_writes_self_removing_workflow_and_keeps_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    calls = _stub_local_install(monkeypatch)
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text("workflow content\n", encoding="utf-8")
    monkeypatch.setattr(ub, "resolve_repo", lambda r: "o/r")
    sys.argv = [
        "backlog-atlas",
        "uninstall",
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
    ]
    rc = ub.main()
    assert rc == 0
    content = wf.read_text(encoding="utf-8")
    assert "name: Uninstall Backlog Atlas" in content
    assert 'BACKLOG_ATLAS_CLEAN_UNINSTALL: "false"' in content
    assert "github.event.repository.default_branch" in content
    assert "ref: main" not in content
    assert "branches: [main]" not in content
    assert "Remove bundled install packages" in content
    assert "backlog-atlas-remove-branch-paths" in content
    assert 'entry.get("branch") != "backlog-atlas"' in content
    assert "xargs -r -d '\\n' -a /tmp/backlog-atlas-remove-branch-paths" in content
    assert "backlog: remove bundled install packages [skip ci]" in content
    assert "retained $BACKLOG_ATLAS_BRANCH branch" in content
    assert ".github/backlog-atlas/manifest.json" in content
    assert 'entry.get("branch") != "default"' in content
    assert 'remove == "uninstall" or (clean and remove == "clean")' in content
    assert "xargs -r -d '\\n' -a /tmp/backlog-atlas-remove-paths" in content
    assert "if clean:" in content
    assert '".github/backlog-atlas/config.yaml"' in content
    out = capsys.readouterr().out
    assert "created uninstall commit" in out
    assert "remove install manifests and bundled install packages" in out
    assert calls == [
        ("clean", tmp_path, "git"),
        ("add", tmp_path, [wf], "git"),
        ("commit", tmp_path, [wf], "git", "backlog: uninstall Backlog Atlas workflow"),
    ]


def test_uninstall_local_checkout_guides_pr_from_non_default_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    _stub_local_install(monkeypatch)
    monkeypatch.setattr(
        install_repo, "is_on_default_branch", lambda target_root, vcs: False
    )
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"

    sys.argv = [
        "backlog-atlas",
        "uninstall",
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
    ]

    rc = ub.main()

    assert rc == 0
    assert "name: Uninstall Backlog Atlas" in wf.read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert "created uninstall commit" in out
    assert "git show --stat HEAD" in out
    assert "git push -u origin HEAD" in out
    assert "# Open or merge a PR for this uninstall commit before continuing." in out


def test_uninstall_dirty_worktree_returns_error_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(ub, "resolve_repo", lambda r: "o/r")
    monkeypatch.setattr(install_repo, "detect_local_vcs", lambda target_root: "git")
    monkeypatch.setattr(
        install_local,
        "ensure_worktree_clean",
        lambda target_root, vcs: False,
    )

    sys.argv = [
        "backlog-atlas",
        "uninstall",
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
    ]

    rc = ub.main()

    assert rc == 1
    assert not (tmp_path / ".github").exists()


def test_uninstall_force_skips_dirty_worktree_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    calls = _stub_local_install(monkeypatch)
    monkeypatch.setattr(ub, "resolve_repo", lambda r: "o/r")
    monkeypatch.setattr(
        install_local,
        "ensure_worktree_clean",
        lambda target_root, vcs: pytest.fail("should not check worktree cleanliness"),
    )
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"

    sys.argv = [
        "backlog-atlas",
        "uninstall",
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
        "--force",
    ]

    rc = ub.main()

    assert rc == 0
    assert "Skipping working tree cleanliness check" in capsys.readouterr().out
    assert calls == [
        ("add", tmp_path, [wf], "git"),
        ("commit", tmp_path, [wf], "git", "backlog: uninstall Backlog Atlas workflow"),
    ]


def test_uninstall_removes_lingering_upgrade_cleanup_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    calls = _stub_local_install(monkeypatch)
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    cleanup_wf = (
        tmp_path
        / ".github"
        / "workflows"
        / "temporary-backlog-atlas-upgrade-cleanup.yml"
    )
    wf.parent.mkdir(parents=True)
    wf.write_text("workflow content\n", encoding="utf-8")
    cleanup_wf.write_text(
        install_artifacts.load_upgrade_cleanup_workflow_template(),
        encoding="utf-8",
    )
    monkeypatch.setattr(ub, "resolve_repo", lambda r: "o/r")

    sys.argv = [
        "backlog-atlas",
        "uninstall",
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
    ]

    rc = ub.main()

    assert rc == 0
    assert "name: Uninstall Backlog Atlas" in wf.read_text(encoding="utf-8")
    assert not cleanup_wf.exists()
    out = capsys.readouterr().out
    assert f"removed temporary upgrade cleanup workflow from {cleanup_wf}" in out
    assert "created uninstall commit" in out
    assert "# Review the uninstall commit." in out
    assert calls == [
        ("clean", tmp_path, "git"),
        ("add", tmp_path, [cleanup_wf, wf], "git"),
        (
            "commit",
            tmp_path,
            [cleanup_wf, wf],
            "git",
            "backlog: uninstall Backlog Atlas workflow",
        ),
    ]


def test_uninstall_normal_writes_cleanup_workflow_after_manual_file_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    calls = _stub_local_install(monkeypatch)
    monkeypatch.setattr(ub, "resolve_repo", lambda r: "o/r")
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"

    sys.argv = [
        "backlog-atlas",
        "uninstall",
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
    ]

    rc = ub.main()

    assert rc == 0
    assert "name: Uninstall Backlog Atlas" in wf.read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert "No default-branch Backlog Atlas install artifacts were found" in out
    assert "remove install manifests and bundled install packages" in out
    assert calls == [
        ("clean", tmp_path, "git"),
        ("add", tmp_path, [wf], "git"),
        ("commit", tmp_path, [wf], "git", "backlog: uninstall Backlog Atlas workflow"),
    ]


def test_uninstall_clean_is_encoded_in_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls = _stub_local_install(monkeypatch)
    monkeypatch.setattr(ub, "resolve_repo", lambda r: "o/r")
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    sys.argv = [
        "backlog-atlas",
        "uninstall",
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
        "--clean",
        "--yes",
    ]
    rc = ub.main()
    assert rc == 0
    content = wf.read_text(encoding="utf-8")
    assert 'BACKLOG_ATLAS_CLEAN_UNINSTALL: "true"' in content
    assert 'git push origin --delete "$BACKLOG_ATLAS_BRANCH"' in content
    assert ".github/backlog-atlas/config.yaml" in content
    assert calls == [
        ("clean", tmp_path, "git"),
        ("add", tmp_path, [wf], "git"),
        (
            "commit",
            tmp_path,
            [wf],
            "git",
            "backlog: clean uninstall Backlog Atlas workflow",
        ),
    ]
