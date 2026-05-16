from __future__ import annotations

import argparse
from pathlib import Path

from ..errors import UserError
from . import artifacts, github, local, repo, sources
from .constants import BACKLOG_BRANCH


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

    install_source = sources.resolve_install_source(
        args.install_from, dry_run=args.dry_run
    )
    if args.repo:
        repo_name = repo.resolve_repo(args.repo)
        return github.run_remote_install(
            repo_name, install_source, args.delivery or "pr", dry_run=args.dry_run
        )

    target_root = (
        Path(args.target_root) if args.target_root else repo.detect_target_root()
    )
    repo_name = repo.resolve_repo(None, target_root)
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
    delete_branch = bool(args.delete_branch)

    print(f"Target repo: {repo_name}")
    print(f"Target working tree: {target_root}")

    if delete_branch and not args.yes:
        print("\nThis will:")
        print(
            "  - write a one-shot uninstall workflow that deletes "
            f"the {BACKLOG_BRANCH} branch on GitHub"
        )
        print("  - make that workflow remove itself after it runs")
        try:
            confirm = input("\nProceed? [y/N] ").strip().lower()
        except EOFError:
            confirm = ""
        if confirm not in {"y", "yes"}:
            print("Aborted.")
            return 1

    wf_path = artifacts.find_workflow_target(target_root)
    if not wf_path.exists() and not delete_branch:
        print("\nNothing to do - Backlog Atlas workflow is not installed.")
        return 0

    wf_content = artifacts.load_uninstall_workflow_template(delete_branch)
    wf_path.parent.mkdir(parents=True, exist_ok=True)
    wf_path.write_text(wf_content, encoding="utf-8")
    print(f"wrote one-shot uninstall workflow to {wf_path}")

    print()
    print("Next steps:")
    print(f"  - commit & push the uninstall workflow in {target_root}")
    print(
        f"  - the workflow will remove {wf_path.relative_to(target_root)} after it runs"
    )
    if delete_branch:
        print(f"  - the workflow will delete the {BACKLOG_BRANCH} branch")
    else:
        print(
            f"  - the workflow will keep the {BACKLOG_BRANCH} branch and log that the hook was uninstalled"
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
        help="For remote installs, create an install PR or push to the default branch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what install would do without writing files or calling GitHub.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="For local installs, proceed even when the target working tree is dirty.",
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
        help="Have the one-shot uninstall workflow delete the backlog-atlas branch.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompt when --delete-branch is used.",
    )
