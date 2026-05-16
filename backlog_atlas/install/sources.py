from __future__ import annotations

import re
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

from .commands import run_command
from .constants import BUNDLED_PACKAGE_DIR
from .models import InstallSource


def installed_version() -> str:
    try:
        return package_version("backlog-atlas")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def package_version_from_checkout(source_root: Path) -> str:
    pyproject_path = source_root / "pyproject.toml"
    if not pyproject_path.exists():
        raise RuntimeError(f"{source_root} is not a Python package checkout")
    in_project_section = False
    for line in pyproject_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text == "[project]":
            in_project_section = True
            continue
        if in_project_section and text.startswith("["):
            break
        if in_project_section:
            match = re.match(r"""version\s*=\s*["']([^"']+)["']""", text)
            if match:
                return match.group(1)
    raise RuntimeError(f"{pyproject_path} does not define project.version")


def build_local_wheel(source_root: Path) -> tuple[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="backlog-atlas-wheel-") as tmp:
        out_dir = Path(tmp)
        run_command(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(out_dir),
            ],
            cwd=source_root,
        )
        wheels = sorted(out_dir.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected one built wheel, found {len(wheels)}")
        wheel = wheels[0]
        return wheel.name, wheel.read_bytes()


def resolve_local_checkout_install_source(source_root: Path) -> InstallSource:
    source_root = source_root.resolve()
    version = package_version_from_checkout(source_root)
    wheel_name, wheel_content = build_local_wheel(source_root)
    bundled_path = f"{BUNDLED_PACKAGE_DIR}/{wheel_name}"
    return InstallSource(
        pip_spec=f"backlog-atlas-branch/{bundled_path}",
        version=version,
        source_type="bundled-wheel",
        bundled_wheel_path=bundled_path,
        bundled_wheel_content=wheel_content,
    )


def parse_pinned_backlog_atlas_version(install_from: str) -> str | None:
    match = re.fullmatch(r"backlog-atlas==([^;\s]+)", install_from.strip())
    return match.group(1) if match else None


def resolve_install_source(install_from: str | None) -> InstallSource:
    if not install_from or install_from.strip() == "backlog-atlas":
        version = installed_version()
        if version == "0.0.0+unknown":
            raise RuntimeError(
                "could not determine installed backlog-atlas version to pin"
            )
        return InstallSource(
            pip_spec=f"backlog-atlas=={version}",
            version=version,
            source_type="pypi",
        )

    text = install_from.strip()
    pinned_version = parse_pinned_backlog_atlas_version(text)
    if pinned_version:
        return InstallSource(
            pip_spec=text,
            version=pinned_version,
            source_type="pypi",
        )

    source_path = Path(text).expanduser()
    if source_path.exists():
        return resolve_local_checkout_install_source(source_path)

    if text.startswith("backlog-atlas"):
        raise RuntimeError(
            "PyPI installs must be pinned exactly, for example backlog-atlas==1.2.3"
        )

    raise RuntimeError(
        "--install-from must be a pinned PyPI spec like backlog-atlas==1.2.3 "
        "or a local Backlog Atlas checkout path"
    )
