import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.state import AgentState
from app.core import model_registry as registry

# The candidate menu is RETRIEVED from app/core/model_registry.py (the source) and
# injected per-run into the user message — not hardcoded here. Add a model = add a
# registry entry; the scout below picks from whatever is registered + installed.
SYSTEM_PROMPT = """You are an expert ML model scout.
From the AVAILABLE MODELS list provided in the user message, select 2-3 candidates
best suited to the data (NOT an exhaustive search). Use ONLY the exact class strings
from that list — never invent a class.

General heuristics:
- n_samples < 5000: prefer linear (LogisticRegression / Ridge) or HistGradientBoosting
- n_samples > 5000 / wide data: prefer XGBoost or HistGradientBoosting
- interpretability required: linear models only
- high class imbalance: prefer models marked [class_weight]
- multilabel: any classifier works (wrapped in MultiOutputClassifier automatically);
  MultiOutputClassifier(LogisticRegression) is a strong baseline
- include at least one boosting model unless interpretability is required

If a RECOMMENDED (not-installed) model would clearly suit this data better, name it in
"discovery_notes" with its pip package — but DO NOT select it (it cannot train until installed).

Respond with JSON:
{
  "selected_models": [
    {"name": "...", "class": "<exact class string from the list>",
     "reason": "<why>", "initial_params": {"...": "..."}}
  ],
  "discovery_notes": "<optional: a not-installed model worth adding, with pip package>",
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
from sklearn.ensemble import (RandomForestClassifier, RandomForestRegressor,
                              GradientBoostingClassifier, GradientBoostingRegressor,
                              HistGradientBoostingClassifier, HistGradientBoostingRegressor)
from sklearn.svm import SVC
from sklearn.multioutput import MultiOutputClassifier
import xgboost as xgb

enriched_path = "{enriched_path}"
df = pd.read_csv(enriched_path)

# For multilabel, target is stored as JSON strings; parse them
task_type = "{task_type}"
if task_type == "multilabel_classification":
    import ast
    y_raw = df["__target__"].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    y = np.array(y_raw.tolist())
else:
    y = df["__target__"].values
X = df.drop(columns=["__target__"])

primary_metric = "{primary_metric}"
class_imbalance = {class_imbalance}
label_columns = {label_columns}
label_delimiter = "{label_delimiter}"
imbalance_strategy = "{imbalance_strategy}"


def _cv_estimator(model):
    # In-fold SMOTE/SMOTE-Tomek for single-label classification: resampling happens
    # ONLY on each training fold (imblearn Pipeline), never the validation fold — no leakage.
    if (task_type in ("binary_classification", "multiclass_classification")
            and imbalance_strategy in ("smote", "smote_tomek")):
        try:
            from imblearn.over_sampling import SMOTE
            from imblearn.combine import SMOTETomek
            from imblearn.pipeline import Pipeline as ImbPipeline
            minority = int(pd.Series(y).value_counts().min())
            if minority >= 6:
                rs = (SMOTE(k_neighbors=min(5, minority - 1), random_state=42)
                      if imbalance_strategy == "smote" else SMOTETomek(random_state=42))
                return ImbPipeline([("resample", rs), ("model", model)])
        except Exception:
            pass
    return model

scoring_map = {{
    "auc_roc": "roc_auc",
    "recall": "recall",
    "precision": "precision",
    "f1": "f1",
    "accuracy": "accuracy",
    "rmse": "neg_root_mean_squared_error",
    "mae": "neg_mean_absolute_error",
    "r2": "r2",
    "pr_auc": "average_precision",
    "f1_micro": "f1_micro",
    "f1_macro": "f1_macro",
    "f1_samples": "f1_samples",
    "hamming_loss": "hamming_loss",
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
        "average_precision": "average_precision",  # PR-AUC not defined for multiclass in sklearn
    }}.get(scoring, scoring)

if task_type != "regression" and task_type != "multilabel_classification":
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

    # Add class_weight for imbalanced classification (not for multilabel)
    if task_type != "regression" and task_type != "multilabel_classification" and class_imbalance:
        if "class_weight" in __import__("inspect").signature(
            eval(config["class"])
        ).parameters:
            params["class_weight"] = "balanced"

    # Route XGBoost to GPU when available
    if "XGB" in config["class"] and GPU_AVAILABLE:
        params["device"] = "cuda"
        params["tree_method"] = "hist"

    try:
        base_model = eval(config["class"])(**params)
        
        # Wrap in MultiOutputClassifier for multilabel
        if task_type == "multilabel_classification":
            model = MultiOutputClassifier(base_model, n_jobs=1)
        else:
            model = base_model
            
        t0 = time.time()
        scores = cross_val_score(_cv_estimator(model), X, y, cv=cv, scoring=scoring, n_jobs=1)
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
if task_type != "regression" and task_type != "multilabel_classification" and class_imbalance:
    winner_params["class_weight"] = "balanced"

base_model = eval(winner_config["class"])(**winner_params)
if task_type == "multilabel_classification":
    winner_model = MultiOutputClassifier(base_model, n_jobs=1)
else:
    winner_model = base_model
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
        task_type = state["task_type"]

        # RETRIEVE the candidate menu from the registry (the source) for this task.
        menu = registry.menu_text(task_type)
        recs = registry.recommendations_text(task_type)
        allowed_classes = {
            registry.class_for(s, task_type)
            for s in registry.catalog_for(task_type, installed_only=True)
        }

        user_message = f"""
