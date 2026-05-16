from __future__ import annotations

import sys
from pathlib import Path

from . import artifacts, github, repo
from .commands import run_command
from .constants import BACKLOG_BRANCH
from .models import InstallSource, describe_install_source, install_commit_message


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
            "commit or stash them before installing",
            file=sys.stderr,
        )
        return False
    return True


def add_local_install_files(
    target_root: Path, artifact_paths: list[Path], vcs: str
) -> None:
    rel_paths = [path.relative_to(target_root).as_posix() for path in artifact_paths]
    if vcs == "sl":
        run_command(["sl", "add", *rel_paths], cwd=target_root)
    elif vcs == "git":
        run_command(["git", "add", *rel_paths], cwd=target_root)
    else:
        raise RuntimeError(f"unsupported VCS: {vcs}")


def local_install_commands(
    vcs: str, on_default: bool | None, install_source: InstallSource
) -> list[str]:
    commit_msg = f'"{install_commit_message(install_source)}"'
    if vcs == "sl":
        return [f"sl commit -m {commit_msg}", "sl push"]
    if vcs == "git":
        push = "git push" if on_default is True else "git push -u origin HEAD"
        return [f"git commit -m {commit_msg}", push]
    raise RuntimeError(f"unsupported VCS: {vcs}")


def print_local_install_next_steps(
    repo_name: str, target_root: Path, vcs: str, install_source: InstallSource
) -> None:
    print()
    print("Next steps:")
    on_default = repo.is_on_default_branch(target_root, vcs)
    print(f"  - from {target_root}, run:")
    for command in local_install_commands(vcs, on_default, install_source):
        print(f"      {command}")
    if on_default is True:
        print("  - the install commit will be on the default branch")
    elif on_default is False:
        print("  - open or merge a PR for the install commit")
    else:
        print("  - use a PR for the install commit if this is not the default branch")
    print(
        "  - after it lands on the default branch, trigger once: "
        f"gh workflow run 'Update Backlog Atlas' --repo {repo_name}"
    )
    print(f"    (the workflow creates the {BACKLOG_BRANCH} branch if needed)")
    print(
        f"  - enable Pages: https://github.com/{repo_name}/settings/pages "
        f"(branch: {BACKLOG_BRANCH}, folder: /)"
    )


def print_local_install_plan(
    repo_name: str,
    target_root: Path,
    install_source: InstallSource,
    vcs: str,
    force: bool = False,
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
    print("Would write or update:")
    print(f"  - {artifacts.find_workflow_target(target_root)}")
    print(f"  - {artifacts.find_install_metadata_target(target_root)}")
    print(f"Would add install artifact(s) with {vcs}.")
    print("Would print commit, push, workflow trigger, and Pages setup next steps.")


def run_local_install(
    repo_name: str,
    target_root: Path,
    install_source: InstallSource,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    vcs = repo.detect_local_vcs(target_root)
    if dry_run:
        print_local_install_plan(
            repo_name, target_root, install_source, vcs, force=force
        )
        return 0

    if force:
        print(f"Skipping working tree cleanliness check for {target_root} (--force)")
    else:
        print(f"Checking working tree at {target_root}")
        if ensure_worktree_clean(target_root, vcs) is False:
            return 1
        print("Working tree is clean")
    github.ensure_backlog_branch_with_bundle(repo_name, install_source)

    print(f"Target repo: {repo_name}")
    print(f"Target working tree: {target_root}")
    print(f"Workflow will install Backlog Atlas from: {install_source.pip_spec}")
    print(f"Resolved install: {describe_install_source(install_source)}")

    result = artifacts.write_install_artifacts(target_root, install_source, force=force)
    print("Checked install workflow and metadata")
    if result.changed_paths:
        if result.workflow_path in result.changed_paths:
            print(f"wrote workflow to {result.workflow_path}")
        else:
            print(f"workflow already exists at {result.workflow_path}")
        if result.metadata_path in result.changed_paths:
            print(f"wrote install metadata to {result.metadata_path}")
        add_local_install_files(target_root, result.changed_paths, vcs)
        print(f"added install artifact(s) with {vcs}")
        print_local_install_next_steps(repo_name, target_root, vcs, install_source)
    else:
        print(f"workflow already exists at {result.workflow_path}")
        if result.workflow_matches:
            print(f"install metadata already exists at {result.metadata_path}")
            print("\nNothing to do - Backlog Atlas is already installed in this repo.")
        else:
            print(
                "left install metadata unchanged because the existing workflow "
                "differs from the generated workflow"
            )
            print("\nNothing changed.")
    return 0
