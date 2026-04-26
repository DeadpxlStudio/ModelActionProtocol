# Model Action Protocol (MAP) — Specification

**Version:** 0.1.0
**Status:** Draft
**Last updated:** 2026-04-25

---

## 1. Abstract

The Model Action Protocol (MAP) defines a wire format and conformance rules
for cryptographically-verifiable logs of autonomous AI agent actions. A MAP
**ledger** is an append-only, hash-chained sequence of entries. Each entry
records a single agent action, the state of the environment before and after
the action, and a **critic** verdict that classifies the action as `PASS`,
`CORRECTED`, or `FLAGGED`.

This document specifies the canonical data model, the JSON canonicalization
rule (per RFC 8785), the hashing rule, the chain verification algorithm, and
the audit export envelope. Implementations that conform to this specification
produce ledgers that verify identically across languages and runtimes.

The MAP ecosystem provides reference implementations in TypeScript and Python.
Both implement this specification; this specification — not either
implementation — is authoritative.

---

## 2. Conformance language

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY**
in this document are to be interpreted as described in
[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and
[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

A "MAP-conforming implementation" is one that, given the same inputs, produces
ledger entries with byte-identical `hash` fields to any other MAP-conforming
implementation.

---

## 3. Terminology

- **Ledger.** An ordered sequence of `LedgerEntry` records, indexed by
  `sequence` starting at 0.
- **Entry.** A single record in the ledger.
- **State.** The serializable application state observed before and after an
  action. Its representation is opaque to MAP; only its canonical
  serialization is significant.
- **Critic.** A function that examines an action and its state transition and
  returns a `CriticResult`. May be rule-based, LLM-based, or tiered.
- **Action.** A single tool invocation by an agent, recorded in an
  `ActionRecord`.
- **Chain.** The cryptographic linkage between consecutive entries via
  `parentHash`.
- **Genesis hash.** The constant `parentHash` value of the first entry in any
  chain: 64 ASCII zeros (`"0000…0"`, 64 characters).
- **JCS.** JSON Canonicalization Scheme, per RFC 8785.

---

## 4. Data model

All field names are case-sensitive. Optional fields, when absent, **MUST NOT**
be serialized as `null`; they **MUST** be omitted entirely. This rule is
load-bearing for hash determinism — see §5.

### 4.1 CriticVerdict

```
"PASS" | "CORRECTED" | "FLAGGED"
```

- `PASS` — the action is correct.
- `CORRECTED` — the action contained an error that the critic auto-fixed; the
  ledger records both the original and the corrected action.
- `FLAGGED` — the action is dangerous and requires human review;
  MAP-conforming runtimes **SHOULD** halt execution until approval.

### 4.2 CriticCost

```
{
  "inputTokens": <integer ≥ 0>,
  "outputTokens": <integer ≥ 0>,
  "model": <string>,
  "latencyMs": <integer ≥ 0>,
  "costUsd": <number, optional>
}
```

### 4.3 CriticResult

```
{
  "verdict": <CriticVerdict>,
  "reason": <string>,
  "correction": {
    "tool": <string>,
    "input": <object>
  } (optional),
  "cost": <CriticCost> (optional)
}
```

### 4.4 ReversalStrategy

```
"COMPENSATE" | "RESTORE" | "ESCALATE"
```

### 4.5 ReversalSchema

```
{
  "strategy": <ReversalStrategy>,
  "compensatingAction": {
    "tool": <string>,
    "inputMapping": <object: string → string>
  } (optional, used with COMPENSATE),
  "captureMethod": <string> (optional, used with RESTORE),
  "approver": <string> (optional, used with ESCALATE),
  "description": <string> (optional)
}
```

### 4.6 ActionRecord

```
{
  "tool": <string>,
  "input": <object>,
  "output": <any JSON value>,
  "reversalStrategy": <ReversalStrategy> (optional),
  "capturedState": <any JSON value> (optional)
}
```

`capturedState` is the pre-write state captured by RESTORE tools. Its presence
is determined by the tool's `reversalStrategy`.

### 4.7 LedgerEntryStatus

```
"ACTIVE" | "ROLLED_BACK"
```

Status transitions are one-way: `ACTIVE → ROLLED_BACK`. Once an entry is
`ROLLED_BACK`, it **MUST NOT** be returned to `ACTIVE`.

### 4.8 ApprovalStatus

```
"pending" | "approved" | "rejected"
```

### 4.9 LedgerEntry

```
{
  "id": <UUID v4 string>,
  "sequence": <integer ≥ 0>,
  "timestamp": <RFC 3339 datetime string>,
  "action": <ActionRecord>,
  "stateBefore": <hex string, 64 chars>,
  "stateAfter": <hex string, 64 chars>,
  "snapshots": {
    "before": <any JSON value>,
    "after": <any JSON value>
  },
  "parentHash": <hex string, 64 chars>,
  "hash": <hex string, 64 chars>,
  "critic": <CriticResult>,
  "status": <LedgerEntryStatus, default "ACTIVE">,
  "approval": <ApprovalStatus> (optional),
  "agentId": <string> (optional),
  "parentEntryId": <string> (optional),
  "lineage": <array of strings> (optional),
  "stateVersion": <integer> (optional)
}
```

`stateBefore` and `stateAfter` are SHA-256 hex digests of the canonical JSON
encoding of `snapshots.before` and `snapshots.after`, respectively (§6.1).

`hash` is computed per §6.2.

### 4.10 Multi-agent provenance (carried, not enforced)

The fields `agentId`, `parentEntryId`, `lineage`, and `stateVersion` exist to
support multi-agent ledgers. v0.1 implementations **MUST** carry these fields
through serialization but **MAY NOT** enforce identity verification or grant
validation. Implementations that use these fields for runtime authorization
are responsible for computing and verifying any cryptographic material
externally.

The associated types `AgentIdentity`, `AuthorizationGrant`, and
`AgentLifecycle` are defined for interoperability but are **not** part of the
hashed payload of a `LedgerEntry`.

---

## 5. Canonicalization

All JSON values that participate in a hash **MUST** be encoded using JSON
Canonicalization Scheme (JCS), as defined in
[RFC 8785](https://www.rfc-editor.org/rfc/rfc8785).

JCS specifies, among other rules:

- Object keys are sorted lexicographically by UTF-16 code units, recursively.
- No insignificant whitespace.
- Numbers are serialized per ECMA-262 7.1.12.1 (`Number::toString`); integers
  within the safe range are emitted without a decimal point.
- Strings are encoded per RFC 8259 with control characters escaped.
- `null` is emitted only where the data model requires a `null` value.

Implementations **MUST** use a JCS-conforming library:

- TypeScript / JavaScript: the `canonicalize` package on npm.
- Python: the `jcs` package on PyPI.

Implementations **MUST NOT** roll their own canonicalization.

### 5.1 Optional field handling

When a data model field is marked optional and the value is absent, the field
**MUST** be omitted entirely from the canonicalized JSON. Implementations
**MUST NOT** emit `"field": null` to represent an absent optional field, as
this would cause hash divergence with implementations that omit the field.

### 5.2 Worked example — canonicalization

Input object (insertion order shown for illustration only):

```json
{ "tool": "issueRefund", "input": { "amount": 100, "reason": "duplicate" }, "output": { "ok": true } }
```

JCS-canonical output (single line, lexicographic key order):

```
{"input":{"amount":100,"reason":"duplicate"},"output":{"ok":true},"tool":"issueRefund"}
```

---

## 6. Hashing

### 6.1 State hashes

Given a state value `S`, its hash is:

```
stateHash(S) = SHA-256(JCS(S))
```

The result is encoded as a 64-character lowercase hexadecimal string.

`LedgerEntry.stateBefore` is `stateHash(snapshots.before)`.
`LedgerEntry.stateAfter` is `stateHash(snapshots.after)`.

### 6.2 Entry hash

Given the fields of a `LedgerEntry`, its hash is:

```
entryHash(entry) = SHA-256(JCS({
  "sequence":    entry.sequence,
  "action":      entry.action,
  "stateBefore": entry.stateBefore,
  "stateAfter":  entry.stateAfter,
  "parentHash":  entry.parentHash,
  "critic":      entry.critic
}))
```

The hash payload **MUST** include exactly these six fields. The result is
encoded as a 64-character lowercase hexadecimal string.

The fields `id`, `timestamp`, `snapshots`, `status`, `approval`, `agentId`,
`parentEntryId`, `lineage`, and `stateVersion` **MUST NOT** be included in the
entry hash payload. This separation allows non-cryptographic metadata
(approval transitions, multi-agent coordination state) to evolve without
invalidating the chain.

### 6.3 LearningEngine fingerprint

The fingerprint of a correction pattern is:

```
fingerprint(entry) = SHA-256(
  entry.critic.verdict + ":" +
  entry.action.tool + ":" +
  (entry.critic.correction.tool ?? "none")
)
```

The three components are joined by ASCII colon (`:`). When
`entry.critic.correction` is absent, the literal string `"none"` is
substituted. The result is encoded as a 64-character lowercase hexadecimal
string.

This fingerprint is **not** part of any chained hash; it is a deterministic
identifier for grouping observed correction patterns.

### 6.4 Worked example — entry hash

Given an entry constructed from `null` state on both sides and a `ping`/`pong`
action:

```
sequence    = 0
action      = { "tool": "ping", "input": {}, "output": "pong" }
stateBefore = "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b"
stateAfter  = "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b"
parentHash  = "0000000000000000000000000000000000000000000000000000000000000000"
critic      = { "verdict": "PASS", "reason": "ok" }
```

The state hashes are `SHA-256(JCS(null))` = `SHA-256("null")` =
`74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b`.

The JCS-canonical hash payload is (single line, no whitespace):

```
{"action":{"input":{},"output":"pong","tool":"ping"},"critic":{"reason":"ok","verdict":"PASS"},"parentHash":"0000000000000000000000000000000000000000000000000000000000000000","sequence":0,"stateAfter":"74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b","stateBefore":"74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b"}
```

The SHA-256 hex digest of those UTF-8 bytes is:

```
25d29bc25a183ebdb29b70b6a03ed2ad8d31033d1fb6347f656b21d7e9efb650
```

A conforming implementation **MUST** produce this exact hex digest from the
same inputs. The conformance test `test_canonical_json_known_hash` asserts
this equality.

---

## 7. Chain verification

A ledger is **valid** if and only if every entry passes the four checks
below, applied in order, for indices `i = 0, 1, …, n-1`.

### 7.1 Sequence continuity

```
entries[i].sequence == i
```

If this fails, the ledger is invalid at index `i`.

### 7.2 Genesis hash

For the first entry only:

```
entries[0].parentHash == "0" repeated 64 times
```

If this fails, the ledger is invalid at index 0.

### 7.3 Chain linkage

For all entries with `i > 0`:

```
entries[i].parentHash == entries[i - 1].hash
```

If this fails, the ledger is invalid at index `i`.

### 7.4 Entry hash integrity

For every entry:

```
entries[i].hash == entryHash(entries[i])
```

If this fails, the ledger is invalid at index `i`.

A verifying implementation **MUST** return both a boolean validity flag and,
on failure, the integer index of the first invalid entry.

---

## 8. Audit export envelope

A MAP audit export is a JSON object of the form:

```json
{
  "protocol": "map",
  "version": "0.1.0",
  "entries": [<LedgerEntry>, …],
  "stats": {
    "total":       <integer>,
    "committed":   <integer>,
    "rolledBack":  <integer>,
    "corrections": <integer>,
    "flags":       <integer>
  }
}
```

`protocol` **MUST** be the constant string `"map"`. `version` **MUST** match
the semantic version of the specification used to produce the ledger.

A consuming implementation **MUST** accept exports whose `version` matches its
own major.minor and **MAY** accept exports with a different patch version.

---

## 9. Versioning

This specification follows semantic versioning. Within `0.x.y`:

- A change to the hash payload structure, canonicalization rule, or any field
  whose absence/presence affects a hash is a **minor** version bump
  (`0.x → 0.(x+1)`).
- A change to non-hashed metadata (status semantics, approval workflow, event
  shapes) is a **patch** version bump.
- The `1.0.0` release will lock the wire format. Hash-breaking changes after
  `1.0.0` require a major version bump.

Conformance fixtures are versioned alongside the specification:
`spec/fixtures/v0.1/`, `spec/fixtures/v0.2/`, etc. Existing fixture
directories are **immutable** once published; a new spec version produces a
new directory, and the old directory is retained for regression testing.

---

## 10. Security considerations

### 10.1 What MAP guarantees

A valid MAP chain proves that the recorded sequence of `(action, state
before, state after, critic)` tuples is internally consistent and has not
been mutated since it was written. Any single-byte change to any chained
field of any entry causes verification to fail at that entry's index.

### 10.2 What MAP does not guarantee

- **Authenticity of the writer.** MAP does not specify how an entry's writer
  is authenticated. Implementations that need writer authentication
  **SHOULD** sign exports out-of-band (e.g., detached JWS) or operate the
  ledger in an authenticated transport.
- **Privacy.** State snapshots embed application data. Implementations
  handling sensitive data **SHOULD** redact, encrypt, or apply field-level
  access control at the storage layer. Hashing state does not protect its
  contents — the canonical bytes are present in `snapshots.before` and
  `snapshots.after`.
- **Liveness or availability.** A ledger that is deleted is not detectable
  by MAP alone. Implementations needing tamper-evidence against deletion
  **SHOULD** publish entry hashes to an external append-only log
  (transparency log, DLT, etc.).
- **Tail truncation.** Dropping the most recent entries leaves a valid
  shorter chain. Detection requires the same external mechanism as
  deletion — a signed latest-hash, a transparency log inclusion proof, or a
  comparable out-of-band commitment. v0.1 does not specify one.
- **Cryptographic key management.** v0.1 is content-addressed only — every
  ledger entry is identified by the hash of its contents, not by a
  signature over them. There is no key material, key rotation, or
  revocation in v0.1. A future version **MAY** add detached signatures,
  signed exports, or signed entry envelopes; until then, integrating MAP
  with an authenticated transport (TLS with mutual auth, signed JWS
  envelopes around exports) is the recommended path for authenticity.

### 10.3 Payload size

v0.1 specifies no maximum size for `snapshots.before`, `snapshots.after`,
`action.input`, or `action.output`. Implementations **MAY** impose limits at
the storage or transport layer; conformance fixtures include payloads up to
~10 KB to exercise streaming/buffering paths. A future major version **MAY**
specify limits if signature overhead or transparency-log inclusion proofs
make unbounded entries impractical.

### 10.4 Hash agility

This specification fixes SHA-256 and JCS for v0.x. A future major version
**MAY** introduce hash agility (multiple hash algorithms per entry).
Implementations **SHOULD NOT** assume SHA-256 is the only valid algorithm
beyond v1.x.

---

## 11. References

### 11.1 Normative

- **RFC 2119** — Key words for use in RFCs to Indicate Requirement Levels.
- **RFC 3339** — Date and Time on the Internet: Timestamps.
- **RFC 8174** — Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words.
- **RFC 8259** — The JavaScript Object Notation (JSON) Data Interchange Format.
- **RFC 8785** — JSON Canonicalization Scheme (JCS).
- **FIPS PUB 180-4** — Secure Hash Standard (SHS), SHA-256.
- **RFC 4122** — UUID specification (UUIDv4 used for `LedgerEntry.id`).

### 11.2 Informative

- **canonicalize** (npm) — JCS implementation for JavaScript/TypeScript.
- **jcs** (PyPI) — JCS implementation for Python.

---

## Appendix A — Conformance fixtures

The directory `spec/fixtures/v0.1/` contains the normative conformance
fixtures for this specification. A conforming implementation **MUST** verify
every fixture as `valid` and **MUST** detect any single-byte mutation at the
correct index. Fixtures are:

- `pass-only-3-actions.json` — three sequential actions, all `PASS`.
- `corrected-mid-chain.json` — one action `CORRECTED`, others `PASS`.
- `flagged-halt.json` — a `FLAGGED` entry that halts execution.
- `rollback-and-resume.json` — entries marked `ROLLED_BACK` followed by
  fresh `ACTIVE` entries.
- `learning-patterns.json` — a ledger plus expected pattern fingerprints
  (see §6.3) for `LearningEngine` conformance.

The directory contents are immutable. Fixture changes belong in a new
`spec/fixtures/v0.x/` directory and a corresponding spec version bump.
