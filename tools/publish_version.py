#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
DEFAULT_REPO = "omry/backlog-atlas"
DEFAULT_TARGET = "main"


class ReleaseError(RuntimeError):
    pass


def run(args: list[str], *, capture: bool = False) -> str:
    print(f"+ {shlex.join(args)}")
    completed = subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=capture,
    )
    if completed.returncode != 0:
        details = ""
        if capture:
            details = (completed.stderr or completed.stdout).strip()
        raise ReleaseError(
            f"{shlex.join(args)} failed"
            + (f": {details}" if details else f" with exit code {completed.returncode}")
        )
    return completed.stdout if capture else ""


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise ReleaseError(f"required command not found: {name}")


def current_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
    if not match:
        raise ReleaseError("could not find project version in pyproject.toml")
    return match.group(1)


def suggest_next_version(version: str) -> str:
    parts = version.split(".")
    if not parts or not all(part.isdigit() for part in parts):
        raise ReleaseError(
            f"cannot suggest next version from {version!r}; pass a version explicitly"
        )
    numbers = [int(part) for part in parts]
    numbers[-1] += 1
    return ".".join(str(part) for part in numbers)


def validate_version(version: str) -> None:
    if not re.fullmatch(r"\d+(?:\.\d+){1,2}", version):
        raise ReleaseError(
            f"{version!r} is not a supported release version; use N.N or N.N.N"
        )


def set_pyproject_version(version: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'^version = "[^"]+"$',
        f'version = "{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise ReleaseError("could not update project version in pyproject.toml")
    PYPROJECT.write_text(updated, encoding="utf-8")


def section_body(text: str, heading: str) -> str | None:
    match = re.search(
        rf"(?ms)^## {re.escape(heading)}\n(?P<body>.*?)(?=^## |\Z)",
        text,
    )
    if not match:
        return None
    return match.group("body").strip()


def update_changelog_for_release(version: str) -> tuple[str, bool]:
    text = CHANGELOG.read_text(encoding="utf-8")
    existing_notes = section_body(text, version)
    if existing_notes:
        return existing_notes, False

    match = re.search(r"(?ms)^## Unreleased\n(?P<body>.*?)(?=^## |\Z)", text)
    if not match:
        raise ReleaseError("CHANGELOG.md is missing an Unreleased section")

    notes = match.group("body").strip()
    if not notes or notes == "- Nothing yet.":
        raise ReleaseError(
            "CHANGELOG.md has no Unreleased notes to publish; add release notes first"
        )

    replacement = f"## Unreleased\n\n- Nothing yet.\n\n## {version}\n\n{notes}\n\n"
    updated = text[: match.start()] + replacement + text[match.end() :].lstrip("\n")
    CHANGELOG.write_text(updated, encoding="utf-8")
    return notes, True


def status_entries() -> list[tuple[str, str]]:
    status = run(["sl", "status"], capture=True).strip()
    entries: list[tuple[str, str]] = []
    for line in status.splitlines():
        if not line.strip():
            continue
        state, path = line.split(maxsplit=1)
        entries.append((state, path))
    return entries


def ensure_no_unrelated_changes(allowed_paths: set[str]) -> None:
    unrelated = [
        f"{state} {path}"
        for state, path in status_entries()
        if path not in allowed_paths
    ]
    if unrelated:
        formatted = "\n".join(f"  {entry}" for entry in unrelated)
        raise ReleaseError(
            "working tree has changes outside release files:\n"
            f"{formatted}\n"
            "commit or shelve unrelated changes first"
        )


def release_files_changed() -> bool:
    return any(
        path in {"CHANGELOG.md", "pyproject.toml"} for _state, path in status_entries()
    )


def confirm(version: str) -> None:
    answer = input(f"Publish Backlog Atlas {version} to PyPI? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise ReleaseError("release cancelled")


def write_release_notes(notes: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        delete=False,
        prefix="backlog-atlas-release-",
        suffix=".md",
    )
    with tmp:
        tmp.write(notes.strip() + "\n")
    return Path(tmp.name)


def print_plan(current: str, target: str, repo: str, target_branch: str) -> None:
    print(f"Current version: {current}")
    print(f"Suggested next version: {suggest_next_version(current)}")
    print(f"Target version: {target}")
    print()
    print("This will:")
    if target != current:
        print(f"  - update pyproject.toml to {target}")
        print(f"  - move CHANGELOG.md Unreleased notes to {target}")
    else:
        print("  - publish the current pyproject.toml version")
    print("  - run formatting, lint, type, test, and build checks")
    if target != current:
        print(f"  - commit release prep as: release: bump Backlog Atlas to {target}")
    else:
        print("  - use the current commit as the release commit")
    print("  - push the commit")
    print(f"  - create GitHub Release v{target} in {repo}")
    print("  - let the GitHub Action publish to PyPI via Trusted Publishing")
    print(f"  - target the release at {target_branch}")
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare and publish a Backlog Atlas release."
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="Version to publish. Defaults to incrementing the current version.",
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"GitHub repository for the release (default: {DEFAULT_REPO}).",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=f"GitHub release target branch or commit (default: {DEFAULT_TARGET}).",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the release plan without changing files or publishing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        current = current_version()
        target = args.version or suggest_next_version(current)
        validate_version(target)

        print_plan(current, target, args.repo, args.target)
        if args.dry_run:
            print("Dry run: no files changed and no commands executed.")
            return 0

        require_tool("sl")
        require_tool("gh")

        if not args.yes:
            confirm(target)

        ensure_no_unrelated_changes({"CHANGELOG.md", "pyproject.toml"})

        if target != current:
            set_pyproject_version(target)
        notes, changelog_changed = update_changelog_for_release(target)

        run(
            [
                sys.executable,
                "-m",
                "black",
                "--check",
                "backlog_atlas",
                "tests",
                "tools",
            ]
        )
        run([sys.executable, "-m", "pyflakes", "backlog_atlas", "tests", "tools"])
        run([sys.executable, "-m", "mypy"])
        run([sys.executable, "-m", "pytest"])
        run([sys.executable, "-m", "build", "--wheel", "--sdist"])

        if changelog_changed or release_files_changed():
            run(["sl", "add", "pyproject.toml", "CHANGELOG.md"])
            run(["sl", "commit", "-m", f"release: bump Backlog Atlas to {target}"])
        run(["sl", "push"])

        notes_path = write_release_notes(notes)
        try:
            run(
                [
                    "gh",
                    "release",
                    "create",
                    f"v{target}",
                    "--repo",
                    args.repo,
                    "--target",
                    args.target,
                    "--title",
                    f"Backlog Atlas {target}",
                    "--notes-file",
                    str(notes_path),
                ]
            )
        finally:
            notes_path.unlink(missing_ok=True)

        print()
        print(f"Published GitHub Release v{target}.")
        print("PyPI publishing is now running in GitHub Actions.")
        print(f"Watch: https://github.com/{args.repo}/actions/workflows/publish.yml")
        return 0
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
