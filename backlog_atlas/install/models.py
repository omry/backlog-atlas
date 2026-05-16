from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstallSource:
    pip_spec: str
    version: str
    source_type: str
    bundled_wheel_path: str | None = None
    bundled_wheel_content: bytes | None = None
