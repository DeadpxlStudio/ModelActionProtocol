"""MAP wire-format models — Pydantic v2.

Conforms to SPEC.md §4. All models exclude unset/None on serialization
(SPEC.md §5.1) so that absent optional fields don't appear in the canonical
JSON used for hashing.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ─── Constants ──────────────────────────────────────────────────────────────

GENESIS_HASH: str = "0" * 64

# ─── Base config ────────────────────────────────────────────────────────────

_CONFIG = ConfigDict(extra="forbid", populate_by_name=True)

# ─── Verdicts and statuses ──────────────────────────────────────────────────

CriticVerdict = Literal["PASS", "CORRECTED", "FLAGGED"]
ReversalStrategy = Literal["COMPENSATE", "RESTORE", "ESCALATE"]
LedgerEntryStatus = Literal["ACTIVE", "ROLLED_BACK"]
ApprovalStatus = Literal["pending", "approved", "rejected"]

# ─── Critic ─────────────────────────────────────────────────────────────────


class CriticCost(BaseModel):
    model_config = _CONFIG

    inputTokens: int = Field(ge=0)
    outputTokens: int = Field(ge=0)
    model: str
    latencyMs: int = Field(ge=0)
    costUsd: float | None = None


class CriticCorrection(BaseModel):
    model_config = _CONFIG

    tool: str
    input: dict[str, Any]


class CriticResult(BaseModel):
    model_config = _CONFIG

    verdict: CriticVerdict
    reason: str
    correction: CriticCorrection | None = None
    cost: CriticCost | None = None


# ─── Reversal ───────────────────────────────────────────────────────────────


class CompensatingAction(BaseModel):
    model_config = _CONFIG

    tool: str
    inputMapping: dict[str, str]


class Reversal(BaseModel):
    """SPEC.md §4.5 — reversal schema for an action.

    Renamed from ``ReversalSchema`` for the Python public surface (see
    DESIGN.md §5). The wire format key remains ``reversalStrategy``.
    """

    model_config = _CONFIG

    strategy: ReversalStrategy
    compensatingAction: CompensatingAction | None = None
    captureMethod: str | None = None
    approver: str | None = None
    description: str | None = None


# Back-compat alias for the spec's exact name.
ReversalSchema = Reversal


# ─── Action ─────────────────────────────────────────────────────────────────


class Action(BaseModel):
    """SPEC.md §4.6 ActionRecord — the unit of work captured in a ledger entry."""

    model_config = _CONFIG

    tool: str
    input: dict[str, Any]
    output: Any = None
    reversalStrategy: ReversalStrategy | None = None
    capturedState: Any = None


# Back-compat alias for the spec's exact name.
ActionRecord = Action


# ─── Snapshots ──────────────────────────────────────────────────────────────


class LedgerSnapshots(BaseModel):
    model_config = _CONFIG

    before: Any = None
    after: Any = None


# ─── Ledger entry ───────────────────────────────────────────────────────────


class LedgerEntry(BaseModel):
    """SPEC.md §4.9 — a single ledger entry."""

    model_config = _CONFIG

    id: str
    sequence: int = Field(ge=0)
    timestamp: str
    action: Action
    stateBefore: str
    stateAfter: str
    snapshots: LedgerSnapshots
    parentHash: str
    hash: str
    critic: CriticResult
    status: LedgerEntryStatus = "ACTIVE"
    approval: ApprovalStatus | None = None
    agentId: str | None = None
    parentEntryId: str | None = None
    lineage: list[str] | None = None
    stateVersion: int | None = None


# ─── Multi-agent (carried, not enforced) ────────────────────────────────────


class AgentIdentity(BaseModel):
    model_config = _CONFIG

    agentId: str
    ownerId: str
    ownerDomain: str
    capabilities: list[str]
    credentialHash: str


class AuthorizationGrant(BaseModel):
    model_config = _CONFIG

    id: str
    timestamp: str
    grantor: AgentIdentity
    grantee: AgentIdentity
    scope: list[str]
    constraints: dict[str, Any]
    expiresAt: str | None = None
    parentGrantId: str | None = None
    revoked: bool | None = None
    hash: str


class AgentLifecycle(BaseModel):
    model_config = _CONFIG

    agentId: str
    parentAgentId: str | None = None
    spawnedAt: str
    terminatedAt: str | None = None
    purpose: str
    isEphemeral: bool
    childAgentIds: list[str]


# ─── Audit export envelope (SPEC.md §8) ─────────────────────────────────────


class LedgerStats(BaseModel):
    model_config = _CONFIG

    total: int
    committed: int
    rolledBack: int
    corrections: int
    flags: int


class LedgerExport(BaseModel):
    model_config = _CONFIG

    protocol: Literal["map"] = "map"
    version: str
    entries: list[LedgerEntry]
    stats: LedgerStats


# ─── Helper ─────────────────────────────────────────────────────────────────


def to_jsonable(model: BaseModel) -> dict[str, Any]:
    """Pydantic dump shape used for hashing — by_alias, exclude_none.

    The wire format spec (§5.1) requires absent optional fields to be
    omitted. This helper centralizes the dump configuration.
    """
    return model.model_dump(by_alias=True, exclude_none=True)
