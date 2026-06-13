import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.state import AgentState

SYSTEM_PROMPT = """You are an expert ML model selector.
Given the data characteristics, select 2-3 model candidates (NOT exhaustive search).

Available models (use ONLY these exact class strings):
  Classification: "xgb.XGBClassifier", "RandomForestClassifier", "GradientBoostingClassifier", "LogisticRegression"
  Regression:     "xgb.XGBRegressor",  "RandomForestRegressor",  "GradientBoostingRegressor",  "Ridge"

Heuristics:
- n_samples < 5000: prefer LogisticRegression or Ridge
- n_samples > 5000: prefer xgb.XGBClassifier / xgb.XGBRegressor
- interpretability required: LogisticRegression or Ridge only
- high class imbalance: use class_weight="balanced" (LogReg, RF, GB only — not XGB)
- Always include XGBoost as one candidate unless interpretability is required

Respond with JSON:
{
  "selected_models": [
    {
      "name": "XGBoost",
      "class": "xgb.XGBClassifier",
      "reason": "<why selected>",
      "initial_params": {"n_estimators": 100, "learning_rate": 0.1, "max_depth": 6}
    }
  ],
  "decisions": [{"decision": "...", "reasoning": "..."}]
}
"""

TRAINING_CODE_TEMPLATE = '''
import pandas as pd
import numpy as np
import joblib
import json
import os
import time
import warnings
warnings.filterwarnings("ignore")

from sklearn.model_selection import cross_val_score, StratifiedKFold, KFold
from sklearn.linear_model import LogisticRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor, GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.svm import SVC
import xgboost as xgb

enriched_path = "{enriched_path}"
df = pd.read_csv(enriched_path)
y = df["__target__"].values
X = df.drop(columns=["__target__"])

task_type = "{task_type}"
primary_metric = "{primary_metric}"
class_imbalance = {class_imbalance}

scoring_map = {{
    "auc_roc": "roc_auc",
    "recall": "recall",
    "precision": "precision",
    "f1": "f1",
    "accuracy": "accuracy",
    "rmse": "neg_root_mean_squared_error",
    "mae": "neg_mean_absolute_error",
    "r2": "r2",
}}
scoring = scoring_map.get(primary_metric, "roc_auc" if task_type != "regression" else "neg_root_mean_squared_error")

# Binary-only scorers silently produce NaN on multiclass (sklearn catches the
# scorer error and applies error_score=nan) — remap to weighted variants.
if task_type == "multiclass_classification":
    scoring = {{
        "roc_auc": "roc_auc_ovr_weighted",
        "recall": "recall_weighted",
        "precision": "precision_weighted",
        "f1": "f1_weighted",
    }}.get(scoring, scoring)

if task_type != "regression":
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
else:
    cv = KFold(n_splits=5, shuffle=True, random_state=42)

models_config = {models_config}

# GPU detection — XGBoost 2.x uses device="cuda" (pip wheels ship CUDA support).
# nvidia-smi is mounted into the container by the NVIDIA runtime when a GPU
# is reserved in docker-compose. sklearn models are CPU-only regardless.
import shutil as _shutil
GPU_AVAILABLE = _shutil.which("nvidia-smi") is not None

results = {{}}
for config in models_config:
    name = config["name"]
    params = config.get("initial_params", {{}})

    # Add class_weight for imbalanced classification
    if task_type != "regression" and class_imbalance:
        if "class_weight" in __import__("inspect").signature(
            eval(config["class"])
        ).parameters:
            params["class_weight"] = "balanced"

    # Route XGBoost to GPU when available
    if "XGB" in config["class"] and GPU_AVAILABLE:
        params["device"] = "cuda"
        params["tree_method"] = "hist"

    try:
        model = eval(config["class"])(**params)
        t0 = time.time()
        scores = cross_val_score(model, X, y, cv=cv, scoring=scoring, n_jobs=1)
        elapsed = time.time() - t0

        if task_type == "regression" and scoring.startswith("neg_"):
            score = float(-scores.mean())
        else:
            score = float(scores.mean())

        # NaN means the scorer is incompatible with this task — sklearn
        # swallows the scorer error and returns error_score=nan per fold.
        if np.isnan(score):
            raise ValueError(
                f"scoring '{{scoring}}' produced NaN for all folds — "
                f"metric incompatible with task '{{task_type}}'"
            )

        results[name] = {{
            "cv_score": score,
            "cv_std": float(scores.std()),
            "training_time_s": round(elapsed, 2),
            "class": config["class"],
            "params": params,
        }}
    except Exception as e:
        results[name] = {{"error": str(e), "cv_score": -999}}

# Select winner
valid = {{k: v for k, v in results.items() if "error" not in v}}
if not valid:
    error_details = "; ".join(f"{{k}}: {{v.get('error', '?')[:120]}}" for k, v in results.items())
    raise RuntimeError(f"All model candidates failed — {{error_details}}")
if task_type == "regression":
    winner = min(valid, key=lambda k: valid[k]["cv_score"])
else:
    winner = max(valid, key=lambda k: valid[k]["cv_score"])

# Train winner on full data and save
winner_config = next(c for c in models_config if c["name"] == winner)
winner_params = valid[winner]["params"]
if task_type != "regression" and class_imbalance:
    winner_params["class_weight"] = "balanced"
winner_model = eval(winner_config["class"])(**winner_params)
winner_model.fit(X, y)

os.makedirs(artifacts_dir, exist_ok=True)
winner_path = os.path.join(artifacts_dir, "winner_model.pkl")
joblib.dump(winner_model, winner_path)

RESULT = {{
    "models_results": results,
    "winner": winner,
    "winner_score": valid[winner]["cv_score"],
    "winner_path": winner_path,
    "winner_class": winner_config["class"],
    "winner_params": winner_params,
    "gpu_used": GPU_AVAILABLE,
}}
'''


