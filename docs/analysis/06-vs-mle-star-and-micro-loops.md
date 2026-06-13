# vs. MLE-STAR: Their Limitations, Our Answer, and the Micro-Loop Gap

> Questions 8 & 9 — Date: 2026-06-12

## How we sidestep each MLE-STAR limitation (Q8)

| MLE-STAR limitation | Our position |
|---|---|
| **Kaggle-centric bias** — optimized for leaderboards, unproven on messy production problems | We optimize for the *production work product*: deployment, drift monitoring, documentation, audit trail. Our benchmark is "would a team ship this," not a leaderboard delta |
| **Hyperparameter sensitivity** — fixed internal loop/candidate counts cause unpredictable quality swings | Our loop knobs are few, explicit, and config-surface (`MAX_ITERATIONS=3`, `IMPROVEMENT_THRESHOLD=0.02`, Optuna trials) — not magic numbers inside prompts. Changing them changes *time spent*, not correctness, because every step is empirically gated |
| **Hallucinated search risk** — executes web-found code | We never execute web code (full analysis in doc 04). Templates only. The risk class does not exist here |
| **Compounding API costs** — hundreds of heavy-LLM calls per run | ~7 LLM calls per run on free-tier models, every token and cent recorded per call and shown in the UI. Cost is a *feature surface*, not a surprise |
| **Time complexity** — human-like write/debug/retry makes it slow | Templates skip the write-debug loop entirely: Iris end-to-end in ~75s, Titanic ~3min. Minutes, not hours |

## Q9 — The micro-loop gap: where MLE-STAR is genuinely better today

The user's framing is correct and we should not deny it: when an MLE-STAR-style
agent sees an evaluation failure, it reads the error, reasons, and **dynamically
jumps back** (e.g., to data cleaning to fix a broken column name). Our current
behavior on the same event is *fail fast with a clean error* — honest, cheap,
debuggable… and less capable.

What we already have that they lack: bounded cost/time, deterministic
reliability, partial-result persistence (scores survive later crashes), and
clean failure semantics. The goal is to add their adaptivity **without importing
their cost curve**.

## The plan: bounded self-healing (three tiers)

### Tier 1 — Self-repair micro-loop (build next)
When a sandbox execution fails, do NOT immediately fail the agent. Instead:
1. Feed the LLM: the traceback + the rendered code + the agent's original
   decision context.
2. Ask for a *revised decision* (not revised code) — e.g., "encoding for column
   X: ordinal instead of onehot," "drop column Y," "use median not knn."
3. Re-render the same template with the repaired parameters; re-execute.
4. **Hard cap: 2 repair attempts per agent, then fail fast as today.**

Key property: repairs stay inside the template vocabulary → the safety model is
untouched, and worst-case cost is +2 LLM calls per agent. We already capture
full tracebacks in `execute_code`, so the wiring is small.

### Tier 2 — Diagnostic router (after Tier 1)
A lightweight triage node classifies a failure (data issue / config issue /
resource issue) and routes back to the *appropriate earlier agent* with a
structured hint in state — e.g., preprocessor crash on an unseen column type →
re-enter EDA with `hint: investigate column X`. LangGraph conditional edges
support this natively; our graph simply doesn't use back-jumps yet. Cap: one
back-jump per run.

### Tier 3 — Plan-level agency (later, optional)
Let the problem_framer emit a *pipeline plan* (stages to run/skip, iteration
budget, repair budget) appropriate to the dataset — moving from a static DAG to
a planned DAG. This is the point where we genuinely match agentic flexibility
while keeping every budget explicit.

## The one-line strategic answer

MLE-STAR behaves like a brilliant intern with an unlimited cloud bill; we behave
like a disciplined senior engineer with a budget. Tier 1–3 add the intern's
adaptability to the senior engineer's discipline — adaptive *within explicit
budgets*, never instead of them.
