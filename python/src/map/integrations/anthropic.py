"""Anthropic SDK integration — thin wrapper, one primitive.

Per DESIGN.md §13. MAP is not building a framework. The integration
exposes a single function — ``wrap_tool_call`` — that takes a tool-use
block from an Anthropic Messages response, invokes the corresponding tool
function, records the call as a ledger entry, and returns a tool_result
block ready to send back to the model.

Researchers compose this with their own agent loop. We don't own the loop.

Requires the ``[anthropic]`` extra::

    pip install "map-protocol[anthropic]"
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..core.action import Action, CriticResult

if TYPE_CHECKING:
    from .._map import Map

logger = logging.getLogger("map.integrations.anthropic")

ToolFn = Callable[..., Any]


def wrap_tool_call(
    map_instance: Map,
    tool_use_block: Any,
    registry: dict[str, ToolFn],
) -> dict[str, Any]:
    """Execute one tool_use block under MAP and return a tool_result block.

    Args:
        map_instance: The ``Map`` orchestrator that owns the ledger and reverser
            registry. The action will be appended to its ledger.
        tool_use_block: An object with ``.name``, ``.input``, and ``.id``
            (Anthropic's ``ToolUseBlock``) — also accepts the equivalent dict
            shape so this works against mocks.
        registry: A mapping of tool name → callable. The callable is invoked
            with ``**tool_use_block.input``.

    Returns:
        A dict in Anthropic's ``tool_result`` content-block shape::

            {"type": "tool_result", "tool_use_id": <id>, "content": <output>}

        Errors during tool execution are converted to a tool_result with
        ``"is_error": True`` and the exception message — the model can then
        recover or escalate.
    """
    name, tool_input, use_id = _unpack_block(tool_use_block)

    fn = registry.get(name)
    if fn is None:
        return _error_result(
            use_id,
            f"unknown tool {name!r}; registry has {sorted(registry.keys())}",
        )

    try:
        output = fn(**tool_input) if isinstance(tool_input, dict) else fn(tool_input)
    except Exception as e:
        logger.warning("tool %s raised: %s", name, e)
        return _error_result(use_id, str(e))

    action = Action(tool=name, input=tool_input, output=output)
    map_instance._record_action(action, output)

    return {
        "type": "tool_result",
        "tool_use_id": use_id,
        "content": _coerce_content(output),
    }


def _unpack_block(block: Any) -> tuple[str, dict[str, Any], str]:
    if isinstance(block, dict):
        return (
            str(block.get("name", "")),
            block.get("input", {}) or {},
            str(block.get("id", "")),
        )
    name = getattr(block, "name", "")
    tool_input = getattr(block, "input", {}) or {}
    use_id = getattr(block, "id", "")
    return str(name), dict(tool_input), str(use_id)


def _coerce_content(output: Any) -> Any:
    """Anthropic accepts string content or a list of content blocks. Normalize."""
    if isinstance(output, str):
        return output
    return [{"type": "text", "text": _to_text(output)}]


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    import json

    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)


def _error_result(use_id: str, message: str) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": use_id,
        "is_error": True,
        "content": message,
    }


__all__ = ["ToolFn", "wrap_tool_call"]
