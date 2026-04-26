"""Tool decorators — the @reversible family.

Decorators are the Pythonic surface; they delegate to the imperative
``Map.register_*`` methods. They produce wrapped callables that:

1. Carry their reversal schema as ``.reversal`` for introspection.
2. Carry their JSON tool schema (Pydantic-derived) as ``.tool_schema`` for
   handoff to the Anthropic SDK or any tool-calling LLM.
3. Otherwise behave exactly like the wrapped function.

The actual reverser registration happens against a ``ReverserRegistry``
which the ``Map`` orchestrator owns.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from ..core.action import (
    CompensatingAction,
    Reversal,
    ReversalStrategy,
)
from ..core.reversal import Reverser, ReverserRegistry

F = TypeVar("F", bound=Callable[..., Any])


def reversible(
    registry: ReverserRegistry,
    *,
    reverser: Reverser,
    description: str | None = None,
) -> Callable[[F], F]:
    """Mark a function as reversible via a custom reverser callable.

    The reverser is invoked as ``reverser(action, output)`` during rollback.
    It receives the original ``Action`` (with input + output) and returns
    whatever compensating result is appropriate (e.g., a credit-memo id).

    The wrapped function gets ``.tool_schema`` and ``.reversal`` attributes
    for handoff to LLM tool-call surfaces.
    """

    def _decorator(fn: F) -> F:
        schema = Reversal(strategy="COMPENSATE", description=description)
        registry.register(fn.__name__, reverser, schema=schema)

        wrapped = _attach_metadata(fn, schema)
        return wrapped  # type: ignore[return-value]

    return _decorator


def compensate(
    registry: ReverserRegistry,
    *,
    compensating_tool: str,
    input_mapping: dict[str, str] | None = None,
    description: str | None = None,
) -> Callable[[F], F]:
    """Mark a function as reversible via COMPENSATE — dispatch a compensating tool.

    Used when the underlying system can't restore prior state but can issue
    a counter-action (e.g., duplicate invoice → credit memo).
    """

    def _decorator(fn: F) -> F:
        schema = Reversal(
            strategy="COMPENSATE",
            compensatingAction=CompensatingAction(
                tool=compensating_tool,
                inputMapping=input_mapping or {},
            ),
            description=description,
        )
        # No reverser callable here — the orchestrator dispatches a different
        # tool by name. Register a sentinel that raises if called directly,
        # so dispatch-by-tool is the only legitimate path.
        def _sentinel(action: Any, output: Any) -> Any:
            raise RuntimeError(
                f"compensate-style reversal for {fn.__name__!r} must be dispatched "
                f"via the {compensating_tool!r} tool, not invoked as a reverser callable"
            )

        registry.register(fn.__name__, _sentinel, schema=schema)
        return _attach_metadata(fn, schema)  # type: ignore[return-value]

    return _decorator


def restore(
    registry: ReverserRegistry,
    *,
    capture: Callable[..., Any],
    reverser: Reverser,
    capture_method: str | None = None,
    description: str | None = None,
) -> Callable[[F], F]:
    """Mark a function as reversible via RESTORE — capture before-state, reverse via reverser.

    The runtime is expected to call ``capture(*args, **kwargs)`` BEFORE the
    function runs and stash the result on the resulting ``Action``'s
    ``capturedState``. On rollback, ``reverser(action, output)`` is invoked;
    the reverser is responsible for using ``action.capturedState`` to put
    the world back.
    """

    def _decorator(fn: F) -> F:
        schema = Reversal(
            strategy="RESTORE",
            captureMethod=capture_method,
            description=description,
        )
        registry.register(fn.__name__, reverser, schema=schema)
        wrapped = _attach_metadata(fn, schema)
        wrapped.capture = capture  # type: ignore[attr-defined]
        return wrapped  # type: ignore[return-value]

    return _decorator


def escalate(
    registry: ReverserRegistry,
    *,
    approver: str,
    description: str | None = None,
) -> Callable[[F], F]:
    """Mark a function as ESCALATE — execution requires human approval.

    The runtime is expected to halt before invoking ``fn`` and route to
    ``approver`` (role / email / group). Reversers for ESCALATE are not
    registered; if the action ran, it ran with approval, and rollback
    becomes a manual reversal coordinated outside MAP.
    """

    def _decorator(fn: F) -> F:
        schema = Reversal(
            strategy="ESCALATE",
            approver=approver,
            description=description,
        )

        def _refuse(action: Any, output: Any) -> Any:
            raise RuntimeError(
                f"ESCALATE-tagged tool {fn.__name__!r} cannot be reversed automatically; "
                f"reversal requires re-routing to approver {approver!r}"
            )

        registry.register(fn.__name__, _refuse, schema=schema)
        return _attach_metadata(fn, schema)  # type: ignore[return-value]

    return _decorator


# ─── Helpers ────────────────────────────────────────────────────────────────


def _attach_metadata(fn: Callable[..., Any], reversal: Reversal) -> Callable[..., Any]:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    wrapper.reversal = reversal  # type: ignore[attr-defined]
    wrapper.tool_schema = tool_schema(fn)  # type: ignore[attr-defined]
    return wrapper


def tool_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    """Derive a JSON-schema-shaped tool definition from a function signature.

    Mirrors the Anthropic / OpenAI tool-call schema. Parameters are typed
    via inspection of annotations; default values mark them optional.
    Complex parameter types should be Pydantic ``BaseModel`` subclasses;
    their ``model_json_schema()`` is inlined.
    """
    import typing

    sig = inspect.signature(fn)
    # PEP 563 / `from __future__ import annotations` makes annotations
    # strings; resolve them via get_type_hints so we get the real types.
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        hints = {}
    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        annotation = hints.get(name, param.annotation)
        if annotation is inspect.Parameter.empty:
            annotation = str
        prop = _annotation_to_schema(annotation)
        properties[name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {
        "name": fn.__name__,
        "description": (fn.__doc__ or "").strip(),
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def _annotation_to_schema(annotation: Any) -> dict[str, Any]:
    # Pydantic BaseModel subclasses → inline JSON schema
    try:
        from pydantic import BaseModel

        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return annotation.model_json_schema()
    except ImportError:
        pass

    mapping = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        list: {"type": "array"},
        dict: {"type": "object"},
    }
    if annotation in mapping:
        return mapping[annotation]  # type: ignore[index]
    return {}


__all__ = ["reversible", "compensate", "restore", "escalate", "tool_schema"]
