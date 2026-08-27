from __future__ import annotations
from dataclasses import dataclass
import re
from .models import Role, Tier
from .policy import POLICIES, tier_allowed

RISK = ("authentication|authorization|access control|payment|ledger|accounting|settlement|secret|encryption|migration|delete|deletion|concurren|idempot|infrastructure|deploy|privilege|public api|financial")
ARCH = ("redesign|architecture|semantic|invariant|unresolved|broad")

@dataclass(frozen=True)
class Route:
    classification: str; role: Role | None; tier: Tier; effort: str | None; risk: str; reasons: tuple[str, ...]; blocked: bool = False
    @property
    def phases(self) -> list[str]:
        if self.classification == "F0": return ["deterministic"]
        if self.classification in ("F4", "F5"): return ["architect", "builder", "verifier"]
        return ["builder" if self.role is Role.BUILDER else "operator", "verifier"]

class Router:
    def route(self, task: str, budget: str = "balanced", max_tier: str | None = None, established_decision: bool = False) -> Route:
        text = task.lower(); reasons=[]; risk_hits = re.findall(RISK, text)
        risk = "high" if risk_hits else "low"
        if re.search(r"^(git status|format|lint|test|graph update|check )", text):
            result = Route("F0", None, Tier.OPERATOR, None, "low", ("deterministic operation",))
        elif any(x in text for x in ("button label", "rename", "typo", "text change", "change the ")) and not risk_hits:
            result = Route("F1", Role.OPERATOR, Tier.OPERATOR, "low", "low", ("established mechanical change", "no schema or security impact", "low expected blast radius"))
        else:
            score = 0
            if risk_hits: score += 4; reasons.append("risk-sensitive domain: " + ", ".join(risk_hits[:3]))
            if re.search(ARCH, text): score += 3; reasons.append("architectural or broad-impact wording")
            if re.search(r"intermittent|debug|failure|two services|cross.service", text): score += 4; reasons.append("ambiguous multi-component diagnosis")
            if re.search(r"crud|endpoint|following existing|implement|add ", text): score += 2; reasons.append("normal implementation work")
            if established_decision and risk_hits: score -= 3; reasons.append("approved pattern lowers execution tier")
            policy=POLICIES[budget]
            exceptional = bool(re.search(r"destructive.*(financial|accounting)|unresolved.*invariant", text))
            if exceptional:
                result=Route("F5", Role.ARCHITECT, Tier.ARCHITECT, "high", "high", tuple(reasons or ["exceptional unresolved high-risk architecture"]))
            elif score >= policy.architect_threshold:
                result=Route("F4", Role.ARCHITECT, Tier.ARCHITECT, "medium", risk, tuple(reasons or ["high impact decision"]))
            elif score >= policy.difficult_threshold:
                result=Route("F3", Role.BUILDER, Tier.BUILDER, "medium", risk, tuple(reasons or ["difficult engineering"]))
            else:
                result=Route("F2", Role.BUILDER, Tier.BUILDER, "low", risk, tuple(reasons or ["normal engineering implementation", "no architectural uncertainty detected"]))
        if not tier_allowed(result.tier, max_tier):
            return Route(result.classification, result.role, result.tier, result.effort, result.risk, result.reasons + ("blocked by --max-tier",), True)
        return result
