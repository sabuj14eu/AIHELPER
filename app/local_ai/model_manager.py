"""Model discovery, availability and per-task selection.

No model name is hard-coded anywhere else in the codebase. The router asks for
a *class* of model ("small", "default", "strong", "embedding") and this module
resolves it against what is actually installed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.core.config import Settings
from app.core.logging import get_logger
from app.database.enums import TaskType
from app.local_ai.ollama_client import OllamaClient

log = get_logger("model_manager")

SMALL = "small"
DEFAULT = "default"
STRONG = "strong"
EMBEDDING = "embedding"

# Which class of model each task type wants. Deliberately data, not code.
TASK_MODEL_CLASS: dict[TaskType, str] = {
    TaskType.GENERAL: DEFAULT,
    TaskType.ARITHMETIC: SMALL,
    TaskType.DATE: SMALL,
    TaskType.CLASSIFICATION: SMALL,
    TaskType.STRUCTURED_DATA: DEFAULT,
    TaskType.EXTRACTION: DEFAULT,
    TaskType.SUMMARIZATION: DEFAULT,
    TaskType.DOCUMENT_QA: STRONG,
    TaskType.RESEARCH: STRONG,
    TaskType.CODE: STRONG,
    TaskType.REASONING: STRONG,
}


@dataclass
class ModelInfo:
    name: str
    installed: bool
    role: str


class ModelManager:
    def __init__(self, client: OllamaClient, settings: Settings, cache_seconds: float = 30.0):
        self.client = client
        self.settings = settings
        self._cache_seconds = cache_seconds
        self._models: list[str] = []
        self._fetched_at: float = 0.0

    # ------------------------------------------------------------ discovery
    def installed_models(self, refresh: bool = False) -> list[str]:
        now = time.monotonic()
        if refresh or not self._models or now - self._fetched_at > self._cache_seconds:
            fetched = self.client.list_models()
            if fetched or refresh:
                self._models = fetched
            self._fetched_at = now
        return self._models

    def invalidate(self) -> None:
        self._fetched_at = 0.0

    def is_available(self) -> bool:
        return bool(self.installed_models())

    def has_model(self, name: str) -> bool:
        installed = self.installed_models()
        if name in installed:
            return True
        # "llama3.2" should match an installed "llama3.2:3b".
        base = name.split(":")[0]
        return any(m.split(":")[0] == base for m in installed)

    # ------------------------------------------------------------ selection
    def configured(self, role: str) -> str:
        return {
            SMALL: self.settings.SMALL_LOCAL_MODEL,
            DEFAULT: self.settings.DEFAULT_LOCAL_MODEL,
            STRONG: self.settings.STRONG_LOCAL_MODEL,
            EMBEDDING: self.settings.EMBEDDING_MODEL,
        }.get(role, self.settings.DEFAULT_LOCAL_MODEL)

    def select(self, task_type: TaskType | str, requested: str | None = None) -> str | None:
        """Resolve a model name, or None when nothing usable is installed.

        Preference order: an explicitly requested model, the model class the
        task asks for, then the remaining classes as a graceful degradation,
        then anything that is installed.
        """
        installed = self.installed_models()
        if not installed:
            return None
        if requested:
            if self.has_model(requested):
                return self._resolve(requested, installed)
            log.warning("requested_model_missing", requested=requested)

        try:
            role = TASK_MODEL_CLASS[TaskType(task_type)]
        except ValueError:
            role = DEFAULT

        order = {
            SMALL: [SMALL, DEFAULT, STRONG],
            DEFAULT: [DEFAULT, STRONG, SMALL],
            STRONG: [STRONG, DEFAULT, SMALL],
        }[role]
        for candidate_role in order:
            name = self.configured(candidate_role)
            if self.has_model(name):
                return self._resolve(name, installed)
        # Nothing configured is installed: use whatever is there rather than
        # failing, but say so loudly.
        fallback = installed[0]
        log.warning("no_configured_model_installed", using=fallback, installed=len(installed))
        return fallback

    def select_embedding_model(self) -> str | None:
        name = self.settings.EMBEDDING_MODEL
        if self.has_model(name):
            return self._resolve(name, self.installed_models())
        return None

    @staticmethod
    def _resolve(name: str, installed: list[str]) -> str:
        if name in installed:
            return name
        base = name.split(":")[0]
        for model in installed:
            if model.split(":")[0] == base:
                return model
        return name

    # --------------------------------------------------------------- report
    def report(self) -> list[dict]:
        installed = self.installed_models()
        roles = {
            self.configured(SMALL): SMALL,
            self.configured(DEFAULT): DEFAULT,
            self.configured(STRONG): STRONG,
            self.configured(EMBEDDING): EMBEDDING,
        }
        # "installed" is exact presence; "resolved_to" is what select() would
        # actually use, which may be a different tag of the same base model.
        rows = [
            {
                "name": name,
                "installed": name in installed,
                "resolved_to": self._resolve(name, installed) if self.has_model(name) else None,
                "role": role,
            }
            for name, role in roles.items()
        ]
        known = {r["name"] for r in rows}
        rows.extend(
            {"name": name, "installed": True, "resolved_to": name, "role": "other"}
            for name in installed
            if name not in known
        )
        return rows
