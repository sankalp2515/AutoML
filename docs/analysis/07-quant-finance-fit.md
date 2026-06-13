# Why Quant Finance / HFT Would Use Us (When We Build for Their Complexity)

> Question 7 — Date: 2026-06-12

## Why quants reject traditional AutoML (user's framing, confirmed)

1. **Edge vs. generalization** — AutoML optimizes for the statistically likely
   generalized solution; alpha lives in tiny anomalies that generalized
   optimization smooths away.
2. **Iteration speed** — cloud AutoML takes hours/days per cycle; quant research
   is a rapid-iteration game.
3. **Black boxes are undeployable** — model risk committees (SR 11-7 and
   equivalents) require documented, validated, explainable models.
4. **IP paranoia** — strategies are the firm's crown jewels; nothing goes to a
   third-party cloud.

## Our genuine angles of attack

| Quant requirement | Our property |
|---|---|
| Rapid iteration | Runs complete in **minutes on local hardware** (GPU XGBoost included) — not cloud-queue hours. Iteration velocity is the currency we already trade in |
| Model risk documentation | The **evidence notebook + decision log is, almost verbatim, model-validation documentation**: every choice, its rationale, its measured effect, the hold-out protocol. This is normally weeks of analyst work per model |
| IP containment | Fully self-hosted; with the Ollama provider in the fallback chain, **zero bytes leave the building** — including prompts |
| Edge preservation | Because templates are open code, a desk injects its *own* alpha features, cost functions, and CV schemes into the menu. The system then automates the disciplined 80% (data hygiene, leakage checks, CV protocol, drift) while the quant owns the 20% that is the edge. We don't find the edge — we *industrialize everything around it* |

## What we must build for them (honest gap list)

1. **Purged/embargoed walk-forward CV** — random k-fold is invalid on financial
   time series (leakage through time); this is table stakes
2. **Finance-native metrics** — Sharpe, Sortino, max drawdown, turnover-aware
   PnL as first-class `primary_metric` options the framer can choose
3. **Leakage detection agent** — automated look-ahead and survivorship checks
4. **Walk-forward backtesting agent** — evaluation = simulated trading, not a
   confusion matrix
5. **Export path for latency** — execution-path inference must be µs-class:
   ONNX/C++ export of the winning model, *not* our REST sandbox

## The honest boundary

We will never sit on the **execution path** of an HFT system — microsecond
inference through a REST sandbox is a category error, and we should say so
plainly. Our seat is the **research and validation workflow**: hypothesis →
disciplined evaluation → documented, audit-ready model → drift-monitored
deployment for the *slower* layers (risk models, regime classifiers, overnight
signals, portfolio construction). That market is large, underserved, and values
exactly what we already are: fast, private, explainable, and cheap.
