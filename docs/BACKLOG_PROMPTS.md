# Backlog — Ready-to-Run Prompts

> One self-contained prompt per remaining feature/fix. Paste a single block into a
> fresh session and it has everything needed to deliver at the established quality.
> Every prompt assumes the **Universal Preamble** below — paste it ABOVE the chosen
> prompt each time.

---

## ⭐ UNIVERSAL PREAMBLE (paste before every prompt)

```
You are working on the AutoML Orchestrator at
E:\AI practical Learning\claude code\Agentic AI\automl-orchestrator\.
Read docs/PROJECT_JOURNAL.md and docs/analysis/README.md first — they hold the full
history, architecture, and every prior decision.

NON-NEGOTIABLE PROJECT RULES (violating these has burned us before):
1. Sandbox agent code is built via Python str.format() on a TEMPLATE constant. EVERY
   literal brace in template code must be DOUBLED: {{ }}. A single brace = KeyError at
   runtime. There is a guard test (tests/test_agents/test_templates.py) — keep it green.
2. Values are injected into templates via repr() (e.g. .replace("PARAM", repr(obj))) or
   .format(param=repr(obj)) — never string-concatenate Python objects.
3. AgentState is a TypedDict in app/core/state.py. LangGraph SILENTLY DROPS any state key
   not declared there. Add new keys to the TypedDict before using them.
4. The Docker IMAGE is the source of truth, NOT `pip install` into a running container —
   those vanish on recreate. New deps go in backend/requirements.txt, then rebuild:
   `docker compose build backend`. Backend code is volume-mounted (./backend:/app) so
   .py edits hot-reload without rebuild; only dependency changes need a rebuild.
5. After ANY backend change: `docker compose restart backend` (hot-reload usually
   suffices), then `docker compose exec -T backend python -m pytest tests/ -q` MUST pass.
6. ALWAYS verify with a real end-to-end run before declaring done — unit tests have
   repeatedly missed agent-level regressions. Use a small CSV already in the shared
   volume: `docker compose exec -T backend python -c "<post to /api/v1/runs, poll>"`.
7. Multiclass: binary-only scorers (roc_auc/recall/precision) silently produce NaN —
   the *_weighted / roc_auc_ovr_weighted remaps already exist in baseline/model_selector/
   tuner; mirror that pattern in any new training template.
8. Frontend: Next.js 14 app at frontend/, host port 3002 (container 3000), pure Tailwind
   + the "Obsidian Atelier" dual-theme design system. Colors are CSS-var RGB triplets in
   app/globals.css; use the existing vocabulary classes (lux-card, eyebrow, btn-gold,
   hairline, corner-ticks, text-bone/gold/jade/terra). Run `docker compose exec -T frontend
   npx tsc --noEmit` — it MUST be clean. Reuse component patterns; no new UI libraries.
9. Self-healing exists: BaseAgent.execute_code_with_repair(render_fn, params, repair_goal)
   — use it for any new code-executing agent instead of bare execute_code.
10. Update docs/PROJECT_JOURNAL.md with what you did + why + any gotcha, and the project
    memory, when you finish. Critical strategic discussion → its own docs/analysis/ file.

Groq free tier is 12K tokens/min — runs may hit rate limits; the fallback chain
(app/core/llm.py) handles it. If a fallback key (GEMINI_API_KEY) is in .env it absorbs them.
```

---

# TIER 1 — Foundations & quick wins

