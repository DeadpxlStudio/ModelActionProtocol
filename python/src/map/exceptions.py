"""MAP exception hierarchy.

Single root (`MapError`); subclasses for the failure modes researchers will
want to catch precisely. Per DESIGN.md §4 — no stdlib multi-inheritance.
"""

from __future__ import annotations


class MapError(Exception):
    """Root of the MAP exception hierarchy.

    Catch this to handle any error originating from MAP. For specific
    handling, catch a subclass.
    """


class ValidationError(MapError):
    """Input shape is invalid or violates a schema constraint."""


class LedgerError(MapError):
    """Ledger-related failure."""


class LedgerCorruption(LedgerError):
    """Hash chain is broken; ledger is no longer trustworthy.

    Carries the index of the first detected corruption when available.
    """

    def __init__(self, message: str, *, corrupted_at: int | None = None) -> None:
        super().__init__(message)
        self.corrupted_at = corrupted_at


class EntryNotFound(LedgerError):
    """Lookup of a ledger entry by ID failed."""


class StoreError(LedgerError):
    """Underlying store I/O failed (DB connection, disk, etc)."""


class ReversalError(MapError):
    """Reversal-related failure."""


class NotReversible(ReversalError):
    """The action has no registered reverser."""


class ReversalFailed(ReversalError):
    """A reverser was registered but its execution failed."""


class CriticError(MapError):
    """Critic invocation or response is invalid."""


class ConformanceError(MapError):
    """A cross-language conformance assertion failed.

    Raised by test infrastructure when verifying fixtures, not by the runtime
    library in normal operation.
    """
