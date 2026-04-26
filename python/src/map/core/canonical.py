"""RFC 8785 (JCS) canonicalization, vendored.

Per DESIGN.md §10, MAP Python carries no `jcs` PyPI dependency. This
implementation produces byte-identical output to the `canonicalize` npm
package (used by the TS reference impl) and to the `jcs` PyPI package for
all values that appear in MAP wire format: JSON objects, arrays, strings,
booleans, integers, IEEE 754 doubles in the safe range, and ``None``.

The MAP wire format does **not** carry exotic numbers (NaN, ±Infinity, very
large integers beyond IEEE 754 safe range). Implementations that pass such
values are violating SPEC.md §4 and behavior is undefined.

References:
- RFC 8785 — JSON Canonicalization Scheme.
- ECMA-262 §7.1.12.1 — Number::toString.
"""

from __future__ import annotations

import json
import math
from typing import Any

from ..exceptions import ValidationError

# RFC 8785 §3.2.2.3 — JCS mandates ECMAScript Number::toString
# (ECMA-262 §7.1.12.1) for serializing IEEE 754 doubles. The relevant
# divergence from Python: integer-valued doubles in JS-safe range emit
# *without* a decimal point. JS's `JSON.stringify(1.0)` is `"1"`; Python's
# `json.dumps(1.0)` is `"1.0"`. The two would hash differently.
#
# We bridge the gap by promoting integer-valued floats in safe range to int
# before handing them to `json.dumps`. The safe range is
# [-(2^53 - 1), 2^53 - 1] — the largest integers IEEE 754 doubles can
# represent without precision loss, matching JS's Number.MAX_SAFE_INTEGER.
# Booleans subclass int in Python; they're skipped so `True`/`False`
# serialize as `true`/`false`, not as `1`/`0`.
#
# This is the minimum bridge for the values that appear in MAP wire
# format. We do NOT implement the full ECMA-262 algorithm (scientific
# notation thresholds, sub-normal handling) because the wire format
# excludes those values per SPEC.md §4.
_MAX_SAFE_INTEGER = (1 << 53) - 1


def _normalize(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            raise ValidationError("NaN is not permitted in MAP wire format (RFC 8785 §3.2.2.3)")
        if math.isinf(value):
            raise ValidationError(
                "±Infinity is not permitted in MAP wire format (RFC 8785 §3.2.2.3)"
            )
        if value.is_integer() and abs(value) <= _MAX_SAFE_INTEGER:
            return int(value)
        return value
    if isinstance(value, int):
        # Python ints are arbitrary precision; JCS requires JS-safe range.
        if abs(value) > _MAX_SAFE_INTEGER:
            raise ValidationError(
                f"integer {value} exceeds JS safe range "
                f"[-(2^53-1), 2^53-1]; MAP wire format requires JS-representable numbers"
            )
        return value
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, tuple):
        return [_normalize(v) for v in value]
    return value


def canonical_str(obj: Any) -> str:
    """Return the JCS-canonical JSON string for ``obj``.

    The result is RFC 8785-compliant for all JSON values that appear in the
    MAP wire format (see module docstring for limits).
    """
    # Python's json.dumps with sort_keys=True sorts dict keys by Unicode
    # codepoint. For all keys that appear in MAP wire format (ASCII / BMP
    # alphanumerics), this is byte-identical to UTF-16 code-unit ordering.
    # If a future spec version permits astral-plane object keys, this
    # function MUST be replaced with a UTF-16 codepoint sort.
    return json.dumps(
        _normalize(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(obj: Any) -> bytes:
    """Return the JCS-canonical UTF-8 bytes for ``obj``."""
    return canonical_str(obj).encode("utf-8")
