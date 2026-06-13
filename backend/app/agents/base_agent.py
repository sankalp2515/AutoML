import json
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.core import metrics
from app.core.llm import get_llm
from app.core.logging import get_logger
from app.core import mlflow_tracker as mlflow
from app.core.state import AgentState, DecisionLogEntry
from app.database import AsyncSessionLocal
from app.models.run import AgentStep, DecisionLog, Run
from app.redis_client import publish_progress
from app.sandbox.executor import get_executor

# ── Tier-1 self-repair micro-loop ─────────────────────────────────────────────
# When a sandbox execution fails, instead of failing the whole pipeline we ask
# the LLM to revise the AGENT'S DECISION (never to write free code), re-render
# the SAME vetted template with the corrected parameters, and retry. Capped at
# MAX_REPAIRS attempts, after which we fail fast as before. Because repairs stay
# inside the template vocabulary, the sandbox safety model is untouched.
MAX_REPAIRS = 2

REPAIR_SYSTEM_PROMPT = """You are a senior ML engineer debugging a failed pipeline step.

A block of code failed with an error. The code was generated from a FIXED, trusted
template that was parameterized by a set of DECISION PARAMETERS (JSON). You CANNOT
change the code or the template — you can ONLY revise the decision parameters to
avoid the error (e.g. change an encoding strategy, drop an offending column, switch
a model that errored, relax an imputation choice).

You MUST respond with a JSON object containing exactly these keys:
{
  "diagnosis": "<one sentence: what went wrong>",
  "revised_params": { <the SAME keys as the params you were given, with corrected values> },
  "change_summary": "<one sentence: what you changed and why it should fix it>"
}

Rules:
- revised_params MUST contain every key from the original params (keep keys you don't change).
- Make the MINIMAL change that addresses the error. Do not gratuitously alter working choices.
- Stay within the allowed value vocabulary implied by the original values.
"""


