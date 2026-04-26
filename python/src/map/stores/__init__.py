"""Pluggable ledger storage backends."""

from .memory import MemoryStore

__all__ = ["MemoryStore"]
