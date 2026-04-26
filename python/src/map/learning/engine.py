"""LearningEngine — the ledger IS the training data.

Three levels of learning, mirroring the TS reference:

1. Rule extraction — after N identical corrections, propose a deterministic
   rule. No LLM needed for that check anymore.
2. Critic fine-tuning — export a corpus of corrections + human resolutions
   in a shape suitable for fine-tuning a critic model.
3. Agent memory — export correction history per-agent so the agent can
   avoid repeating mistakes ("last time I tried X, it was FLAGGED").

All learning is **local to the org**. Nothing leaves your environment via
this module. See SPEC.md §10 for security context.

The pattern fingerprint algorithm is documented in SPEC.md §6.3 and is
part of the cross-language conformance fixtures — Python's fingerprint
output MUST match TS for the same inputs.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..core.action import Action, CriticCorrection, LedgerEntry
from ..core.critic import Critic
from ..core.action import CriticResult

logger = logging.getLogger("map.learning")

_CONFIG = ConfigDict(extra="forbid")


class CorrectionPattern(BaseModel):
    """An observed cluster of similar corrections."""

    model_config = _CONFIG

    tool: str
    fingerprint: str
    summary: str
    count: int
    entryIds: list[str]
    typicalCorrection: CriticCorrection | None = None
    typicalReason: str


class LearnedRule(BaseModel):
    """A proposal for a deterministic rule, derived from a pattern."""

    model_config = _CONFIG

    id: str
    description: str
    tool: str
    verdict: str
    correction: CriticCorrection | None = None
    observedCount: int
    approved: bool = False
    proposedAt: str
    approvedAt: str | None = None


class LearningEngine:
    """Read-only consumer of the ledger.

    Never modifies the ledger. Proposes rules; humans approve them.
    """

    def __init__(self) -> None:
        self._rules: list[LearnedRule] = []
        self._patterns: dict[str, CorrectionPattern] = {}

    # ─── Pattern extraction ────────────────────────────────────────────────

    def analyze_patterns(self, entries: list[LedgerEntry]) -> list[CorrectionPattern]:
        """Group ledger entries by SPEC.md §6.3 fingerprint.

        Returns the patterns observed across ``entries``. Calling this
        replaces any previously-cached patterns on the engine.
        """
        self._patterns.clear()
        for entry in entries:
            if entry.critic.verdict not in ("CORRECTED", "FLAGGED"):
                continue
            fp = self._fingerprint(entry)
            existing = self._patterns.get(fp)
            if existing:
                existing.count += 1
                existing.entryIds.append(entry.id)
            else:
                typical_correction = (
                    CriticCorrection(
                        tool=entry.critic.correction.tool,
                        input=entry.critic.correction.input,
                    )
                    if entry.critic.correction
                    else None
                )
                self._patterns[fp] = CorrectionPattern(
                    tool=entry.action.tool,
                    fingerprint=fp,
                    summary=f"{entry.critic.verdict}: {entry.action.tool} — {entry.critic.reason}",
                    count=1,
                    entryIds=[entry.id],
                    typicalCorrection=typical_correction,
                    typicalReason=entry.critic.reason,
                )
        return list(self._patterns.values())

    @staticmethod
    def _fingerprint(entry: LedgerEntry) -> str:
        """SPEC.md §6.3 — SHA-256(verdict:tool:correctionTool|"none")."""
        correction_tool = entry.critic.correction.tool if entry.critic.correction else "none"
        material = f"{entry.critic.verdict}:{entry.action.tool}:{correction_tool}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    # ─── Rule proposal ─────────────────────────────────────────────────────

    def propose_rules(
        self,
        entries: list[LedgerEntry],
        threshold: int = 3,
    ) -> list[LearnedRule]:
        """Propose rules for any pattern observed at least ``threshold`` times.

        Existing rules with the same id are not re-proposed. Returns the
        newly-proposed rules; the caller is expected to review and call
        ``add_proposed_rule(...)`` + ``approve_rule(...)``.
        """
        patterns = self.analyze_patterns(entries)
        proposals: list[LearnedRule] = []
        for pattern in patterns:
            if pattern.count < threshold:
                continue
            rule_id = f"rule_{pattern.fingerprint}"
            if any(r.id == rule_id for r in self._rules):
                continue
            rule = LearnedRule(
                id=rule_id,
                description=(
                    f"Auto-proposed: {pattern.summary} "
                    f"(observed {pattern.count} times)"
                ),
                tool=pattern.tool,
                verdict="CORRECTED" if pattern.typicalCorrection else "FLAGGED",
                correction=pattern.typicalCorrection,
                observedCount=pattern.count,
                approved=False,
                proposedAt=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
            proposals.append(rule)
        return proposals

    def add_proposed_rule(self, rule: LearnedRule) -> None:
        self._rules.append(rule)

    def approve_rule(self, rule_id: str) -> None:
        for rule in self._rules:
            if rule.id == rule_id:
                rule.approved = True
                rule.approvedAt = (
                    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                )
                return
        raise ValueError(f"rule {rule_id!r} not found; add_proposed_rule first")

    def get_rules(self) -> list[LearnedRule]:
        return list(self._rules)

    def get_patterns(self) -> list[CorrectionPattern]:
        return list(self._patterns.values())

    # ─── Critic adapter — Level 1 learning ─────────────────────────────────

    def to_rule_critic(self) -> Critic:
        """Compile approved rules into a sync ``Critic`` callable.

        The result fires for any approved rule whose tool matches the
        action's tool; first match wins. If no rule fires, returns PASS.
        """
        approved = [r for r in self._rules if r.approved]

        def _critic(action: Action, state_before: Any, state_after: Any) -> CriticResult:
            for rule in approved:
                if rule.tool == action.tool:
                    return CriticResult(
                        verdict=rule.verdict,  # type: ignore[arg-type]
                        reason=f"[learned] {rule.description}",
                        correction=rule.correction,
                    )
            return CriticResult(verdict="PASS", reason="no learned rules triggered")

        return _critic

    # ─── Exports — Levels 2 & 3 ────────────────────────────────────────────

    def export_fine_tuning_data(
        self, entries: list[LedgerEntry]
    ) -> list[dict[str, Any]]:
        """Level 2 — export human-resolved corrections as training examples.

        **Export format is MAP-native, not provider-native.** Each item is::

            {
              "input":  {"action": ActionRecord, "stateBefore": Any, "stateAfter": Any},
              "output": {"verdict": str, "reason": str,
                         "correction": {"tool": str, "input": dict} | None},
              "humanApproval": "approved" | "rejected" | "pending"
            }

        This is **not** OpenAI's fine-tune JSONL shape (``{"messages": [...]}``)
        nor Anthropic's. To feed the export to a specific provider's
        fine-tuning API, write a small adapter — typically 10–20 lines that
        flattens MAP's input/output into the provider's expected role-tagged
        message format. A future minor release may ship adapters in
        ``map.learning.adapters`` if there's demand.

        Only entries whose ``approval`` is set (``approved`` / ``rejected`` /
        ``pending``) are included — unresolved corrections are not training
        signal.
        """
        out: list[dict[str, Any]] = []
        for e in entries:
            if e.critic.verdict not in ("CORRECTED", "FLAGGED"):
                continue
            if e.approval is None:
                continue
            correction_dump: dict[str, Any] | None = None
            if e.critic.correction:
                correction_dump = {
                    "tool": e.critic.correction.tool,
                    "input": e.critic.correction.input,
                }
            out.append(
                {
                    "input": {
                        "action": e.action.model_dump(by_alias=True, exclude_none=True),
                        "stateBefore": e.snapshots.before,
                        "stateAfter": e.snapshots.after,
                    },
                    "output": {
                        "verdict": e.critic.verdict,
                        "reason": e.critic.reason,
                        "correction": correction_dump,
                    },
                    "humanApproval": e.approval,
                }
            )
        return out

    def export_agent_memory(
        self,
        entries: list[LedgerEntry],
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Level 3 — export correction history scoped to an agent."""
        import json

        out: list[dict[str, Any]] = []
        for e in entries:
            if e.critic.verdict not in ("CORRECTED", "FLAGGED"):
                continue
            if agent_id is not None and e.agentId != agent_id:
                continue
            lesson = (
                f"This action was auto-corrected: {e.critic.reason}. Avoid this pattern."
                if e.critic.verdict == "CORRECTED"
                else f"This action was FLAGGED and required human review: {e.critic.reason}. "
                "Do not attempt this without explicit approval."
            )
            out.append(
                {
                    "tool": e.action.tool,
                    "whatHappened": f"Called {e.action.tool} with {json.dumps(e.action.input)}",
                    "verdict": e.critic.verdict,
                    "lesson": lesson,
                }
            )
        return out


__all__ = ["CorrectionPattern", "LearnedRule", "LearningEngine"]
