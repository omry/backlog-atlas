from __future__ import annotations

import base64
import json
from typing import Any

from .artifacts import build_install_metadata, load_workflow_template
from .commands import run_gh, try_gh
from .constants import (
    BACKLOG_BRANCH,
    INSTALL_BRANCH,
    INSTALL_COMMIT_MESSAGE,
    INSTALL_METADATA_RELATIVE_PATH,
    WORKFLOW_RELATIVE_PATH,
)
from .models import InstallSource


def github_default_branch(repo: str) -> str:
    data = json.loads(run_gh(["api", f"repos/{repo}"]))
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


def ensure_backlog_branch_with_bundle(repo: str, install_source: InstallSource) -> None:
    if (
        not install_source.bundled_wheel_path
        or install_source.bundled_wheel_content is None
    ):
        return

    if github_ref_sha(repo, BACKLOG_BRANCH):
        put_github_file_bytes(
            repo,
            BACKLOG_BRANCH,
            install_source.bundled_wheel_path,
            install_source.bundled_wheel_content,
            "backlog: bundle Backlog Atlas package",
        )
        return

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


def ensure_github_branch(repo: str, branch: str, source_branch: str) -> None:
    if github_ref_sha(repo, branch):
        return
    source_sha = github_ref_sha(repo, source_branch)
    if not source_sha:
        raise RuntimeError(f"could not resolve {source_branch} branch for {repo}")
    payload = {"ref": f"refs/heads/{branch}", "sha": source_sha}
    run_gh(
        ["api", f"repos/{repo}/git/refs", "--method", "POST", "--input", "-"],
        input_text=json.dumps(payload),
    )


def ensure_github_pr(repo: str, branch: str, base_branch: str) -> None:
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
            "url",
            "--limit",
            "1",
        ]
    )
    if json.loads(existing):
        return
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
            "Install Backlog Atlas",
            "--body",
            "Adds the Backlog Atlas workflow.",
        ]
    )


def install_remote_workflow(
    repo: str, install_source: InstallSource, delivery: str
) -> None:
    ensure_backlog_branch_with_bundle(repo, install_source)
    default_branch = github_default_branch(repo)
    workflow_content = load_workflow_template(install_source.pip_spec)
    metadata_content = build_install_metadata(install_source)
    if delivery == "push":
        put_github_file(
            repo,
            default_branch,
            WORKFLOW_RELATIVE_PATH,
            workflow_content,
            INSTALL_COMMIT_MESSAGE,
        )
        put_github_file(
            repo,
            default_branch,
            INSTALL_METADATA_RELATIVE_PATH,
            metadata_content,
            INSTALL_COMMIT_MESSAGE,
        )
        return

    if delivery != "pr":
        raise RuntimeError(f"unsupported delivery mode: {delivery}")
    ensure_github_branch(repo, INSTALL_BRANCH, default_branch)
    put_github_file(
        repo,
        INSTALL_BRANCH,
        WORKFLOW_RELATIVE_PATH,
        workflow_content,
        INSTALL_COMMIT_MESSAGE,
    )
    put_github_file(
        repo,
        INSTALL_BRANCH,
        INSTALL_METADATA_RELATIVE_PATH,
        metadata_content,
        INSTALL_COMMIT_MESSAGE,
    )
    ensure_github_pr(repo, INSTALL_BRANCH, default_branch)


def run_remote_install(repo: str, install_source: InstallSource, delivery: str) -> int:
    install_remote_workflow(repo, install_source, delivery)
    if delivery == "push":
        print(f"pushed Backlog Atlas workflow to {repo}")
    else:
        print(f"opened or updated Backlog Atlas install PR for {repo}")
    return 0
