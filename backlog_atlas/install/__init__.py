from __future__ import annotations

from .artifacts import (
    build_install_metadata,
    find_install_metadata_target,
    find_workflow_target,
    load_uninstall_workflow_template,
    load_workflow_template,
    seed_backlog_content,
    write_install_artifacts,
    write_text_artifact,
)
from .cli import add_install_args, add_uninstall_args, run_install, run_uninstall
from .commands import read_text, run_command, run_gh, strip_ansi, try_command, try_gh
from .constants import (
    BACKLOG_BRANCH,
    BEGIN_GENERATED,
    BEGIN_MANUAL,
    BUNDLED_PACKAGE_DIR,
    END_GENERATED,
    END_MANUAL,
    INSTALL_BRANCH,
    INSTALL_COMMIT_MESSAGE,
    INSTALL_METADATA_RELATIVE_PATH,
    INSTALL_METADATA_SCHEMA_VERSION,
    MANUAL_FENCE,
    PROJECT_DIR,
    UNINSTALL_WORKFLOW_TEMPLATE_PATH,
    WORKFLOW_RELATIVE_PATH,
    WORKFLOW_TEMPLATE_PATH,
)
from .github import (
    create_blob,
    create_branch_ref,
    create_commit,
    create_tree,
    ensure_backlog_branch_with_bundle,
    ensure_github_branch,
    ensure_github_pr,
    github_default_branch,
    github_file_sha,
    github_ref_sha,
    install_remote_workflow,
    put_github_file,
    put_github_file_bytes,
    run_remote_install,
)
from .local import (
    add_local_install_files,
    ensure_worktree_clean,
    local_install_commands,
    print_local_install_next_steps,
    run_local_install,
)
from .models import InstallSource
from .repo import (
    detect_current_branch,
    detect_default_branch,
    detect_local_vcs,
    detect_repo_from_git,
    detect_repo_from_sl,
    detect_target_root,
    is_on_default_branch,
    normalize_github_repo,
    parse_github_repo,
    resolve_repo,
)
from .sources import (
    build_local_wheel,
    installed_version,
    package_version_from_checkout,
    parse_pinned_backlog_atlas_version,
    resolve_install_source,
    resolve_local_checkout_install_source,
)
