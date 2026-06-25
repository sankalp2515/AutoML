import os
import shutil
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.auth import current_tenant
from app.core.job_queue import submit_run
from app.core.logging import get_logger
from app.database import get_db
from app.models.run import LLMCall, Run

_log = get_logger("runs")
from app.schemas.run import CreateRunRequest, RunDetailOut, RunListOut, RunOut, ResultsOut
from app.redis_client import get_run_state

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


async def _save_dataset(file: UploadFile, run_id: str) -> str:
    run_dir = os.path.join(settings.DATA_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)
    dest = os.path.join(run_dir, "dataset.csv")
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return dest


@router.post("", response_model=RunOut, status_code=201)
async def create_run(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_goal: str = Form(..., min_length=10),
    exclude_columns: str = Form(default=""),
    fp_fn_preference: str = Form(default=""),
    interpretability_required: bool = Form(default=False),
    pipeline: str = Form(default="tabular"),
    db: AsyncSession = Depends(get_db),
    tenant: str = Depends(current_tenant),
) -> RunOut:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    if pipeline not in ("tabular", "timeseries"):
        raise HTTPException(status_code=400, detail="pipeline must be 'tabular' or 'timeseries'")

    if file.size and file.size > 500 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 500MB limit")

    # Per-tenant concurrency quota (0 = unlimited).
    if settings.QUOTA_MAX_ACTIVE_RUNS_PER_TENANT:
        active = await db.execute(
            select(func.count()).select_from(Run).where(
                Run.tenant_id == tenant, Run.status.in_(("queued", "running"))
            )
        )
        if (active.scalar() or 0) >= settings.QUOTA_MAX_ACTIVE_RUNS_PER_TENANT:
            raise HTTPException(
                status_code=429,
                detail=f"Active-run quota reached ({settings.QUOTA_MAX_ACTIVE_RUNS_PER_TENANT}). "
                       "Wait for a run to finish.",
            )

    # Per-tenant cumulative LLM-cost budget (0 = unlimited).
    if settings.TENANT_BUDGET_USD and settings.TENANT_BUDGET_USD > 0:
        spent = await db.execute(
            select(func.coalesce(func.sum(LLMCall.estimated_cost_usd), 0.0))
            .select_from(LLMCall).join(Run, LLMCall.run_id == Run.id)
            .where(Run.tenant_id == tenant)
        )
        if float(spent.scalar() or 0.0) >= settings.TENANT_BUDGET_USD:
            raise HTTPException(
                status_code=402,
                detail=f"LLM budget of ${settings.TENANT_BUDGET_USD} reached for this tenant.",
            )

    # Guardrail: sanitize free-text goal + scan/neutralize prompt injection.
    from app.core.guardrails import sanitize_user_goal, neutralize_injection
    user_goal = sanitize_user_goal(user_goal)
    user_goal, injection_flags = neutralize_injection(user_goal)
    if injection_flags:
        if settings.INJECTION_GUARD_STRICT:
            raise HTTPException(status_code=400, detail="Goal rejected: prompt-injection detected.")
        _log.warning("prompt_injection_neutralized", flags=injection_flags)
    if len(user_goal) < 10:
        raise HTTPException(status_code=422, detail="user_goal too short after sanitization")

    run_id = str(uuid.uuid4())
    dataset_path = await _save_dataset(file, run_id)

    # Guardrail: reject absurdly wide CSVs (column count) before any agent runs.
    if settings.MAX_DATASET_COLUMNS:
        try:
            with open(dataset_path, "r", encoding="utf-8", errors="ignore") as fh:
                header = fh.readline()
            n_cols = header.count(",") + 1 if header else 0
            if n_cols > settings.MAX_DATASET_COLUMNS:
                os.remove(dataset_path)
                raise HTTPException(
                    status_code=400,
                    detail=f"Dataset has {n_cols} columns; max is {settings.MAX_DATASET_COLUMNS}.",
                )
        except HTTPException:
            raise
        except OSError:
            pass  # unreadable header — let the auditor surface it

    exclude_list = [c.strip() for c in exclude_columns.split(",") if c.strip()]

    run = Run(
        id=run_id,
        status="queued",
        tenant_id=tenant,
        dataset_filename=file.filename,
        dataset_path=dataset_path,
        user_goal=user_goal,
        exclude_columns=exclude_list,
        fp_fn_preference=fp_fn_preference or None,
        interpretability_required=interpretability_required,
        pipeline=pipeline,
    )
    db.add(run)
    await db.flush()

    # Durable queue when enabled, else in-process background task.
    await submit_run(run_id, background_tasks)

    return RunOut.model_validate(run)


@router.get("", response_model=RunListOut)
async def list_runs(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    tenant: str = Depends(current_tenant),
) -> RunListOut:
    result = await db.execute(
        select(Run).where(Run.tenant_id == tenant)
        .order_by(Run.created_at.desc()).offset(skip).limit(limit)
    )
    runs = result.scalars().all()
    total_result = await db.execute(
        select(func.count()).select_from(Run).where(Run.tenant_id == tenant)
    )
    total = total_result.scalar() or 0
    return RunListOut(runs=[RunOut.model_validate(r) for r in runs], total=total)


@router.get("/{run_id}", response_model=RunDetailOut)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)) -> RunDetailOut:
    result = await db.execute(
        select(Run)
        .where(Run.id == run_id)
        .options(
            selectinload(Run.agent_steps),
            selectinload(Run.decision_logs),
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunDetailOut.model_validate(run)


@router.get("/{run_id}/results", response_model=ResultsOut)
async def get_results(run_id: str, db: AsyncSession = Depends(get_db)) -> ResultsOut:
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status not in ("completed", "failed"):
        raise HTTPException(status_code=409, detail=f"Run is still {run.status}")

    state = await get_run_state(run_id)

    return ResultsOut(
        run_id=run_id,
        task_type=run.task_type,
        target_column=run.target_column,
        primary_metric=run.primary_metric,
        baseline_score=run.baseline_score,
        final_score=run.final_score,
        winner_model=run.winner_model,
        iteration_count=run.iteration_count,
        evaluation_report=state.get("evaluation_report") if state else None,
        shap_top_features=state.get("shap_top_features") if state else None,
        artifact_paths=state.get("artifact_paths") if state else None,
    )
