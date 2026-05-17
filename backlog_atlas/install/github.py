from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from .. import config as app_config
from ..errors import UserError
from .artifacts import (
    bundled_package_paths_to_cleanup,
    build_install_manifest,
    manifest_bundled_package_paths,
    load_upgrade_cleanup_workflow_template,
    load_workflow_template,
    parse_install_manifest,
)
from .commands import run_gh, try_gh
from .constants import (
    APP_CONFIG_RELATIVE_PATH,
    BACKLOG_BRANCH,
    INSTALL_BRANCH,
    INSTALL_MANIFEST_RELATIVE_PATH,
    INSTALL_METADATA_RELATIVE_PATH,
    UPGRADE_CLEANUP_WORKFLOW_RELATIVE_PATH,
    WORKFLOW_RELATIVE_PATH,
)
from .models import (
    InstallSource,
    bundle_commit_message,
    describe_install_source,
    install_commit_message,
    install_pr_body,
    install_pr_title,
)


def github_default_branch(repo: str) -> str:
    data = json.loads(run_gh(["api", f"repos/{repo}"]))
    return data.get("default_branch") or "main"


def verify_remote_repo_readable(repo: str) -> str:
    try:
        data = json.loads(run_gh(["api", f"repos/{repo}"]))
    except UserError as e:
        details = str(e)
        if "HTTP 404" in details or "Not Found" in details:
            raise UserError(
                f"GitHub could not find {repo}. Check the repository URL "
                "and that the current gh authentication can access it"
            ) from e
        raise UserError(
            f"could not verify GitHub repository {repo}; run gh auth status "
            f"and try again: {e}"
        ) from e
    return data.get("default_branch") or "main"


def verify_remote_install_target(repo: str) -> str:
    try:
        data = json.loads(run_gh(["api", f"repos/{repo}"]))
    except UserError as e:
        details = str(e)
        if "HTTP 404" in details or "Not Found" in details:
            raise UserError(
                f"GitHub could not find {repo}. Check the repository URL "
                "and that the current gh authentication can access it"
            ) from e
        raise UserError(
            f"could not verify GitHub repository {repo}; run gh auth status "
            f"and try again: {e}"
        ) from e

    permissions = data.get("permissions")
    if not isinstance(permissions, dict):
        raise UserError(
            f"could not verify write access to {repo}; authenticate with gh "
            "and try again"
        )
    if not any(permissions.get(name) for name in ("admin", "maintain", "push")):
        raise UserError(
            f"{repo} exists, but the authenticated GitHub user does not appear "
            "to have write access"
        )
    return data.get("default_branch") or "main"


def github_ref_sha(repo: str, branch: str) -> str | None:
    output = try_gh(["api", f"repos/{repo}/git/ref/heads/{branch}"])
    if not output:
        return None
    data = json.loads(output)
    return data.get("object", {}).get("sha")


def github_file_sha(repo: str, branch: str, path: str) -> str | None:
    output = try_gh(["api", f"repos/{repo}/contents/{path}?ref={branch}"])
    if not output:
        return None
    data = json.loads(output)
    return data.get("sha")


def github_file_text(repo: str, branch: str, path: str) -> str | None:
    output = try_gh(["api", f"repos/{repo}/contents/{path}?ref={branch}"])
    if not output:
        return None
    data = json.loads(output)
    if data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
        return None
    try:
        return base64.b64decode(data["content"]).decode()
    except (binascii.Error, UnicodeDecodeError):
        return None


def github_pages_configured(repo: str) -> bool:
    output = try_gh(["api", f"repos/{repo}/pages"])
    if not output:
        return False
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return False
    source = data.get("source")
    if not isinstance(source, dict):
        return False
    return source.get("branch") == BACKLOG_BRANCH and source.get("path") == "/"


