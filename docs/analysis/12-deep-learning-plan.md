# Deep-Learning Phase — Plan, Fit, and Honest Capability Map

> The largest and most complex phase. This document decides WHERE PyTorch fits in
> the existing flow, WHICH architectures we will (and won't) use and why, and gives
> an honest map of what the system can solve now / will solve / could solve / never
> will. Date: 2026-06-26.

## 1. The invariants that constrain everything

Every decision below follows from four core invariants of this platform. Violating
any of them means building a *different product*, not extending this one:

1. **Data is a CSV; the LLM sees only statistical profiles** — not pixels, graphs, or raw streams.
2. **The sandbox has NO network** (Phase 1 isolation) — so we **cannot download pretrained weights** at runtime. From-scratch training only, unless weights are baked into the image.
3. **One modest GPU** (GTX 1660 Ti, 6 GB) — caps model size and rules out anything needing multi-GPU/large-VRAM.
4. **Supervised fit/predict paradigm** — a static labeled dataset, no environment, no reward, no generative objective.

These are not temporary; they are the design. They cleanly partition what DL we can do.

## 2. Where PyTorch fits — extend the registry, don't rebuild

**Decision: a PyTorch model is just another entry in the model registry**, wrapped as
an sklearn-compatible estimator (`fit`/`predict`/`predict_proba`, `get_params`). This
reuses the entire existing flow with no new graph:

```
model_selector (LLM scout picks DL candidate from the registry menu, when data suits it)
      → trains in the SANDBOX via a vetted DL training template (GPU + AMP + early-stop)
      → wrapped estimator slots into the SAME CV / walk-forward / purged-CV machinery
tuner    → Optuna over the registry search space (lr, layers, hidden, dropout, epochs)
evaluator→ unchanged (predict interface); holdout / backtest as today
exporter → TORCH-AWARE serialization (state_dict + architecture config), not joblib
```

What changes, concretely:
- **`model_registry.py`**: new entries (MLP, LSTM/GRU, TCN, Transformer, Autoencoder), each `installed=False` until the sandbox image bakes `torch`. Each declares its Optuna search space — so the tuner needs zero changes.
- **New `DL_TRAIN_TEMPLATE`** (vetted, per the doctrine: code owns the training loop *mechanics*; the LLM owns the *architecture-family + hyperparameter decisions*). GPU-aware (`device="cuda"`, mixed precision), early stopping, returns CV score + a serialized artifact.
- **sklearn-compat wrapper** via **skorch** (or a thin custom wrapper) so a `nn.Module` behaves like any estimator in CV and pipelines.
- **Torch-aware inference** (the real new plumbing): the inference pickle is currently a joblib dict; torch models need `state_dict` + an architecture spec to reconstruct the `nn.Module` at serve time. This is the single hardest integration point.
- **TS path**: register LSTM/TCN/Transformer in the time-series graph — walk-forward + purged CV + the cost-aware backtest already exist, so a sequence model drops straight in. **This is the Tower-relevant headline** (the LOB engine = a Transformer registered here, trained on order-book features).

### Honest integration risks (call these out in interviews)
- **Serialization**: torch ≠ joblib; inference must reconstruct the module from a saved arch spec + weights.
- **No network in the sandbox** → no pretrained backbones; from-scratch only (or pre-baked weights).
- **CV cost**: DL training inside k-fold is slow on one GPU — DL candidates may use a single validation split, not full k-fold.
- **Image size**: `torch` adds ~2 GB to the sandbox image.

## 3. Which architectures we WILL use (focused, not all of them)

A deliberate, senior call: **5 architectures**, all supervised + CSV/sequence + single-GPU-feasible. We are NOT using "all DL models" — most don't fit the chassis (§5).

| Architecture | Use case in our system | Fit |
|---|---|---|
| **ANN / MLP** | Tabular classification/regression (when DL beats GBDTs) | ✅ registry entry |
| **LSTM / GRU (RNN family)** | Time-series forecasting | ✅ TS registry entry |
| **TCN** (temporal conv) | Time-series / sequence — often beats LSTM, trains faster | ✅ TS registry entry |
| **Transformer** (Informer/TCN-attention) | Sequence forecasting, **LOB mid-price prediction (Tower #2)** | ✅ TS registry entry |
| **Autoencoder** | Anomaly detection + dimensionality reduction (streaming #3) | ✅ as a model/transform |

Note (intellectual honesty): on *tabular* data, gradient-boosted trees usually beat MLPs
(Grinsztajn et al. 2022 — already in our analysis docs). So tabular DL is offered as a
*candidate the LLM can pick when warranted*, not a default. The real DL value is **sequence
models on time-series/LOB** — which is exactly Tower's domain.

## 4. Phased DL build plan

- **DL-0 (foundation, hardest):** bake `torch` + `skorch` into the sandbox image; sklearn-wrapped MLP estimator + one registry entry; the `DL_TRAIN_TEMPLATE` (GPU + AMP + early stopping); torch-aware inference serialization. **Prove one tabular MLP end-to-end** (train → CV → tune → deploy → predict). Everything else builds on this.
- **DL-1 (Tower-relevant):** LSTM/GRU/TCN in the TS path; walk-forward + purged CV + backtest (all already exist).
- **DL-2 (the headline):** Transformer + the LOB engine (#2) — order-book features via the TS feature builder, TorchScript/ONNX inference.
- **DL-3:** distributed training DDP/FSDP + profiling + mixed precision (#4, demonstrable at small scale on one GPU, documented for multi-node); autoencoder anomaly detector (#3).

Each phase gates on the prior; **DL-0 is make-or-break** — if the serialization/sandbox/GPU plumbing works for one MLP, the rest is mostly new registry entries + templates.

## 5. Capability map (the explicit ask)

### ✅ CAN SOLVE NOW (shipped)
- Tabular **binary / multiclass / multilabel classification** and **regression** (sklearn/XGBoost).
- **Free-text** classification (TF-IDF).
- **Imbalanced** classification (in-fold SMOTE, PR-AUC).
- **Time-series forecasting** (walk-forward, lag/rolling features, sklearn regressors) + **trading backtest** (Sharpe/drawdown/turnover) + **purged/embargoed CV**.
- The **reproducible research toolkit** (CSV + YAML → models → backtest → report).

### 🔜 WILL SOLVE (planned — this DL phase)
- **Deep learning on tabular** (MLP, FT-Transformer) when it beats GBDTs.
- **Deep sequence forecasting** (LSTM/GRU/TCN/Transformer) on time-series and **LOB mid-price prediction** (Tower #2).
- **Autoencoder anomaly detection** (incl. streaming, #3).
- **Distributed GPU training** (DDP/FSDP, #4).
- Multivariate / probabilistic forecasting (TS model depth).

### 🟡 NOT PLANNED, BUT POSSIBLE (separate "studio", different data layer, large effort)
Each needs a new data-ingestion layer + models + eval — feasible on the agentic chassis, but a distinct pipeline like the TS studio:
- **Recommendation systems** — interactions CSV (user/item) → matrix factorization / implicit-ALS / two-tower neural; ranking metrics (NDCG, recall@k). Our single-target supervised flow doesn't fit recsys directly, but a recsys studio could. **Yes, our agents could orchestrate it — with a new data layer and models.**
- **Reinforcement learning** (Q-learning, **DQN**) — needs an **environment** (state/action/reward + rollouts), which we don't have; our data is a static labeled CSV. A legit version is an **RL-on-backtest-environment studio** for trading (state = market features, action = position, reward = PnL net of costs). Architecturally possible, **large** effort, and notoriously prone to overfitting the simulator — so high-risk. **Not in the current plan.**
- **GNNs** — graph-structured data (nodes/edges) via PyG/DGL; needs a graph data layer.
- **Synthetic tabular data** (CTGAN) — generative tabular; a niche augmentation studio.

### ⛔ CANNOT SOLVE (effectively never, on this design + hardware)
Each violates a core invariant (§1); doing them means a different product:
- **Computer vision on images (CNN)** at real scale — needs image ingestion (not CSV), pretrained backbones (network — blocked), and a bigger GPU.
- **Large NLP / LLM-grade Transformers** needing pretrained weights — the sandbox is network-isolated (can't fetch HF weights) and the GPU is too small. (Small from-scratch text models on tokenized columns are weak and not worth it.)
- **Diffusion models / large GANs** (image/video/audio generation) — compute far beyond one 6 GB GPU; wrong data modality and objective.
- **True HFT low-latency execution** (microseconds) — that's C++/FPGA/kernel-bypass territory, not a Python orchestration platform. (We do the *research/modeling* layer, not the execution layer.)
- **Open-ended / AGI-style tasks** — this is a bounded supervised-ML platform by design.

**Why "never":** these require abandoning at least one invariant — non-CSV data, network access for pretrained weights, large/multi-GPU compute, or a non-supervised paradigm. They're out of scope by construction, not by laziness.

## 6. Recommended scope for the phase

Do **DL-0 → DL-1 → DL-2** (tabular MLP foundation → TS sequence models → the LOB Transformer).
That delivers the Tower-mandatory deep-learning + sequence-model + GPU story on the existing
chassis. Treat RL, RecSys, GNN, and generative models as **explicitly out of scope** for now —
name them as "possible future studios" in interviews to show you know the boundary, but don't
build them: they're separate products and would dilute the focused, defensible story.
