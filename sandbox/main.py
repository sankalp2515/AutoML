import ast
import asyncio
import builtins as _builtins
import contextlib
import io
import multiprocessing as mp
import os
import traceback
from typing import Any

# Spawn (never fork): the historical sandbox deadlock came from fork()ing a
# process that holds threads/locks (uvicorn workers, CUDA). Spawn starts a clean
# interpreter, so each execution is fully isolated.
_MP = mp.get_context("spawn")

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="AutoML Sandbox Executor")

DATA_DIR = os.getenv("DATA_DIR", "/data")

# ── E1 safety: AST screen + restricted globals for LLM-GENERATED code ──────────
# Trusted templates run with full builtins (restricted=False). Generated code runs
# with restricted=True: only whitelisted imports, no os/subprocess/eval/open-escapes.
_IMPORT_WHITELIST = {
    "pandas", "numpy", "sklearn", "xgboost", "scipy", "joblib", "json", "math",
    "re", "datetime", "statistics", "collections", "itertools", "warnings",
    "imblearn", "random", "functools",
}
_BANNED_NAMES = {
    "eval", "exec", "compile", "open", "__import__", "input", "exit", "quit",
    "globals", "vars", "locals", "getattr", "setattr", "delattr", "memoryview",
    "breakpoint", "help", "classmethod", "staticmethod",
}
_BANNED_ATTRS = {
    "system", "popen", "spawn", "fork", "__globals__", "__builtins__",
    "__import__", "__subclasses__", "__bases__", "__mro__", "__class__",
    "__code__", "__dict__", "__getattribute__",
}


def screen_code(code: str) -> str | None:
    """Return an error string if generated code is unsafe, else None."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in _IMPORT_WHITELIST:
                    return f"blocked import: {a.name}"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in _IMPORT_WHITELIST:
                return f"blocked import-from: {node.module}"
        elif isinstance(node, ast.Attribute):
            if node.attr in _BANNED_ATTRS:
                return f"blocked attribute: {node.attr}"
        elif isinstance(node, ast.Name) and node.id in _BANNED_NAMES:
            return f"blocked name: {node.id}"
    return None


def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".")[0] not in _IMPORT_WHITELIST:
        raise ImportError(f"import of {name!r} is not allowed in generated code")
    return _builtins.__import__(name, globals, locals, fromlist, level)


def _restricted_builtins() -> dict:
    safe = {
        k: getattr(_builtins, k) for k in (
            "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
            "frozenset", "int", "isinstance", "issubclass", "len", "list", "map",
            "max", "min", "print", "range", "repr", "reversed", "round", "set",
            "slice", "sorted", "str", "sum", "tuple", "type", "zip", "abs",
            "Exception", "ValueError", "KeyError", "TypeError", "IndexError",
            "RuntimeError", "ZeroDivisionError", "ArithmeticError", "True",
            "False", "None", "format",
        ) if hasattr(_builtins, k)
    }
    safe["__import__"] = _restricted_import
    return safe


class ExecuteRequest(BaseModel):
    code: str
    run_id: str
    timeout: int = 60
    restricted: bool = False   # True → AST-screen + restricted globals (generated code)


class ExecuteResponse(BaseModel):
    success: bool
    result: Any = None
    stdout: str = ""
    error: str = ""


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


def execute_code(code: str, run_id: str, timeout: int, restricted: bool = False) -> dict:
    """Compile + exec the code IN THIS PROCESS. The timeout is enforced by the
    parent (run_isolated kills the worker), so no in-process signal handling is
    needed — which also makes this cross-platform and thread-safe."""
    stdout_buf = io.StringIO()
    safe_globals = _build_safe_globals(run_id)

    if restricted:
        # Screen generated code, then strip full builtins + os before running.
        violation = screen_code(code)
        if violation:
            return {"success": False, "result": None, "stdout": "",
                    "error": f"Blocked by safety screen: {violation}"}
        safe_globals["__builtins__"] = _restricted_builtins()
        safe_globals.pop("os", None)  # generated code gets paths as strings, not the os module

    try:
        with contextlib.redirect_stdout(stdout_buf):
            exec(compile(code, "<agent_code>", "exec"), safe_globals)
        return {
            "success": True,
            "result": safe_globals.get("RESULT"),
            "stdout": stdout_buf.getvalue(),
            "error": "",
        }
    except Exception:
        return {
            "success": False,
            "result": None,
            "stdout": stdout_buf.getvalue(),
            "error": traceback.format_exc(),
        }


def _worker(code: str, run_id: str, timeout: int, restricted: bool, q) -> None:
    """Runs in the spawned child process; ships the result back over the queue."""
    try:
        q.put(execute_code(code, run_id, timeout, restricted))
    except Exception as exc:  # e.g. an unpicklable RESULT
        q.put({"success": False, "result": None, "stdout": "",
               "error": f"worker could not return a result: {exc}"})


def run_isolated(code: str, run_id: str, timeout: int, restricted: bool) -> dict:
    """Execute in a dedicated child process with a HARD wall-clock timeout.

    A runaway loop, a segfault, or an OOM in generated code kills only the child
    — the sandbox service stays up. This is the real boundary for the agentic
    (LLM-written) execution path that Phase 2 makes the norm.
    """
    q = _MP.Queue()
    proc = _MP.Process(target=_worker, args=(code, run_id, timeout, restricted, q))
    proc.start()
    proc.join(timeout)

    if proc.is_alive():
        proc.terminate()
        proc.join(5)
        if proc.is_alive():
            proc.kill()
            proc.join()
        return {"success": False, "result": None, "stdout": "",
                "error": f"Execution timed out after {timeout} seconds (process killed)"}

    try:
        return q.get_nowait()
    except Exception:
        # Process exited without delivering a result — crash / OOM / OS kill.
        return {"success": False, "result": None, "stdout": "",
                "error": f"Worker exited (code {proc.exitcode}) without a result — likely a crash or OOM."}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "sandbox"}


@app.post("/execute", response_model=ExecuteResponse)
async def execute(request: ExecuteRequest) -> ExecuteResponse:
    if not request.code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty")
    if request.timeout < 1 or request.timeout > 600:
        raise HTTPException(status_code=400, detail="Timeout must be between 1 and 600 seconds")

    # Run the (blocking) process-join off the event loop so /health stays
    # responsive and independent executions can proceed concurrently.
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, run_isolated, request.code, request.run_id, request.timeout, request.restricted
    )
    return ExecuteResponse(**result)