## P1. Per-agent mocked-sandbox smoke tests
```
GOAL: Add a fast test that runs each agent's .run() against a tiny fixture with the
sandbox and LLM MOCKED, so agent-level regressions (NameError, undefined vars, bad state
keys) are caught in seconds instead of only by minutes-long live runs. Two such
regressions slipped through this session (see journal Phase 3.7).

APPROACH:
- New file backend/tests/test_agents/test_agent_smoke.py.
- For each of the 10 agents: instantiate it, mock self.execute_code /
  execute_code_with_repair to return a realistic success dict (matching what that agent's
  template RESULT produces — read the template's RESULT={{...}} block to get the keys),
  mock self.llm.complete_json to return a valid decision dict matching the agent's
  SYSTEM_PROMPT schema, mock self._mark_step/_log_decision/emit/_update_run_field as
  AsyncMock, and call await agent.run(state) with a minimal AgentState.
- Assert it returns a dict with no exception and the expected output keys
  (e.g. preprocessor returns preprocessor_path/processed_data_path).
- Use pytest.mark.asyncio (already configured). Follow the mocking style in
  tests/test_agents/test_problem_framer.py and test_self_repair.py.

GOTCHAS: agents call _update_run_field (hits DB) — mock it. data_auditor/eda read
profile dicts with many keys — build a representative fixture. Keep fixtures tiny.

DONE WHEN: all 10 agents have a smoke test, full suite green, and deliberately breaking
one agent (e.g. reference an undefined var) makes exactly that test fail.
```

## P2. CI-style "preflight" script
```
GOAL: One command that runs everything we manually run after changes, so nothing is
forgotten: pytest + tsc --noEmit + template render guard + import-check of every agent.

APPROACH: backend/scripts/preflight.sh (and a tiny frontend check). Backend script:
  pytest tests/ -q && python -c "import all agent modules" (catches import-time errors).
Document it in the journal and reference from the Universal Preamble.

DONE WHEN: `bash scripts/preflight.sh` exits 0 on green, non-zero on any failure.
```

---

# TIER 2 — Time-Series & Quant Studio (the big differentiator; doc 09 approved)

> Build as a SEPARATE PIPELINE ON THE SHARED CHASSIS — NOT a fork. New LangGraph graph,
> new agent roster, new templates; reuse executor, DB, LLM client, observability, deploy,
> frontend shell. Read docs/analysis/09-separate-ts-architecture-decision.md fully first.

## P3. TS Studio — Phase T1: Validity Core
```
GOAL: Make time-series modelling STATISTICALLY VALID and user-selectable. This is the
unlock; nothing else in the studio matters until walk-forward CV is the only CV TS data
can meet. Read docs/analysis/08 and 09 before coding.

SCOPE (T1 only — validity, not yet signal tooling):
1. MODE SELECTION:
   - Add `pipeline` column to the Run model (app/models/run.py): "tabular" (default) |
     "timeseries". Migration: it's SQLAlchemy create_all on a dev DB — a new nullable
     column with default "tabular" is safe; confirm init_db picks it up.
   - createRun endpoint (app/api/routes/runs.py) accepts a `pipeline` form field.
   - Frontend UploadForm: a two-option mode selector (Tabular Studio | Time-Series &
     Quant Studio) styled in the Atelier vocabulary. Pass it through createRun in lib/api.ts
     and lib/types.ts.
2. SEPARATE GRAPH: new app/agents/ts_orchestrator.py with its own build_graph() and a
   ts_ prefixed roster. run_pipeline() in the existing orchestrator branches on
   run.pipeline to pick which graph to invoke (keep ONE entry point).
3. T1 AGENTS (new files, subclass BaseAgent, follow existing agent structure exactly):
   - ts_auditor: detect/require a timestamp column; check monotonicity, gaps, duplicate
     timestamps, frequency inference, min-length for walk-forward. Verdict usable/warn/abort.
     ABORT if no parseable timestamp.
   - ts_framer: task_type="time_series_forecasting"; ask user-confirmed horizon & frequency
     (add to AgentState + UploadForm advanced options); metric default = RMSE/MAE (finance
     metrics come in T2).
   - ts baseline: naive / seasonal-naive forecast as the honest floor (NOT LogisticRegression).
   - walk_forward_evaluator: PURGED + EMBARGOED walk-forward CV (López de Prado style).
     Temporal hold-out = last N% by time, NEVER random. This template REPLACES every
     shuffled KFold — there must be NO shuffle=True path for TS data.
   - Reuse tabular preprocessor/exporter where sensible, but CV must be walk-forward.
4. WRONG-DOOR GUARD (critical): the TABULAR data_auditor gains a temporal-structure probe
   (monotonic datetime column + autocorrelated target) → verdict "warn" with a banner in
   the run record, UI, and notebook: "data appears time-ordered; consider Time-Series studio."

CONSTRAINTS: GBDT-first model menu (no deep TS models in v1 — 6GB GPU). Daily/hourly data
only (tick data out of scope). statsmodels is pip-installable (pure wheel) — add to
requirements.txt and rebuild. Design walk-forward to support PANEL DATA (entity grouping)
from day one even if v1 tests single-series — retrofitting groups later is painful.
Backtest loops are PROCEDURAL inside one sandbox call (no per-window LLM calls) with hard
budget caps in config (max_windows, max_fit_seconds) — same philosophy as MAX_ITERATIONS.

GOTCHAS: doubled braces in new templates (run the template guard test — add the new
templates to it). Add ALL new state keys (timestamp_col, horizon, frequency, pipeline,
wrong_door_warning, walk_forward_scores) to AgentState. Use execute_code_with_repair.

DONE WHEN: a CSV with a date column + numeric target, in TS mode, completes with a
walk-forward score and a temporal hold-out; the SAME CSV in tabular mode shows the
Wrong-Door warning; tabular regression/classification runs are unaffected; suite green;
journal + a new docs/analysis entry updated.
```

