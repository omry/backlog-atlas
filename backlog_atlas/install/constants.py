from __future__ import annotations

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKFLOW_TEMPLATE_PATH = PROJECT_DIR / "templates" / "workflow.yml"
UNINSTALL_WORKFLOW_TEMPLATE_PATH = PROJECT_DIR / "templates" / "uninstall_workflow.yml"
UPGRADE_CLEANUP_WORKFLOW_TEMPLATE_PATH = (
    PROJECT_DIR / "templates" / "upgrade_cleanup_workflow.yml"
)

BACKLOG_BRANCH = "backlog-atlas"
WORKFLOW_RELATIVE_PATH = ".github/workflows/update-backlog-atlas.yml"
UPGRADE_CLEANUP_WORKFLOW_RELATIVE_PATH = (
    ".github/workflows/temporary-backlog-atlas-upgrade-cleanup.yml"
)
INSTALL_METADATA_RELATIVE_PATH = ".github/backlog-atlas.json"
INSTALL_MANIFEST_RELATIVE_PATH = ".github/backlog-atlas/manifest.json"
APP_CONFIG_RELATIVE_PATH = ".github/backlog-atlas/config.yaml"
INSTALL_METADATA_SCHEMA_VERSION = 1
INSTALL_MANIFEST_SCHEMA_VERSION = 1
INSTALL_BRANCH = "temporary_backlog_atlas_install_pr"
BUNDLED_PACKAGE_DIR = ".backlog-atlas/packages"
