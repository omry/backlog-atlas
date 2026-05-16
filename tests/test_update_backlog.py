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
import backlog_atlas.install as inst  # noqa: E402
from backlog_atlas.install import github as install_github  # noqa: E402
from backlog_atlas.install import local as install_local  # noqa: E402
from backlog_atlas.install import repo as install_repo  # noqa: E402
from backlog_atlas.install import sources as install_sources  # noqa: E402

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
    assert ub.try_command(["nonexistent_binary_xyz"]) is None


def test_try_command_nonzero_exit():
    assert ub.try_command(["false"]) is None


def test_try_command_success():
    result = ub.try_command(["echo", "hello"])
    assert result is not None
    assert "hello" in result


# ---------------------------------------------------------------------------
# render_template
# ---------------------------------------------------------------------------


def test_render_template_simple_var():
    assert ub.render_template("hello {{name}}", {"name": "world"}) == "hello world"


def test_render_template_missing_var_is_empty():
    assert ub.render_template("{{x}}", {}) == ""


def test_render_template_section_loop():
    tmpl = "{{#items}}[{{val}}]{{/items}}"
    result = ub.render_template(tmpl, {"items": [{"val": "a"}, {"val": "b"}]})
    assert result == "[a][b]"


def test_render_template_empty_section():
    assert ub.render_template("{{#items}}x{{/items}}", {"items": []}) == ""


def test_render_template_none_section():
    assert ub.render_template("{{#items}}x{{/items}}", {"items": None}) == ""


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
        "title_display": f"Issue {number}",
        "status": status,
        "category": "Enhancement",
        "labels": labels,
        "labels_display": "",
        "pr_numbers": [],
        "pr_links": "",
        "issue_link": f"[#{number}](url)",
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
        _cfg(), _prev_row("803", "[Question] Why hide this?"), _L2C, _KW
    )
    assert row["category"] == "Question"


def test_normalize_previous_row_derives_category_from_label():
    row = ub.normalize_previous_row(
        _cfg(), _prev_row("1", "Something", labels=["bug"]), _L2C, _KW
    )
    assert row["category"] == "Bug"


def test_normalize_previous_row_ignores_stale_category_field():
    raw = {
        **_prev_row("1", "Add a feature"),
        "category": '<span title="<span>garbage</span>">✨</span>',
    }
    row = ub.normalize_previous_row(_cfg(), raw, _L2C, _KW)
    assert row["category"] == "Enhancement"


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
    row["title_display"] = f"Issue {number}"
    row["labels_display"] = ""
    row["issue_link"] = f"[#{number}](url)"
    row["pr_links"] = ""
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


def test_event_log_cleared_after_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    event_log = tmp_path / "events.jsonl"
    event_log.write_text('{"event": "issues", "action": "opened"}\n', encoding="utf-8")
    snapshot_path = tmp_path / "snap.json"

    def fake_fetch_collaborators(repo: str) -> set[str]:
        return set()

    def fake_fetch_open_issues(repo: str) -> list[dict[str, Any]]:
        return []

    def fake_fetch_open_prs(repo: str) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(ub, "fetch_collaborators", fake_fetch_collaborators)
    monkeypatch.setattr(ub, "fetch_open_issues", fake_fetch_open_issues)
    monkeypatch.setattr(ub, "fetch_open_prs", fake_fetch_open_prs)
    monkeypatch.setattr(ub, "detect_target_root", lambda *a, **kw: tmp_path)

    with patch.object(ub, "resolve_repo", return_value="o/r"):
        sys.argv = [
            "backlog-atlas",
            "update",
            "--snapshot-path",
            str(snapshot_path),
            "--event-log-path",
            str(event_log),
        ]
        ub.main()

    assert event_log.read_text(encoding="utf-8") == ""


def test_initial_update_creates_empty_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    event_log = tmp_path / "events.jsonl"
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
            "--event-log-path",
            str(event_log),
        ]
        ub.main()

    assert (tmp_path / "BACKLOG-UPDATES.md").read_text(encoding="utf-8") == ""
    assert event_log.read_text(encoding="utf-8") == ""
    assert (tmp_path / ".backlog-atlas" / "updates.jsonl").read_text(
        encoding="utf-8"
    ) == ""


