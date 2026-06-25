# Design: Self-Debugging Execution Engine + Code Cookbook (non-vector RAG)

> User ask (2026-06-17): build a code-writing/self-debugging engine so agents truly handle
> their own errors — WITHOUT removing templates. Keep proven code in a retrievable store
> ("RAG but not vectors — we don't want hallucination"); the LLM reuses + tweaks it.
> Status: **PLAN — awaiting confirmation before implementation.**

## 1. The idea, precisely

Three layers, composed:
1. **Templates** (the 12 existing `_CODE_TEMPLATE` constants) — the trusted, vetted seed corpus + fallback.
2. **Code Cookbook** — a store of code that has *actually run successfully*, retrieved by **exact tags +
   keyword (BM25) ranking — NO embeddings** (deterministic, auditable, no hallucinated "relevance").
3. **Self-debugging loop** — when no stored code fits, or it fails, the agent (LLM) writes/repairs the
   *actual code*, runs it, reads the traceback, and retries — bounded.

Today: LLM returns JSON decisions → fixed template runs. Edge case the template author didn't foresee →
crash. New engine: LLM can author and debug the code itself, seeded by proven code, fenced by safety.

## 2. Current reality (what we're changing)

- `sandbox/main.py:49` exposes **full `__builtins__`**, and `:54` exposes the **`os` module**.
  Safe for hand-written templates; **dangerous for LLM-generated code** (`os.system`, arbitrary file
  read/write, exfiltration). This is the #1 thing to fix before executing any generated code.
- Agents call `complete_json` (decisions) + `execute_code` / `execute_code_with_repair` (Tier-1: revise
  *params*, re-render the *same* template). Tier-1 cannot author new code paths — that's the ceiling.

## 3. Why non-vector retrieval is correct here

The user's worry is sound. Semantic/vector retrieval returns "plausibly similar" code by cosine distance —
it can surface confidently-wrong snippets (hallucinated relevance) with no explanation. Instead:
- **Structured tag match** (deterministic): each snippet keyed by `agent_role`, `task_type`, and boolean
  data tags (`has_text`, `has_datetime`, `has_missing_target`, `n_classes_bucket`, `multilabel`, …).
