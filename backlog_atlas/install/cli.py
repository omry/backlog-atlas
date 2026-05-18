from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path

from ..errors import UserError
from . import artifacts, github, local, repo, sources
from .constants import BACKLOG_BRANCH


def install_output_context(verbose: bool):
    if verbose:
        return contextlib.nullcontext()
    return contextlib.redirect_stdout(io.StringIO())


def run_install(args: argparse.Namespace) -> int:
    if args.repo and args.target_root:
        raise UserError(
            "--repo and --target-root are mutually exclusive for install; "
            "use --repo for remote install or --target-root for local checkout install"
        )
    if args.repo and args.force:
        raise UserError(
            "--force only applies to local installs; remote installs do not "
            "inspect the working tree"
        )
    if args.delivery and not args.repo:
        raise UserError("--delivery only applies to remote installs with --repo")
    if args.repo and not args.delivery:
        raise UserError(
            "--delivery is required for remote installs with --repo; "
            "choose --delivery pr or --delivery push"
        )

    verbose = bool(args.verbose or args.dry_run)
    with install_output_context(verbose):
        install_source = sources.resolve_install_source(
            args.install_from, dry_run=args.dry_run
        )
    if args.repo:
        repo_name = repo.resolve_repo(args.repo)
        with install_output_context(verbose):
            return github.run_remote_install(
                repo_name,
                install_source,
                args.delivery,
                dry_run=args.dry_run,
            )

    target_root = (
        Path(args.target_root) if args.target_root else repo.detect_target_root()
    )
    repo_name = repo.resolve_repo(None, target_root)
    with install_output_context(verbose):
        return local.run_local_install(
            repo_name,
            target_root,
            install_source,
            dry_run=args.dry_run,
            force=args.force,
        )


def run_uninstall(args: argparse.Namespace) -> int:
    target_root = (
        Path(args.target_root) if args.target_root else repo.detect_target_root()
    )
    repo_name = repo.resolve_repo(args.repo, target_root)
    clean = bool(args.clean or args.delete_branch)
    vcs = repo.detect_local_vcs(target_root)

    print(f"Target repo: {repo_name}")
    print(f"Target working tree: {target_root}")

    if clean and not args.yes:
        print("\nThis will:")
        print(
            "  - write a one-shot clean uninstall workflow that deletes "
            f"the {BACKLOG_BRANCH} branch"
        )
        print("  - remove Backlog Atlas install config from the default branch")
        print("  - make that workflow remove itself after it runs")
        try:
            confirm = input("\nProceed? [y/N] ").strip().lower()
        except EOFError:
            confirm = ""
        if confirm not in {"y", "yes"}:
            print("Aborted.")
            return 1

    if args.force:
        print(f"Skipping working tree cleanliness check for {target_root} (--force)")
    else:
        print(f"Checking working tree at {target_root}")
        if local.ensure_worktree_clean(target_root, vcs) is False:
            return 1
        print("Working tree is clean")

    wf_path = artifacts.find_workflow_target(target_root)
    had_install_artifacts = artifacts.has_install_artifacts(target_root)
    changed_paths = []
    removed_cleanup_path = artifacts.remove_upgrade_cleanup_artifact(target_root)
    if removed_cleanup_path:
        changed_paths.append(removed_cleanup_path)
        print(f"removed temporary upgrade cleanup workflow from {removed_cleanup_path}")

    if not had_install_artifacts and not clean:
        print(
            "\nNo default-branch Backlog Atlas install artifacts were found; "
            "writing the one-shot cleanup workflow anyway in case generated "
            "branch artifacts remain."
        )

    wf_content = artifacts.load_uninstall_workflow_template(clean)
    if artifacts.write_text_artifact(wf_path, wf_content):
        changed_paths.append(wf_path)
        print(f"wrote one-shot uninstall workflow to {wf_path}")
    else:
        print(f"one-shot uninstall workflow already exists at {wf_path}")

    if not changed_paths:
        print("\nNothing to do - Backlog Atlas uninstall workflow is already present.")
        return 0

    local.add_local_install_files(target_root, changed_paths, vcs)
    message = (
        "backlog: clean uninstall Backlog Atlas workflow"
        if clean
        else "backlog: uninstall Backlog Atlas workflow"
    )
    local.commit_local_files(target_root, changed_paths, vcs, message)
    print("created uninstall commit")

    local.print_local_uninstall_next_steps(target_root, vcs)
    print()
    print(f"The workflow will remove {wf_path.relative_to(target_root)} after it runs.")
    if clean:
        print(
            f"The workflow will delete the {BACKLOG_BRANCH} branch and "
            "Backlog Atlas install config"
        )
    else:
        print(
            "The workflow will remove install manifests and bundled install "
            f"packages, then keep the {BACKLOG_BRANCH} branch, generated artifacts, "
            "and config"
        )
    return 0


def add_install_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        help=(
            "Repository URL. GitHub URLs are supported today; owner/name is "
            "accepted as GitHub shorthand. Installs remotely and cannot be "
            "combined with --target-root."
        ),
    )
    parser.add_argument(
        "--target-root",
        help=(
            "Target working tree root for local install. Cannot be combined "
            "with --repo. Defaults to detection via 'sl root' or "
            "'git rev-parse --show-toplevel' from cwd."
        ),
    )
    parser.add_argument(
        "--install-from",
        help=(
            "Where the generated GitHub Actions workflow installs Backlog Atlas "
            "from. Defaults to the source of the current CLI: pinned PyPI "
            "version for PyPI installs, or bundled wheel for local source "
            "installs. Use a "
            "pinned backlog-atlas==X.Y.Z spec or a local checkout path."
        ),
    )
    parser.add_argument(
        "--delivery",
        choices=["pr", "push"],
        help=(
            "Required for remote installs: create an install PR or push to the "
            "default branch."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print what install would do without writing files; remote dry runs "
            "verify GitHub access."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="For local installs, proceed even when the target working tree is dirty.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print install progress and next-step commands.",
    )


def add_uninstall_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        help=(
            "Repository URL. GitHub URLs are supported today; owner/name is "
            "accepted as GitHub shorthand. Auto-detected by default."
        ),
    )
    parser.add_argument("--target-root", help="Target working tree root.")
    parser.add_argument(
        "--delete-branch",
        action="store_true",
        help="Deprecated alias for --clean.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help=(
            "Clean uninstall: delete the backlog-atlas branch and Backlog Atlas "
            "install config."
        ),
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompt when --clean or --delete-branch is used.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Proceed even when the target working tree is dirty.",
    )
