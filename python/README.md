# model-action-protocol (Python)

Python implementation of the [Model Action Protocol](../spec/SPEC.md). Cryptographic provenance, self-healing, and state rollback for autonomous AI agents.

This package conforms to MAP spec version `0.1.0`. Both this implementation and the TypeScript reference implementation produce byte-identical hashes for the same inputs, verified by the shared conformance fixtures in `../spec/fixtures/v0.1/`.

## Install

```bash
pip install model-action-protocol
```

Optional extras:

```bash
pip install "model-action-protocol[anthropic]"   # LLM critic via Anthropic SDK
pip install "model-action-protocol[sqlite]"      # async SQLite store
pip install "model-action-protocol[postgres]"    # async Postgres store
pip install "model-action-protocol[fastapi]"     # FastAPI demo deps
pip install "model-action-protocol[all]"
```

## Quickstart

See `examples/quickstart.ipynb` for the full Jupyter walkthrough and `examples/fastapi_app/` for an HTTP service template.

## Specification

The wire format, canonicalization rule (RFC 8785), hash inputs, and chain verification algorithm are defined in [`spec/SPEC.md`](../spec/SPEC.md). Implementation details (Pydantic models, async I/O patterns, anthropic SDK integration) are not part of the spec — they are this implementation's choices.