def test_dry_run_does_not_bootstrap_updates_jsonl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    updates = tmp_path / "BACKLOG-UPDATES.md"
    updates_jsonl = tmp_path / "updates.jsonl"
    updates.write_text(
        "- `2024-01-01T00:00:00Z` new: [#1](https://github.com/o/r/issues/1) Issue 1\n",
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
            "--updates-jsonl-path",
            str(updates_jsonl),
        ]
        ub.main()

    assert not updates_jsonl.exists()


# ---------------------------------------------------------------------------
# install / uninstall
# ---------------------------------------------------------------------------


def _stub_local_install(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    calls: list[tuple[Any, ...]] = []

    def fake_clean(target_root: Path, vcs: str) -> None:
        calls.append(("clean", target_root, vcs))

    def fake_add(target_root: Path, artifact_paths: list[Path], vcs: str) -> None:
        calls.append(("add", target_root, artifact_paths, vcs))

    monkeypatch.setattr(install_repo, "detect_local_vcs", lambda target_root: "git")
    monkeypatch.setattr(install_local, "ensure_worktree_clean", fake_clean)
    monkeypatch.setattr(install_local, "add_local_install_files", fake_add)
    monkeypatch.setattr(
        install_repo, "is_on_default_branch", lambda target_root, vcs: None
    )
    monkeypatch.setattr(install_sources, "installed_version", lambda: "1.2.3")
    return calls


def _make_backlog_atlas_checkout(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "pyproject.toml").write_text(
        "[project]\nname = 'backlog-atlas'\nversion = '2.3.4'\n",
        encoding="utf-8",
    )
    return source_root


def test_workflow_template_substitutes_install_source():
    out = ub.load_workflow_template("git+https://example.com/x.git")
    assert "__BACKLOG_ATLAS_PIP__" not in out
    assert "BACKLOG_ATLAS_PIP: git+https://example.com/x.git" in out
    assert "BACKLOG_ATLAS_BRANCH: backlog-atlas" in out
    assert 'pip install "$BACKLOG_ATLAS_PIP"' in out
    assert "backlog-atlas update" in out
    assert "backlog-atlas dump-web" in out
    assert "ensure-backlog-branch:" in out
    assert "needs: ensure-backlog-branch" in out
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


def test_install_writes_workflow_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls = _stub_local_install(monkeypatch)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
        "--install-from",
        "backlog-atlas==2.0.0",
    ]
    rc = ub.main()
    assert rc == 0
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    metadata = tmp_path / ".github" / "backlog-atlas.json"
    assert wf.exists()
    assert metadata.exists()
    content = wf.read_text(encoding="utf-8")
    assert "BACKLOG_ATLAS_PIP: backlog-atlas==2.0.0" in content
    assert "${{ github.event_name }}" in content
    metadata_obj = json.loads(metadata.read_text(encoding="utf-8"))
    assert metadata_obj == {
        "schema_version": 1,
        "tool": "backlog-atlas",
        "installed_version": "2.0.0",
        "install_source": "backlog-atlas==2.0.0",
        "source_type": "pypi",
        "workflow_path": ".github/workflows/update-backlog-atlas.yml",
    }
    assert calls == [
        ("clean", tmp_path, "git"),
        ("add", tmp_path, [wf, metadata], "git"),
    ]


def test_install_defaults_to_pypi_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _stub_local_install(monkeypatch)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
    ]
    rc = ub.main()
    assert rc == 0
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    metadata = tmp_path / ".github" / "backlog-atlas.json"
    assert "BACKLOG_ATLAS_PIP: backlog-atlas==1.2.3" in wf.read_text(encoding="utf-8")
    metadata_obj = json.loads(metadata.read_text(encoding="utf-8"))
    assert metadata_obj["install_source"] == "backlog-atlas==1.2.3"
    assert metadata_obj["installed_version"] == "1.2.3"
    assert metadata_obj["source_type"] == "pypi"


def test_install_leaves_unmatched_existing_workflow_and_metadata_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    metadata = tmp_path / ".github" / "backlog-atlas.json"
    wf.parent.mkdir(parents=True)
    wf.write_text("# preexisting\n", encoding="utf-8")
    calls = _stub_local_install(monkeypatch)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
    ]
    rc = ub.main()
    assert rc == 0
    # Existing workflow not overwritten
    assert wf.read_text(encoding="utf-8") == "# preexisting\n"
    assert not metadata.exists()
    assert calls == [("clean", tmp_path, "git")]


