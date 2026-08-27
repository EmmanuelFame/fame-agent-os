from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class Role(str, Enum):
    ARCHITECT = "architect"
    BUILDER = "builder"
    OPERATOR = "operator"

class Tier(str, Enum):
    OPERATOR = "operator"
    BUILDER = "builder"
    ARCHITECT = "architect"

@dataclass(frozen=True)
class ModelSpec:
    model: str
    effort: str

DEFAULT_MODELS = {
    Role.ARCHITECT: ModelSpec("gpt-5.6-sol", "medium"),
    Role.BUILDER: ModelSpec("gpt-5.6-terra", "low"),
    Role.OPERATOR: ModelSpec("gpt-5.6-luna", "low"),
}

class ModelResolver:
    def __init__(self, config: dict | None = None):
        mappings = (config or {}).get("models", {})
        self.specs = {role: ModelSpec(str(mappings.get(role.value, {}).get("model", default.model)), str(mappings.get(role.value, {}).get("effort", default.effort))) for role, default in DEFAULT_MODELS.items()}
    def resolve(self, role: Role, elevate: bool = False) -> ModelSpec:
        spec = self.specs[role]
        return ModelSpec(spec.model, "high" if elevate and role is Role.ARCHITECT else spec.effort)