- **BM25 keyword rank** over the snippet's problem-signature + code (exact terms, not embeddings).
- Result is auditable: "reused snippet #42 because it matches `agent=preprocessor, task=regression,
  has_datetime=true` and ranked top on keywords {robust_scaler, datetime_expand}." No black-box similarity.

## 4. Architecture

### 4a. Code Cookbook store (Postgres table `code_snippets`)
```
id, agent_role, task_type, tags(JSON list), signature(text),
code(text), result_keys(JSON), provenance("template"|"generated"|"repaired"),
checksum(unique), success_count(int), fail_count(int),
last_used_at, created_at
```
- Seeded from the 12 templates (provenance="template", high trust).
- `retrieve(agent_role, task_type, tags, keywords) -> ranked snippets` = SQL tag filter + in-process BM25.
- `record_success(checksum, code, ...)` upserts; `record_failure` increments fail_count.
- Dedup by checksum; cap top-N per (agent, task, signature) by success_count.

### 4b. Safety gate (NEW — prerequisite for generated code)
- **Hardened sandbox globals**: a *restricted* builtins set (no `eval`/`exec`/`open`/`__import__`
  beyond an allowlist; no `os.system`); whitelist modules (pandas, numpy, sklearn, xgboost, joblib,
  scipy, json, math, re, datetime). Templates may keep the current trusted globals; **generated code
  runs under the restricted globals.**
- **AST screen** before executing generated code: reject `import os/subprocess/socket/sys`, attribute
  access to `system/popen/__globals__/__builtins__`, file `open()` outside `/data/{run_id}`, network libs.
- **Network egress off** for the sandbox container (compose `internal` network / no default route).
- **RESULT contract validation**: generated code must set `RESULT` with the expected `result_keys`;
  reject/repair if missing. Resource caps already exist (SIGALRM timeout, mem limit in compose).
- **Trust tiers**: template → run as-is. cookbook(generated, previously screened, success_count>0) →
  light re-screen. fresh generated → full AST screen + restricted globals.

### 4c. The loop — `BaseAgent.execute_code_agentic(agent_role, task_type, tags, goal, params, result_keys)`
```
1. retrieve top snippets from cookbook (templates included)
2. if a high-trust template/snippet fits → adapt via LLM (or use as-is) 
3. else → LLM WRITES code from scratch (given profile + goal + result_keys contract)
4. AST-screen + run (restricted globals for generated code)
5. on FAILURE: feed {code, traceback, goal} to LLM → rewrite → goto 4   (cap: 3 attempts)
6. on SUCCESS: validate RESULT keys; record_success() into cookbook; return result
7. on EXHAUSTION: fall back to the static template (today's behavior) → clean fail if that also fails
```
- Composes with Tier-1 (param repair) and Tier-2 (diagnostic back-jump): the agentic loop is the
  *innermost* repair; Tier-2 remains the *outermost* re-route.

## 5. Edge cases (analyzed)

| # | Edge case | Mitigation |
|---|---|---|
| 1 | **Cookbook poisoning** — a subtly-wrong "success" gets reused | Store provenance + signature; templates outrank generated; existing validation gates (CV-lift, NaN, RESULT-keys) still run; fail_count demotes bad snippets; periodic prune |
| 2 | **Retrieval mismatch** — matches tags, wrong for data (runs, garbage) | Adapt step + validation gates; wrong-context avoided by signature tags; not a crash → caught by metric sanity checks |
| 3 | **Infinite/expensive debug loop** | Hard cap (3 attempts); loop only on failure (success path = 0 extra LLM calls); per-run agentic-call budget |
| 4 | **Non-determinism** of generated code | Pin seeds in the contract; we already persist exact executed code per run (notebook_cells) |
| 5 | **Security escape** (os.system, read /etc, exfiltrate) | Restricted globals + AST screen + no-egress network + non-root + read-only data; **generated code never gets full builtins** |
| 6 | **RESULT contract drift** | Validate `result_keys` post-run; repair if missing |
| 7 | **Store schema growth** | Versioned, nullable columns; dedup by checksum |
| 8 | **Concurrency** (two runs write same snippet) | DB upsert on checksum |
| 9 | **Template vs cookbook precedence** | Explicit rank: template > proven-generated(success_count, recency) > fresh-generated |
| 10 | **Hallucinated retrieval** (user's worry) | No vectors — tag+BM25 only; retrieval is explainable |
| 11 | **Module not installed** (e.g. catboost) | AST/whitelist rejects unknown imports → forces LLM to a supported lib |
| 12 | **Sandbox can't pip-install** (apt blocked) | Generated code restricted to the whitelist of already-installed libs |

## 6. Pros / Cons

**Pros**: agents genuinely fix novel errors (the goal); cookbook makes runs cheaper/faster over time
(reuse > regenerate); non-vector store is auditable; templates stay as the safety floor + fallback;
the system *learns* from every successful run.

**Cons / risks**: executing generated code expands the security surface (hence the hardening prerequisite);
weaker determinism; cookbook-poisoning risk; more LLM calls on failure paths; meaningfully more engine
complexity. Net: high value, but Phase E1 (safety) is non-negotiable and must land first.

## 7. Phased plan (each independently shippable + verifiable)

- **E1 — Sandbox hardening (prerequisite).** Restricted globals for generated code + AST safety screen +
  no-egress sandbox network + RESULT validation. Templates keep trusted globals. *Verify: malicious
  snippets (os.system, open /etc/passwd, socket) are rejected; normal templates still run; suite green.*
- **E2 — Code Cookbook store.** `code_snippets` table + retrieve(tag+BM25) + record_success/failure +
  seed from the 12 templates. *Verify: retrieval returns the right template for a given agent/task/tags;
  deterministic ordering.*
- **E3 — Agentic execution loop.** `execute_code_agentic` (retrieve→adapt/write→screen→run→debug→store→
  fallback). Wire into the **two most brittle agents first** (preprocessor, feature_engineer); others keep
  templates. *Verify: a deliberately novel data quirk that crashes the template gets fixed by the loop and
  the fix is stored + reused on a second run.*
- **E4 — Governance/UI.** Trust tiers, dedup/prune, an endpoint + panel to inspect the cookbook and a
  snippet's provenance/success. *Verify: cookbook visible; poisoned snippet demotable.*

## 8. Decisions to confirm (before building)

1. **Scope of generated code**: only the *brittle data-wrangling* agents (preprocessor/feature_engineer)
   write code, while model/tuner/evaluator stay templated (safer, recommended)? Or all agents?
2. **Retrieval store**: Postgres table (recommended — queryable, concurrent) vs a JSONL file in the repo?
3. **Build order**: E1 → E2 → E3 → E4 as above (E1 first, non-negotiable)?
4. **Fallback policy**: always fall back to the static template when the agentic loop exhausts (recommended),
   so we never regress below today's reliability?