def remote_installed_bundled_package_paths(repo: str, branch: str) -> list[str]:
    manifest = github_file_text(repo, branch, INSTALL_MANIFEST_RELATIVE_PATH)
    if manifest is None:
        return []
    package_paths = manifest_bundled_package_paths(manifest)
    return package_paths or []


def verify_backlog_atlas_installed(repo: str) -> str:
    branch = verify_remote_repo_readable(repo)
    manifest = github_file_text(repo, branch, INSTALL_MANIFEST_RELATIVE_PATH)
    if manifest is None or parse_install_manifest(manifest) is None:
        raise UserError(
            f"{repo} does not appear to have Backlog Atlas installed.\n\n"
            "Expected to find a valid Backlog Atlas install manifest at:\n"
            f"  https://github.com/{repo}@{branch}:{INSTALL_MANIFEST_RELATIVE_PATH}\n\n"
            f"Run `backlog-atlas install --repo https://github.com/{repo}` in "
            "that repository, merge the install, then rerun `backlog-atlas atlas add`."
        )
    return branch


def remote_config_text(repo: str, branch: str) -> str | None:
    output = try_gh(
        ["api", f"repos/{repo}/contents/{APP_CONFIG_RELATIVE_PATH}?ref={branch}"]
    )
    if not output:
        return None
    source = remote_config_source(repo, branch)
    data = json.loads(output)
    if data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
        raise UserError(
            "remote Backlog Atlas config is not readable:\n"
            f"  {source}\n\n"
            "The file exists, but GitHub did not return base64 text content."
        )
    content = "".join(data["content"].split())
    try:
        return base64.b64decode(content, validate=True).decode()
    except (binascii.Error, UnicodeDecodeError) as e:
        raise UserError(
            "remote Backlog Atlas config is not readable:\n"
            f"  {source}\n\n"
            "The file exists, but it could not be decoded as UTF-8 YAML."
        ) from e


def remote_config_source(repo: str, branch: str) -> str:
    return f"https://github.com/{repo}@{branch}:{APP_CONFIG_RELATIVE_PATH}"


def validate_remote_config(repo: str, branch: str) -> bool:
    content = remote_config_text(repo, branch)
    if content is None:
        return False
    app_config.validate_config_content(content, remote_config_source(repo, branch))
    return True


def put_github_file_bytes(
    repo: str, branch: str, path: str, content: bytes, message: str
) -> None:
    payload: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content).decode(),
        "branch": branch,
    }
    sha = github_file_sha(repo, branch, path)
    if sha:
        payload["sha"] = sha
    run_gh(
        ["api", f"repos/{repo}/contents/{path}", "--method", "PUT", "--input", "-"],
        input_text=json.dumps(payload),
    )


def put_github_file(
    repo: str, branch: str, path: str, content: str, message: str
) -> None:
    put_github_file_bytes(repo, branch, path, content.encode(), message)


def create_blob(repo: str, content: bytes) -> str:
    payload = {
        "content": base64.b64encode(content).decode(),
        "encoding": "base64",
    }
    output = run_gh(
        ["api", f"repos/{repo}/git/blobs", "--method", "POST", "--input", "-"],
        input_text=json.dumps(payload),
    )
    return json.loads(output)["sha"]


def create_tree(repo: str, entries: dict[str, bytes]) -> str:
    tree = []
    for path, content in entries.items():
        tree.append(
            {
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": create_blob(repo, content),
            }
        )
    output = run_gh(
        ["api", f"repos/{repo}/git/trees", "--method", "POST", "--input", "-"],
        input_text=json.dumps({"tree": tree}),
    )
    return json.loads(output)["sha"]


def create_commit(repo: str, message: str, tree_sha: str) -> str:
    output = run_gh(
        ["api", f"repos/{repo}/git/commits", "--method", "POST", "--input", "-"],
        input_text=json.dumps({"message": message, "tree": tree_sha}),
    )
    return json.loads(output)["sha"]


