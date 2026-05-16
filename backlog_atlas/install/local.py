from __future__ import annotations

import os
import sys
from pathlib import Path

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
    color = color_enabled()
    print()
    print(style("Next steps:", ANSI_BOLD, color))
    on_default = repo.is_on_default_branch(target_root, vcs)
    if Path.cwd().resolve() != target_root.resolve():
        print(style(f"cd {target_root}", ANSI_COMMAND, color))
        print()
    print(style("# Commit and push the install files.", ANSI_DIM, color))
    for command in local_install_commands(vcs, on_default, install_source):
        print(style(command, ANSI_COMMAND, color))
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
