"""
Central model registry — the single SOURCE the model-scout retrieves from.

Adding a model = one entry here. No hardcoded menu in prompts, no if/elif search
spaces in the tuner. The model_selector builds its candidate menu from
`catalog_for(task)`, and the tuner reads `search_space_for(class_str)`.

SAFETY: only models whose library is actually installed in the SANDBOX image can
train (`installed=True`). Entries with `installed=False` are *recommendations* the
scout may surface (with an install hint) but never trains — we never execute
code for an uninstalled/web-fetched library against the user's mounted data.
"""

from typing import Any

# Search-space spec grammar (consumed generically by the tuner's Optuna objective):
#   {"type": "int", "low": int, "high": int}
#   {"type": "float", "low": float, "high": float, "log": bool}
#   {"type": "categorical", "choices": [...]}

_XGB_SPACE = {
    "n_estimators": {"type": "int", "low": 100, "high": 500},
    "learning_rate": {"type": "float", "low": 0.01, "high": 0.3, "log": True},
    "max_depth": {"type": "int", "low": 3, "high": 10},
    "subsample": {"type": "float", "low": 0.6, "high": 1.0},
    "colsample_bytree": {"type": "float", "low": 0.6, "high": 1.0},
    "reg_alpha": {"type": "float", "low": 1e-8, "high": 10.0, "log": True},
    "reg_lambda": {"type": "float", "low": 1e-8, "high": 10.0, "log": True},
}
_GB_SPACE = {
    "n_estimators": {"type": "int", "low": 50, "high": 300},
    "learning_rate": {"type": "float", "low": 0.01, "high": 0.3, "log": True},
    "max_depth": {"type": "int", "low": 2, "high": 8},
    "subsample": {"type": "float", "low": 0.6, "high": 1.0},
}
_RF_SPACE = {
    "n_estimators": {"type": "int", "low": 50, "high": 400},
    "max_depth": {"type": "int", "low": 3, "high": 20},
    "min_samples_split": {"type": "int", "low": 2, "high": 20},
    "max_features": {"type": "categorical", "choices": ["sqrt", "log2"]},
}
_HGB_SPACE = {
    "learning_rate": {"type": "float", "low": 0.01, "high": 0.3, "log": True},
    "max_iter": {"type": "int", "low": 100, "high": 400},
    "max_depth": {"type": "int", "low": 3, "high": 12},
    "l2_regularization": {"type": "float", "low": 1e-8, "high": 10.0, "log": True},
}
_LOGREG_SPACE = {
    "C": {"type": "float", "low": 1e-4, "high": 100.0, "log": True},
    "penalty": {"type": "categorical", "choices": ["l1", "l2"]},
}
_RIDGE_SPACE = {"alpha": {"type": "float", "low": 1e-4, "high": 100.0, "log": True}}
# Deep MLP: tune the scalar training knobs Optuna handles cleanly; architecture
# (hidden_dims) stays at a sensible default for DL-0 (architecture search is a later step).
_TORCHMLP_SPACE = {
    "lr": {"type": "float", "low": 1e-4, "high": 1e-2, "log": True},
    "dropout": {"type": "float", "low": 0.0, "high": 0.5},
    "weight_decay": {"type": "float", "low": 1e-6, "high": 1e-3, "log": True},
}

# family → search space (tuner matches winner_class substring to a family)
SEARCH_SPACES: dict[str, dict] = {
    "XGB": _XGB_SPACE, "GradientBoosting": _GB_SPACE, "RandomForest": _RF_SPACE,
    "HistGradientBoosting": _HGB_SPACE, "LogisticRegression": _LOGREG_SPACE,
    "Ridge": _RIDGE_SPACE, "TorchMLP": _TORCHMLP_SPACE,
}

