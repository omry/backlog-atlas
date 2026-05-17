from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from omegaconf import DictConfig, OmegaConf
from omegaconf.errors import OmegaConfBaseException

from .errors import UserError
from .install.constants import APP_CONFIG_RELATIVE_PATH

PROJECT_DIR = Path(__file__).resolve().parent
PACKAGE_CONFIG_PATH = PROJECT_DIR / "config.yaml"


@dataclass
class CategoryConfig:
    emoji: str = ""
    labels: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


_DEFAULT_CATEGORIES: dict[str, CategoryConfig] = {
    "Bug": CategoryConfig(
        emoji="🐛",
        labels=["bug"],
        keywords=[
            "bug",
            "error",
            "fail",
            "broken",
            "crash",
            "exception",
            "runtimeerror",
            "assertionerror",
        ],
    ),
    "Enhancement": CategoryConfig(
        emoji="✨",
        labels=[
            "enhancement",
            "good first issue",
            "help wanted",
            "performance",
            "duplicate",
            "invalid",
            "wontfix",
            "discussion",
            "awaiting response",
            "wishlist",
        ],
        keywords=[
            "feature",
            "add",
            "support",
            "allow",
            "enable",
            "implement",
            "enhancement",
            "request",
            "wishlist",
            "consider",
            "performance",
            "speed",
            "slow",
            "optimize",
            "memory",
            "cpu",
            "latency",
        ],
    ),
    "Documentation": CategoryConfig(
        emoji="📄",
        labels=["documentation"],
        keywords=["doc", "documentation", "readme", "comment", "typo", "spelling"],
    ),
    "Question": CategoryConfig(
        emoji="❓",
        labels=["question"],
        keywords=["question", "how to", "help", "confused", "unclear", "wonder"],
    ),
    "Refactor": CategoryConfig(
        emoji="🔧",
        labels=["refactor"],
        keywords=[
            "refactor",
            "cleanup",
            "clean up",
            "remove",
            "delete",
            "deprecated",
            "modernize",
        ],
    ),
    "Build": CategoryConfig(
        emoji="🏗️",
        labels=["build", "dependencies"],
        keywords=[
            "build",
            "package",
            "release",
            "ci",
            "github actions",
            "setup.py",
            "pyproject",
            "wheel",
            "packaging",
        ],
    ),
}


@dataclass
class BacklogConfig:
    done_expire_days: int | None = 14
    updates_jsonl_filename: str = "updates.jsonl"
    data_json_filename: str = "backlog.json"
    data_updates_limit: int = 200
    blocked_labels: list[str] = field(default_factory=lambda: ["awaiting response"])
    repo: str | None = None
    issue_url_template: str = "https://github.com/${repo}/issues/{number}"
    pr_url_template: str = "https://github.com/${repo}/pull/{number}"
    status_emojis: dict[str, str] = field(
        default_factory=lambda: {
            "in progress": "🔄",
            "community PR": "🤝",
            "blocked": "🚫",
            "not started": "⬜",
            "done": "✅",
        }
    )
    categories: dict[str, CategoryConfig] = field(
        default_factory=lambda: {
            k: CategoryConfig(
                emoji=v.emoji, labels=list(v.labels), keywords=list(v.keywords)
            )
            for k, v in _DEFAULT_CATEGORIES.items()
        }
    )


@dataclass
class LoadedConfig:
    config: DictConfig
    source: str
    path: Path | None = None


def target_config_path(target_root: Path) -> Path:
    return target_root / APP_CONFIG_RELATIVE_PATH


def packaged_config_content() -> str:
    return PACKAGE_CONFIG_PATH.read_text(encoding="utf-8")


def _base_config() -> DictConfig:
    cfg = OmegaConf.structured(BacklogConfig)
    if PACKAGE_CONFIG_PATH.exists():
        cfg = OmegaConf.merge(cfg, OmegaConf.load(PACKAGE_CONFIG_PATH))
    return cast(DictConfig, cfg)


def _format_config_error(source: str, error: Exception) -> UserError:
    return UserError(
        "existing Backlog Atlas config is invalid:\n"
        f"  {source}\n\n"
        f"{error}\n\n"
        "Fix the config and rerun the command.\n"
        "To reset to the packaged default, delete or move that config file and "
        "rerun `backlog-atlas install`."
    )


def _is_yaml_error(error: Exception) -> bool:
    return type(error).__module__.split(".", 1)[0] == "yaml"


def merge_config_content(content: str, source: str) -> DictConfig:
    try:
        cfg = OmegaConf.merge(_base_config(), OmegaConf.create(content))
        OmegaConf.to_container(cfg, resolve=False)
    except (OSError, OmegaConfBaseException, ValueError, TypeError) as e:
        raise _format_config_error(source, e) from e
    except Exception as e:
        if _is_yaml_error(e):
            raise _format_config_error(source, e) from e
        raise
    return cast(DictConfig, cfg)


def validate_config_content(content: str, source: str) -> DictConfig:
    return merge_config_content(content, source)


def validate_config_file(path: Path) -> DictConfig:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise _format_config_error(str(path), e) from e
    return validate_config_content(content, str(path))


def load_config_with_source(target_root: Path | None = None) -> LoadedConfig:
    if target_root is not None:
        config_path = target_config_path(target_root)
        if config_path.exists():
            return LoadedConfig(
                config=validate_config_file(config_path),
                source=config_path.relative_to(target_root).as_posix(),
                path=config_path,
            )
    return LoadedConfig(config=_base_config(), source="packaged defaults")


def load_config(target_root: Path | None = None) -> DictConfig:
    return load_config_with_source(target_root).config


def categories_from_config(cfg: DictConfig) -> dict[str, CategoryConfig]:
    return cast(dict[str, CategoryConfig], OmegaConf.to_object(cfg.categories))


def category_matchers(
    cfg: DictConfig,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    categories = categories_from_config(cfg)
    label_to_category: dict[str, str] = {
        str(label).lower().strip(): cat
        for cat, c in categories.items()
        for label in c.labels
    }
    category_keywords: dict[str, list[str]] = {
        cat: [str(keyword).lower().strip() for keyword in c.keywords]
        for cat, c in categories.items()
    }
    return label_to_category, category_keywords