class ModelSelectorAgent(BaseAgent):
    name = "model_selector"

    async def run(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        await self._mark_step(run_id, "running")
        await self.emit(run_id, "Selecting 2-3 model candidates based on data characteristics...")

        audit = state.get("data_audit", {})
        eda = state.get("eda_insights", {})
        n_samples = audit.get("shape", [0])[0]
        class_imbalance = eda.get("class_imbalance", {})

        user_message = f"""
Task: {state['task_type']}
Primary metric: {state['primary_metric']}
n_samples: {n_samples}
n_features (after preprocessing): {audit.get('shape', [0, 0])[1]}
Class imbalance: {json.dumps(class_imbalance)}
Interpretability required: {state.get('interpretability_required', False)}
Current baseline score: {state.get('current_score')} ({state.get('primary_metric')})

Select 2-3 model candidates with initial parameters.
"""
        response = await self.llm.complete_json(SYSTEM_PROMPT, user_message)
        selected_models = response.get("selected_models", [])

        if not selected_models:
            default = {"name": "XGBoost", "class": "xgb.XGBClassifier",
                       "reason": "default", "initial_params": {"n_estimators": 100}}
            selected_models = [default]

        def render(p: dict) -> str:
            return TRAINING_CODE_TEMPLATE.format(
                enriched_path=state.get("enriched_data_path", ""),
                task_type=state["task_type"],
                primary_metric=state["primary_metric"],
                class_imbalance=repr(bool(class_imbalance and class_imbalance.get("imbalanced"))),
                models_config=repr(p["models_config"]),
            )

        result = await self.execute_code_with_repair(
            run_id, render, {"models_config": selected_models},
            repair_goal=(
                "Train & cross-validate candidate models. models_config is a list of "
                '{"name", "class", "initial_params"} where class is one of: '
                "xgb.XGBClassifier, RandomForestClassifier, GradientBoostingClassifier, "
                "LogisticRegression (or the *Regressor / Ridge variants). Fix errors by "
                "removing a model that errored, correcting invalid initial_params, or "
                "swapping to a compatible model for this task."
            ),
            timeout=600,
        )
        if not result["success"]:
            await self._mark_step(run_id, "failed", result["error"])
            return {"error": f"Model training failed: {result['error']}", "status": "failed"}

        # Reflect any repaired candidate list in the decisions we log
        selected_models = result.get("final_params", {}).get("models_config", selected_models)
        code = render({"models_config": selected_models})  # exact code that ran (post-repair)
        data = result["result"]
        winner = data["winner"]
        winner_score = data["winner_score"]
        # NaN serializes to null over the sandbox HTTP boundary — guard so a
        # bad score fails this agent cleanly instead of crashing the pipeline.
        if winner_score is None or winner_score != winner_score:
            error_msg = f"Model selection produced invalid score for '{winner}' (metric incompatible with task?)"
            await self._mark_step(run_id, "failed", error_msg)
            return {"error": error_msg, "status": "failed"}

        decision_log_entries = []
        for d in response.get("decisions", []):
            entry = await self._log_decision(
                run_id=run_id,
                decision=d["decision"],
                reasoning=d["reasoning"],
                result_summary=f"winner={winner}, score={winner_score:.4f}",
            )
            decision_log_entries.append(entry)

        for model_name, model_data in data["models_results"].items():
            if "error" not in model_data:
                entry = await self._log_decision(
                    run_id=run_id,
                    decision=f"Trained {model_name}: cv_score={model_data['cv_score']:.4f}",
                    reasoning=f"Cross-validation with 5 folds. Std: {model_data['cv_std']:.4f}",
                    result_summary=f"time={model_data['training_time_s']}s",
                )
                decision_log_entries.append(entry)

        from app.core import mlflow_tracker as mlflow
        iteration = state.get("iteration", 0)
        # Use iteration-prefixed keys — MLflow forbids changing param values
        mlflow.log_params({f"i{iteration}_winner_model": winner})
        mlflow.log_metric("post_model_selection_score", winner_score, step=iteration)
        for m_name, m_data in data["models_results"].items():
            if "error" not in m_data:
                mlflow.log_metric(f"cv_score_{m_name}", m_data["cv_score"], step=iteration)

        await self.emit(
            run_id,
            f"Winner: {winner} with {winner_score:.4f} {state['primary_metric']}",
            {"winner": winner, "score": winner_score, "all_results": {
                k: v.get("cv_score") for k, v in data["models_results"].items()
            }},
        )
        await self._mark_step(run_id, "completed")

        existing_log = state.get("decision_log", [])
        existing_cells = state.get("notebook_cells", [])
        iteration = state.get("iteration", 0)
        new_cell = {
            "agent": self.name,
            "title": f"Model Selection — Iteration {iteration + 1}",
            "iteration": iteration + 1,
            "code": code,
            "stdout": result.get("stdout", ""),
            "result_summary": {
                "iteration": iteration + 1,
                "models_compared": {
                    name: {
                        "cv_score": round(m.get("cv_score", -999), 4),
                        "cv_std": round(m.get("cv_std", 0), 4),
                        "training_time_s": m.get("training_time_s", 0),
                        "class": m.get("class", ""),
                    }
                    for name, m in data["models_results"].items()
                    if "error" not in m
                },
                "winner": winner,
                "winner_score": round(winner_score, 4),
                "winner_class": data["winner_class"],
                "winner_params": data["winner_params"],
                "selection_reasons": [
                    m.get("reason", "") for m in selected_models
                ],
            },
        }
        return {
            "models_evaluated": data["models_results"],
            "winner_model": winner,
            "winner_model_path": data["winner_path"],
            "winner_model_class": data["winner_class"],
            "best_hyperparams": data["winner_params"],
            "current_score": winner_score,
            "prev_score": state.get("current_score", state.get("baseline_score", 0.0)),
            "decision_log": existing_log + decision_log_entries,
            "notebook_cells": existing_cells + [new_cell],
        }