class BaseAgent:
    name: str = "base_agent"

    def __init__(self) -> None:
        self.llm = get_llm()
        self.executor = get_executor()
        self._log = get_logger(self.name)
        self._agent_start_time: float = 0.0

    async def run(self, state: AgentState) -> dict[str, Any]:
        raise NotImplementedError

    # ── Instrumented wrappers ─────────────────────────────────────────────────

    async def execute_code(
        self, code: str, run_id: str, timeout: int = 120
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        result = await self.executor.execute(code, run_id, timeout)
        elapsed = time.perf_counter() - t0

        status = "success" if result.get("success") else (
            "timeout" if "timed out" in str(result.get("error", "")) else "error"
        )
        metrics.sandbox_executions_total.labels(status=status).inc()
        metrics.sandbox_duration_seconds.observe(elapsed)

        if not result.get("success"):
            self._log.warning(
                "sandbox_execution_failed",
                run_id=run_id,
                agent=self.name,
                status=status,
                error=str(result.get("error", ""))[:300],
                duration_s=round(elapsed, 2),
            )
        else:
            self._log.debug(
                "sandbox_execution_ok",
                run_id=run_id,
                agent=self.name,
                duration_s=round(elapsed, 2),
            )
        return result

    async def execute_code_with_repair(
        self,
        run_id: str,
        render_fn: Callable[[dict], str],
        params: dict,
        repair_goal: str,
        timeout: int = 120,
        max_repairs: int = MAX_REPAIRS,
    ) -> dict[str, Any]:
        """Execute a templated step with Tier-1 self-repair.

        render_fn(params) -> code string. On failure, the LLM revises `params`
        (same keys) and we re-render + retry, up to `max_repairs` times. The
        returned dict adds: repair_attempts (int), repaired (bool),
        final_params (dict), repair_history (list).
        """
        attempt = 0
        current_params = dict(params)
        repair_history: list[dict] = []

        while True:
            code = render_fn(current_params)
            result = await self.execute_code(code, run_id, timeout)

            if result.get("success"):
                result["repair_attempts"] = attempt
                result["repaired"] = attempt > 0
                result["final_params"] = current_params
                result["repair_history"] = repair_history
                if attempt > 0:
                    metrics.agent_repairs_total.labels(
                        agent_name=self.name, outcome="recovered"
                    ).inc()
                    self._log.info(
                        "self_repair_recovered", run_id=run_id, agent=self.name,
                        attempts=attempt,
                    )
                return result

            if attempt >= max_repairs:
                metrics.agent_repairs_total.labels(
                    agent_name=self.name, outcome="exhausted"
                ).inc()
                self._log.error(
                    "self_repair_exhausted", run_id=run_id, agent=self.name,
                    attempts=attempt, error=str(result.get("error", ""))[:200],
                )
                result["repair_attempts"] = attempt
                result["repaired"] = False
                result["repair_history"] = repair_history
                return result

            # Ask the LLM to revise the decision parameters
            attempt += 1
            error_text = str(result.get("error", ""))[-1500:]  # tail = the actual traceback
            await self.emit(
                run_id,
                f"Step failed — attempting self-repair ({attempt}/{max_repairs})...",
                {"attempt": attempt},
            )
            try:
                revision = await self.llm.complete_json(
                    REPAIR_SYSTEM_PROMPT,
                    f"Goal of this step: {repair_goal}\n\n"
                    f"Decision parameters (JSON):\n{json.dumps(current_params, default=str, indent=2)}\n\n"
                    f"The code failed with this error:\n```\n{error_text}\n```\n\n"
                    f"Return the revised parameters.",
                )
            except Exception as exc:
                self._log.error("self_repair_llm_failed", run_id=run_id,
                                agent=self.name, error=str(exc)[:200])
                result["repair_attempts"] = attempt - 1
                result["repaired"] = False
                result["repair_history"] = repair_history
                return result

            revised = revision.get("revised_params")
            if not isinstance(revised, dict) or set(revised.keys()) != set(current_params.keys()):
                # LLM didn't honor the contract — keep keys it got right, ignore the rest
                if isinstance(revised, dict):
                    current_params = {k: revised.get(k, current_params[k]) for k in current_params}
                else:
                    # Unusable revision; record and let the next loop hit the cap
                    repair_history.append({
                        "attempt": attempt,
                        "diagnosis": revision.get("diagnosis", ""),
                        "change_summary": "LLM returned no usable revised_params",
                    })
                    continue
            else:
                current_params = revised

            repair_history.append({
                "attempt": attempt,
                "diagnosis": revision.get("diagnosis", "")[:300],
                "change_summary": revision.get("change_summary", "")[:300],
            })
            self._log.info(
                "self_repair_attempt", run_id=run_id, agent=self.name,
                attempt=attempt, diagnosis=revision.get("diagnosis", "")[:120],
            )
            # Record the repair as a decision so it appears in the evidence trail
            await self._log_decision(
                run_id=run_id,
                decision=f"Self-repair #{attempt}: {revision.get('change_summary', '')[:160]}",
                reasoning=f"Diagnosis: {revision.get('diagnosis', '')[:300]}",
                result_summary=f"repair attempt {attempt}/{max_repairs}",
            )

    async def emit(self, run_id: str, message: str, data: dict | None = None) -> None:
        payload = {
            "agent": self.name,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        self._log.info("agent_progress", run_id=run_id, agent=self.name, message=message)
        await publish_progress(run_id, payload)

    async def _mark_step(
        self, run_id: str, status: str, error: str | None = None
    ) -> None:
        now = datetime.now(timezone.utc)

        if status == "running":
            self._agent_start_time = time.perf_counter()
            self._log.info("agent_started", run_id=run_id, agent=self.name)
            # Set context so LLM calls know which agent is calling
            self.llm._current_agent = self.name
            self.llm._current_run_id = run_id

        elif status in ("completed", "failed"):
            elapsed = time.perf_counter() - self._agent_start_time
            metrics.agent_runs_total.labels(agent_name=self.name, status=status).inc()
            metrics.agent_duration_seconds.labels(agent_name=self.name).observe(elapsed)

            if status == "completed":
                self._log.info(
                    "agent_completed",
                    run_id=run_id,
                    agent=self.name,
                    duration_s=round(elapsed, 2),
                )
            else:
                self._log.error(
                    "agent_failed",
                    run_id=run_id,
                    agent=self.name,
                    duration_s=round(elapsed, 2),
                    error=error,
                )

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(AgentStep).where(
                    AgentStep.run_id == run_id,
                    AgentStep.agent_name == self.name,
                )
            )
            step = result.scalar_one_or_none()

            if step is None:
                step = AgentStep(
                    run_id=run_id,
                    agent_name=self.name,
                    status=status,
                    started_at=now if status == "running" else None,
                    completed_at=now if status in ("completed", "failed") else None,
                    error_message=error,
                )
                db.add(step)
            else:
                step.status = status
                if status == "running":
                    step.started_at = now
                if status in ("completed", "failed"):
                    step.completed_at = now
                if error:
                    step.error_message = error

            await db.commit()

    async def _log_decision(
        self,
        run_id: str,
        decision: str,
        reasoning: str,
        code_executed: str = "",
        result_summary: str = "",
    ) -> DecisionLogEntry:
        now = datetime.now(timezone.utc)
        self._log.info(
            "decision",
            run_id=run_id,
            agent=self.name,
            decision=decision[:120],
            result=result_summary,
        )
        async with AsyncSessionLocal() as db:
            log = DecisionLog(
                run_id=run_id,
                agent_name=self.name,
                timestamp=now,
                decision=decision,
                reasoning=reasoning,
                code_executed=code_executed,
                result_summary=result_summary,
            )
            db.add(log)
            await db.commit()

        return DecisionLogEntry(
            agent=self.name,
            timestamp=now.isoformat(),
            decision=decision,
            reasoning=reasoning,
            code_executed=code_executed,
            result_summary=result_summary,
        )

    async def _update_run_field(self, run_id: str, **fields: Any) -> None:
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Run).where(Run.id == run_id))
            run = result.scalar_one_or_none()
            if run:
                for key, value in fields.items():
                    setattr(run, key, value)
                await db.commit()
