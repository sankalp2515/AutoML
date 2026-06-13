# Decision Analysis: A Separate, User-Selected Architecture for Time-Series & Quant Finance

> User proposal (2026-06-13): "Completely build a separate architecture for
> Time-Series and Quant Finance; the user must select that mode for it to trigger."
> Asked for: deep analysis — every edge case, pros & cons, infra limits — and a
> verdict only at 100% confidence.

## VERDICT

**YES — build it. But with one amendment that changes "completely separate" into
"separate pipeline on a shared chassis," and one complement the proposal needs
to be safe.** I am fully confident in the amended version; I am equally confident
the *literal* version (a fork) would hurt us. Details below — the reasoning is
the deliverable.

---

## 1. What "separate architecture" could mean — three options

| Option | Description | Verdict |
|---|---|---|
| **A. Full fork** | Second codebase/service: own backend, own sandbox, own pipeline | ❌ Rejected |
| **B. Separate pipeline, shared chassis** | Own LangGraph graph, own agent roster, own templates, own CV/evaluation machinery — sharing the sandbox executor, DB, observability, LLM client, deployment, frontend shell | ✅ **Build this** |
| **C. Same pipeline, branching templates** | `if task_type == "time_series"` branches inside existing agents/templates | ❌ Rejected |

### Why not A (full fork)
~80% of the system is task-agnostic plumbing: orchestrator runner, sandbox
executor, DB models, the LLM resilience chain, Prometheus/MLflow/structlog,
deploy/drift endpoints, the entire frontend. Forking doubles the maintenance and
bug surface of all of it. Our own history is the proof: the MLflow
iteration-prefix bug had to be fixed in *two* agents; the frontend/backend
contract drifted *twice* within one codebase. A fork institutionalizes that
failure mode. Infra agrees: this machine struggles to run *one* stack (port
leaks, 6GB GPU, pip-only sandbox) — a second stack is not realistic.

### Why not C (branching inside the shared pipeline)
This is the dangerous cheap path. Every template doubles its conditional logic;
the test matrix explodes; and one missed branch silently runs shuffled K-fold on
financial data — the exact "credible but invalid result" doc 08 identifies as the
one unforgivable failure. Validity guarantees you have to *remember* are not
guarantees.

### Why B is right
- **Validity by construction**: the TS graph's templates contain *only*
  walk-forward machinery. There is no code path in which TS data meets shuffled
  K-fold. The guarantee is structural, not behavioral.
- **Different roster, naturally expressed**: TS needs agents tabular doesn't have
  (labeling, leakage forensics, backtester) and drops none of the shared chassis.
- **One fix, both pipelines**: LLM fallback, observability, deploy plumbing —
  fixed once.
- **The user's explicit-selection instinct is preserved** — and it's correct:
  mode is a *contract about evaluation protocol*, too consequential to infer
  silently from data shape alone.

---

## 2. The complement the proposal needs: the Wrong-Door Guard

Explicit selection alone has a fatal edge case: **a user uploads stock prices
into the tabular mode** (doesn't know better, or didn't notice the toggle). The
tabular pipeline happily produces an invalid 0.94 AUC. The selector made the
right path *available*; it didn't make the wrong path *safe*.

Required complement: the tabular **data_auditor gains temporal-structure
detection** (monotonic datetime column + autocorrelated target ⇒ warn). Verdict
"warn": run continues but the run record, UI, and notebook carry a visible
banner — *"This data appears time-ordered; results may overstate performance.
Consider the Time-Series studio."* Cheap (one profiling check + one prompt rule),
and it closes the loophole that makes mode selection safe in both directions.
The reverse guard is trivial: TS mode with no parseable timestamp column ⇒ abort
with a clear message.

---

## 3. Edge-case sweep (the ones that shape the design)

| # | Edge case | Design consequence |
|---|---|---|
| 1 | Tabular mode + time-ordered data | Wrong-Door Guard (above) — warn, don't block |
| 2 | TS mode + no timestamp | Early abort in TS auditor with explicit message |
| 3 | **Boundary ambiguity**: churn with dated snapshots — tabular or TS? | Mode = *evaluation protocol*, not "data has dates." Tabular-with-temporal-split is a TS-studio sub-mode ("snapshot prediction"), not a third pipeline |
| 4 | **Panel data** (many tickers × time) | TS architecture must support entity grouping from day one: group-aware purged CV, per-entity or pooled models. Designing for single-series only would force a painful retrofit |
| 5 | Irregular timestamps, gaps, duplicates, timezones, DST | TS auditor's core job — a different checklist from the tabular auditor (this alone justifies a separate auditor) |
| 6 | Forecast horizon & prediction time | New required user inputs in TS mode (horizon, frequency); the framer can propose, user confirms |
| 7 | Backtest runtime explosion | Walk-forward = dozens-hundreds of fits. Hard budget caps (max windows, max fit seconds) in config — same philosophy as MAX_ITERATIONS. LLM stays at decision level; backtest loops are procedural (no per-window LLM calls → no cost explosion) |
| 8 | Inference shape differs | Forecasting needs recent history at predict time, not one row. The predict endpoint gets a TS variant (`history` payload or server-side feature store of recent observations). Drift monitoring must tolerate expected non-stationarity (different thresholds/logic) |
| 9 | Tiny series (< 100 obs) | TS auditor verdict logic: walk-forward needs minimum length per window; abort/warn thresholds differ from tabular's row counts |
| 10 | Target leakage via engineered features | TS feature engineer's lag vocabulary must be *strictly backward-looking by construction* (template enforces shift ≥ 1); leakage-forensics agent double-checks |

