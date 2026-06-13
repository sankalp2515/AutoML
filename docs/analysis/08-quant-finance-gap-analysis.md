# Quant Finance: Can We Ever Fit? Holdbacks, Requirements, and Whether MLE-STAR Can

> Follow-up to doc 07 — Date: 2026-06-13
> Verdict up front: **Yes for the research/validation layer (Tier B/C), achievable
> in ~2 focused phases. Never for the execution path (Tier A) — and neither can
> MLE-STAR. On the dimensions quant desks actually buy on, MLE-STAR is *more*
> disqualified than we are.**

## First, segment the market — "quant finance" is three different problems

| Tier | Examples | Latency | Can ANY AutoML/agentic system fit? |
|---|---|---|---|
| **A — Execution path (HFT)** | Order-book microstructure, market-making quotes | µs–ns, FPGA/C++ colocation | **No. Ever.** Not us, not MLE-STAR, not Vertex. Models are hand-fused with the execution stack |
| **B — Signal research (mid-frequency)** | Daily/hourly alphas, regime detection, risk models, portfolio construction | ms–minutes | **Yes — this is the realistic target** |
| **C — Operational ML around trading** | Fraud, trade surveillance, margin-call prediction, client churn, settlement risk | seconds | **Yes — we can serve this nearly today** (it's tabular classification/regression) |

Everything below is about earning Tier B. Tier C needs little beyond what exists.

## Our holdbacks — why we cannot do it TODAY (ranked by severity)

### 1. Our cross-validation is actively dangerous on financial data ⛔ (the blocker)
Every template uses `KFold/StratifiedKFold(shuffle=True)` — random shuffling on
time-ordered data leaks the future into training. On financial series this
produces **beautiful, credible, completely invalid scores**. This is worse than
having no product: it would tell a desk a dead strategy works. Nothing else
matters until this is fixed (purged & embargoed walk-forward CV — López de Prado's
standard treatment).

### 2. No concept of time anywhere in the pipeline
The problem framer has no "forecasting" task type; the train/test split is random,
not temporal; the feature engineer never builds lags, rolling windows, or
exponentially-weighted features — the entire vocabulary of signal construction
is absent.

### 3. Wrong objective functions
RMSE/AUC do not map to money. A model with worse AUC and better tail behavior
makes more PnL. Required: Sharpe, Sortino, max drawdown, hit-rate, and
**turnover/transaction-cost-aware** scoring as first-class `primary_metric`
options the framer can select.

### 4. No leakage forensics
Look-ahead bias (using the same bar's close in a feature), survivorship bias,
restatement bias — a professional quant's first hour on any dataset. Our agents
have zero checks for any of them.

### 5. Labels are assumed, not constructed
We expect a target column to exist. Quant labels are *engineered* — fixed-horizon
returns, triple-barrier outcomes, meta-labels. Needs a labeling agent.

### 6. Non-IID samples
Overlapping return windows make samples non-independent; without uniqueness
weighting, models overfit the overlap. Subtle, and it invalidates naive training.

### 7. Evaluation ≠ backtest
Our evaluator produces a confusion matrix / residuals. A desk needs a
walk-forward backtest with costs and slippage producing an equity curve. Without
it we can't answer the only question that matters: "would this have made money?"

### 8. Serving latency and scale
Sandbox REST inference ≈ 1s — fine for Tier C and daily Tier B signals,
unusable below that. Tick-level data (billions of rows) exceeds our CSV
ingestion entirely. Mitigations exist (ONNX export; parquet via pip-installable
pyarrow) but aren't built.

**Summary: today our results on financial time series would be statistically
invalid (items 1, 2, 6), economically misleading (3, 7), and operationally
incomplete (5, 8). That is the honest "why not now."**

## Requirements roadmap — what we must accomplish

**Phase Q1 — Validity (must precede everything; ~the size of Phase 3):**
- `time_series_forecasting` task type in the problem framer; detect/require a
  timestamp column
- Purged & embargoed walk-forward CV wired into *every* template (baseline,
  feature lift-testing, model bake-off, tuning, evaluation)
- Temporal hold-out (last N% by time, never random)
- Leakage forensics agent: timestamp-ordering assertions, feature-vs-future
  correlation probes, same-bar contamination checks

**Phase Q2 — Signal tooling:**
- Lag/rolling/EWM feature vocabulary in the feature engineer (still
  hypothesis-tested, now under walk-forward lift measurement)
- Finance metrics (Sharpe, Sortino, max-DD, cost-adjusted return) as
  `primary_metric` options + cost model input from the user
- Labeling agent: fixed-horizon and triple-barrier label construction
- Sample-uniqueness weighting for overlapping outcomes

**Phase Q3 — Process credibility:**
- Backtest agent: walk-forward equity curve with costs/slippage in the evidence
  notebook (this artifact alone is a selling event)
- Drift/regime-triggered retraining with champion/challenger promotion
- Determinism guarantees: pinned seeds + environment manifest per run (model
  risk committees require reproducibility)

**Phase Q4 — Productization:**
- ONNX export of winners (sub-ms inference outside the sandbox)
- Parquet/database ingestion (pyarrow is pip-installable into the sandbox)
- Feature-store hooks

Nothing here fights our architecture — every item is new templates, new metrics,
new agents in the same pattern. **It is roadmap, not rewrite.**

## Can MLE-STAR meet the quant finance fit?

**Mostly no — and structurally, not incidentally.** Scored against what desks buy on:

| Desk requirement | MLE-STAR | Us (after Q1–Q3) |
|---|---|---|
| **IP containment** | Disqualifying: Gemini-hosted, *pulls public web code into the research environment*. Strategy data + code transit a third-party cloud | Self-hosted; Ollama option = zero egress |
| **Statistical validity on time series** | Nothing enforces it. It *can* write purged CV if expertly prompted (free code gen) — but nothing guarantees it, and MLE-bench/Kaggle optimization rewards exactly the generalized-IID assumptions quants reject | Enforced by construction: walk-forward CV is *the only* CV the templates offer for time-series tasks |
| **Reproducibility (model risk / SR 11-7)** | Free-form code generation is non-deterministic run-to-run; the artifact is "code + a score." Validation committees reject what they can't reproduce | Same templates every run, pinned seeds, full decision log + evidence notebook ≈ the validation document itself |
| **Iteration speed/cost** | Hours per run, compounding Gemini Pro bills — against a culture of rapid iteration | Minutes, cents, local GPU |
| **Edge preservation** | Its "edge" comes from public web search — by definition, anything found there is not an edge | The desk injects private alpha features into open templates; we industrialize the disciplined 80% around their secret 20% |

**Honest credit where due:** MLE-STAR's free-form code generation means it could
*in principle* implement triple-barrier labeling or purged CV tomorrow if a
skilled user demanded it — our closed templates cannot until we build them.
The asymmetry: **it can but doesn't guarantee; we guarantee but support less.**
In regulated finance, guaranteed discipline beats possible brilliance — an
unvalidatable strategy is an undeployable strategy, whatever its backtest says.

## Bottom line

- **Can we ever fit?** Yes — Tier C almost now, Tier B after Q1–Q3. Tier A never
  (and no one else either; say it plainly and gain credibility).
- **Why not now?** Our CV/metrics/evaluation are IID-shaped; on financial series
  they produce credible-looking invalid results — the one failure mode a quant
  tool cannot have.
- **What must we accomplish?** Q1 validity → Q2 signal tooling → Q3 process
  credibility → Q4 productization, all within the existing template architecture.
- **Does MLE-STAR fit?** No — its cloud dependence, web-code ingestion,
  non-determinism, and leaderboard DNA are misaligned with the three things
  desks pay for: secrecy, validity, auditability. Those three are already our DNA;
  we lack only the time-series machinery, which is buildable.
