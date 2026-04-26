"""Reverser registry and execution.

A *reverser* is a sync callable provided by the user that undoes an action.
The registry is keyed by tool name. When a ledger entry is rolled back via
its reversal strategy (COMPENSATE / RESTORE), the registry is consulted to
find and execute the appropriate reverser.

Per DESIGN.md §2 — sync at v0.1. Reverser callables are
``Callable[[Action, Any], Any]`` (the action and its recorded output).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..exceptions import NotReversible, ReversalFailed
from .action import Action, Reversal

logger = logging.getLogger("map.reversal")

#: A reverser takes the original action + its output and returns the
#: compensating result (e.g., the credit-memo invoice id, or `None`).
Reverser = Callable[[Action, Any], Any]


class ReverserRegistry:
    """In-memory mapping of tool name → reverser callable.

    Reversers are registered at runtime (typically via the ``@reversible``
    decorator from ``map.tools``). The registry is owned by a ``Map``
    instance; multiple instances do not share state.
    """

    def __init__(self) -> None:
        self._reversers: dict[str, Reverser] = {}
        self._schemas: dict[str, Reversal] = {}

    def register(
        self,
        tool: str,
        reverser: Reverser,
        schema: Reversal | None = None,
    ) -> None:
        """Register a reverser for a tool.

        ``schema`` is the optional declarative reversal description (used by
        the LLM critic and external auditors). Re-registering a tool
        replaces the prior reverser without warning — last write wins.
        """
        self._reversers[tool] = reverser
        if schema is not None:
            self._schemas[tool] = schema
        logger.debug("registered reverser for tool=%s", tool)

    def get_reverser(self, tool: str) -> Reverser | None:
        return self._reversers.get(tool)

    def get_schema(self, tool: str) -> Reversal | None:
        return self._schemas.get(tool)

    def execute(self, action: Action, output: Any) -> Any:
        """Run the registered reverser for ``action.tool``.

        Raises:
            NotReversible: no reverser is registered for ``action.tool``.
            ReversalFailed: the reverser ran but raised an exception.
        """
        reverser = self._reversers.get(action.tool)
        if reverser is None:
            raise NotReversible(
                f"no reverser registered for tool {action.tool!r}; "
                "register one with @map.reversible(...) or registry.register(...)"
            )
        try:
            return reverser(action, output)
        except Exception as e:
            raise ReversalFailed(
                f"reverser for tool {action.tool!r} raised: {e}"
            ) from e

    def known_tools(self) -> list[str]:
        return sorted(self._reversers.keys())


__all__ = ["Reverser", "ReverserRegistry"]
