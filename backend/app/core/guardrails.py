"""Guardrails — validate inputs INTO the system and decisions OUT of the LLM.

The pipeline trusts LLM output as *decisions* (per the doctrine), but a malformed
decision can poison the whole run (e.g. a metric that doesn't exist for the task
→ silent NaN scorer; an out-of-range threshold → crash). These guardrails clamp
LLM output to valid values BEFORE it flows downstream, and sanitize free-text user
input. They never raise — they FIX and report, so the run continues safely.
"""

from __future__ import annotations

from app.core import metric_registry

_VALID_TASKS = {
    "binary_classification", "multiclass_classification",
    "multilabel_classification", "regression",
}
_MAX_GOAL_LEN = 2000


def sanitize_user_goal(goal: str) -> str:
    """Strip control characters (keep newlines/tabs), collapse whitespace, cap length.
    Defends against junk/binary paste and absurdly long prompts inflating tokens."""
    if not goal:
        return ""
    cleaned = "".join(c for c in goal if c in ("\n", "\t") or ord(c) >= 32)
    cleaned = " ".join(cleaned.split())
    return cleaned[:_MAX_GOAL_LEN]


def validate_and_fix_framing(framing: dict, columns: list[str]) -> tuple[dict, list[str]]:
    """Clamp the problem-framer's output to valid values. Returns (fixed, notes).

    - task_type must be one of the known tasks (else → binary_classification)
    - primary_metric must be valid FOR that task (else → the task's default scorer)
    - good_enough_threshold must be in [0, 1] (else → 0.8)
    - target_column should exist in the dataset (reported; not auto-fixed)
    """
    f = dict(framing)
    notes: list[str] = []

    task = f.get("task_type")
    if task not in _VALID_TASKS:
        notes.append(f"task_type '{task}' is invalid → defaulting to binary_classification")
        task = "binary_classification"
        f["task_type"] = task

    metric = f.get("primary_metric")
    if metric not in metric_registry.allowed_for(task):
        fixed = metric_registry.default_for(task)
        notes.append(f"primary_metric '{metric}' is not valid for {task} → {fixed}")
        f["primary_metric"] = fixed

    th = f.get("good_enough_threshold")
    if not isinstance(th, (int, float)) or isinstance(th, bool) or not (0.0 <= float(th) <= 1.0):
        notes.append(f"good_enough_threshold '{th}' out of [0,1] → 0.8")
        f["good_enough_threshold"] = 0.8

    tgt = f.get("target_column")
    if task != "multilabel_classification" and columns and tgt not in columns:
        # Can't safely guess the target — surface it loudly; baseline will error clearly.
        notes.append(f"target_column '{tgt}' was not found in dataset columns {columns[:8]}")

    return f, notes