def test_install_writes_metadata_when_existing_workflow_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    metadata = tmp_path / ".github" / "backlog-atlas.json"
    wf.parent.mkdir(parents=True)
    wf.write_text(ub.load_workflow_template("backlog-atlas==1.2.3"), encoding="utf-8")
    calls = _stub_local_install(monkeypatch)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
    ]
    rc = ub.main()
    assert rc == 0
    assert metadata.exists()
    assert calls == [("clean", tmp_path, "git"), ("add", tmp_path, [metadata], "git")]


def test_install_updates_managed_existing_workflow_and_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wf = tmp_path / ".github" / "workflows" / "update-backlog-atlas.yml"
    metadata = tmp_path / ".github" / "backlog-atlas.json"
    wf.parent.mkdir(parents=True)
    old_workflow = ub.load_workflow_template("backlog-atlas==1.2.3").replace(
        "ref: ${{ github.event.repository.default_branch }}", "ref: main"
    )
    wf.write_text(old_workflow, encoding="utf-8")
    calls = _stub_local_install(monkeypatch)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
    ]
    rc = ub.main()
    assert rc == 0
    assert "ref: main" not in wf.read_text(encoding="utf-8")
    assert metadata.exists()
    assert calls == [
        ("clean", tmp_path, "git"),
        ("add", tmp_path, [wf, metadata], "git"),
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
    metadata = tmp_path / ".github" / "backlog-atlas.json"
    assert wf.exists()
    assert metadata.exists()
    assert calls == [
        ("clean", tmp_path, "git"),
        ("add", tmp_path, [wf, metadata], "git"),
    ]


def test_install_local_checkout_rejects_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _stub_local_install(monkeypatch)
    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
        "--delivery",
        "push",
    ]
    with pytest.raises(RuntimeError, match="--delivery only applies to remote"):
        ub.main()


def test_resolve_install_source_from_local_checkout_builds_bundled_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source_root = _make_backlog_atlas_checkout(tmp_path)
    monkeypatch.setattr(
        install_sources,
        "build_local_wheel",
        lambda path: ("backlog_atlas-2.3.4-py3-none-any.whl", b"wheel bytes"),
    )

    source = inst.resolve_install_source(str(source_root))

    assert source == inst.InstallSource(
        pip_spec=(
            "backlog-atlas-branch/.backlog-atlas/packages/"
            "backlog_atlas-2.3.4-py3-none-any.whl"
        ),
        version="2.3.4",
        source_type="bundled-wheel",
        bundled_wheel_path=".backlog-atlas/packages/backlog_atlas-2.3.4-py3-none-any.whl",
        bundled_wheel_content=b"wheel bytes",
    )


def test_install_rejects_floating_install_source():
    with pytest.raises(RuntimeError, match="must be a pinned PyPI spec"):
        inst.resolve_install_source("git+https://example.com/x.git@main")


def test_install_local_target_bundles_local_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls = _stub_local_install(monkeypatch)
    source_root = _make_backlog_atlas_checkout(tmp_path)
    target_root = tmp_path / "target"
    bundle_calls: list[tuple[str, inst.InstallSource]] = []
    monkeypatch.setattr(
        install_sources,
        "build_local_wheel",
        lambda path: ("backlog_atlas-2.3.4-py3-none-any.whl", b"wheel bytes"),
    )
    monkeypatch.setattr(
        install_github,
        "ensure_backlog_branch_with_bundle",
        lambda repo, source: bundle_calls.append((repo, source)),
    )
    sys.argv = [
        "backlog-atlas",
        "install",
        "--repo",
        "o/r",
        "--target-root",
        str(target_root),
        "--install-from",
        str(source_root),
    ]
    rc = ub.main()
    assert rc == 0
    assert bundle_calls[0][0] == "o/r"
    install_source = bundle_calls[0][1]
    assert install_source.source_type == "bundled-wheel"
    assert install_source.bundled_wheel_content == b"wheel bytes"
    wf = target_root / ".github" / "workflows" / "update-backlog-atlas.yml"
    metadata = target_root / ".github" / "backlog-atlas.json"
    assert calls == [
        ("clean", target_root, "git"),
        ("add", target_root, [wf, metadata], "git"),
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
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
    ]
    rc = ub.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert 'git commit -m "backlog: install Backlog Atlas workflow"' in out
    assert "git push" in out
    assert "git push -u origin HEAD" not in out
    assert "the install commit will be on the default branch" in out
    assert "after it lands on the default branch" in out


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
        "--repo",
        "o/r",
        "--target-root",
        str(tmp_path),
    ]
    rc = ub.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert 'git commit -m "backlog: install Backlog Atlas workflow"' in out
    assert "git push -u origin HEAD" in out
    assert "open or merge a PR for the install commit" in out
    assert "after it lands on the default branch" in out


