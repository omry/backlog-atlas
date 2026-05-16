from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstallSource:
    pip_spec: str
    version: str
    source_type: str
    bundled_wheel_path: str | None = None
    bundled_wheel_content: bytes | None = None


def describe_install_source(install_source: InstallSource) -> str:
    if install_source.source_type == "pypi":
        return f"Backlog Atlas {install_source.version} from {install_source.pip_spec}"
    if install_source.bundled_wheel_path:
        return (
            f"Backlog Atlas {install_source.version} from bundled wheel "
            f"{install_source.bundled_wheel_path}"
        )
    return f"Backlog Atlas {install_source.version} from {install_source.pip_spec}"


def bundled_wheel_name(install_source: InstallSource) -> str:
    if not install_source.bundled_wheel_path:
        return "bundled wheel"
    return install_source.bundled_wheel_path.rsplit("/", 1)[-1]


def install_commit_message(install_source: InstallSource) -> str:
    if install_source.source_type == "bundled-wheel":
        return (
            "backlog: install Backlog Atlas workflow from "
            f"{bundled_wheel_name(install_source)}"
        )
    return f"backlog: install Backlog Atlas {install_source.version} workflow"


def bundle_commit_message(install_source: InstallSource) -> str:
    if install_source.source_type == "bundled-wheel":
        return f"backlog: bundle {bundled_wheel_name(install_source)}"
    return f"backlog: bundle Backlog Atlas {install_source.version} package"


def install_pr_title(install_source: InstallSource) -> str:
    if install_source.source_type == "bundled-wheel":
        return f"Install Backlog Atlas from {bundled_wheel_name(install_source)}"
    return f"Install Backlog Atlas {install_source.version}"


def install_pr_body(install_source: InstallSource) -> str:
    return (
        "Adds the Backlog Atlas workflow.\n\n"
        f"Installs {describe_install_source(install_source)}.\n\n"
        f"Install source: `{install_source.pip_spec}`"
    )