## P4. TS Studio — Phase T2: Signal Tooling
```
PREREQ: P3 merged. GOAL: give the studio the vocabulary of signal construction.
- ts_feature_engineer: lag / rolling-window / EWM features, STRICTLY backward-looking by
  construction (template enforces shift >= 1) — each still hypothesis-tested for lift, but
  under walk-forward CV.
- Finance metrics as first-class primary_metric options the ts_framer can pick: Sharpe,
  Sortino, max drawdown, hit-rate, turnover/transaction-cost-adjusted return. Take an
  optional cost model (bps per trade) as user input.
- labeling_agent: construct labels when the target isn't given — fixed-horizon returns and
  triple-barrier. Adds a labeling step before baseline.
- Sample-uniqueness weighting for overlapping outcome windows (non-IID correction).
GOTCHAS: backward-looking guarantee is a safety property — a lag feature using the current
or future bar is leakage. The leakage_forensics agent (P5) double-checks, but the template
must be correct by construction. DONE WHEN: lag features measurably improve a forecast under
walk-forward CV; Sharpe selectable as the optimization target.
```

## P5. TS Studio — Phase T3: Backtest + Leakage Forensics
```
PREREQ: P4. GOAL: process credibility = the artifact a quant desk actually trusts.
- leakage_forensics agent: timestamp-ordering assertions, feature-vs-future correlation
  probes, same-bar contamination checks, survivorship/look-ahead heuristics. Runs early;
  warns/aborts on detected leakage with specifics.
- backtest agent: walk-forward EQUITY CURVE with costs + slippage, rendered in the evidence
  notebook (this single artifact is a selling event). Produces drawdown/Sharpe/turnover.
- Determinism: pinned seeds + an environment manifest per run (model-risk committees
  require reproducibility — SR 11-7).
DONE WHEN: a run produces an equity-curve plot + backtest metrics in the notebook, and a
deliberately leaky feature is caught by forensics.
```

## P6. TS Studio — Phase T4: Productization
```
PREREQ: P5. GOAL: deploy + scale for the studio.
- TS variant of the predict endpoint: accepts recent history (or a server-side store of
  recent observations) instead of a single row; drift monitoring tolerant of expected
  non-stationarity (different thresholds/logic than tabular drift).
- ONNX export of the winning model for sub-ms inference outside the sandbox.
- Parquet/DB ingestion (pyarrow is pip-installable — add + rebuild) for larger series.
DONE WHEN: a deployed TS model serves a forecast from a history payload; ONNX artifact
downloads and loads.
```

---

# TIER 3 — Capability expansion

