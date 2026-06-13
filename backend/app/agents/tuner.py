from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.state import AgentState

TUNING_CODE_TEMPLATE = '''
import pandas as pd
import numpy as np
import joblib
import optuna
import os
import warnings
warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

from sklearn.model_selection import cross_val_score, StratifiedKFold, KFold
import xgboost as xgb
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import (RandomForestClassifier, RandomForestRegressor,
                               GradientBoostingClassifier, GradientBoostingRegressor)

enriched_path = "{enriched_path}"
df = pd.read_csv(enriched_path)
y = df["__target__"].values
X = df.drop(columns=["__target__"])

task_type = "{task_type}"
primary_metric = "{primary_metric}"
winner_class = "{winner_class}"
n_trials = {n_trials}

scoring_map = {{
    "auc_roc": "roc_auc", "recall": "recall", "precision": "precision",
    "f1": "f1", "accuracy": "accuracy", "rmse": "neg_root_mean_squared_error",
    "mae": "neg_mean_absolute_error", "r2": "r2",
}}
scoring = scoring_map.get(primary_metric, "roc_auc")

# Binary-only scorers produce NaN on multiclass — remap to weighted variants
if task_type == "multiclass_classification":
    scoring = {{
        "roc_auc": "roc_auc_ovr_weighted",
        "recall": "recall_weighted",
        "precision": "precision_weighted",
        "f1": "f1_weighted",
    }}.get(scoring, scoring)

higher_is_better = not scoring.startswith("neg_")

if task_type != "regression":
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
else:
    cv = KFold(n_splits=5, shuffle=True, random_state=42)

# GPU detection — XGBoost trials run on CUDA when the GPU is reserved
import shutil as _shutil
GPU_AVAILABLE = _shutil.which("nvidia-smi") is not None
_xgb_device = {{"device": "cuda", "tree_method": "hist"}} if GPU_AVAILABLE else {{}}


def objective(trial):
    if "XGB" in winner_class:
        params = {{
            "n_estimators": trial.suggest_int("n_estimators", 100, 500),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        }}
        if task_type == "regression":
            model = xgb.XGBRegressor(**params, **_xgb_device, random_state=42, verbosity=0)
        else:
            model = xgb.XGBClassifier(**params, **_xgb_device, random_state=42, verbosity=0)

    elif "GradientBoosting" in winner_class:
        params = {{
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "max_depth": trial.suggest_int("max_depth", 2, 8),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        }}
        if task_type == "regression":
            model = GradientBoostingRegressor(**params, random_state=42)
        else:
            model = GradientBoostingClassifier(**params, random_state=42)

    elif "RandomForest" in winner_class:
        params = {{
            "n_estimators": trial.suggest_int("n_estimators", 50, 400),
            "max_depth": trial.suggest_int("max_depth", 3, 20),
            "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2"]),
        }}
        if task_type == "regression":
            model = RandomForestRegressor(**params, random_state=42, n_jobs=1)
        else:
            model = RandomForestClassifier(**params, random_state=42, n_jobs=1,
                                            class_weight="balanced")

    elif "LogisticRegression" in winner_class:
        params = {{
            "C": trial.suggest_float("C", 1e-4, 100, log=True),
            "penalty": trial.suggest_categorical("penalty", ["l1", "l2"]),
            "solver": "liblinear",
        }}
        model = LogisticRegression(**params, max_iter=1000, random_state=42)

    elif "Ridge" in winner_class:
        params = {{"alpha": trial.suggest_float("alpha", 1e-4, 100, log=True)}}
        model = Ridge(**params)

    else:
        return 0.0

    scores = cross_val_score(model, X, y, cv=cv, scoring=scoring, n_jobs=1)
    return float(scores.mean()) if higher_is_better else float(-scores.mean())


study = optuna.create_study(
    direction="maximize",
    sampler=optuna.samplers.TPESampler(seed=42),
)
study.optimize(objective, n_trials=n_trials, timeout=300)

best_params = study.best_params
best_value = study.best_value
if not higher_is_better:
    best_value = -best_value

# Re-train tuned model on full data
if "XGB" in winner_class:
    if task_type == "regression":
        tuned_model = xgb.XGBRegressor(**best_params, **_xgb_device, random_state=42, verbosity=0)
    else:
        tuned_model = xgb.XGBClassifier(**best_params, **_xgb_device, random_state=42, verbosity=0)
elif "GradientBoosting" in winner_class:
    if task_type == "regression":
        tuned_model = GradientBoostingRegressor(**best_params, random_state=42)
    else:
        tuned_model = GradientBoostingClassifier(**best_params, random_state=42)
elif "RandomForest" in winner_class:
    if task_type == "regression":
        tuned_model = RandomForestRegressor(**best_params, random_state=42)
    else:
        tuned_model = RandomForestClassifier(**best_params, random_state=42)
elif "Ridge" in winner_class:
    tuned_model = Ridge(**best_params)
else:
    tuned_model = joblib.load("{winner_path}")

tuned_model.fit(X, y)

os.makedirs(artifacts_dir, exist_ok=True)
tuned_path = os.path.join(artifacts_dir, "tuned_model.pkl")
joblib.dump(tuned_model, tuned_path)

RESULT = {{
    "best_params": best_params,
    "tuned_score": best_value,
    "n_trials_completed": len(study.trials),
    "tuned_path": tuned_path,
}}
'''


