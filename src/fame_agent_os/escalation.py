"""Deterministic retry/escalation governor; it never calls a model itself."""
from __future__ import annotations
from dataclasses import dataclass, field
from .models import Role

@dataclass
class EscalationGovernor:
    attempts: dict[Role, set[str]] = field(default_factory=lambda: {r:set() for r in Role})
    def record(self, role: Role, approach: str, failure_kind: str, architectural_uncertainty: bool=False) -> Role | None:
        """Return the next required role, or None for retry/no escalation.

        Environmental failures and repeat attempts do not consume the distinct-approach budget.
        """
        if failure_kind == "environmental": return None
        if architectural_uncertainty and role is Role.BUILDER: return Role.ARCHITECT
        before=len(self.attempts[role]); self.attempts[role].add(approach.strip().lower())
        if len(self.attempts[role]) == before: return None
        if len(self.attempts[role]) < 2: return None
        if role is Role.OPERATOR: return Role.BUILDER
        if role is Role.BUILDER: return Role.ARCHITECT
        return None
