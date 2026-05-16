from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .commands import read_text
from .constants import (
    BACKLOG_BRANCH,
    INSTALL_METADATA_RELATIVE_PATH,
    INSTALL_METADATA_SCHEMA_VERSION,
    UNINSTALL_WORKFLOW_TEMPLATE_PATH,
    WORKFLOW_RELATIVE_PATH,
    WORKFLOW_TEMPLATE_PATH,
)
from .models import InstallSource


@dataclass
class InstallArtifactResult:
    workflow_path: Path
    metadata_path: Path
    changed_paths: list[Path]
    workflow_matches: bool


def load_workflow_template(install_from: str) -> str:
    return (
        read_text(WORKFLOW_TEMPLATE_PATH)
        .replace("__BACKLOG_ATLAS_PIP__", install_from)
        .replace("__BACKLOG_ATLAS_BRANCH__", BACKLOG_BRANCH)
    )


def load_uninstall_workflow_template(delete_branch: bool) -> str:
    return (
        read_text(UNINSTALL_WORKFLOW_TEMPLATE_PATH)
        .replace("__BACKLOG_ATLAS_BRANCH__", BACKLOG_BRANCH)
        .replace("__BACKLOG_ATLAS_DELETE_BRANCH__", str(delete_branch).lower())
    )


def find_workflow_target(target_repo_root: Path) -> Path:
    return target_repo_root / WORKFLOW_RELATIVE_PATH


def find_install_metadata_target(target_repo_root: Path) -> Path:
    return target_repo_root / INSTALL_METADATA_RELATIVE_PATH


def build_install_metadata(install_source: InstallSource) -> str:
    metadata = {
        "schema_version": INSTALL_METADATA_SCHEMA_VERSION,
        "tool": "backlog-atlas",
        "installed_version": install_source.version,
        "install_source": install_source.pip_spec,
        "source_type": install_source.source_type,
        "workflow_path": WORKFLOW_RELATIVE_PATH,
    }
    if install_source.bundled_wheel_path:
        metadata["bundled_wheel_path"] = install_source.bundled_wheel_path
    return json.dumps(metadata, indent=2, sort_keys=True) + "\n"


def write_text_artifact(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def is_managed_workflow(content: str) -> bool:
    return (
        "name: Update Backlog Atlas" in content
        and "BACKLOG_ATLAS_PIP" in content
        and "backlog-atlas update" in content
    )


def write_install_artifacts(
    target_root: Path, install_source: InstallSource
) -> InstallArtifactResult:
    wf_path = find_workflow_target(target_root)
    metadata_path = find_install_metadata_target(target_root)
    changed_paths = []
    workflow_content = load_workflow_template(install_source.pip_spec)

    if wf_path.exists():
        current_workflow = wf_path.read_text(encoding="utf-8")
        workflow_matches = current_workflow == workflow_content
        if not workflow_matches and is_managed_workflow(current_workflow):
            if write_text_artifact(wf_path, workflow_content):
                changed_paths.append(wf_path)
            workflow_matches = True
    else:
        workflow_matches = True
        if write_text_artifact(wf_path, workflow_content):
            changed_paths.append(wf_path)

    if workflow_matches and write_text_artifact(
        metadata_path, build_install_metadata(install_source)
    ):
        changed_paths.append(metadata_path)
    return InstallArtifactResult(
        workflow_path=wf_path,
        metadata_path=metadata_path,
        changed_paths=changed_paths,
        workflow_matches=workflow_matches,
    )
