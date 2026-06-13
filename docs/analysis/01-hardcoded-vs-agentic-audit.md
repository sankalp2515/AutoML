# Honest Audit: What Is Agentic vs. What Is Hardcoded

> Question: "Did we hardcode any part or any agent? Does it only use the models we
> pre-defined, or is it thinking on its own like a professional Data Scientist?"
> Date: 2026-06-12

## The honest one-line answer

**Decisions are agentic; execution is templated.** The LLM decides *what* to do at
every step; vetted code templates decide *how* it is executed. This is a deliberate
architecture, not an accident — but it has real limits worth knowing.

## What the LLM genuinely decides (agentic)

| Decision | Agent | Evidence it's not hardcoded |
|---|---|---|
| Task type, target column, metric, "good enough" threshold | problem_framer | Framed Titanic as binary/recall, Iris as multiclass/accuracy, Boston as regression/RMSE — from plain-English goals |
| Data quality verdict (usable / warn / abort) | data_auditor | Reads statistical profile, decides whether the pipeline may proceed |
| Which issues matter and in what order | eda_agent | Prioritizes from actual skew/correlation/imbalance numbers |
| Per-column imputation, encoding, scaling (incl. text_tfidf) | preprocessor | Chose RobustScaler for outliers unprompted; chooses per column |
| Feature hypotheses + formulas | feature_engineer | Invents features (PetalArea, SepalPetalAreaRatio) with stated hypotheses |
| Which 2–3 model candidates and their initial params | model_selector | Picks from the menu based on n_samples, imbalance, interpretability |
| Notebook structure, narrative, emphasis | exporter | Different sections/story per problem type |

## What is hardcoded (scaffolding and guardrails)

1. **The pipeline sequence itself** — the 10 stages and their order are a fixed
   LangGraph; the LLM cannot reorder, skip, or invent stages.
2. **Code templates** — agents do NOT write free-form code. They emit *decisions*
   (JSON) that parameterize pre-written, vetted sandbox templates. This is the
   single biggest difference from MLE-STAR-style systems.
3. **The model menu** — XGBoost, RandomForest, GradientBoosting, LogisticRegression,
   Ridge. The LLM selects among them; it cannot go off-menu.
4. **Numeric guardrails** — feature kept only if CV lift > 0.002; iterate only if
   improvement ≥ 2%; max 3 iterations; Optuna search spaces per model family;
   TF-IDF max_features=200; 5-fold CV; SHAP top-15.
5. **The baseline recipe** — always LogisticRegression/Ridge with minimal prep.

## Does it think like a professional DS/MLE?

The *workflow shape* is professional: baseline first → error-driven EDA →
hypothesis-tested features (each measured, not assumed) → bounded tuning →
hold-out evaluation → documented decisions. Every LLM claim is **verified by
execution** — the sandbox result is ground truth, never the LLM's opinion.

What a real senior DS does that ours cannot (yet):
- Write novel code when the template vocabulary doesn't fit
- Question the task itself ("this target is leaky, use X instead")
- Dynamically re-plan the workflow order
- Trade off budget vs. quality consciously

## Why we chose this hybrid deliberately

- **Safety**: templated execution can't import malicious/broken web code
- **Cost**: ~7 LLM calls/run vs hundreds for free-code-gen agents
- **Reliability**: a template that ran 50 times has known failure modes
- **Auditability**: same code shape every run → diffs are meaningful

The trade-off: we sacrifice novelty ceiling for floor reliability. See
`06-control-flow-and-micro-loops.md` for the plan to raise the ceiling without
losing the floor.
