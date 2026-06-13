"""
LLM client with rate-limit resilience.

Strategy:
  1. RETRY    — each provider gets up to 3 attempts with exponential backoff
                (honours Retry-After on 429s).
  2. FALLBACK — if a provider exhausts its retries, the next provider in the
                chain takes over: groq → gemini → openrouter → deepseek → ollama.
                Providers without an API key configured are skipped automatically.

All providers speak the OpenAI chat-completions dialect (Gemini and Ollama both
expose OpenAI-compatible endpoints), so one HTTP code path serves every provider.
Anthropic is also supported via its native SDK when configured.

Every call is instrumented: tokens, latency, estimated cost, and WHICH provider
actually answered — persisted to the llm_calls table and Prometheus.
"""

import asyncio
import json
import random
import re
import time
from typing import Any

import httpx

from app.config import settings
from app.core.logging import get_logger

_log = get_logger("llm")

# Approximate cost per 1M tokens (USD). Free tiers = $0.
_COST_PER_1M = {
    "llama-3.3-70b-versatile": {"prompt": 0.0, "completion": 0.0},
    "gemini-3.1-flash-lite": {"prompt": 0.0, "completion": 0.0},
    "deepseek-chat": {"prompt": 0.27, "completion": 1.10},
    "claude-opus-4-8": {"prompt": 15.0, "completion": 75.0},
    "claude-sonnet-4-6": {"prompt": 3.0, "completion": 15.0},
    "claude-haiku-4-5-20251001": {"prompt": 0.25, "completion": 1.25},
}

_MAX_RETRIES_PER_PROVIDER = 3
_BACKOFF_BASE_S = 1.2
_BACKOFF_CAP_S = 20.0
# Groq free tier = 12K tokens/MINUTE — a 429's Retry-After is often 30-60s.
# Waiting it out beats burning the retry budget and falling back prematurely.
_RETRY_AFTER_CAP_S = 75.0


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = _COST_PER_1M.get(model, {"prompt": 0.0, "completion": 0.0})
    return (prompt_tokens * pricing["prompt"] + completion_tokens * pricing["completion"]) / 1_000_000


class _Provider:
    """One OpenAI-compatible provider in the fallback chain."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str,
                 supports_json_mode: bool = True) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.supports_json_mode = supports_json_mode

    @property
    def configured(self) -> bool:
        # Ollama needs no key — a URL is enough
        return bool(self.api_key) or self.name == "ollama"

    async def chat(self, system: str, user: str, temperature: float,
                   max_tokens: int) -> tuple[str, int, int]:
        """One HTTP attempt. Returns (text, prompt_tokens, completion_tokens)."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.name == "openrouter":
            headers["HTTP-Referer"] = "http://localhost:3002"
            headers["X-Title"] = "AutoML Orchestrator"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.supports_json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", headers=headers, json=payload
            )

        if resp.status_code != 200:
            raise _ProviderHTTPError(resp.status_code, resp.text[:300], resp.headers.get("retry-after"))

        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        return (
            text,
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
        )


class _ProviderHTTPError(Exception):
    def __init__(self, status: int, body: str, retry_after: str | None = None):
        self.status = status
        self.retry_after = retry_after
        super().__init__(f"HTTP {status}: {body}")

    @property
    def retryable(self) -> bool:
        return self.status == 429 or self.status >= 500


def _build_chain() -> list[_Provider]:
    """Build the fallback chain from settings; unconfigured providers are skipped."""
    catalog = {
        "groq": _Provider(
            "groq", "https://api.groq.com/openai/v1",
            settings.GROQ_API_KEY, settings.GROQ_MODEL,
        ),
        "gemini": _Provider(
            "gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
            settings.GEMINI_API_KEY, settings.GEMINI_MODEL,
        ),
        "openrouter": _Provider(
            "openrouter", "https://openrouter.ai/api/v1",
            settings.OPENROUTER_API_KEY, settings.OPENROUTER_MODEL,
        ),
        "deepseek": _Provider(
            "deepseek", "https://api.deepseek.com",
            settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_MODEL,
        ),
        "ollama": _Provider(
            "ollama", f"{settings.OLLAMA_URL}/v1",
            "", settings.OLLAMA_MODEL,
            supports_json_mode=False,  # older ollama versions reject response_format
        ),
    }
    chain = []
    for name in [p.strip().lower() for p in settings.LLM_FALLBACK_CHAIN.split(",") if p.strip()]:
        provider = catalog.get(name)
        if provider and provider.configured:
            chain.append(provider)
    return chain