## P7. Curated model-menu expansion (CatBoost + HistGradientBoosting + TabPFN)
```
GOAL: widen the model menu the model_selector chooses from. Highest quality-per-effort on
existing tabular runs; low risk. Read docs/analysis/04 (why curated, not web-searched).

APPROACH:
- Add to backend/sandbox/requirements.txt: catboost (pure wheel). HistGradientBoosting is
  already in sklearn (zero new dep). TabPFN optional (only for <10K rows / <100 features).
  Rebuild the SANDBOX image: `docker compose build sandbox` (NOTE: sandbox, not backend).
- model_selector SYSTEM_PROMPT: add the new classes to the allowed menu with heuristics
  (CatBoost for high-cardinality categoricals; HistGradientBoosting as a fast strong
  baseline; TabPFN only for tiny data). Update the eval() class map in TRAINING_CODE_TEMPLATE
  and the tuner's per-family Optuna search spaces.
- GPU: CatBoost supports task_type="GPU"; gate on the existing GPU_AVAILABLE check like XGBoost.

GOTCHAS: sandbox image (NOT backend) must be rebuilt — different Dockerfile. Verify the
sandbox can import the new libs: `docker compose exec -T sandbox python -c "import catboost"`.
Doubled braces if you add template code. Keep the template render guard green.
DONE WHEN: a run where the LLM selects CatBoost completes and CatBoost wins on a
high-cardinality dataset; suite green; journal updated.
```

## P8. Tier-2 diagnostic router (deeper self-healing; doc 06)
```
PREREQ: Tier-1 self-repair (done). GOAL: when an agent fails in a way that's really an
EARLIER agent's fault (e.g. preprocessor hits a column type EDA mis-profiled), route BACK
to the appropriate earlier agent with a structured hint, instead of only repairing in place.

APPROACH: a lightweight triage node classifies a failure (data issue / config issue /
resource issue) via one LLM call, and LangGraph conditional edges route back to the right
agent with a `repair_hint` in AgentState. HARD CAP: one back-jump per run (add a
`backjumps_used` counter to AgentState; route to END/exporter once exhausted).
GOTCHAS: bounded — must not create cycles beyond the cap. The macro feedback loop
(evaluator→feature_engineer) already exists; don't conflict with it. DONE WHEN: a run that
would fail at preprocessor due to an EDA mis-read recovers by re-entering EDA once.
```

---

# TIER 4 — High-value product features (the "10 cool features")

## P9. What-if explorer (sliders → live prediction + SHAP delta)
```
GOAL: on a deployed run, a panel of inputs (auto-generated from GET /runs/{id}/schema) with
sliders/fields; on change, call POST /runs/{id}/predict and show prediction + confidence
live. The feature stakeholders demo first.
APPROACH: new frontend component WhatIfPanel.tsx, added as a tab on the run page (only when
deployed). Reuse the schema endpoint + predict endpoint (both exist). Debounce calls.
Optionally add a per-prediction SHAP endpoint (see P11) to show contribution bars.
GOTCHAS: Atelier styling; tsc clean; the predict endpoint aligns columns server-side
already. DONE WHEN: moving an input updates the prediction within ~1s on a deployed model.
```

## P10. Run-vs-run comparison
```
GOAL: pick two runs of (ideally) the same dataset → side-by-side metric deltas + decision
diffs + which features each kept. Reuses existing run/results/decision-log data — no new ML.
APPROACH: backend GET /api/v1/runs/compare?a=<id>&b=<id> returning both runs' results +
decision logs aligned by agent. Frontend /runs/compare page in Atelier style. DONE WHEN:
two completed runs render a clean diff (scores, models, kept features, key decisions).
```

## P11. Per-prediction SHAP attribution (closes Vertex XAI parity; doc 03 Q6b)
```
GOAL: explain an INDIVIDUAL prediction, not just global SHAP. APPROACH: extend the predict
sandbox code (app/api/routes/inference.py PREDICT_CODE) to optionally compute SHAP values
for the submitted row(s) using the model already in inference_pipeline.pkl; return
top contributing features + signed contributions. New optional `explain: bool` on
PredictRequest. Surface in the What-If panel (P9) as contribution bars.
GOTCHAS: SHAP TreeExplainer for tree models, LinearExplainer for linear — mirror the logic
already in evaluator.py. Doubled braces in the sandbox code. DONE WHEN: a prediction returns
per-feature contributions that sum coherently toward the output.
```

