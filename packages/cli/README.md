# `@model-action-protocol/cli`

CLI for the Model Action Protocol. Verify ledgers and (soon) wrap MCP servers from the command line.

## Install

```bash
npm install -g @model-action-protocol/cli
# or run without installing:
npx -p @model-action-protocol/cli map verify ./agent.ledger.json
```

## Usage

```bash
# Verify a ledger file
map verify ./agent.ledger.json

# Verify from stdin
cat ./agent.ledger.json | map verify -

# Machine-readable output
map verify ./agent.ledger.json --json
```

Exit codes: `0` valid, `1` tampered, `2` argument or parse error.

## Web verifier

For a shareable view of any ledger:

```
https://verify.modelactionprotocol.org
```

## Producing a ledger

A MAP ledger is whatever `map.exportLedger()` from `@model-action-protocol/core` returns. Save the JSON to disk:

```ts
import { writeFileSync } from "node:fs";
const ledger = map.exportLedger();
writeFileSync("./agent.ledger.json", JSON.stringify(ledger, null, 2));
```

## Roadmap

- `map verify` ✅
- `map mcp wrap <server>` — wrap an MCP server so every tool call is attested
- `map ledger tail` — live tail a ledger file