class LLMClient:
    def __init__(self) -> None:
        self.chain = _build_chain()
        if not self.chain and not settings.ANTHROPIC_API_KEY:
            raise ValueError(
                "No LLM provider configured. Set at least one of: GROQ_API_KEY, "
                "GEMINI_API_KEY, OPENROUTER_API_KEY, DEEPSEEK_API_KEY, or run Ollama."
            )
        # Backward-compat: report the head of the chain
        self.provider = self.chain[0].name if self.chain else "anthropic"
        self.model = self.chain[0].model if self.chain else settings.ANTHROPIC_MODEL

        # Populated by BaseAgent before each call so we know which agent is calling
        self._current_agent: str = "unknown"
        self._current_run_id: str | None = None

    # ── Core call with retry + fallback ──────────────────────────────────────

    async def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        last_error: Exception | None = None

        for provider in self.chain:
            for attempt in range(1, _MAX_RETRIES_PER_PROVIDER + 1):
                t0 = time.perf_counter()
                try:
                    text, p_tok, c_tok = await provider.chat(system, user, temperature, max_tokens)
                    await self._record(provider.name, provider.model, p_tok, c_tok,
                                       time.perf_counter() - t0)
                    return text

                except _ProviderHTTPError as exc:
                    last_error = exc
                    if not exc.retryable:
                        _log.warning("llm_provider_rejected", provider=provider.name,
                                     status=exc.status, agent=self._current_agent)
                        break  # bad key / bad request — move to next provider now
                    if attempt < _MAX_RETRIES_PER_PROVIDER:
                        delay = self._backoff_delay(attempt, exc.retry_after)
                        _log.warning("llm_rate_limited_retrying", provider=provider.name,
                                     attempt=attempt, delay_s=round(delay, 1),
                                     agent=self._current_agent)
                        await asyncio.sleep(delay)

                except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
                    last_error = exc
                    if attempt < _MAX_RETRIES_PER_PROVIDER:
                        delay = self._backoff_delay(attempt)
                        _log.warning("llm_network_error_retrying", provider=provider.name,
                                     attempt=attempt, error=str(exc)[:120])
                        await asyncio.sleep(delay)

            _log.error("llm_provider_exhausted_falling_back", provider=provider.name,
                       agent=self._current_agent)

        # Anthropic as the final resort if configured (native SDK, not OpenAI-compatible)
        if settings.ANTHROPIC_API_KEY:
            try:
                return await self._anthropic_complete(system, user, temperature, max_tokens)
            except Exception as exc:
                last_error = exc

        tried = ", ".join(p.name for p in self.chain) or "none"
        raise RuntimeError(
            f"All LLM providers failed (tried: {tried}). "
            f"Add GEMINI_API_KEY / OPENROUTER_API_KEY / DEEPSEEK_API_KEY to .env, "
            f"or start Ollama. Last error: {str(last_error)[:200]}"
        )

    @staticmethod
    def _backoff_delay(attempt: int, retry_after: str | None = None) -> float:
        # An explicit Retry-After is authoritative — honour it (within reason)
        # so per-minute token limits recover instead of exhausting retries.
        if retry_after:
            try:
                return min(float(retry_after) + 1.0, _RETRY_AFTER_CAP_S)
            except ValueError:
                pass
        return min(_BACKOFF_BASE_S * (2 ** (attempt - 1)) + random.uniform(0, 0.5), _BACKOFF_CAP_S)

    async def _anthropic_complete(self, system: str, user: str,
                                  temperature: float, max_tokens: int) -> str:
        from anthropic import AsyncAnthropic
        t0 = time.perf_counter()
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = response.content[0].text
        p_tok = response.usage.input_tokens or 0
        c_tok = response.usage.output_tokens or 0
        await self._record("anthropic", settings.ANTHROPIC_MODEL, p_tok, c_tok,
                           time.perf_counter() - t0)
        return text

    # ── Instrumentation ───────────────────────────────────────────────────────

    async def _record(self, provider: str, model: str, prompt_tokens: int,
                      completion_tokens: int, latency_s: float) -> None:
        from app.core import metrics
        agent = self._current_agent

        metrics.llm_calls_total.labels(agent_name=agent, provider=provider).inc()
        metrics.llm_tokens_total.labels(agent_name=agent, direction="prompt").inc(prompt_tokens)
        metrics.llm_tokens_total.labels(agent_name=agent, direction="completion").inc(completion_tokens)
        metrics.llm_latency_seconds.labels(agent_name=agent).observe(latency_s)
        cost = _estimate_cost(model, prompt_tokens, completion_tokens)
        if cost > 0:
            metrics.llm_cost_usd_total.labels(agent_name=agent).inc(cost)

        if self._current_run_id:
            await _persist_llm_call(
                run_id=self._current_run_id,
                agent_name=agent,
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=round(latency_s * 1000, 1),
                estimated_cost_usd=cost,
            )

    # ── JSON helpers (unchanged contract) ─────────────────────────────────────

    async def complete_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        raw = await self.complete(system, user, temperature, max_tokens)
        return self._parse_json(raw)

    def _parse_json(self, raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
            if match:
                return json.loads(match.group(1))
            # last resort: first {...} block (Ollama without JSON mode)
            match = re.search(r"\{[\s\S]+\}", raw)
            if match:
                return json.loads(match.group(0))
            raise ValueError(f"LLM did not return valid JSON:\n{raw[:500]}")


async def _persist_llm_call(
    run_id: str,
    agent_name: str,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
    estimated_cost_usd: float,
) -> None:
    try:
        from app.database import AsyncSessionLocal
        from app.models.run import LLMCall

        async with AsyncSessionLocal() as db:
            call = LLMCall(
                run_id=run_id,
                agent_name=agent_name,
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                latency_ms=latency_ms,
                estimated_cost_usd=estimated_cost_usd,
            )
            db.add(call)
            await db.commit()
    except Exception:
        pass  # never crash the pipeline on observability writes


_llm_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
