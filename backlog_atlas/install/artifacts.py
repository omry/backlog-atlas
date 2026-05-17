from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .commands import read_text
from .constants import (
    APP_CONFIG_RELATIVE_PATH,
    BACKLOG_BRANCH,
    BUNDLED_PACKAGE_DIR,
    INSTALL_MANIFEST_RELATIVE_PATH,
    INSTALL_MANIFEST_SCHEMA_VERSION,
    INSTALL_METADATA_RELATIVE_PATH,
    UNINSTALL_WORKFLOW_TEMPLATE_PATH,
    UPGRADE_CLEANUP_WORKFLOW_RELATIVE_PATH,
    UPGRADE_CLEANUP_WORKFLOW_TEMPLATE_PATH,
    WORKFLOW_RELATIVE_PATH,
    WORKFLOW_TEMPLATE_PATH,
)
from .models import InstallSource


@dataclass
class InstallArtifactResult:
    workflow_path: Path
    manifest_path: Path
    upgrade_cleanup_path: Path
    changed_paths: list[Path]
    workflow_matches: bool


LEGACY_UNINSTALL_RELATIVE_PATHS = (
    INSTALL_METADATA_RELATIVE_PATH,
    INSTALL_MANIFEST_RELATIVE_PATH,
    UPGRADE_CLEANUP_WORKFLOW_RELATIVE_PATH,
    WORKFLOW_RELATIVE_PATH,
)

LEGACY_CLEAN_UNINSTALL_RELATIVE_PATHS = (
    *LEGACY_UNINSTALL_RELATIVE_PATHS,
    APP_CONFIG_RELATIVE_PATH,
)


def load_workflow_template(install_from: str) -> str:
    return (
        read_text(WORKFLOW_TEMPLATE_PATH)
        .replace("__BACKLOG_ATLAS_PIP__", install_from)
        .replace("__BACKLOG_ATLAS_BRANCH__", BACKLOG_BRANCH)
    )


def load_uninstall_workflow_template(clean: bool) -> str:
    return (
        read_text(UNINSTALL_WORKFLOW_TEMPLATE_PATH)
        .replace("__BACKLOG_ATLAS_BRANCH__", BACKLOG_BRANCH)
        .replace("__BACKLOG_ATLAS_CLEAN_UNINSTALL__", str(clean).lower())
    )


def yaml_single_quoted(value: str) -> str:
    return value.replace("'", "''")


def load_upgrade_cleanup_workflow_template(
    remove_package_paths: list[str] | None = None,
) -> str:
    remove_package_paths = remove_package_paths or []
    return (
        read_text(UPGRADE_CLEANUP_WORKFLOW_TEMPLATE_PATH)
        .replace("__BACKLOG_ATLAS_BRANCH__", BACKLOG_BRANCH)
        .replace(
            "__BACKLOG_ATLAS_CLEANUP_WORKFLOW__",
            UPGRADE_CLEANUP_WORKFLOW_RELATIVE_PATH,
        )
        .replace(
            "__BACKLOG_ATLAS_REMOVE_PACKAGES_JSON__",
            yaml_single_quoted(json.dumps(remove_package_paths)),
        )
    )


def find_workflow_target(target_repo_root: Path) -> Path:
    return target_repo_root / WORKFLOW_RELATIVE_PATH


def find_upgrade_cleanup_workflow_target(target_repo_root: Path) -> Path:
    return target_repo_root / UPGRADE_CLEANUP_WORKFLOW_RELATIVE_PATH


def find_install_manifest_target(target_repo_root: Path) -> Path:
    return target_repo_root / INSTALL_MANIFEST_RELATIVE_PATH


