from __future__ import annotations

from pathlib import Path

from . import artifacts, github, repo
from .commands import run_command
from .constants import (
    BACKLOG_BRANCH,
    INSTALL_COMMIT_MESSAGE,
)
from .models import InstallSource


def ensure_worktree_clean(target_root: Path, vcs: str) -> None:
    if vcs == "sl":
        output = run_command(["sl", "status"], cwd=target_root)
    elif vcs == "git":
        output = run_command(["git", "status", "--porcelain"], cwd=target_root)
    else:
        raise RuntimeError(f"unsupported VCS: {vcs}")

    if output.strip():
        raise RuntimeError(
            f"{target_root} has uncommitted changes; commit or stash them before installing"
        )


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


def local_install_commands(vcs: str, on_default: bool | None) -> list[str]:
    commit_msg = f'"{INSTALL_COMMIT_MESSAGE}"'
    if vcs == "sl":
        return [f"sl commit -m {commit_msg}", "sl push"]
    if vcs == "git":
        push = "git push" if on_default is True else "git push -u origin HEAD"
        return [f"git commit -m {commit_msg}", push]
    raise RuntimeError(f"unsupported VCS: {vcs}")


def print_local_install_next_steps(repo_name: str, target_root: Path, vcs: str) -> None:
    print()
    print("Next steps:")
    on_default = repo.is_on_default_branch(target_root, vcs)
    print(f"  - from {target_root}, run:")
    for command in local_install_commands(vcs, on_default):
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


def run_local_install(
    repo_name: str, target_root: Path, install_source: InstallSource
) -> int:
    vcs = repo.detect_local_vcs(target_root)
    ensure_worktree_clean(target_root, vcs)
    github.ensure_backlog_branch_with_bundle(repo_name, install_source)

    print(f"Target repo: {repo_name}")
    print(f"Target working tree: {target_root}")
    print(f"Workflow will install Backlog Atlas from: {install_source.pip_spec}")

    result = artifacts.write_install_artifacts(target_root, install_source)
    if result.changed_paths:
        if result.workflow_path in result.changed_paths:
            print(f"wrote workflow to {result.workflow_path}")
        else:
            print(f"workflow already exists at {result.workflow_path}")
        if result.metadata_path in result.changed_paths:
            print(f"wrote install metadata to {result.metadata_path}")
        add_local_install_files(target_root, result.changed_paths, vcs)
        print(f"added install artifact(s) with {vcs}")
        print_local_install_next_steps(repo_name, target_root, vcs)
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
