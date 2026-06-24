"""Single source of truth for evaluation metrics.

Doctrine (docs/analysis/11-dynamic-doctrine.md): the *choice* of metric is an ML
DECISION the LLM makes; how a chosen metric maps to an sklearn scorer is a
MECHANIC that lives in code. This registry is that mechanic — and it replaces the
metric vocabulary that used to be hand-typed in the problem-framer prompt AND
duplicated across the baseline/model_selector/tuner/feature_engineer/evaluator
scoring maps (a documented source of drift bugs).

The framer's allowed-metric menu is now DERIVED from this registry, so adding a
metric is a one-line registry change — never a prompt edit. Mirrors model_registry.
"""

from __future__ import annotations

# metric_id → spec. `sklearn` is the base scorer; `multiclass` overrides it for
# multiclass tasks (binary-only scorers silently NaN otherwise — a real bug we hit).
# `tasks` is the set of task_types the metric is OFFERED for (the framer menu).
# `higher_is_better=False` marks "lower is better" metrics (error/loss).
_METRICS: dict[str, dict] = {
    "auc_roc":      {"sklearn": "roc_auc",  "multiclass": "roc_auc_ovr_weighted", "tasks": {"binary_classification"}, "higher_is_better": True},
    "pr_auc":       {"sklearn": "average_precision", "multiclass": "average_precision", "tasks": {"binary_classification"}, "higher_is_better": True},
    "recall":       {"sklearn": "recall",    "multiclass": "recall_weighted",    "tasks": {"binary_classification"}, "higher_is_better": True},
    "precision":    {"sklearn": "precision", "multiclass": "precision_weighted", "tasks": {"binary_classification"}, "higher_is_better": True},
    "f1":           {"sklearn": "f1",        "multiclass": "f1_weighted",        "tasks": {"binary_classification", "multiclass_classification"}, "higher_is_better": True},
    "accuracy":     {"sklearn": "accuracy",  "multiclass": "accuracy",           "tasks": {"binary_classification", "multiclass_classification"}, "higher_is_better": True},
    "rmse":         {"sklearn": "neg_root_mean_squared_error", "multiclass": None, "tasks": {"regression"}, "higher_is_better": False},
    "mae":          {"sklearn": "neg_mean_absolute_error",     "multiclass": None, "tasks": {"regression"}, "higher_is_better": False},
    "r2":           {"sklearn": "r2",         "multiclass": None,                "tasks": {"regression"}, "higher_is_better": True},
    "f1_micro":     {"sklearn": "f1_micro",   "multiclass": None,                "tasks": {"multilabel_classification"}, "higher_is_better": True},
    "f1_macro":     {"sklearn": "f1_macro",   "multiclass": None,                "tasks": {"multilabel_classification"}, "higher_is_better": True},
    "f1_samples":   {"sklearn": "f1_samples", "multiclass": None,                "tasks": {"multilabel_classification"}, "higher_is_better": True},
    "hamming_loss": {"sklearn": "hamming_loss", "multiclass": None,              "tasks": {"multilabel_classification"}, "higher_is_better": False},
}

# The default the framer should pick when the goal gives no strong signal.
_DEFAULT_BY_TASK = {
    "regression": "rmse",
    "multiclass_classification": "f1",       # → f1_weighted scorer
    "multilabel_classification": "f1_micro",
    "binary_classification": "auc_roc",
}


def all_metrics() -> list[str]:
    return list(_METRICS)


def allowed_for(task_type: str) -> list[str]:
    """Metrics offered to the LLM for a task (the framer menu)."""
    return [m for m, spec in _METRICS.items() if task_type in spec["tasks"]]


def default_for(task_type: str) -> str:
    return _DEFAULT_BY_TASK.get(task_type, "f1")


def higher_is_better(metric: str) -> bool:
    spec = _METRICS.get(metric)
    return True if spec is None else spec["higher_is_better"]


def sklearn_scorer(metric: str, task_type: str) -> str:
    """The sklearn scoring string for a (metric, task) — applies the multiclass
    remap so binary-only scorers don't silently NaN on multiclass."""
    spec = _METRICS.get(metric)
    if spec is None:
        return default_scorer(task_type)
    if task_type == "multiclass_classification" and spec.get("multiclass"):
        return spec["multiclass"]
    return spec["sklearn"]


def default_scorer(task_type: str) -> str:
    return sklearn_scorer(default_for(task_type), task_type)


def framer_menu_text() -> str:
    """Per-task allowed-metric menu injected into the problem-framer prompt, so
    the vocabulary is never hand-typed/duplicated in the prompt."""
    lines = []
    for task in ("binary_classification", "multiclass_classification",
                 "multilabel_classification", "regression"):
        allowed = " | ".join(allowed_for(task))
        lines.append(f"- {task}: {allowed} (default: {default_for(task)})")
    return "\n".join(lines)
