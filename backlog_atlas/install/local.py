from __future__ import annotations

import os
import sys
from pathlib import Path

from .. import config as app_config
from . import artifacts, github, repo
from .commands import run_command
from .constants import BACKLOG_BRANCH
from .models import InstallSource, describe_install_source, install_commit_message

ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_COMMAND = "\033[36m"
ANSI_URL = "\033[36;4m"


def color_enabled() -> bool:
    if "NO_COLOR" in os.environ:
        return False
    if os.environ.get("CLICOLOR_FORCE") not in {None, "", "0"}:
        return True
    if os.environ.get("FORCE_COLOR") not in {None, "", "0"}:
        return True
    if os.environ.get("CLICOLOR") == "0":
        return False
    return sys.stdout.isatty()


def style(text: str, ansi_code: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{ansi_code}{text}{ANSI_RESET}"


def ensure_worktree_clean(target_root: Path, vcs: str) -> bool:
    if vcs == "sl":
        output = run_command(["sl", "status"], cwd=target_root)
    elif vcs == "git":
        output = run_command(["git", "status", "--porcelain"], cwd=target_root)
    else:
        raise RuntimeError(f"unsupported VCS: {vcs}")

    if output.strip():
        print(
            f"error: {target_root} has uncommitted changes; "
            "commit or stash them before continuing",
            file=sys.stderr,
        )
        return False
    return True


def add_local_install_files(
    target_root: Path, artifact_paths: list[Path], vcs: str
) -> None:
    if not artifact_paths:
        return
    rel_paths = [path.relative_to(target_root).as_posix() for path in artifact_paths]
    if vcs == "sl":
        run_command(["sl", "addremove", *rel_paths], cwd=target_root)
    elif vcs == "git":
        run_command(["git", "add", "-A", "--", *rel_paths], cwd=target_root)
    else:
        raise RuntimeError(f"unsupported VCS: {vcs}")


def commit_local_files(
    target_root: Path, artifact_paths: list[Path], vcs: str, message: str
) -> None:
    if not artifact_paths:
        return
    rel_paths = [path.relative_to(target_root).as_posix() for path in artifact_paths]
    if vcs == "sl":
        run_command(["sl", "commit", "-m", message, *rel_paths], cwd=target_root)
        return
    if vcs == "git":
        run_command(
            ["git", "commit", "-m", message, "--only", "--", *rel_paths],
            cwd=target_root,
        )
        return
    raise RuntimeError(f"unsupported VCS: {vcs}")


def local_review_command(vcs: str) -> str:
    if vcs == "sl":
        return "sl show --stat"
    if vcs == "git":
        return "git show --stat HEAD"
    raise RuntimeError(f"unsupported VCS: {vcs}")


def local_push_command(vcs: str, on_default: bool | None) -> str:
    if vcs == "sl":
        return "sl push"
    if vcs == "git":
        return "git push" if on_default is True else "git push -u origin HEAD"
    raise RuntimeError(f"unsupported VCS: {vcs}")


def print_local_install_next_steps(repo_name: str, target_root: Path, vcs: str) -> None:
    color = color_enabled()
    print()
    print(style("Next steps:", ANSI_BOLD, color))
    on_default = repo.is_on_default_branch(target_root, vcs)
    if Path.cwd().resolve() != target_root.resolve():
        print(style(f"cd {target_root}", ANSI_COMMAND, color))
        print()
    print(style("# Review the install commit.", ANSI_DIM, color))
    print(style(local_review_command(vcs), ANSI_COMMAND, color))
    print()
    print(style("# Push when ready.", ANSI_DIM, color))
    print(style(local_push_command(vcs, on_default), ANSI_COMMAND, color))
    print()
    if on_default is False:
        print(
            style(
                "# Open or merge a PR for this install commit before continuing.",
                ANSI_DIM,
                color,
            )
        )
        print()
    elif on_default is None:
        print(
            style(
                "# If this is not the default branch, merge the install commit first.",
                ANSI_DIM,
                color,
            )
        )
        print()
    print(style("# Trigger the first Backlog Atlas run.", ANSI_DIM, color))
    print(
        style(
            f"gh workflow run 'Update Backlog Atlas' --repo {repo_name}",
            ANSI_COMMAND,
            color,
        )
    )
    print()
    print(
        style(
            "# Enable Pages from the backlog-atlas branch, folder /.", ANSI_DIM, color
        )
    )
    print(style(f"# https://github.com/{repo_name}/settings/pages", ANSI_URL, color))


def print_local_uninstall_next_steps(target_root: Path, vcs: str) -> None:
    color = color_enabled()
    print()
    print(style("Next steps:", ANSI_BOLD, color))
    on_default = repo.is_on_default_branch(target_root, vcs)
    if Path.cwd().resolve() != target_root.resolve():
        print(style(f"cd {target_root}", ANSI_COMMAND, color))
        print()
    print(style("# Review the uninstall commit.", ANSI_DIM, color))
    print(style(local_review_command(vcs), ANSI_COMMAND, color))
    print()
    print(style("# Push when ready.", ANSI_DIM, color))
    print(style(local_push_command(vcs, on_default), ANSI_COMMAND, color))
    print()
    if on_default is False:
        print(
            style(
                "# Open or merge a PR for this uninstall commit before continuing.",
                ANSI_DIM,
                color,
            )
        )
    elif on_default is None:
        print(
            style(
                "# If this is not the default branch, merge the uninstall commit first.",
                ANSI_DIM,
                color,
            )
        )


def print_local_install_plan(
    repo_name: str,
    target_root: Path,
    install_source: InstallSource,
    vcs: str,
    force: bool = False,
    cleanup_old_bundled_packages: bool = False,
) -> None:
    print("Dry run: would install Backlog Atlas locally")
    print("No files would be written and no GitHub calls would be made.")
    print(f"Target repo: {repo_name}")
    print(f"Target working tree: {target_root}")
    print(f"Workflow would install Backlog Atlas from: {install_source.pip_spec}")
    if force:
        print(
            "Would skip the clean working tree requirement because --force was provided."
        )
    else:
        print("Would require a clean working tree.")
    if install_source.bundled_wheel_path:
        action = (
            "Would build and upload bundled wheel"
            if install_source.bundled_wheel_content is None
            else "Would upload bundled wheel"
        )
        print(f"{action} to {BACKLOG_BRANCH}: " f"{install_source.bundled_wheel_path}")
    print("Would first remove previous install hooks/manifests if present.")
    if cleanup_old_bundled_packages:
        print(
            "Would write a temporary upgrade cleanup workflow that removes old "
            "bundled wheels after the install lands."
        )
    print("Would write or update:")
    print(f"  - {artifacts.find_workflow_target(target_root)}")
    print(f"  - {artifacts.find_install_manifest_target(target_root)}")
    print(
        f"  - {artifacts.find_app_config_target(target_root)} "
        "(created only if missing)"
    )
    if cleanup_old_bundled_packages:
        print(f"  - {artifacts.find_upgrade_cleanup_workflow_target(target_root)}")
    print(f"Would add and commit install artifact(s) with {vcs}.")
    print("Would print review, push, workflow trigger, and Pages setup next steps.")


def run_local_install(
    repo_name: str,
    target_root: Path,
    install_source: InstallSource,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    vcs = repo.detect_local_vcs(target_root)
    old_bundled_package_paths = artifacts.installed_bundled_package_paths(target_root)
    cleanup_package_paths = artifacts.bundled_package_paths_to_cleanup(
        install_source,
        old_bundled_package_paths,
    )
    config_path = artifacts.find_app_config_target(target_root)
    if config_path.exists():
        app_config.validate_config_file(config_path)
    if dry_run:
        print_local_install_plan(
            repo_name,
            target_root,
            install_source,
            vcs,
            force=force,
            cleanup_old_bundled_packages=bool(cleanup_package_paths),
        )
        return 0

    if force:
        print(f"Skipping working tree cleanliness check for {target_root} (--force)")
    else:
        print(f"Checking working tree at {target_root}")
        if ensure_worktree_clean(target_root, vcs) is False:
            return 1
        print("Working tree is clean")

    print(f"Target repo: {repo_name}")
    print(f"Target working tree: {target_root}")
    print(f"Workflow will install Backlog Atlas from: {install_source.pip_spec}")
    print(f"Resolved install: {describe_install_source(install_source)}")
    workflow_blocks_install = artifacts.workflow_blocks_install(
        target_root,
        install_source,
        force=force,
    )
    if not workflow_blocks_install:
        github.ensure_backlog_branch_with_bundle(repo_name, install_source)

    if workflow_blocks_install:
        removed_paths = []
    else:
        removed_paths = artifacts.remove_install_artifacts(target_root)
        legacy_metadata_path = artifacts.remove_legacy_install_metadata(target_root)
        if legacy_metadata_path is not None:
            removed_paths.append(legacy_metadata_path)
    if removed_paths:
        print("Removed previous Backlog Atlas install hook/manifest files")

    result = artifacts.write_install_artifacts(
        target_root,
        install_source,
        force=force,
        old_bundled_package_paths=old_bundled_package_paths,
    )
    print("Checked install workflow and manifest")
    changed_paths = unique_paths([*result.changed_paths, *removed_paths])
    if changed_paths:
        if result.workflow_path in result.changed_paths:
            print(f"wrote workflow to {result.workflow_path}")
        else:
            print(f"workflow already exists at {result.workflow_path}")
        if result.manifest_path in result.changed_paths:
            print(f"wrote install manifest to {result.manifest_path}")
        if config_path in result.changed_paths:
            print(f"wrote editable config to {config_path}")
        if result.upgrade_cleanup_path in result.changed_paths:
            if cleanup_package_paths:
                print(
                    "wrote temporary upgrade cleanup workflow to "
                    f"{result.upgrade_cleanup_path}"
                )
            else:
                print(
                    "removed temporary upgrade cleanup workflow from "
                    f"{result.upgrade_cleanup_path}"
                )
        add_local_install_files(target_root, changed_paths, vcs)
        print(f"added install artifact(s) with {vcs}")
        commit_local_files(
            target_root,
            changed_paths,
            vcs,
            install_commit_message(install_source),
        )
        print("created install commit")
        print_local_install_next_steps(repo_name, target_root, vcs)
    else:
        print(f"workflow already exists at {result.workflow_path}")
        if result.workflow_matches:
            print(f"install manifest already exists at {result.manifest_path}")
            print("\nNothing to do - Backlog Atlas is already installed in this repo.")
        else:
            print(
                "left install manifest unchanged because the existing workflow "
                "differs from the generated workflow"
            )
            print("\nNothing changed.")
    return 0


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique
