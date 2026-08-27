from __future__ import annotations
from typing import Protocol
from .codex import CodexRunner, CodexResult
from .models import ModelSpec

class ExecutionBackend(Protocol):
    def run(self, prompt: str, spec: ModelSpec, write: bool = True, cwd: str | None = None) -> CodexResult: ...

class CodexCliBackend(CodexRunner):
    """Legacy/headless backend retained behind a frontend-neutral interface."""

class ExtensionDelegationBackend:
    """Marker backend: the Codex extension executes the selected custom agent."""
    extension_native = True
