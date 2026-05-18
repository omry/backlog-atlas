from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load_publish_module() -> ModuleType:
    path = ROOT / "tools" / "publish_version.py"
    spec = importlib.util.spec_from_file_location("publish_version_under_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


publish = load_publish_module()


def test_publish_requires_completely_clean_working_tree(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        publish,
        "status_entries",
        lambda: [("M", "pyproject.toml"), ("?", "dist/pkg.whl")],
    )

    with pytest.raises(publish.ReleaseError) as exc:
        publish.ensure_clean_working_tree()

    message = str(exc.value)
    assert "working tree has uncommitted changes" in message
    assert "M pyproject.toml" in message
    assert "? dist/pkg.whl" in message


def test_publish_checks_default_branch_before_release_edits(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, capture: bool = False) -> str:
        calls.append(args)
        if args[:2] == ["sl", "log"]:
            return "abc123 backlog: other change\n"
        return ""

    monkeypatch.setattr(publish, "run", fake_run)

    with pytest.raises(publish.ReleaseError) as exc:
        publish.ensure_default_branch_current()

    assert calls[0] == ["sl", "pull"]
    assert calls[1][:3] == ["sl", "log", "-r"]
    assert "missing commits from the remote default branch" in str(exc.value)
    assert "abc123 backlog: other change" in str(exc.value)


def test_publish_restore_release_files_restores_snapshot(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    changelog = tmp_path / "CHANGELOG.md"
    pyproject.write_text('version = "0.14"\n', encoding="utf-8")
    changelog.write_text("## Unreleased\n\n- Notes\n", encoding="utf-8")

    snapshot = {
        pyproject: pyproject.read_text(encoding="utf-8"),
        changelog: changelog.read_text(encoding="utf-8"),
    }
    pyproject.write_text('version = "0.15"\n', encoding="utf-8")
    changelog.write_text("changed\n", encoding="utf-8")

    publish.restore_release_files(snapshot)

    assert pyproject.read_text(encoding="utf-8") == 'version = "0.14"\n'
    assert changelog.read_text(encoding="utf-8") == "## Unreleased\n\n- Notes\n"
