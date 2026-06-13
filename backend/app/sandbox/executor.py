from typing import Any

import httpx

from app.config import settings


class SandboxExecutor:
    def __init__(self, base_url: str = settings.SANDBOX_URL) -> None:
        self.base_url = base_url

    async def execute(
        self,
        code: str,
        run_id: str,
        timeout: int = settings.SANDBOX_TIMEOUT,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout + 10) as client:
            response = await client.post(
                f"{self.base_url}/execute",
                json={"code": code, "run_id": run_id, "timeout": timeout},
            )
            response.raise_for_status()
            return response.json()

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception:
            return False


_executor: SandboxExecutor | None = None


def get_executor() -> SandboxExecutor:
    global _executor
    if _executor is None:
        _executor = SandboxExecutor()
    return _executor
