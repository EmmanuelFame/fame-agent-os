from __future__ import annotations
from dataclasses import dataclass
from .models import Role, Tier

TIER_ORDER = {Tier.OPERATOR: 0, Tier.BUILDER: 1, Tier.ARCHITECT: 2}
ALIASES = {"luna": Tier.OPERATOR, "terra": Tier.BUILDER, "sol": Tier.ARCHITECT}

@dataclass(frozen=True)
class BudgetPolicy:
    name: str
    architect_threshold: int
    difficult_threshold: int

POLICIES = {"economy": BudgetPolicy("economy", 8, 5), "balanced": BudgetPolicy("balanced", 6, 4), "quality": BudgetPolicy("quality", 5, 3)}

def tier_allowed(required: Tier, maximum: str | None) -> bool:
    if not maximum: return True
    maximum_tier = ALIASES.get(maximum, Tier(maximum))
    return TIER_ORDER[required] <= TIER_ORDER[maximum_tier]
