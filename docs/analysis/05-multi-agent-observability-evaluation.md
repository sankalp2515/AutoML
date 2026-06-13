# Multi-Agent Architecture, Observability, and LLM Evaluation

> Question 5 — Date: 2026-06-12

## How many agents?

**Ten agents** in the pipeline; **seven of them call the LLM**, three are
procedural specialists (no LLM — they execute fixed statistical procedures):

| # | Agent | LLM? | Role |
|---|---|---|---|
| 1 | data_auditor | ✅ | Profile data, verdict: usable/warn/abort |
| 2 | problem_framer | ✅ | Task type, target, metric from plain English |
| 3 | baseline_builder | ❌ | LogReg/Ridge performance floor + error analysis |
| 4 | eda_agent | ✅ | Targeted EDA, prioritized issues |
| 5 | preprocessor | ✅ | Per-column strategy → sklearn ColumnTransformer |
| 6 | feature_engineer | ✅ | Hypothesis features, each CV-tested |
| 7 | model_selector | ✅ | 2–3 candidates from menu, CV bake-off |
| 8 | tuner | ❌ | Optuna Bayesian search (30 trials) |
| 9 | evaluator | ❌ | Hold-out metrics, SHAP, calibration, threshold |
| 10 | exporter | ✅ | Pipeline pickle, API scaffold, narrated notebook |

## Is it a multi-agent system?

Yes — in the **pipelined/vertical** sense: specialized roles, a shared typed
state (LangGraph `AgentState`), each agent reading predecessors' outputs and
writing its own. It is *not* a concurrent/negotiating multi-agent system (no
agent-to-agent debate, no parallel execution). Coordination is via the
orchestrator graph, communication via state — which is what makes the whole
thing auditable.

## Observability — four layers

1. **Structured logs** (structlog → JSON): every agent start/complete/fail with
   durations; every decision with reasoning; every sandbox execution; every LLM
   retry/fallback event.
2. **Prometheus + Grafana**: 19 metrics — pipeline run rates & durations, per-agent
   durations, sandbox success/timeout/error, LLM tokens/latency/cost per agent,
   score distributions, prediction latency, drift PSI gauge, active deployments.
3. **MLflow**: per-run params, per-iteration metrics (step-indexed), all artifacts
   (plots, models, notebook, decision log JSON).
4. **Database audit trail** (the product surface): `decision_logs` (what/why/
   evidence per decision), `llm_calls` (provider, model, tokens, latency, cost per
   call), `agent_steps` (timeline), `prediction_logs` (every served prediction —
   drift raw material). Exposed via `/llm-stats`, `/agent-timeline`, and the UI.

## How we evaluate LLM outputs — the key design decision

**We never trust an LLM claim; we verify it by execution.** The evaluation
hierarchy:

1. **Structural validation** — every response must parse as JSON matching the
   expected shape; malformed → re-extract → fail loudly (never silently guess).
2. **Empirical gating (the heart of the system)** — every LLM proposal is tested
   in the sandbox before it is accepted:
   - A proposed feature survives only if it shows **measured CV lift > 0.002** —
     in the Iris run the LLM proposed 6 features and the data rejected 4.
   - A model choice is validated by an actual 5-fold CV bake-off, not by the
     LLM's stated preference.
   - A preprocessing plan is validated by the pipeline fitting + transforming
     real data, with hard failure on error.
   - The final score comes from a 20% hold-out the LLM never sees.
   *The sandbox result is ground truth; the LLM only generates hypotheses.*
3. **Human review surface** — the decision log + evidence notebook exist so a
   human can audit every LLM judgment after the fact.

## Honest gaps (roadmap)

- No LLM-as-judge scoring of *reasoning quality* (only outcomes are scored)
- No prompt regression suite (a prompt edit could silently degrade decisions —
  mitigated today by the empirical gates, but not measured)
- No A/B comparison across providers (the fallback chain now records provider
  per call, so the data for this already accumulates)
