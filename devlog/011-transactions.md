# 011: Datomic-inspired transactions

**Date:** 2026-05-20

## The problem

Checkpoint/restore is all-or-nothing. Agent 2 restores Agent 1's full
graph but can't ask "what did Agent 1 actually change?" or "what was
true before that rename?" The claim graph is a snapshot — it has no
timeline.

## What we built

### Tx entities

Every `claim!` call now belongs to a transaction. Without an explicit
tx, each claim gets its own implicit tx (one entity, one hash entry,
negligible cost). With `begin-tx!`/`commit-tx!`, multiple claims share
a tx — an atomic batch rename creates one tx for all 7 claim updates.

Tx entities are tracked in a side table (`tx-meta`), not in the
regular object store. This keeps `all-objects` and `object-exists?`
unchanged — tx entities are infrastructure, not user-visible objects.
Each tx gets a monotonic sequence number for ordering.

### Hook suppression and rollback

During an explicit transaction, `claim!` defers all matview hooks
(`on-claim-hooks`, `on-supersede-hooks`) to a pending list. Claims
still get indexed and associated with the tx — only notification to
the matview is delayed.

On `commit-tx!`, deferred hooks fire in order. The matview updates
as if the claims arrived sequentially, but from the matview's
perspective they're one atomic batch.

On `rollback-tx!`, a pre-tx snapshot of all mutable state (13 hash
tables + 2 counters) is restored. The matview never saw the claims
(hooks were suppressed), so it's untouched. No invalidation needed.

`call-with-transaction` wraps this: run thunk, commit on success,
rollback + re-raise on exception.

### Temporal queries

`claims-visible-as-of(seq)` returns claims whose tx seq <= the given
point AND that aren't superseded as of that point. The supersession
filter is critical — a claim superseded at seq 10 shouldn't appear in
an as-of-8 query, but should appear in as-of-5 only if its
supersession claim also has seq <= 5.

Four new Datalog EDB relations:
- `as-of-triple(TxSeq, L, P, R)` — triples visible at a point
- `as-of-claim(TxSeq, Cid, L, P, R)` — with claim IDs
- `tx-info(TxId, Seq)` — tx metadata
- `tx-claims-rel(TxId, Cid)` — claims in a tx

Temporal relations have empty provenance (they're point-in-time
snapshots, not live relations to track).

### MCP tools

`tx_log` — list transactions, filterable by `since_seq`. Agents call
`current_tx_seq` on connect, save the number, then later ask "what
happened since I was last here?"

`batch` gains `atomic: true` — all operations in one tx. If any
operation fails, the entire batch rolls back. This is the mechanism
for safe multi-step mutations (rename + query + define_rule as one
atomic unit).

### Serialization v2

`export-store` bumps to version 2, adding `claim-txs` (claim→tx map),
`tx-meta` (tx→seq map), and `tx-counter`. `import-store!` handles
both versions — v1 data gets a synthetic "import" tx grouping all
existing claims under seq 1.

## Design decisions

**Tx entities are not regular objects.** The plan agent suggested
making them full entities in `cnf-ctx-objects`. But that inflates
`all-objects`, breaks object-count tests, and makes the graph noisy.
Tx entities live in `tx-meta` only. If we later need to query them
as entities (add `:db/txInstant` style attributes), we can promote
them.

**Side-table, not struct fields.** Tx state lives in the `ext` hash
(via `ctx-ref`/`ctx-set!`) rather than new `cnf-ctx` struct fields.
The struct already has 13 positional fields. Using ext keeps the core
struct stable and is consistent with how rules, matviews, hooks, and
predicates are stored.

**No nested transactions.** `begin-tx!` errors if a tx is active.
This is the Datomic model. If we need savepoints later, we can add
them — but the current use cases (atomic batch, agent attribution)
don't require nesting.

## What this enables

1. **Diff-based reasoning.** Agent 2 restores, calls `current_tx_seq`,
   does work, then later asks `tx_log since_seq N` to see what
   changed. No more loading the full graph to find deltas.

2. **Agent attribution.** Wrap each agent's operations in a tx.
   "What did Agent A do?" is a `tx_log` query.

3. **Safe mutations.** Atomic batch ensures a rename + query + rule
   definition either all succeeds or leaves the graph unchanged.

4. **Time travel.** `claims-visible-as-of` + the Datalog EDB lets
   agents query the graph at any historical point. "What were the
   deps before that rename?" is now answerable.

## Numbers

- 72 tests total (13 new tx tests, all 59 existing pass)
- 26 MCP tools (was 24)
- Serialization format v2, backward-compatible v1 import
- Rollback snapshot: 13 hash copies + 2 counter saves
