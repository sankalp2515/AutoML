# Competitive Positioning vs. Google Vertex AutoML

> Questions 3 & 6 — Date: 2026-06-12

## Why a user switches to us (the honest pitch)

| Axis | Google Vertex AutoML | Us |
|---|---|---|
| **Transparency** | Black box. You get a model + feature attribution; you never learn *why* preprocessing/feature choices were made | Glass box. Decision log with reasoning per choice, LLM-narrated evidence notebook, SHAP — the system explains itself like a senior DS handing over a project |
| **Cost** | ~$21+/node-hour for tabular training; egress + endpoint costs; bills scale opaquely | Free-tier LLMs (Groq/Gemini) + your own hardware/GPU; per-call LLM cost shown in the UI. A full run costs cents at most |
| **Data sovereignty** | Data lives in Google Cloud | Fully self-hosted; with Ollama the data never leaves the machine. Critical for healthcare/finance/government |
| **Lock-in** | Model served only on Vertex endpoints; export options limited | Artifacts are plain sklearn/joblib + a generated FastAPI server — runs on any box with Python |
| **Auditability** | Compliance docs are your problem | The evidence notebook ≈ model-validation documentation (huge for regulated buyers) |
| **Hackability** | Closed | Open codebase; teams can extend templates, metrics, model menu |

**Where Google honestly wins:** terabyte-scale data, NAS-grade neural models,
image/video/multimodal, managed autoscaling with SLAs, enterprise IAM. We do not
pretend to compete there — our buyer is the team that wants *understanding,
control, and low cost* on tabular problems.

## Feature-by-feature vs Vertex core features (Q6)

### a) One-click deployment
- **Have**: `POST /runs/{id}/deploy` → live REST `POST /predict` with confidence +
  threshold, every prediction logged, deployment registry, UI playground.
- **Gap**: no batch-prediction endpoint yet (upload CSV → scored CSV — roadmap),
  no autoscaling; inference runs through the sandbox (~1s/request) vs Vertex's
  managed low-latency endpoints. *Capability parity, not scale parity.*

### b) Feature attribution / Explainable AI
- **Have**: SHAP computed every run — top-15 features + summary plot + stored in
  state and the model card. Plus a layer Vertex doesn't have: *decision*
  attribution (why each pipeline choice was made), not just *prediction* attribution.
- **Gap**: per-prediction attribution (Vertex explains each individual prediction).
  Roadmap: per-prediction SHAP endpoint + what-if explorer — straightforward since
  the pipeline artifact already contains the model.

### c) Vertex Pipelines (scheduled retraining)
- **Have**: drift detection (PSI + KS) against training data; manual re-run on the
  same dataset is one click.
- **Gap (real)**: no scheduler, no drift-triggered automatic retraining, no
  champion/challenger promotion. This is our weakest leg of the three and is the
  highest-priority Phase 4+ item: cron schedules + "retrain when max_PSI > 0.25 →
  promote only if challenger beats champion on hold-out."

## Positioning sentence

> Vertex sells you a model. We sell you a *data scientist's complete work product* —
> the model, the reasoning, the documentation, the monitoring — at hobbyist cost,
> on your own hardware.