class TunerAgent(BaseAgent):
    name = "tuner"

    async def run(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        await self._mark_step(run_id, "running")

        winner = state.get("winner_model", "XGBoost")
        await self.emit(run_id, f"Tuning {winner} with Optuna Bayesian search...")

        n_samples = state.get("data_audit", {}).get("shape", [0])[0]
        n_trials = 30 if n_samples < 50000 else 20

        code = TUNING_CODE_TEMPLATE.format(
            enriched_path=state.get("enriched_data_path", ""),
            task_type=state["task_type"],
            primary_metric=state["primary_metric"],
            winner_class=state.get("winner_model_class", "xgb.XGBClassifier"),
            winner_path=state.get("winner_model_path", ""),
            n_trials=n_trials,
        )

        result = await self.execute_code(code, run_id, timeout=400)
        if not result["success"]:
            await self._mark_step(run_id, "failed", result["error"])
            return {"error": f"Tuning failed: {result['error']}", "status": "failed"}

        data = result["result"]
        tuned_score = data["tuned_score"]
        best_params = data["best_params"]

        entry = await self._log_decision(
            run_id=run_id,
            decision=f"Hyperparameter tuning: {winner} tuned score = {tuned_score:.4f}",
            reasoning=(
                f"Optuna Bayesian search with {data['n_trials_completed']} trials. "
                f"Best params: {best_params}. "
                f"Improvement vs pre-tuning: {tuned_score - state.get('current_score', 0):.4f}"
            ),
            result_summary=f"tuned_score={tuned_score:.4f}",
        )

        from app.core import mlflow_tracker as mlflow
        iteration = state.get("iteration", 0)
        mlflow.log_metric("post_tuning_score", tuned_score, step=iteration)
        # Prefix with iteration number — MLflow forbids changing a param's value
        mlflow.log_params({f"i{iteration}_tuned_{k}": str(v) for k, v in best_params.items()})

        await self.emit(
            run_id,
            f"Tuning complete: {tuned_score:.4f} {state['primary_metric']} after {data['n_trials_completed']} trials",
            {"tuned_score": tuned_score, "best_params": best_params},
        )
        await self._mark_step(run_id, "completed")

        existing_log = state.get("decision_log", [])
        existing_cells = state.get("notebook_cells", [])
        iteration = state.get("iteration", 0)
        new_cell = {
            "agent": self.name,
            "title": f"Hyperparameter Tuning — Iteration {iteration + 1}",
            "iteration": iteration + 1,
            "code": code,
            "stdout": result.get("stdout", ""),
            "result_summary": {
                "iteration": iteration + 1,
                "model_tuned": winner,
                "n_trials": data["n_trials_completed"],
                "tuned_score": round(tuned_score, 4),
                "pre_tuning_score": round(
                    state.get("current_score", state.get("baseline_score", 0.0)), 4
                ),
                "improvement": round(
                    tuned_score - state.get("current_score", state.get("baseline_score", 0.0)), 4
                ),
                "best_params": best_params,
            },
        }
        return {
            "tuned_score": tuned_score,
            "best_hyperparams": best_params,
            "tuned_model_path": data["tuned_path"],
            "current_score": tuned_score,
            "prev_score": state.get("current_score", state.get("baseline_score", 0.0)),
            "decision_log": existing_log + [entry],
            "notebook_cells": existing_cells + [new_cell],
        }
