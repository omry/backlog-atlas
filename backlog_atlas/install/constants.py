from __future__ import annotations

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKFLOW_TEMPLATE_PATH = PROJECT_DIR / "templates" / "workflow.yml"
UNINSTALL_WORKFLOW_TEMPLATE_PATH = PROJECT_DIR / "templates" / "uninstall_workflow.yml"

BACKLOG_BRANCH = "backlog-atlas"
WORKFLOW_RELATIVE_PATH = ".github/workflows/update-backlog-atlas.yml"
INSTALL_METADATA_RELATIVE_PATH = ".github/backlog-atlas.json"
INSTALL_METADATA_SCHEMA_VERSION = 1
INSTALL_BRANCH = "temporary_backlog_atlas_install_pr"
BUNDLED_PACKAGE_DIR = ".backlog-atlas/packages"
