"""Smoke tests for the LearningEngine.

The cross-language fingerprint conformance is exercised by
`test_conformance.py` against `spec/fixtures/v0.1/learning-patterns.json`.
This file covers the engine's other behaviors: thresholding, rule
proposals, exports.
"""

from __future__ import annotations

from typing import Any

from map import (
    Action,
    CriticResult,
    Ledger,
    LearningEngine,
    MemoryStore,
)
from map.core.action import LedgerEntry


def _populate_with_corrections(ledger: Ledger, n: int = 4) -> None:
    """Ledger with `n` identical CORRECTED entries on the same tool."""
    for i in range(n):
        ledger.append(
            Action(tool="createTicket", input={"title": f"Issue {i}"}, output={"id": i}),
            {"tickets": i},
            {"tickets": i + 1},
            CriticResult(
                verdict="CORRECTED",
                reason="missing project tag; auto-prefixed",
                correction={"tool": "createTicket", "input": {"title": f"[OPS] Issue {i}"}},  # type: ignore[arg-type]
            ),
        )


# ─── analyze_patterns ──────────────────────────────────────────────────────


def test_analyze_patterns_groups_by_fingerprint() -> None:
    ledger = Ledger(MemoryStore())
    _populate_with_corrections(ledger, 4)

    engine = LearningEngine()
    patterns = engine.analyze_patterns(ledger.get_entries())

    assert len(patterns) == 1
    assert patterns[0].count == 4
    assert patterns[0].tool == "createTicket"


def test_analyze_patterns_ignores_pass_entries() -> None:
    ledger = Ledger(MemoryStore())
    ledger.append(
        Action(tool="x", input={}, output=None),
        None,
        None,
        CriticResult(verdict="PASS", reason="ok"),
    )
    engine = LearningEngine()
    assert engine.analyze_patterns(ledger.get_entries()) == []


# ─── propose_rules ─────────────────────────────────────────────────────────


def test_propose_rules_respects_threshold() -> None:
    ledger = Ledger(MemoryStore())
    _populate_with_corrections(ledger, 4)

    engine = LearningEngine()
    # Threshold 5 — 4 observations is below it.
    assert engine.propose_rules(ledger.get_entries(), threshold=5) == []
    # Threshold 3 — 4 observations is above it.
    proposed = engine.propose_rules(ledger.get_entries(), threshold=3)
    assert len(proposed) == 1
    assert proposed[0].observedCount == 4
    assert proposed[0].verdict == "CORRECTED"
    assert proposed[0].approved is False


def test_propose_rules_does_not_re_propose_existing() -> None:
    ledger = Ledger(MemoryStore())
    _populate_with_corrections(ledger, 4)

    engine = LearningEngine()
    first = engine.propose_rules(ledger.get_entries(), threshold=3)
    for rule in first:
        engine.add_proposed_rule(rule)

    second = engine.propose_rules(ledger.get_entries(), threshold=3)
    assert second == []


def test_approve_rule_marks_it_approved() -> None:
    ledger = Ledger(MemoryStore())
    _populate_with_corrections(ledger, 4)

    engine = LearningEngine()
    [proposal] = engine.propose_rules(ledger.get_entries(), threshold=3)
    engine.add_proposed_rule(proposal)
    engine.approve_rule(proposal.id)

    rules = engine.get_rules()
    assert len(rules) == 1
    assert rules[0].approved is True
    assert rules[0].approvedAt is not None


# ─── to_rule_critic ────────────────────────────────────────────────────────


def test_to_rule_critic_fires_on_matching_tool() -> None:
    ledger = Ledger(MemoryStore())
    _populate_with_corrections(ledger, 4)

    engine = LearningEngine()
    [proposal] = engine.propose_rules(ledger.get_entries(), threshold=3)
    engine.add_proposed_rule(proposal)
    engine.approve_rule(proposal.id)

    critic = engine.to_rule_critic()
    result = critic(
        Action(tool="createTicket", input={"title": "Issue 99"}, output=None),
        None,
        None,
    )
    assert result.verdict == "CORRECTED"
    assert "[learned]" in result.reason


def test_to_rule_critic_passes_on_non_matching_tool() -> None:
    engine = LearningEngine()
    critic = engine.to_rule_critic()
    result = critic(
        Action(tool="unrelated_tool", input={}, output=None),
        None,
        None,
    )
    assert result.verdict == "PASS"


# ─── exports ───────────────────────────────────────────────────────────────


def test_export_fine_tuning_data_only_includes_human_resolved() -> None:
    """Entries without `approval` set MUST NOT appear in fine-tuning export."""
    ledger = Ledger(MemoryStore())
    e1 = ledger.append(
        Action(tool="x", input={}, output=None),
        None,
        None,
        CriticResult(verdict="CORRECTED", reason="r"),
    )
    # Mark e1 as approved
    ledger._entries[0] = e1.model_copy(update={"approval": "approved"})

    ledger.append(
        Action(tool="y", input={}, output=None),
        None,
        None,
        CriticResult(verdict="CORRECTED", reason="r2"),
    )
    # Second entry has no approval — should be excluded.

    engine = LearningEngine()
    exported = engine.export_fine_tuning_data(ledger.get_entries())
    assert len(exported) == 1
    assert exported[0]["humanApproval"] == "approved"


def test_export_agent_memory_filters_by_agent_id() -> None:
    ledger = Ledger(MemoryStore())
    e1 = ledger.append(
        Action(tool="x", input={}, output=None),
        None,
        None,
        CriticResult(verdict="FLAGGED", reason="dangerous"),
    )
    e2 = ledger.append(
        Action(tool="y", input={}, output=None),
        None,
        None,
        CriticResult(verdict="CORRECTED", reason="auto-fixed"),
    )
    # Tag entries with different agent IDs
    ledger._entries[0] = e1.model_copy(update={"agentId": "agent-A"})
    ledger._entries[1] = e2.model_copy(update={"agentId": "agent-B"})

    engine = LearningEngine()
    a_only = engine.export_agent_memory(ledger.get_entries(), agent_id="agent-A")
    assert len(a_only) == 1
    assert a_only[0]["tool"] == "x"
    assert "FLAGGED" in a_only[0]["lesson"] or "FLAGGED" in a_only[0]["verdict"]

    all_agents = engine.export_agent_memory(ledger.get_entries())
    assert len(all_agents) == 2