def create_branch_ref(repo: str, branch: str, commit_sha: str) -> None:
    payload = {"ref": f"refs/heads/{branch}", "sha": commit_sha}
    run_gh(
        ["api", f"repos/{repo}/git/refs", "--method", "POST", "--input", "-"],
        input_text=json.dumps(payload),
    )


def delete_github_file(repo: str, branch: str, path: str, message: str) -> bool:
    sha = github_file_sha(repo, branch, path)
    if not sha:
        return False
    payload = {"message": message, "sha": sha, "branch": branch}
    run_gh(
        ["api", f"repos/{repo}/contents/{path}", "--method", "DELETE", "--input", "-"],
        input_text=json.dumps(payload),
    )
    return True


def write_or_delete_upgrade_cleanup_workflow(
    repo: str,
    branch: str,
    install_source: InstallSource,
    message: str,
    old_bundled_package_paths: list[str] | None = None,
) -> None:
    cleanup_package_paths = bundled_package_paths_to_cleanup(
        install_source,
        old_bundled_package_paths or [],
    )
    if cleanup_package_paths:
        print(
            f"Writing upgrade cleanup workflow to {branch}: "
            f"{UPGRADE_CLEANUP_WORKFLOW_RELATIVE_PATH}"
        )
        put_github_file(
            repo,
            branch,
            UPGRADE_CLEANUP_WORKFLOW_RELATIVE_PATH,
            load_upgrade_cleanup_workflow_template(cleanup_package_paths),
            message,
        )
    elif delete_github_file(
        repo,
        branch,
        UPGRADE_CLEANUP_WORKFLOW_RELATIVE_PATH,
        "backlog: remove temporary Backlog Atlas upgrade cleanup workflow",
    ):
        print(f"Removed old upgrade cleanup workflow from {branch}")


def ensure_backlog_branch_with_bundle(repo: str, install_source: InstallSource) -> None:
    if (
        not install_source.bundled_wheel_path
        or install_source.bundled_wheel_content is None
    ):
        return

    print(
        f"Publishing bundled wheel to {BACKLOG_BRANCH}: "
        f"{install_source.bundled_wheel_path}"
    )
    if github_ref_sha(repo, BACKLOG_BRANCH):
        put_github_file_bytes(
            repo,
            BACKLOG_BRANCH,
            install_source.bundled_wheel_path,
            install_source.bundled_wheel_content,
            bundle_commit_message(install_source),
        )
        print(f"Updated bundled wheel on {BACKLOG_BRANCH}")
        return

    print(f"Creating {BACKLOG_BRANCH} branch for bundled wheel")
    tree_sha = create_tree(
        repo,
        {
            install_source.bundled_wheel_path: install_source.bundled_wheel_content,
        },
    )
    commit_sha = create_commit(
        repo, f"backlog: initialize {BACKLOG_BRANCH} branch", tree_sha
    )
    create_branch_ref(repo, BACKLOG_BRANCH, commit_sha)
    print(f"Created {BACKLOG_BRANCH} branch with bundled wheel")


def ensure_github_branch(repo: str, branch: str, source_branch: str) -> None:
    if github_ref_sha(repo, branch):
        return
    source_sha = github_ref_sha(repo, source_branch)
    if not source_sha:
        raise UserError(f"could not resolve {source_branch} branch for {repo}")
    payload = {"ref": f"refs/heads/{branch}", "sha": source_sha}
    run_gh(
        ["api", f"repos/{repo}/git/refs", "--method", "POST", "--input", "-"],
        input_text=json.dumps(payload),
    )