---

## 4. Pros & cons of the amended proposal

**Pros**
1. Statistical validity becomes structural, not behavioral — the headline win
2. Clean agent rosters; no template bloat; independently testable pipelines
3. Tabular pipeline (working, verified) stays untouched — zero regression risk
4. Sellable as a distinct "Quant Studio" with its own UI affordances
5. Sets the pattern for future verticals (NLP studio, vision studio) — the
   chassis/pipeline split is the actual product architecture emerging
6. Shared chassis means observability/deploy/LLM improvements keep landing in both

**Cons (accepted, with mitigations)**
1. ~30–40% more code to own (new graph + ~6 new/variant agents + templates).
   Mitigation: template render-tests already pattern-proofed; same BaseAgent
2. Two pipelines to keep conceptually consistent. Mitigation: shared chassis
   forces interface consistency; journal documents divergences
3. Mode selection adds user friction/confusion. Mitigation: framer can suggest
   the right studio from the goal text; Wrong-Door Guard catches mistakes
4. TS runs are slower (backtests) and more LLM-call-heavy (~10–12 calls vs 7).
   Mitigation: budget caps; the fallback chain + a Gemini key absorb TPM pressure
5. Risk of over-engineering before demand is proven. Mitigation: phase order
   below ships value at each step; Phase T1 alone fixes the validity problem

---

## 5. Infra reality check (this machine, today)

| Constraint | Impact on TS architecture | Verdict |
|---|---|---|
| Sandbox is pip-only (apt blocked) | statsmodels, pyarrow are pure-wheel pip installs — **rebuild is feasible** (Dockerfile is pip-only; 443 works). sktime optional later | ✅ No blocker |
| 6GB GTX 1660 Ti | GBDTs on daily/hourly data are tiny; fine. No deep TS models (DeepAR etc.) in v1 — deliberate menu choice anyway | ✅ No blocker |
| 500MB CSV ingestion | Daily/hourly series fit easily; tick data does not — **explicitly out of scope** (Tier A excluded per doc 08) | ✅ Scoped out |
| Single sandbox, sequential exec | Backtest windows run inside one sandbox call with timeout — needs the budget caps from edge case 7 | ⚠️ Managed by config |
| Groq 12K TPM | More agents per run = more TPM pressure | ⚠️ Fallback chain + user adds Gemini key |
| One machine, one compose stack | Confirms Option B over A — no second stack | ✅ Decided |

---

## 6. Proposed shape (for when we build)

- **Mode selector** at commission time: *Tabular Studio* | *Time-Series & Quant
  Studio* (+ framer suggests if the goal text obviously implies one)
- **TS graph roster (~11 agents)**: ts_auditor → ts_framer (horizon/frequency/
  metric incl. Sharpe/cost-adjusted) → labeling_agent (horizon & triple-barrier)
  → leakage_forensics → baseline (naive/seasonal-naive — the honest floor) →
  ts_eda (ACF/stationarity/seasonality) → ts_preprocessor → ts_feature_engineer
  (lags/rolling/EWM, backward-looking by construction) → model_selector (GBDT-first
  menu) → walk_forward_evaluator (purged/embargoed, equity curve when costs given)
  → exporter (notebook narrates the backtest)
- **Shared chassis untouched**: executor, DB (+ `pipeline` column on runs),
  LLM client, observability, deployment (+ TS predict variant), frontend shell
  (+ mode selector, + equity-curve panel)
- **Build order**: T1 validity core (auditor/framer/walk-forward evaluator + guard)
  → T2 signal tooling (labeling, lags, finance metrics) → T3 backtest + forensics
  → T4 TS deploy/drift variants. T1 is the unlock; everything after compounds

## Bottom line

Okay — **build it**, as a separate *pipeline* with its own agents, templates, and
walk-forward machinery behind an explicit user-selected mode, on the shared
chassis — plus the Wrong-Door Guard so the unselected path can never silently
produce invalid finance results. Not okay to a literal fork: it doubles every
maintenance burden we've already paid for once and contradicts the infra we run on.
