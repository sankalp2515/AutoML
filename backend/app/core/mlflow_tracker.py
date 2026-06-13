import os
from typing import Any

import mlflow

from app.config import settings


def setup_mlflow() -> None:
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)


def start_run(run_id: str, tags: dict[str, str] | None = None) -> str:
    mlflow.set_experiment("automl-orchestrator")
    active_run = mlflow.start_run(
        run_name=run_id,
        tags={"run_id": run_id, **(tags or {})},
    )
    return active_run.info.run_id


def end_run(status: str = "FINISHED") -> None:
    mlflow.end_run(status=status)


def log_params(params: dict[str, Any]) -> None:
    safe = {k: str(v)[:250] for k, v in params.items() if v is not None}
    mlflow.log_params(safe)


def log_metrics(metrics: dict[str, float], step: int | None = None) -> None:
    mlflow.log_metrics({k: v for k, v in metrics.items() if v is not None}, step=step)


def log_metric(key: str, value: float, step: int | None = None) -> None:
    mlflow.log_metric(key, value, step=step)


def log_artifact(local_path: str) -> None:
    """Upload a local file to the MLflow artifact store via HTTP (requires --serve-artifacts)."""
    if not os.path.exists(local_path):
        import logging
        logging.getLogger("mlflow_tracker").warning(
            "log_artifact skipped — file not found: %s", local_path
        )
        return
    try:
        mlflow.log_artifact(local_path)
    except Exception as exc:
        import logging
        logging.getLogger("mlflow_tracker").error(
            "log_artifact failed for %s: %s", local_path, exc
        )


def set_tag(key: str, value: str) -> None:
    mlflow.set_tag(key, value)


def log_dict(data: Any, filename: str) -> None:
    try:
        mlflow.log_dict(data, filename)
    except Exception as exc:
        import logging
        logging.getLogger("mlflow_tracker").error(
            "log_dict failed for %s: %s", filename, exc
        )