# The registry. `class` maps task family → concrete sklearn/xgb class string.
MODEL_REGISTRY: list[dict[str, Any]] = [
    {
        "name": "XGBoost", "family": "XGB", "installed": True, "gpu": True,
        "class": {"classification": "xgb.XGBClassifier", "regression": "xgb.XGBRegressor"},
        "tasks": ["binary_classification", "multiclass_classification", "regression"],
        "supports_class_weight": False,
        "desc": "Gradient-boosted trees. Strong default; scales to large/wide tabular; GPU-capable.",
    },
    {
        "name": "RandomForest", "family": "RandomForest", "installed": True, "gpu": False,
        "class": {"classification": "RandomForestClassifier", "regression": "RandomForestRegressor"},
        "tasks": ["binary_classification", "multiclass_classification", "regression"],
        "supports_class_weight": True,
        "desc": "Bagged trees. Robust, low-tuning, good on noisy/mixed features.",
    },
    {
        "name": "GradientBoosting", "family": "GradientBoosting", "installed": True, "gpu": False,
        "class": {"classification": "GradientBoostingClassifier", "regression": "GradientBoostingRegressor"},
        "tasks": ["binary_classification", "multiclass_classification", "regression"],
        "supports_class_weight": False,
        "desc": "Classic boosting. Accurate on small/medium data; slower than HistGB/XGB.",
    },
    {
        "name": "HistGradientBoosting", "family": "HistGradientBoosting", "installed": True, "gpu": False,
        "class": {"classification": "HistGradientBoostingClassifier", "regression": "HistGradientBoostingRegressor"},
        "tasks": ["binary_classification", "multiclass_classification", "regression"],
        "supports_class_weight": True,
        "desc": "Histogram boosting (sklearn). Fast on large rows, native NaN handling. Strong all-rounder.",
    },
    {
        "name": "LogisticRegression", "family": "LogisticRegression", "installed": True, "gpu": False,
        "class": {"classification": "LogisticRegression"},
        "tasks": ["binary_classification", "multiclass_classification"],
        "supports_class_weight": True,
        "desc": "Linear, interpretable baseline for classification. Best when interpretability required.",
    },
    {
        "name": "Ridge", "family": "Ridge", "installed": True, "gpu": False,
        "class": {"regression": "Ridge"},
        "tasks": ["regression"],
        "supports_class_weight": False,
        "desc": "Linear, interpretable baseline for regression.",
    },
    {
        "name": "TorchMLP", "family": "TorchMLP", "installed": False, "gpu": True,
        "class": {"classification": "TorchMLPClassifier", "regression": "TorchMLPRegressor"},
        "tasks": ["binary_classification", "multiclass_classification", "regression"],
        "supports_class_weight": False,
        "requires": "torch",
        "desc": "Feed-forward neural net (PyTorch, GPU+AMP). Consider on large, high-signal "
                "datasets where non-linear interactions matter; GBDTs usually win on small tabular.",
    },
    # ── Recommendations (NOT installed — scout may surface with an install hint) ──
    {
        "name": "CatBoost", "family": "CatBoost", "installed": False, "gpu": True,
        "class": {"classification": "CatBoostClassifier", "regression": "CatBoostRegressor"},
        "tasks": ["binary_classification", "multiclass_classification", "regression"],
        "supports_class_weight": True,
        "requires": "catboost",
        "desc": "Boosting with native high-cardinality categorical handling. Often beats XGB on categorical-heavy data.",
    },
    {
        "name": "LightGBM", "family": "LightGBM", "installed": False, "gpu": True,
        "class": {"classification": "LGBMClassifier", "regression": "LGBMRegressor"},
        "tasks": ["binary_classification", "multiclass_classification", "regression"],
        "supports_class_weight": True,
        "requires": "lightgbm",
        "desc": "Very fast leaf-wise boosting for large datasets.",
    },
]


def _task_family(task_type: str) -> str:
    return "regression" if task_type == "regression" else "classification"


def class_for(spec: dict, task_type: str) -> str | None:
    """Resolve a registry entry to its concrete class string for the task."""
    return spec.get("class", {}).get(_task_family(task_type))


def catalog_for(task_type: str, installed_only: bool = True) -> list[dict]:
    """Models that support this task. installed_only=True → trainable now."""
    fam = _task_family(task_type)
    out = []
    for spec in MODEL_REGISTRY:
        if task_type in spec["tasks"] and fam in spec.get("class", {}):
            if installed_only and not spec.get("installed"):
                continue
            out.append(spec)
    return out


def menu_text(task_type: str) -> str:
    """Human-readable menu injected into the model_selector prompt (installed only)."""
    lines = []
    for s in catalog_for(task_type, installed_only=True):
        cls = class_for(s, task_type)
        gpu = " [GPU]" if s.get("gpu") else ""
        cw = " [class_weight]" if s.get("supports_class_weight") else ""
        lines.append(f'- "{cls}" ({s["name"]}){gpu}{cw}: {s["desc"]}')
    return "\n".join(lines)


def recommendations_text(task_type: str) -> str:
    """Not-installed candidates the scout may recommend (advisory; needs sandbox rebuild)."""
    fam = _task_family(task_type)
    recs = [s for s in MODEL_REGISTRY
            if task_type in s["tasks"] and fam in s.get("class", {}) and not s.get("installed")]
    if not recs:
        return ""
    return "\n".join(f'- {s["name"]} (pip: {s.get("requires")}): {s["desc"]}' for s in recs)


def search_space_for(class_str: str) -> dict:
    """Optuna search space for a concrete class string.

    Match by family substring, LONGEST family first — so "HistGradientBoosting"
    wins over "GradientBoosting" (which is a substring of it).
    """
    cs = class_str or ""
    for fam in sorted(SEARCH_SPACES, key=len, reverse=True):
        if fam in cs:
            return SEARCH_SPACES[fam]
    return {}
