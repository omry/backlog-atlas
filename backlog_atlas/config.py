from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from omegaconf import DictConfig, OmegaConf

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


def load_config() -> DictConfig:
    defaults = OmegaConf.structured(BacklogConfig)
    if PACKAGE_CONFIG_PATH.exists():
        return cast(
            DictConfig,
            OmegaConf.merge(defaults, OmegaConf.load(PACKAGE_CONFIG_PATH)),
        )
    return defaults


def categories_from_config(cfg: DictConfig) -> dict[str, CategoryConfig]:
    return cast(dict[str, CategoryConfig], OmegaConf.to_object(cfg.categories))


def category_matchers(
    cfg: DictConfig,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    categories = categories_from_config(cfg)
    label_to_category: dict[str, str] = {
        label: cat for cat, c in categories.items() for label in c.labels
    }
    category_keywords: dict[str, list[str]] = {
        cat: c.keywords for cat, c in categories.items()
    }
    return label_to_category, category_keywords