def ensure_github_pr(
    repo: str, branch: str, base_branch: str, install_source: InstallSource
) -> None:
    title = install_pr_title(install_source)
    body = install_pr_body(install_source)
    print(f"Checking for existing install PR from {branch} to {base_branch}")
    existing = run_gh(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--head",
            branch,
            "--base",
            base_branch,
            "--state",
            "open",
            "--json",
            "number",
            "--limit",
            "1",
        ]
    )
    existing_prs = json.loads(existing)
    if existing_prs:
        number = str(existing_prs[0]["number"])
        print(f"Updating existing install PR #{number}")
        run_gh(
            [
                "pr",
                "edit",
                number,
                "--repo",
                repo,
                "--title",
                title,
                "--body",
                body,
            ]
        )
        return
    print(f"Creating install PR from {branch} to {base_branch}")
    run_gh(
        [
            "pr",
            "create",
            "--repo",
            repo,
            "--base",
            base_branch,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ]
    )


def install_remote_workflow(
    repo: str, install_source: InstallSource, delivery: str
) -> None:
    print(f"Preparing remote install for {repo}")
    print("Resolving default branch")
    default_branch = github_default_branch(repo)
    print(f"Default branch is {default_branch}")
    remote_config_exists = validate_remote_config(repo, default_branch)
    ensure_backlog_branch_with_bundle(repo, install_source)
    old_bundled_package_paths = remote_installed_bundled_package_paths(
        repo,
        default_branch,
    )
    cleanup_package_paths = bundled_package_paths_to_cleanup(
        install_source,
        old_bundled_package_paths,
    )
    workflow_content = load_workflow_template(install_source.pip_spec)
    include_upgrade_cleanup = bool(cleanup_package_paths)
    manifest_content = build_install_manifest(
        install_source,
        include_upgrade_cleanup=include_upgrade_cleanup,
    )
    commit_message = install_commit_message(install_source)
    if delivery == "push":
        if delete_github_file(
            repo,
            default_branch,
            UPGRADE_CLEANUP_WORKFLOW_RELATIVE_PATH,
            "backlog: remove stale temporary Backlog Atlas upgrade cleanup workflow",
        ):
            print(f"Removed stale upgrade cleanup workflow from {default_branch}")
        print(f"Writing workflow to {default_branch}: {WORKFLOW_RELATIVE_PATH}")
        put_github_file(
            repo,
            default_branch,
            WORKFLOW_RELATIVE_PATH,
            workflow_content,
            commit_message,
        )
        if delete_github_file(
            repo,
            default_branch,
            INSTALL_METADATA_RELATIVE_PATH,
            "backlog: remove legacy Backlog Atlas install metadata",
        ):
            print(f"Removed legacy install metadata from {default_branch}")
        print(
            f"Writing install manifest to {default_branch}: "
            f"{INSTALL_MANIFEST_RELATIVE_PATH}"
        )
        put_github_file(
            repo,
            default_branch,
            INSTALL_MANIFEST_RELATIVE_PATH,
            manifest_content,
            commit_message,
        )
        if not remote_config_exists:
            print(
                f"Writing editable config to {default_branch}: "
                f"{APP_CONFIG_RELATIVE_PATH}"
            )
            put_github_file(
                repo,
                default_branch,
                APP_CONFIG_RELATIVE_PATH,
                app_config.packaged_config_content(),
                commit_message,
            )
        write_or_delete_upgrade_cleanup_workflow(
            repo,
            default_branch,
            install_source,
            commit_message,
            old_bundled_package_paths=old_bundled_package_paths,
        )
        return

    if delivery != "pr":
        raise RuntimeError(f"unsupported delivery mode: {delivery}")
    print(f"Ensuring install branch {INSTALL_BRANCH} from {default_branch}")
    ensure_github_branch(repo, INSTALL_BRANCH, default_branch)
    print(f"Writing workflow to {INSTALL_BRANCH}: {WORKFLOW_RELATIVE_PATH}")
    put_github_file(
        repo,
        INSTALL_BRANCH,
        WORKFLOW_RELATIVE_PATH,
        workflow_content,
        commit_message,
    )
    if delete_github_file(
        repo,
        INSTALL_BRANCH,
        INSTALL_METADATA_RELATIVE_PATH,
        "backlog: remove legacy Backlog Atlas install metadata",
    ):
        print(f"Removed legacy install metadata from {INSTALL_BRANCH}")
    print(
        f"Writing install manifest to {INSTALL_BRANCH}: "
        f"{INSTALL_MANIFEST_RELATIVE_PATH}"
    )
    put_github_file(
        repo,
        INSTALL_BRANCH,
        INSTALL_MANIFEST_RELATIVE_PATH,
        manifest_content,
        commit_message,
    )
    if not remote_config_exists:
        print(
            f"Writing editable config to {INSTALL_BRANCH}: "
            f"{APP_CONFIG_RELATIVE_PATH}"
        )
        put_github_file(
            repo,
            INSTALL_BRANCH,
            APP_CONFIG_RELATIVE_PATH,
            app_config.packaged_config_content(),
            commit_message,
        )
    write_or_delete_upgrade_cleanup_workflow(
        repo,
        INSTALL_BRANCH,
        install_source,
        commit_message,
        old_bundled_package_paths=old_bundled_package_paths,
    )
    ensure_github_pr(repo, INSTALL_BRANCH, default_branch, install_source)