def build_install_manifest(
    install_source: InstallSource, include_upgrade_cleanup: bool
) -> str:
    install = {
        "installed_version": install_source.version,
        "install_source": install_source.pip_spec,
        "source_type": install_source.source_type,
        "workflow_path": WORKFLOW_RELATIVE_PATH,
    }
    if install_source.bundled_wheel_path:
        install["bundled_wheel_path"] = install_source.bundled_wheel_path
    manifest = {
        "schema_version": INSTALL_MANIFEST_SCHEMA_VERSION,
        "tool": "backlog-atlas",
        "install": install,
        "files": install_manifest_entries(
            install_source,
            include_upgrade_cleanup=include_upgrade_cleanup,
        ),
    }
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def install_manifest_entries(
    install_source: InstallSource, include_upgrade_cleanup: bool
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = [
        {
            "path": WORKFLOW_RELATIVE_PATH,
            "branch": "default",
            "remove": "uninstall",
        },
        {
            "path": INSTALL_MANIFEST_RELATIVE_PATH,
            "branch": "default",
            "remove": "uninstall",
        },
        {
            "path": APP_CONFIG_RELATIVE_PATH,
            "branch": "default",
            "remove": "clean",
            "optional": True,
        },
    ]
    if include_upgrade_cleanup:
        entries.append(
            {
                "path": UPGRADE_CLEANUP_WORKFLOW_RELATIVE_PATH,
                "branch": "default",
                "remove": "uninstall",
                "optional": True,
            }
        )
    if install_source.bundled_wheel_path:
        entries.append(
            {
                "path": install_source.bundled_wheel_path,
                "branch": BACKLOG_BRANCH,
                "remove": "uninstall",
            }
        )
    return entries


def parse_install_manifest(content: str) -> dict[str, object] | None:
    try:
        manifest = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(manifest, dict) or manifest.get("tool") != "backlog-atlas":
        return None
    files = manifest.get("files")
    if not isinstance(files, list):
        return None
    return manifest


def manifest_entries(content: str) -> list[dict[str, object]] | None:
    manifest = parse_install_manifest(content)
    if manifest is None:
        return None
    files = manifest.get("files")
    if not isinstance(files, list):
        return None
    entries = []
    for entry in files:
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def safe_manifest_relative_path(path: object) -> str | None:
    if not isinstance(path, str):
        return None
    if "\n" in path or path.startswith("/"):
        return None
    normalized = PurePosixPath(path).as_posix()
    if normalized in {"", "."}:
        return None
    if ".." in PurePosixPath(normalized).parts:
        return None
    return normalized


def manifest_paths_for_branch(
    content: str, branch: str, clean: bool = False
) -> list[str] | None:
    entries = manifest_entries(content)
    if entries is None:
        return None
    paths = []
    for entry in entries:
        if entry.get("branch") != branch:
            continue
        remove = entry.get("remove")
        if remove != "uninstall" and not (clean and remove == "clean"):
            continue
        path = safe_manifest_relative_path(entry.get("path"))
        if path is not None:
            paths.append(path)
    return paths


def manifest_default_branch_paths(content: str, clean: bool) -> list[str] | None:
    return manifest_paths_for_branch(content, "default", clean=clean)


def manifest_bundled_package_paths(content: str) -> list[str] | None:
    branch_paths = manifest_paths_for_branch(content, BACKLOG_BRANCH)
    if branch_paths is None:
        return None
    paths = []
    for path in branch_paths:
        if path.startswith(f"{BUNDLED_PACKAGE_DIR}/") and path.endswith(".whl"):
            paths.append(path)
    return paths


def bundled_package_paths_to_cleanup(
    install_source: InstallSource, installed_package_paths: list[str]
) -> list[str]:
    current_package_path = install_source.bundled_wheel_path
    cleanup_paths = []
    for path in installed_package_paths:
        safe_path = safe_manifest_relative_path(path)
        if safe_path is None:
            continue
        if safe_path == current_package_path:
            continue
        if safe_path.startswith(f"{BUNDLED_PACKAGE_DIR}/") and safe_path.endswith(
            ".whl"
        ):
            cleanup_paths.append(safe_path)
    return list(dict.fromkeys(cleanup_paths))


def installed_bundled_package_paths(target_root: Path) -> list[str]:
    manifest_path = find_install_manifest_target(target_root)
    if not manifest_path.exists() or manifest_path.is_dir():
        return []
    try:
        package_paths = manifest_bundled_package_paths(
            manifest_path.read_text(encoding="utf-8")
        )
    except UnicodeDecodeError:
        return []
    return package_paths or []


def write_text_artifact(path: Path, content: str, force: bool = False) -> bool:
    if not force and path.exists() and path.read_text(encoding="utf-8") == content:
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


def is_uninstall_workflow(content: str) -> bool:
    return "name: Uninstall Backlog Atlas" in content


def is_upgrade_cleanup_workflow(content: str) -> bool:
    return "name: Backlog Atlas Upgrade Cleanup" in content


def is_managed_json_artifact(path: Path) -> bool:
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    return isinstance(content, dict) and content.get("tool") == "backlog-atlas"


def is_removable_install_artifact(path: Path, rel_path: str) -> bool:
    if rel_path == WORKFLOW_RELATIVE_PATH:
        content = path.read_text(encoding="utf-8")
        return is_managed_workflow(content) or is_uninstall_workflow(content)
    if rel_path == UPGRADE_CLEANUP_WORKFLOW_RELATIVE_PATH:
        return is_upgrade_cleanup_workflow(path.read_text(encoding="utf-8"))
    if rel_path in {INSTALL_METADATA_RELATIVE_PATH, INSTALL_MANIFEST_RELATIVE_PATH}:
        return is_managed_json_artifact(path)
    return rel_path.startswith(".github/backlog-atlas/")


def legacy_uninstall_relative_paths(clean: bool = False) -> tuple[str, ...]:
    if clean:
        return LEGACY_CLEAN_UNINSTALL_RELATIVE_PATHS
    return LEGACY_UNINSTALL_RELATIVE_PATHS


def uninstall_relative_paths_from_manifest(target_root: Path, clean: bool) -> list[str]:
    manifest_path = find_install_manifest_target(target_root)
    if not manifest_path.exists() or manifest_path.is_dir():
        return list(legacy_uninstall_relative_paths(clean))
    try:
        paths = manifest_default_branch_paths(
            manifest_path.read_text(encoding="utf-8"),
            clean=clean,
        )
    except UnicodeDecodeError:
        paths = None
    if paths is None:
        return list(legacy_uninstall_relative_paths(clean))
    return paths


def remove_install_artifacts(target_root: Path, clean: bool = False) -> list[Path]:
    rel_paths = uninstall_relative_paths_from_manifest(target_root, clean=clean)
    removed_paths: list[Path] = []
    for rel_path in rel_paths:
        rel_path = safe_manifest_relative_path(rel_path) or ""
        if not rel_path:
            continue
        path = target_root / rel_path
        if not path.exists():
            continue
        if path.is_dir():
            continue
        if not is_removable_install_artifact(path, rel_path):
            continue
        path.unlink()
        removed_paths.append(path)
    return removed_paths


def remove_upgrade_cleanup_artifact(target_root: Path) -> Path | None:
    path = find_upgrade_cleanup_workflow_target(target_root)
    if not path.exists() or path.is_dir():
        return None
    try:
        if not is_upgrade_cleanup_workflow(path.read_text(encoding="utf-8")):
            return None
    except UnicodeDecodeError:
        return None
    path.unlink()
    return path


def remove_legacy_install_metadata(target_root: Path) -> Path | None:
    path = target_root / INSTALL_METADATA_RELATIVE_PATH
    if not path.exists() or path.is_dir():
        return None
    if not is_removable_install_artifact(path, INSTALL_METADATA_RELATIVE_PATH):
        return None
    path.unlink()
    return path


def has_install_artifacts(target_root: Path) -> bool:
    for rel_path in uninstall_relative_paths_from_manifest(target_root, clean=False):
        rel_path = safe_manifest_relative_path(rel_path) or ""
        if not rel_path:
            continue
        path = target_root / rel_path
        if (
            path.exists()
            and path.is_file()
            and is_removable_install_artifact(path, rel_path)
        ):
            return True
    return False


def workflow_blocks_install(
    target_root: Path, install_source: InstallSource, force: bool = False
) -> bool:
    if force:
        return False
    wf_path = find_workflow_target(target_root)
    if not wf_path.exists():
        return False
    try:
        current_workflow = wf_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return True
    workflow_content = load_workflow_template(install_source.pip_spec)
    return current_workflow != workflow_content and not is_managed_workflow(
        current_workflow
    )


def write_install_artifacts(
    target_root: Path,
    install_source: InstallSource,
    force: bool = False,
    old_bundled_package_paths: list[str] | None = None,
) -> InstallArtifactResult:
    old_bundled_package_paths = old_bundled_package_paths or []
    cleanup_package_paths = bundled_package_paths_to_cleanup(
        install_source,
        old_bundled_package_paths,
    )
    wf_path = find_workflow_target(target_root)
    manifest_path = find_install_manifest_target(target_root)
    upgrade_cleanup_path = find_upgrade_cleanup_workflow_target(target_root)
    changed_paths = []
    workflow_content = load_workflow_template(install_source.pip_spec)
    include_upgrade_cleanup = bool(cleanup_package_paths)

    if wf_path.exists():
        current_workflow = wf_path.read_text(encoding="utf-8")
        workflow_matches = current_workflow == workflow_content
        if force or (not workflow_matches and is_managed_workflow(current_workflow)):
            if write_text_artifact(wf_path, workflow_content, force=force):
                changed_paths.append(wf_path)
            workflow_matches = True
    else:
        workflow_matches = True
        if write_text_artifact(wf_path, workflow_content, force=force):
            changed_paths.append(wf_path)

    if workflow_matches and write_text_artifact(
        manifest_path,
        build_install_manifest(
            install_source,
            include_upgrade_cleanup=include_upgrade_cleanup,
        ),
        force=force,
    ):
        changed_paths.append(manifest_path)
    if workflow_matches:
        if include_upgrade_cleanup:
            cleanup_content = load_upgrade_cleanup_workflow_template(
                cleanup_package_paths
            )
            if write_text_artifact(upgrade_cleanup_path, cleanup_content, force=force):
                changed_paths.append(upgrade_cleanup_path)
        elif upgrade_cleanup_path.exists() and is_upgrade_cleanup_workflow(
            upgrade_cleanup_path.read_text("utf-8")
        ):
            upgrade_cleanup_path.unlink()
            changed_paths.append(upgrade_cleanup_path)
    return InstallArtifactResult(
        workflow_path=wf_path,
        manifest_path=manifest_path,
        upgrade_cleanup_path=upgrade_cleanup_path,
        changed_paths=changed_paths,
        workflow_matches=workflow_matches,
    )
