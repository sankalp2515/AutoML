"""Phase 0.2 — honest evaluation: carve a true holdout up front.

Runs right after problem framing (target/task known) and BEFORE any agent
fits, selects features, picks a model, or tunes. It physically splits the raw
dataset into ``train.csv`` (the working set every downstream agent reads) and
``holdout.csv`` (never seen until the evaluator scores it). Because every
downstream agent reads ``dataset_path``, simply repointing it at ``train.csv``
makes the entire pipeline train-only with no template changes — eliminating the
selection/tuning leakage that made the old "holdout" inside the evaluator
optimistic.

Doctrine: this is a *mechanic/rail* (how data is partitioned), not an ML
decision — so it lives in code. Time-series uses its own graph + temporal split
and never reaches this node.
"""

from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.state import AgentState

# Below this many rows a 20% holdout is too small to be meaningful — fall back
# to CV-only evaluation (evaluator handles holdout_path == "").
_MIN_ROWS_FOR_HOLDOUT = 60

SPLIT_CODE_TEMPLATE = '''
import pandas as pd
import os
from sklearn.model_selection import train_test_split

df = pd.read_csv(dataset_path)
target_col = __TARGET_COLUMN__
task_type = __TASK_TYPE__
holdout_frac = __HOLDOUT_FRAC__
min_rows = __MIN_ROWS__

run_dir = os.path.dirname(artifacts_dir.rstrip("/"))  # /data/<run_id>
train_path = os.path.join(run_dir, "train.csv")
holdout_path = os.path.join(run_dir, "holdout.csv")

n = len(df)
if n < min_rows:
    # Too small for a trustworthy holdout — keep all rows for training, signal
    # the evaluator to fall back to CV.
    RESULT = {"split": False, "n_total": int(n), "reason": "dataset too small for a holdout"}
else:
    # Stratify only for single-label classification with a clean, multi-class
    # target where every class can appear on both sides.
    stratify = None
    if task_type in ("binary_classification", "multiclass_classification") and target_col in df.columns:
        yv = df[target_col]
        vc = yv.value_counts(dropna=True)
        if len(vc) > 1 and int(vc.min()) >= 2 and bool(yv.notna().all()):
            stratify = yv
    try:
        train_df, holdout_df = train_test_split(
            df, test_size=holdout_frac, random_state=42, stratify=stratify
        )
    except Exception:
        train_df, holdout_df = train_test_split(
            df, test_size=holdout_frac, random_state=42
        )
    train_df.to_csv(train_path, index=False)
    holdout_df.to_csv(holdout_path, index=False)
    RESULT = {
        "split": True,
        "train_path": train_path,
        "holdout_path": holdout_path,
        "n_train": int(len(train_df)),
        "n_holdout": int(len(holdout_df)),
        "stratified": stratify is not None,
    }
'''


class DataSplitterAgent(BaseAgent):
    name = "data_splitter"

    async def run(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        await self._mark_step(run_id, "running")
        await self.emit(run_id, "Reserving a held-out test set before any fitting — honest evaluation...")

        holdout_frac = float(state.get("holdout_frac") or 0.2)
        code = (
            SPLIT_CODE_TEMPLATE
            .replace("__TARGET_COLUMN__", repr(state.get("target_column", "")))
            .replace("__TASK_TYPE__", repr(state.get("task_type", "")))
            .replace("__HOLDOUT_FRAC__", repr(holdout_frac))
            .replace("__MIN_ROWS__", repr(_MIN_ROWS_FOR_HOLDOUT))
        )

        result = await self.execute_code(code, run_id, timeout=120)
        if not result["success"]:
            # A split failure must not kill the run — degrade to CV-only eval.
            self._log.warning("holdout_split_failed", run_id=run_id,
                              error=str(result.get("error", ""))[:200])
            await self._mark_step(run_id, "completed")
            return {"holdout_path": "", "holdout_frac": 0.0}

        data = result["result"] or {}
        if not data.get("split"):
            await self._log_decision(
                run_id=run_id,
                decision="No holdout reserved — dataset too small; evaluation falls back to cross-validation",
                reasoning=f"{data.get('n_total', '?')} rows < {_MIN_ROWS_FOR_HOLDOUT} minimum. "
                          "A 20% holdout would be too small to estimate generalization reliably.",
                result_summary="evaluation_basis=cv",
            )
            await self.emit(run_id, "Dataset too small for a holdout — using cross-validation for the final score.")
            await self._mark_step(run_id, "completed")
            return {"holdout_path": "", "holdout_frac": 0.0}

        entry = await self._log_decision(
            run_id=run_id,
            decision=(
                f"Reserved a {int(holdout_frac*100)}% holdout: "
                f"{data['n_train']} train / {data['n_holdout']} holdout "
                f"({'stratified' if data['stratified'] else 'random'})"
            ),
            reasoning=(
                "The holdout is split from the RAW data before preprocessing, feature "
                "selection, model selection, and tuning — so the final score reported on it "
                "is an unbiased generalization estimate, not the selection CV."
            ),
            code_executed=code[:300],
            result_summary=f"train={data['n_train']}, holdout={data['n_holdout']}",
        )
        await self.emit(
            run_id,
            f"Holdout reserved: {data['n_train']} train / {data['n_holdout']} held out.",
            {"n_train": data["n_train"], "n_holdout": data["n_holdout"]},
        )
        await self._mark_step(run_id, "completed")

        # Repoint dataset_path at the train split — every downstream agent now
        # reads train-only data automatically.
        return {
            "dataset_path": data["train_path"],
            "holdout_path": data["holdout_path"],
            "holdout_frac": holdout_frac,
            "decision_log": state.get("decision_log", []) + [entry],
        }