def print_remote_install_plan(
    repo: str,
    install_source: InstallSource,
    delivery: str,
    default_branch: str,
    cleanup_old_bundled_packages: bool = False,
    remote_config_exists: bool = False,
) -> None:
    print("Dry run: would install Backlog Atlas remotely")
    print("Verified GitHub repository exists and current gh auth can write.")
    print("No files, branches, commits, or pull requests would be created.")
    print(f"Target repo: {repo}")
    print(f"Default branch: {default_branch}")
    print(f"Delivery: {'direct push' if delivery == 'push' else 'pull request'}")
    print(f"Workflow would install Backlog Atlas from: {install_source.pip_spec}")
    print("Would first remove previous install hooks/manifests if present.")
    if install_source.bundled_wheel_path:
        action = (
            "Would build and upload bundled wheel"
            if install_source.bundled_wheel_content is None
            else "Would upload bundled wheel"
        )
        print(f"{action} to {BACKLOG_BRANCH}: " f"{install_source.bundled_wheel_path}")
    if cleanup_old_bundled_packages:
        print(
            "Would write a temporary upgrade cleanup workflow that removes old "
            "bundled wheels after the install lands."
        )
    if delivery == "push":
        print(f"Would write these files to {default_branch}:")
    else:
        print(
            f"Would create or update {INSTALL_BRANCH} from {default_branch}, "
            "then open an install pull request with:"
        )
    print(f"  - {WORKFLOW_RELATIVE_PATH}")
    print(f"  - {INSTALL_MANIFEST_RELATIVE_PATH}")
    if not remote_config_exists:
        print(f"  - {APP_CONFIG_RELATIVE_PATH} (created only if missing)")
    if cleanup_old_bundled_packages:
        print(f"  - {UPGRADE_CLEANUP_WORKFLOW_RELATIVE_PATH}")
    print(
        f"After the install lands, the workflow creates or updates the "
        f"{BACKLOG_BRANCH} branch."
    )


def run_remote_install(
    repo: str, install_source: InstallSource, delivery: str, dry_run: bool = False
) -> int:
    if dry_run:
        default_branch = verify_remote_install_target(repo)
        remote_config_exists = validate_remote_config(repo, default_branch)
        cleanup_old_bundled_packages = bool(
            remote_installed_bundled_package_paths(repo, default_branch)
        )
        print_remote_install_plan(
            repo,
            install_source,
            delivery,
            default_branch,
            cleanup_old_bundled_packages=cleanup_old_bundled_packages,
            remote_config_exists=remote_config_exists,
        )
        return 0

    install_remote_workflow(repo, install_source, delivery)
    installed = describe_install_source(install_source)
    if delivery == "push":
        print(f"pushed Backlog Atlas workflow to {repo}; installs {installed}")
    else:
        print(
            f"opened or updated Backlog Atlas install PR for {repo}; installs {installed}"
        )
    return 0
