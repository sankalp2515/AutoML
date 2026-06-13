# Deep Analysis: Should We Web-Search for Modern Model Architectures?

> Question 4 — flagged "highly important." Date: 2026-06-12
> Verdict up front: **NO to runtime web-search-for-code. YES to a curated
> model-registry pipeline and (later) search-for-knowledge-not-code.**

## What web search buys MLE-STAR

MLE-STAR's search step exists to escape the LLM's training cutoff: it finds
recent architectures (FT-Transformer, TabPFN, novel ensembling tricks) and pulls
implementation code from the public web into its working environment. On Kaggle
benchmarks this yields real leaderboard gains — *novelty is rewarded there.*

## Why the same move is wrong for us — four arguments

### 1. It destroys our core safety property
Our entire execution-safety story is: **the sandbox only runs vetted templates,
parameterized by LLM decisions.** The moment we execute web-discovered code, we
inherit MLE-STAR's own admitted worst risk — "pulling poorly optimized, broken,
or insecure public code into its environment" — and we inherit it *worse*,
because our sandbox mounts the user's dataset. A poisoned snippet exfiltrating
training data is a company-ending event for the regulated buyers we target
(see doc 03: data sovereignty is a primary switching reason).

### 2. The marginal return on tabular data is small — empirically
For tabular datasets in our operating range (10² – 10⁷ rows), gradient-boosted
trees remain at or near state of the art; the well-known result (Grinsztajn et
al., 2022, "Why do tree-based models still outperform deep learning on tabular
data") has held up in practice. Exotic architectures help mainly on the margins
(TabPFN: only tiny datasets; FT-Transformer: needs heavy tuning to match XGBoost).
**On tabular problems, feature engineering and tuning — which we already automate —
dominate architecture choice.** Web search optimizes the lowest-leverage stage of
our pipeline.

### 3. Dependency reality
Novel architectures arrive with novel dependencies (torch versions, CUDA matrices,
compiled extensions). Our sandbox cannot even `apt-get` (network constraint,
documented), and per-run `pip install` of arbitrary packages is both a reliability
sinkhole and a second supply-chain door. MLE-STAR runs in disposable cloud VMs;
we run on the user's machine. Different blast radius.

### 4. It adopts the competitor's cost structure
Search → read → adapt → debug → retry loops are precisely the "compounding API
call costs" and "time complexity" limitations the user listed for MLE-STAR (Q8).
Our differentiation is minutes-and-cents per run. Importing their search loop
imports their bill.

## What we should do instead — three concrete mechanisms

### A. Curated model-registry expansion (now)
A quarterly *human-in-the-loop* process: we (the maintainers) evaluate candidate
model families and add vetted adapters to the menu. Immediate candidates:
- **CatBoost** — native categorical handling, frequently beats XGBoost on
  high-cardinality data; pip-installable, pure-wheel
- **TabPFN v2** — near-zero-cost strong baselines for datasets < 10K rows
- **HistGradientBoosting** (sklearn-native) — already importable, zero new deps
The LLM still *chooses*; the menu just grows. Novelty enters through a vetted door.

### B. Search-for-knowledge, not code (Phase 4+, optional "research mode")
A research agent MAY search the web for *text*: best practices, benchmark
results, "what works for imbalanced fraud data." Its findings are injected into
the model_selector / feature_engineer prompts as advisory context. Text cannot
execute. This captures most of the freshness benefit at near-zero security cost.
Guardrails: allow-listed domains (arxiv, sklearn docs, official model docs),
findings logged in the decision log like every other input.

### C. Architecture telemetry (free)
We already record every model choice and outcome. Aggregated across runs, this
becomes our own evidence base for menu curation — *our* benchmark, on *real user
workloads*, instead of Kaggle's.

## Decision

| Option | Verdict |
|---|---|
| Runtime web search → execute found code | **Rejected** — breaks safety architecture, low tabular ROI, dependency hell, adopts competitor's cost curve |
| Curated registry expansion (CatBoost, TabPFN, HGBT) | **Adopt** — next menu update |
| Search-for-knowledge (text-only, allow-listed) | **Adopt later** — Phase 4+ optional flag |
| Per-run architecture telemetry | **Adopt** — already 90% built via decision logs |