## P12. Drift-triggered champion/challenger retraining (closes Vertex Pipelines gap; doc 03 Q6c)
```
GOAL: our weakest leg vs Vertex. When drift on a deployed run exceeds a threshold
(max_PSI > 0.25), automatically retrain on the latest data and promote the challenger ONLY
if it beats the champion on a fresh hold-out. APPROACH: a scheduler (start with a manual
"retrain now" button + a simple interval check; full cron later). Reuse the existing drift
endpoint + run_pipeline. Add a Deployment.champion_run_id and challenger comparison.
GOTCHAS: never auto-promote a worse model; log the decision. DONE WHEN: a drifted deployment
produces a challenger and promotes it only on improvement.
```

## P13. Batch scoring endpoint (Vertex parity; doc 03 Q6a)
```
GOAL: upload a CSV to a deployed run → download it scored (prediction + confidence + per-row
drift flag) columns appended. APPROACH: POST /runs/{id}/batch-predict (multipart CSV) → runs
the existing predict sandbox code over all rows in chunks → returns a CSV. Frontend: a
file-drop on the deploy tab. GOTCHAS: cap rows/size; stream the response; reuse column
alignment + text-NaN fill already in PREDICT_CODE. DONE WHEN: a 1000-row CSV returns scored.
```

## P14. "Ask your model" chat over the run
```
GOAL: natural-language Q&A grounded in a run's decision log, SHAP, metrics, and notebook —
"why did it drop Cabin?". APPROACH: backend POST /runs/{id}/ask {question} → retrieves the
run's decision_logs + results + shap + drift, builds a grounded context, one LLM call via
the existing resilient client, returns the answer with cited decisions. Frontend chat panel
on the run page. GOTCHAS: ground STRICTLY in stored run data (no hallucinated metrics);
reuse get_llm(); show which decisions were cited. DONE WHEN: questions about a completed run
get accurate, citation-backed answers.
```

## P15. Fairness audit agent (regulated-buyer value)
```
GOAL: slice metrics by user-specified sensitive attribute(s); report disparate-impact ratio
in the model card + UI. APPROACH: optional sensitive-columns input; an evaluator extension
(or new agent) computes per-group metrics + 80%-rule ratio inside the sandbox; surface in
results + notebook. GOTCHAS: groups with tiny support → suppress/flag, don't divide by ~0.
DONE WHEN: a run with a sensitive column shows per-group performance + a fairness verdict.
```

---

# TIER 5 — Production hardening (Phase 4)

## P16. Auth + rate limiting + dataset versioning
```
GOAL: gate the API before any real traffic. APPROACH: API-key or JWT auth dependency on
mutating routes; per-key rate limiting (slowapi or a Redis token bucket — Redis is already
running); dataset versioning (hash uploaded CSVs; a v2 of a dataset links to v1). GOTCHAS:
don't break the existing frontend (add the key in lib/api.ts headers); keep health/metrics
open. DONE WHEN: unauthenticated mutating calls are rejected; the frontend still works with
a configured key.
```

## P17. Prompt regression suite + LLM-as-judge (doc 05 gaps)
```
GOAL: catch silent prompt degradations. APPROACH: a fixture set of (agent input → expected
decision shape/properties); a test that runs each agent's prompt against a recorded input
and asserts structural + semantic properties (e.g. problem_framer picks regression for a
continuous target). Optionally an LLM-as-judge scoring reasoning quality, logged not gated.
GOTCHAS: keep it deterministic where possible (low temperature); don't make CI depend on a
live LLM unless keyed — mock for structure, separate "live" mark for semantics.
DONE WHEN: editing a prompt to be obviously worse fails a test.
```

---

# QUICK REFERENCE — current state (so a fresh session has the map)

- **Working pipelines:** tabular binary/multiclass classification + regression on flat CSVs,
  incl. free-text (TF-IDF) columns. 10 agents, LangGraph, sandboxed execution.
- **Done:** evidence notebook, full observability (structlog/Prometheus/Grafana/MLflow),
  frontend (Obsidian Atelier, dual theme), inference + drift, GPU XGBoost, LLM fallback chain,
  Tier-1 self-repair, template render guard, baked-in deps.
- **Test suite:** 32 passing (backend/tests/). Template guard + self-repair tests included.
- **Known user action:** add GEMINI_API_KEY to .env to absorb Groq rate limits mid-run.
- **Not built:** everything in P1–P17 above.
```