Task: {task_type}
Primary metric: {state['primary_metric']}
n_samples: {n_samples}
n_features (after preprocessing): {audit.get('shape', [0, 0])[1]}
Class imbalance: {json.dumps(class_imbalance)}
Interpretability required: {state.get('interpretability_required', False)}
Current baseline score: {state.get('current_score')} ({state.get('primary_metric')})

AVAILABLE MODELS (choose 2-3; use the exact class string):
{menu}
{("RECOMMENDED (not installed — advisory only, do NOT select):" + chr(10) + recs) if recs else ""}

Select 2-3 model candidates with initial parameters.
"""
        response = await self.llm.complete_json(SYSTEM_PROMPT, user_message)
        selected_models = response.get("selected_models", [])

        # Validate against the registry — drop any class the LLM invented (eval-safety),
        # and fall back to the registry's default candidates if nothing valid remains.
        selected_models = [m for m in selected_models if m.get("class") in allowed_classes]
        if not selected_models:
            fallback = registry.catalog_for(task_type, installed_only=True)[:2]
            selected_models = [
                {"name": s["name"], "class": registry.class_for(s, task_type),
                 "reason": "registry default", "initial_params": {}}
                for s in fallback
            ]

        discovery_notes = response.get("discovery_notes", "")
        if discovery_notes:
            await self.emit(run_id, f"Scout note: {discovery_notes[:160]}", {"discovery": True})

        def render(p: dict) -> str:
            return TRAINING_CODE_TEMPLATE.format(
                enriched_path=state.get("enriched_data_path", ""),
                task_type=state["task_type"],
                primary_metric=state["primary_metric"],
                class_imbalance=repr(bool(class_imbalance and class_imbalance.get("imbalanced"))),
                models_config=repr(p["models_config"]),
                label_columns=repr(state.get("label_columns", [])),
                label_delimiter=state.get("label_delimiter", ""),
                imbalance_strategy=state.get("imbalance_strategy", "none"),
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
            # Tier-1 (param revision) exhausted → let the agent WRITE its own fix.
            result = await self.try_agentic_repair(
                run_id, render({"models_config": selected_models}), result,
                task_type=state.get("task_type", "unknown"),
                result_keys=["winner", "winner_score", "models_results", "winner_path", "winner_class"],
                goal=("From enriched.csv (has a '__target__' column), train & cross-validate the "
                      "candidate models, pick the best by CV score, save it to "
                      "artifacts_dir/winner_model.pkl. Set RESULT with winner (str), winner_score "
                      "(float), models_results ({name: {cv_score, cv_std, training_time_s}}), "
                      "winner_path (str), winner_class (str)."),
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
