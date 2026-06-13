import contextlib
import io
import os
import signal
import traceback
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="AutoML Sandbox Executor")

DATA_DIR = os.getenv("DATA_DIR", "/data")


class ExecuteRequest(BaseModel):
    code: str
    run_id: str
    timeout: int = 60


class ExecuteResponse(BaseModel):
    success: bool
    result: Any = None
    stdout: str = ""
    error: str = ""


class _Timeout(Exception):
    pass


def _timeout_handler(signum: int, frame: Any) -> None:
    raise _Timeout()


def _build_safe_globals(run_id: str) -> dict:
    import pandas as pd
    import numpy as np
    import json as json_mod
    import joblib
    import os as os_mod

    dataset_path = os_mod.path.join(DATA_DIR, run_id, "dataset.csv")
    artifacts_dir = os_mod.path.join(DATA_DIR, run_id, "artifacts")
    os_mod.makedirs(artifacts_dir, exist_ok=True)

    return {
        "__builtins__": __builtins__,
        "pd": pd,
        "np": np,
        "json": json_mod,
        "joblib": joblib,
        "os": os_mod,
        "dataset_path": dataset_path,
        "artifacts_dir": artifacts_dir,
        "run_id": run_id,
        "target_column": "",
        "RESULT": None,
    }


def execute_code(code: str, run_id: str, timeout: int) -> dict:
    stdout_buf = io.StringIO()
    safe_globals = _build_safe_globals(run_id)

    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout)

    try:
        with contextlib.redirect_stdout(stdout_buf):
            exec(compile(code, "<agent_code>", "exec"), safe_globals)
        signal.alarm(0)
        return {
            "success": True,
            "result": safe_globals.get("RESULT"),
            "stdout": stdout_buf.getvalue(),
            "error": "",
        }
    except _Timeout:
        return {
            "success": False,
            "result": None,
            "stdout": stdout_buf.getvalue(),
            "error": f"Execution timed out after {timeout} seconds",
        }
    except Exception:
        return {
            "success": False,
            "result": None,
            "stdout": stdout_buf.getvalue(),
            "error": traceback.format_exc(),
        }
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "sandbox"}


@app.post("/execute", response_model=ExecuteResponse)
async def execute(request: ExecuteRequest) -> ExecuteResponse:
    if not request.code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty")
    if request.timeout < 1 or request.timeout > 600:
        raise HTTPException(status_code=400, detail="Timeout must be between 1 and 600 seconds")

    result = execute_code(request.code, request.run_id, request.timeout)
    return ExecuteResponse(**result)
