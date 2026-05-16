from __future__ import annotations

import json
import re
import sys
import tempfile
from importlib.metadata import (
    PackageNotFoundError,
    distribution as package_distribution,
    version as package_version,
)
from pathlib import Path
from urllib.parse import unquote, urlparse

from ..errors import UserError
from .commands import run_command, try_command
from .constants import BUNDLED_PACKAGE_DIR
from .models import InstallSource


def installed_version() -> str:
    try:
        return package_version("backlog-atlas")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def installed_local_source_root() -> Path | None:
    try:
        dist = package_distribution("backlog-atlas")
    except PackageNotFoundError:
        return None

    direct_url = dist.read_text("direct_url.json")
    if not direct_url:
        return None
    try:
        data = json.loads(direct_url)
    except json.JSONDecodeError:
        return None
    dir_info = data.get("dir_info")
    if not isinstance(dir_info, dict):
        return None
    url = data.get("url")
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None
    source_root = Path(unquote(parsed.path))
    if not source_root.exists():
        raise UserError(
            f"backlog-atlas was installed from local source {source_root}, "
            "but that path no longer exists"
        )
    return source_root


def package_version_from_checkout(source_root: Path) -> str:
    pyproject_path = source_root / "pyproject.toml"
    if not pyproject_path.exists():
        raise UserError(f"{source_root} is not a Python package checkout")
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
    raise UserError(f"{pyproject_path} does not define project.version")


def build_local_wheel(source_root: Path) -> tuple[str, bytes]:
    build_tag = checkout_wheel_build_tag(source_root)
    with tempfile.TemporaryDirectory(prefix="backlog-atlas-wheel-") as tmp:
        out_dir = Path(tmp)
        print(f"Building Backlog Atlas wheel from {source_root}...")
        try:
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
        except UserError as e:
            details = str(e)
            if "No module named build" in details:
                raise UserError(
                    "backlog-atlas is installed from a local checkout, so install "
                    "needs to build a bundled wheel from that checkout. This "
                    "Python environment is missing the 'build' package; install "
                    f"it with: {sys.executable} -m pip install build"
                ) from e
            raise
        wheels = sorted(out_dir.glob("*.whl"))
        if len(wheels) != 1:
            raise UserError(f"expected one built wheel, found {len(wheels)}")
        wheel = wheels[0]
        storage_name = wheel_storage_name(wheel.name, build_tag)
        print(f"Built wheel {storage_name}")
        return storage_name, wheel.read_bytes()


def checkout_state(source_root: Path) -> tuple[str | None, bool]:
    revision = try_command(["git", "rev-parse", "--short=12", "HEAD"], cwd=source_root)
    if revision:
        status = try_command(["git", "status", "--porcelain"], cwd=source_root)
        return revision.strip().splitlines()[0], bool(status and status.strip())

    revision = try_command(
        ["sl", "log", "-r", ".", "-T", "{node|short}\\n"], cwd=source_root
    )
    if revision:
        status = try_command(["sl", "status"], cwd=source_root)
        return revision.strip().splitlines()[0], bool(status and status.strip())

    return None, False


def checkout_wheel_build_tag(source_root: Path) -> str | None:
    revision, dirty = checkout_state(source_root)
    if revision is None:
        return None
    tag = f"0.g{re.sub(r'[^A-Za-z0-9.]+', '.', revision).strip('.')}"
    if dirty:
        tag += ".dirty"
    return tag


def wheel_storage_name(wheel_name: str, build_tag: str | None) -> str:
    if build_tag is None:
        return wheel_name
    if not wheel_name.endswith(".whl"):
        raise UserError(f"unexpected wheel filename: {wheel_name}")
    stem = wheel_name[:-4]
    parts = stem.split("-")
    if len(parts) == 5:
        distribution, version, python_tag, abi_tag, platform_tag = parts
        return (
            f"{distribution}-{version}-{build_tag}-"
            f"{python_tag}-{abi_tag}-{platform_tag}.whl"
        )
    if len(parts) == 6:
        distribution, version, existing_build, python_tag, abi_tag, platform_tag = parts
        return (
            f"{distribution}-{version}-{existing_build}.{build_tag}-"
            f"{python_tag}-{abi_tag}-{platform_tag}.whl"
        )
    raise UserError(f"unexpected wheel filename: {wheel_name}")


def dry_run_wheel_name(source_root: Path, version: str) -> str:
    build_tag = checkout_wheel_build_tag(source_root)
    if build_tag is None:
        return "<built-wheel>"
    return f"backlog_atlas-{version}-{build_tag}-py3-none-any.whl"


def resolve_local_checkout_install_source(
    source_root: Path, build_wheel: bool = True
) -> InstallSource:
    source_root = source_root.resolve()
    version = package_version_from_checkout(source_root)
    if not build_wheel:
        bundled_path = (
            f"{BUNDLED_PACKAGE_DIR}/{dry_run_wheel_name(source_root, version)}"
        )
        return InstallSource(
            pip_spec=f"backlog-atlas-branch/{bundled_path}",
            version=version,
            source_type="bundled-wheel",
            bundled_wheel_path=bundled_path,
        )
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


def resolve_install_source(
    install_from: str | None, dry_run: bool = False
) -> InstallSource:
    if not install_from or install_from.strip() == "backlog-atlas":
        source_root = installed_local_source_root()
        if source_root is not None:
            return resolve_local_checkout_install_source(
                source_root, build_wheel=not dry_run
            )
        version = installed_version()
        if version == "0.0.0+unknown":
            raise UserError(
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
        return resolve_local_checkout_install_source(
            source_path, build_wheel=not dry_run
        )

    if text.startswith("backlog-atlas"):
        raise UserError(
            "PyPI installs must be pinned exactly, for example backlog-atlas==1.2.3"
        )

    raise UserError(
        "--install-from must be a pinned PyPI spec like backlog-atlas==1.2.3 "
        "or a local Backlog Atlas checkout path"
    )
