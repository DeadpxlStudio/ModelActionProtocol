"""Model Action Protocol (MAP) — Python reference implementation.

Conforms to ``spec/SPEC.md`` v0.1.0. See the spec for the wire format,
canonicalization rule, and chain verification algorithm. See
``DESIGN.md`` for implementation choices.
"""

from __future__ import annotations

import logging as _logging

from ._version import SPEC_VERSION, __version__
from .core.action import (
    Action,
    ActionRecord,  # back-compat alias for the spec's exact name
    AgentIdentity,
    AgentLifecycle,
    ApprovalStatus,
    AuthorizationGrant,
    CompensatingAction,
    CriticCorrection,
    CriticCost,
    CriticResult,
    CriticVerdict,
    LedgerEntry,
    LedgerEntryStatus,
    LedgerExport,
    LedgerSnapshots,
    LedgerStats,
    Reversal,
    ReversalSchema,  # back-compat alias
    ReversalStrategy,
    to_jsonable,
)
from ._map import Map
from .core.canonical import canonical_bytes, canonical_str
from .core.critic import (
    Critic,
    RiskClassifier,
    RiskTier,
    Rule,
    default_risk_classifier,
    llm_critic,
    rule_critic,
    tiered_critic,
)
from .core.ledger import Ledger, MapEvent, MapEventHandler
from .core.reversal import Reverser, ReverserRegistry
from .learning import CorrectionPattern, LearnedRule, LearningEngine
from .core.snapshot import (
    GENESIS_HASH,
    capture_snapshot,
    compute_entry_hash,
    sha256_hex,
    state_hash,
    verify_chain,
)
from .exceptions import (
    ConformanceError,
    CriticError,
    EntryNotFound,
    LedgerCorruption,
    LedgerError,
    MapError,
    NotReversible,
    ReversalError,
    ReversalFailed,
    StoreError,
    ValidationError,
)
from .stores.memory import LedgerStore, MemoryStore

# Library logging hygiene per DESIGN.md §7 — attach a NullHandler so users
# who don't configure logging don't see "no handlers" warnings.
_logging.getLogger("map").addHandler(_logging.NullHandler())

__all__ = [
    # Version
    "__version__",
    "SPEC_VERSION",
    # Constants
    "GENESIS_HASH",
    # Core models
    "Action",
    "ActionRecord",
    "AgentIdentity",
    "AgentLifecycle",
    "ApprovalStatus",
    "AuthorizationGrant",
    "CompensatingAction",
    "CriticCorrection",
    "CriticCost",
    "CriticResult",
    "CriticVerdict",
    "LedgerEntry",
    "LedgerEntryStatus",
    "LedgerExport",
    "LedgerSnapshots",
    "LedgerStats",
    "Reversal",
    "ReversalSchema",
    "ReversalStrategy",
    # Hashing & verification
    "canonical_bytes",
    "canonical_str",
    "capture_snapshot",
    "compute_entry_hash",
    "sha256_hex",
    "state_hash",
    "verify_chain",
    # Orchestrator
    "Map",
    # Ledger and stores
    "Ledger",
    "LedgerStore",
    "MemoryStore",
    "MapEvent",
    "MapEventHandler",
    # Critic
    "Critic",
    "Rule",
    "RiskClassifier",
    "RiskTier",
    "default_risk_classifier",
    "llm_critic",
    "rule_critic",
    "tiered_critic",
    # Reversal
    "Reverser",
    "ReverserRegistry",
    # Learning
    "CorrectionPattern",
    "LearnedRule",
    "LearningEngine",
    # Exceptions
    "MapError",
    "ValidationError",
    "LedgerError",
    "LedgerCorruption",
    "EntryNotFound",
    "StoreError",
    "ReversalError",
    "NotReversible",
    "ReversalFailed",
    "CriticError",
    "ConformanceError",
    # Helpers
    "to_jsonable",
]