def test_install_remote_defaults_to_pr_delivery_for_github_url(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, str] = {}

    def fake_remote_install(
        repo: str, install_source: inst.InstallSource, delivery: str
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

    monkeypatch.setattr(install_sources, "installed_version", lambda: "1.2.3")
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
    assert captured == {
        "repo": "o/r",
        "install_from": "backlog-atlas==2.0.0",
        "version": "2.0.0",
        "source_type": "pypi",
        "delivery": "pr",
    }


def test_install_remote_supports_push_delivery_for_ssh_url(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, str] = {}

    def fake_remote_install(
        repo: str, install_source: inst.InstallSource, delivery: str
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

    monkeypatch.setattr(install_sources, "installed_version", lambda: "1.2.3")
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
    assert captured == {
        "repo": "o/r",
        "install_from": "backlog-atlas==1.2.3",
        "version": "1.2.3",
        "source_type": "pypi",
        "delivery": "push",
    }


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
        repo: str, install_source: inst.InstallSource, delivery: str
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


def test_install_remote_pr_writes_workflow_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[Any, ...]] = []

    monkeypatch.setattr(install_sources, "installed_version", lambda: "1.2.3")
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
        "ensure_github_pr",
        lambda repo, branch, base_branch: calls.append(
            ("pr", repo, branch, base_branch)
        ),
    )

    install_github.install_remote_workflow(
        "o/r",
        inst.InstallSource(
            pip_spec="backlog-atlas==1.2.3",
            version="1.2.3",
            source_type="pypi",
        ),
        "pr",
    )

    put_calls = [call for call in calls if call[0] == "put"]
    assert [call[3] for call in put_calls] == [
        ".github/workflows/update-backlog-atlas.yml",
        ".github/backlog-atlas.json",
    ]
    metadata = json.loads(put_calls[1][4])
    assert metadata["installed_version"] == "1.2.3"
    assert metadata["install_source"] == "backlog-atlas==1.2.3"
    assert metadata["source_type"] == "pypi"
    assert "ref: ${{ github.event.repository.default_branch }}" in put_calls[0][4]
    assert "ref: main" not in put_calls[0][4]
    assert calls[0] == ("branch", "o/r", "backlog-atlas-install", "develop")
    assert calls[-1] == ("pr", "o/r", "backlog-atlas-install", "develop")


def test_bundled_wheel_is_published_to_backlog_branch(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[Any, ...]] = []
    source = inst.InstallSource(
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
            "backlog: bundle Backlog Atlas package",
        )
    ]


def test_uninstall_writes_self_removing_workflow_and_keeps_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
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
    assert 'BACKLOG_ATLAS_DELETE_BRANCH: "false"' in content
    assert "github.event.repository.default_branch" in content
    assert "ref: main" not in content
    assert "branches: [main]" not in content
    assert "retained $BACKLOG_ATLAS_BRANCH branch" in content
    assert (
        "git rm --ignore-unmatch .github/backlog-atlas.json "
        ".github/workflows/update-backlog-atlas.yml"
    ) in content


def test_uninstall_delete_branch_is_encoded_in_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
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
        "--delete-branch",
        "--yes",
    ]
    rc = ub.main()
    assert rc == 0
    content = wf.read_text(encoding="utf-8")
    assert 'BACKLOG_ATLAS_DELETE_BRANCH: "true"' in content
    assert 'git push origin --delete "$BACKLOG_ATLAS_BRANCH"' in content
