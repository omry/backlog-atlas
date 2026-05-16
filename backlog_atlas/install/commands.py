from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", text)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def try_command(args: list[str], cwd: Path | None = None) -> str | None:
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "NO_COLOR": "1", "CLICOLOR": "0"},
            cwd=cwd,
        )
    except FileNotFoundError:
        return None
    if completed.returncode != 0:
        return None
    return strip_ansi(completed.stdout)


def run_command(args: list[str], cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "NO_COLOR": "1", "CLICOLOR": "0"},
            cwd=cwd,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"{args[0]} is required but was not found") from e
    if completed.returncode != 0:
        stderr = strip_ansi(completed.stderr).strip()
        stdout = strip_ansi(completed.stdout).strip()
        details = stderr or stdout or "unknown command failure"
        raise RuntimeError(f"{' '.join(args)} failed: {details}")
    return strip_ansi(completed.stdout)


def run_gh(args: list[str], input_text: str | None = None) -> str:
    try:
        completed = subprocess.run(
            ["gh", *args],
            check=False,
            capture_output=True,
            text=True,
            input=input_text,
            env={**os.environ, "NO_COLOR": "1", "CLICOLOR": "0"},
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "GitHub CLI 'gh' is required for GitHub operations; install it "
            "and run 'gh auth login' or set GH_TOKEN"
        ) from e
    if completed.returncode != 0:
        stderr = strip_ansi(completed.stderr).strip()
        stdout = strip_ansi(completed.stdout).strip()
        details = stderr or stdout or "unknown gh failure"
        raise RuntimeError(f"gh {' '.join(args)} failed: {details}")
    return strip_ansi(completed.stdout)


def try_gh(args: list[str]) -> str | None:
    try:
        return run_gh(args)
    except RuntimeError:
        return None
