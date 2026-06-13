# Architecture: Sequential or Non-Sequential?

> Question 2 — Date: 2026-06-12

## Classification

Our system is a **statically-defined DAG with bounded dynamic routing** — in plain
words: *mostly sequential, with one deliberate feedback cycle and fail-fast exits.*

```
audit → frame → baseline → eda → preprocess ─→ feature_eng → select → tune → evaluate ─→ export
  │       │        │         │       │              ▲                            │
  └───────┴────────┴─────────┴───────┴── fail ──→ END                            │
                                                    └──── improvement ≥ 2% ──────┘
                                                          and iter < max (3)
```

Three kinds of control flow exist today:

1. **Sequential backbone** — the 10 stages always run in the same order.
2. **One macro feedback loop** — Evaluator routes back to Feature Engineer when
   the score improved ≥ 2% and iterations remain. This is *conditional*, decided
   at runtime from measured results — so the run length is data-dependent
   (Titanic took 3 iterations; Iris took 1).
3. **Fail-fast conditional exits** — every mid-pipeline agent has a conditional
   edge to END on failure (added after the Iris zombie-run incident).

## What we are NOT (yet)

- **Not free-form**: no agent can decide "skip EDA" or "jump back two stages."
- **No micro-loops**: when a sandbox execution fails, we stop cleanly — we do not
  yet diagnose the traceback and self-repair (MLE-STAR's strength; see doc 06).
- **No parallelism**: model candidates train sequentially inside one sandbox call;
  agents never run concurrently.

## Why this point on the spectrum

LangGraph supports arbitrary dynamic routing — our restraint is a choice:
- Bounded loops ⇒ bounded cost and bounded wall-clock (a run cannot spiral)
- A fixed backbone ⇒ every run is comparable to every other run (debuggability)
- The 2% improvement gate is an explicit, config-visible stopping rule
  (`IMPROVEMENT_THRESHOLD`, `MAX_ITERATIONS` in config.py) — not a magic number
  buried in a prompt

The next evolution (doc 06) adds *bounded* non-sequential behavior — diagnostic
re-routing on failure — without giving up the cost ceiling.
