from __future__ import annotations

import re
from pathlib import Path

from ..errors import UserError
from .commands import try_command


def parse_github_repo(url: str) -> str | None:
    text = (url or "").strip()
    patterns = [
        r"^(?:ssh://)?git@github\.com[:/](?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$",
        r"^https://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$",
        r"^git://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text)
        if match:
            return match.group("repo")
    return None


def normalize_github_repo(repo_or_url: str) -> str | None:
    text = (repo_or_url or "").strip()
    if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", text):
        return text
    return parse_github_repo(text)


def detect_repo_from_sl(cwd: Path | None = None) -> str | None:
    output = try_command(["sl", "paths"], cwd=cwd)
    if not output:
        return None
    for line in output.splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() not in {"default", "default-push"}:
            continue
        repo = parse_github_repo(value)
        if repo:
            return repo
    return None


def detect_repo_from_git(cwd: Path | None = None) -> str | None:
    for args in (
        ["git", "remote", "get-url", "origin"],
        ["git", "remote", "get-url", "upstream"],
    ):
        output = try_command(args, cwd=cwd)
        if not output:
            continue
        repo = parse_github_repo(output.strip())
        if repo:
            return repo
    return None


def resolve_repo(explicit_repo: str | None, cwd: Path | None = None) -> str:
    if explicit_repo:
        repo = normalize_github_repo(explicit_repo)
        if repo:
            return repo
        raise UserError(
            "unsupported --repo value; expected a GitHub repository URL like "
            "https://github.com/owner/name or the shorthand owner/name"
        )
    else:
        repo = detect_repo_from_sl(cwd) or detect_repo_from_git(cwd)
    if repo:
        return repo
    raise UserError(
        "could not determine repository; pass --repo https://github.com/owner/name "
        "(owner/name is accepted as GitHub shorthand), or ensure Git or Sapling "
        "remotes point at GitHub"
    )


def detect_target_root(cwd: Path | None = None) -> Path:
    cwd = (cwd or Path.cwd()).resolve()
    output = try_command(["sl", "root"], cwd=cwd)
    if output:
        candidate = Path(output.strip())
        if candidate.exists():
            return candidate
    output = try_command(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"])
    if output:
        candidate = Path(output.strip())
        if candidate.exists():
            return candidate
    return cwd


def detect_local_vcs(target_root: Path) -> str:
    output = try_command(["sl", "root"], cwd=target_root)
    if output:
        candidate = Path(output.strip())
        if candidate.exists() and candidate.resolve() == target_root.resolve():
            return "sl"

    output = try_command(["git", "rev-parse", "--show-toplevel"], cwd=target_root)
    if output:
        candidate = Path(output.strip())
        if candidate.exists() and candidate.resolve() == target_root.resolve():
            return "git"

    raise UserError(
        f"{target_root} is not a Git or Sapling working tree; run install inside "
        "a checkout or pass --repo for remote installation"
    )


def detect_current_branch(target_root: Path, vcs: str) -> str | None:
    if vcs == "sl":
        output = try_command(["sl", "branch"], cwd=target_root)
        if output:
            branch = output.strip()
            if branch:
                return branch
        output = try_command(["sl", "bookmarks"], cwd=target_root)
        if output:
            for line in output.splitlines():
                text = line.strip()
                if text.startswith("* "):
                    return text[2:].split()[0]
        return None

    if vcs == "git":
        output = try_command(["git", "branch", "--show-current"], cwd=target_root)
        branch = output.strip() if output else ""
        return branch or None

    raise RuntimeError(f"unsupported VCS: {vcs}")


def detect_default_branch(target_root: Path, vcs: str) -> str | None:
    if vcs == "sl":
        output = try_command(["sl", "bookmarks"], cwd=target_root)
        if output:
            bookmarks = set()
            for line in output.splitlines():
                text = line.strip()
                if text:
                    bookmarks.add(text.lstrip("* ").split()[0])
            for candidate in ("main", "master"):
                if candidate in bookmarks:
                    return candidate
        return None

    if vcs == "git":
        output = try_command(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"], cwd=target_root
        )
        if output:
            prefix = "refs/remotes/origin/"
            ref = output.strip()
            if ref.startswith(prefix):
                return ref[len(prefix) :]
        output = try_command(["git", "remote", "show", "origin"], cwd=target_root)
        if output:
            for line in output.splitlines():
                text = line.strip()
                if text.startswith("HEAD branch:"):
                    branch = text.split(":", 1)[1].strip()
                    if branch:
                        return branch
        for candidate in ("main", "master"):
            if try_command(
                ["git", "rev-parse", "--verify", candidate], cwd=target_root
            ):
                return candidate
        return None

    raise RuntimeError(f"unsupported VCS: {vcs}")


def is_on_default_branch(target_root: Path, vcs: str) -> bool | None:
    current = detect_current_branch(target_root, vcs)
    default = detect_default_branch(target_root, vcs)
    if current is None or default is None:
        return None
    return current == default
