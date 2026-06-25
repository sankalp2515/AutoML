const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  TableOfContents, PageBreak, BorderStyle, LevelFormat,
} = require("docx");

// ───────────────────────────── Content ─────────────────────────────
// Each item: { q, s, t, a, r }  (STAR)  OR  { q, answer }  (direct technical)
const SECTIONS = [
  ["1. Project Overview", [
    { q: "Walk me through this project in a minute.",
      s: "Non-experts with tabular data and a prediction goal can't hand-write an ML pipeline, and existing AutoML tools are black boxes you must blindly trust.",
      t: "Build a system that takes a CSV plus a plain-English goal and returns a trained, deployable, fully-explained model a stakeholder can audit.",
      a: "Designed a 10-agent LangGraph pipeline where an LLM makes every decision (task framing, metrics, preprocessing, features, model choice) and a sandboxed executor runs vetted code; every claim is verified by cross-validation, never trusted on the LLM's word.",
      r: "End-to-end it produces a deployed prediction endpoint, drift monitoring, SHAP explanations, and an auto-written notebook — across binary/multiclass/multilabel/regression and time-series, with 132 passing tests." },
    { q: "Who is it for, and why does the 'glass box' matter?",
      s: "Most AutoML hands you a number with no provenance; most LLM agent demos are autonomous but unreliable and hallucinate results.",
      t: "Serve users who need a model AND a defensible audit trail of how it was built.",
      a: "Logged every decision with reasoning to a decision-log table, MLflow, and a narrated notebook; made the LLM propose while sklearn disposes, so outputs are empirical, not opinions.",
      r: "A reviewer can trace each choice to the data that justified it — the differentiator versus both black-box AutoML and free-running agents." },
  ]],

  ["2. Architecture & Design Decisions", [
    { q: "Why LangGraph instead of a plain async loop?",
      s: "The pipeline isn't strictly linear — it has a conditional improvement loop and must fail fast on any agent error.",
      t: "Pick an orchestration model that makes stateful, conditional flow explicit and testable.",
      a: "Used LangGraph's stateful graph with conditional edges: a sequential DAG, one bounded Evaluator→FeatureEngineer feedback cycle, and fail-fast routers that send any failed agent straight to END.",
      r: "Routing logic became declarative and unit-testable; I later added an integration harness that drives the real graph end-to-end to catch wiring regressions." },
    { q: "Why is the code-execution sandbox a separate service from the backend?",
      s: "Agents generate and run ML code against user data; doing that in the API process is both a security and a reliability risk.",
      t: "Isolate execution so untrusted/heavy code can't compromise or destabilize the orchestrator.",
      a: "Split a dedicated sandbox container with the full ML stack and GPU; the backend only orchestrates and sends code over an internal network. The LLM never sees raw rows — only statistical profiles.",
      r: "Privacy, resource isolation, and independent ML dependencies; it also became the natural place to enforce the security boundary (no network, non-root, process isolation)." },
    { q: "Explain 'the LLM proposes; sklearn disposes.'",
      answer: "The LLM chooses what to do — the metric, per-column preprocessing, feature hypotheses, candidate models — but it never decides whether those choices are good. Each is executed and measured: features must show positive cross-validated lift to survive, model picks must win measured CV. The action space is bounded by vetted templates and a curated registry, so the LLM's creativity is harnessed but every claim is checked against ground truth." },
  ]],

  ["3. AI / LLM Engineering", [
    { q: "How do you handle LLM rate limits and provider outages?",
      s: "On a free Groq tier (12K tokens/min), two concurrent runs exhausted the budget; every agent retried Groq then fell back, so latency compounded and a second run stalled.",
      t: "Make the LLM layer resilient without burning the token budget on doomed retries.",
      a: "Built a provider-agnostic client with a retry+fallback chain across six providers, then added a process-wide rate-limit cooldown circuit-breaker: a 429 cools that provider for its Retry-After window so every subsequent agent and concurrent run skips straight to the fallback.",
      r: "Eliminated the per-agent retry storm; concurrent runs now flow to the fallback provider instantly instead of serializing — verified with a unit test of the cooldown behavior." },
    { q: "How do you keep token cost and context usage down?",
      s: "Agentic pipelines can fire many large LLM calls per run.",
      t: "Minimize tokens without losing decision quality.",
      a: "Sent the LLM statistical profiles only (never raw rows), kept the happy path template-first (zero LLM cost unless a template fails), added an opt-in completion cache keyed on a content hash, and enforce a per-tenant cumulative cost budget.",
      r: "Repeated/identical prompts are free, costs are capped per tenant, and the LLM only writes code on the rare failure path." },
    { q: "How do you stop the LLM from hallucinating a good result?",
      answer: "It never reports the score — sklearn does, on an untouched hold-out. The LLM only proposes decisions; the sandbox executes and the measured metric is ground truth. A feature is kept only if it shows positive cross-validated lift; a model wins only if it wins measured CV. There is no path where the LLM's claim becomes the result without verification." },
    { q: "How do you validate the LLM's structured output?",
      s: "A malformed framing decision — an invalid task type or a metric that doesn't exist for the task — could crash or silently NaN a downstream scorer.",
      t: "Guarantee that bad model output can't poison a run.",
      a: "Added a guardrails layer that clamps the framing: unknown task → default, a metric invalid for the task → the registry default for that task, out-of-range threshold → clamped, missing target flagged; plus a robustness eval suite that feeds adversarial/malformed framings through the validator.",
      r: "The validator never crashes and always yields a task-valid metric — proven by a parametrized adversarial test suite." },
    { q: "How do you handle prompt injection in the user's goal?",
      answer: "Defense-in-depth. The goal is only ever used as DATA to frame an ML problem — the LLM has no tools or data access and its output is structurally validated — so the blast radius is small. On top of that I sanitize the input (strip control chars, cap length) and run a prompt-injection scanner that detects and neutralizes override/exfiltration/jailbreak patterns, logging them, with a strict mode that rejects outright." },
    { q: "You said 'no hardcoding' — what's actually dynamic vs static?",
      s: "A strict requirement was that nothing about the ML decisions be hardcoded, but a production system can't be 100% non-deterministic LLM output.",
      t: "Draw a defensible line between LLM-owned decisions and code-owned mechanics.",
      a: "Codified a doctrine: the LLM owns every ML decision (framing, metric, preprocessing, features, models, corrective code); code owns contracts, mechanics, and safety rails (the RESULT/state schema, the metric→scorer mapping, CV mechanics, the sandbox boundary). I removed hardcoded menus by deriving the framer's metric vocabulary from a single metric registry.",
      r: "Adding a metric is now one registry line with no prompt edit, and the duplication that previously caused metric-drift bugs is gone." },
  ]],

  ["4. Security", [
    { q: "You execute LLM-generated code — how is that safe?",
      s: "Self-repair makes LLM-written code a normal execution path, so the sandbox had to become a real boundary, not just a name.",
      t: "Contain arbitrary generated code so it can't reach the network, escalate, or take down the service.",
      a: "Made the container the primary boundary: no internet egress (internal Docker network), non-root, all Linux capabilities dropped, no-new-privileges, a PID cap, and per-execution process isolation with a hard wall-clock kill. An AST allow-list screen plus stripped builtins is the secondary in-process defense for generated code.",
      r: "A runaway loop, crash, or OOM kills only its child process; the sandbox can't reach the internet — both verified by tests and a documented live check." },
    { q: "How does agentic self-repair work, and why doesn't it crash runs?",
      s: "A vetted template can hit an edge case on a real dataset and fail.",
      t: "Recover automatically instead of failing the whole pipeline.",
      a: "On a template failure the failing agent writes corrected code — seeded by prior fixes from a cookbook plus the traceback — runs it in the restricted sandbox, reads the new traceback, retries up to a cap, validates the RESULT contract, and records the working fix. The happy path stays template-first, so there's no extra LLM cost unless something actually fails.",
      r: "Generalized across all ten agents; no agent dies on a template error before attempting a fix, proven by a fault-injection unit test." },
  ]],

  ["5. ML Rigor & Correctness", [
    { q: "How do you ensure the reported score is honest? (Strongest answer)",
      s: "The reported metric was the selection cross-validation — the same data was used to select features, models, and hyperparameters AND to report the score, which is optimistic.",
      t: "Report a true generalization estimate, not a leaked one.",
      a: "Added a data-splitter step that carves a hold-out from the RAW data BEFORE any agent fits, selects, or tunes; all downstream agents read only the train split, and the evaluator scores the untouched hold-out by replaying the exact inference transform. Iteration is gated on statistical significance — a gain must beat the CV noise floor.",
      r: "Reported scores correctly dropped to honest hold-out numbers, and the pipeline stopped chasing fold noise; covered by template and routing tests." },
    { q: "How do you handle class imbalance without leakage?",
      s: "Fraud-like datasets (minority under 5%) make accuracy and ROC-AUC misleading, and naive resampling leaks.",
      t: "Improve minority detection without contaminating validation.",
      a: "The framer prefers PR-AUC/recall for severe imbalance; resampling (SMOTE/SMOTE-Tomek) is applied INSIDE CV folds only via an imbalanced-learn pipeline, never touching the validation fold, with a guard that falls back to class weighting for tiny minorities. The resampler is train-time only and excluded from the serialized inference pipeline.",
      r: "End-to-end verified on a synthetic 0.1%-fraud dataset; PR-AUC and recall reported with no train/serve leakage." },
    { q: "How do you prevent train/serve skew?",
      answer: "The sklearn Pipeline is the contract. The exact fitted ColumnTransformer used in training is serialized and reused at inference, and LLM-engineered features are reproduced from the same formulas with the training-time fill values. The inference pipeline is a plain dict — preprocessor, model, threshold, class labels, engineered-feature recipe — so the same transformation runs at train and serve time." },
    { q: "How are models explained and monitored?",
      answer: "Explainability: SHAP attributions, calibration curves, threshold selection honoring the false-positive/false-negative preference, and slice analysis. Monitoring: a from-scratch drift report — Population Stability Index over quantile bins plus a Kolmogorov-Smirnov test — comparing live prediction traffic against the training distribution, surfaced through the API and UI." },
  ]],

  ["6. MLOps & Observability", [
    { q: "How do you track experiments and models?",
      answer: "MLflow is the backbone: every run logs its metrics, parameters, and artifacts, with iteration-prefixed keys to respect MLflow's immutability rules. Models can be promoted through the registry (Staging→Production) via an API endpoint, and the agent-written evidence notebook plus the decision-log table give a human-readable audit alongside the structured tracking." },
    { q: "How do you observe the system?",
      answer: "Prometheus metrics (pipeline rates, per-agent durations, sandbox executions, repair counts) on a Grafana dashboard; structured JSON logging via structlog; and per-LLM-call tracking of tokens, latency, estimated cost, and which provider actually answered — emitted as one structured trace line per call, correlated by run id and ready to ship to OpenTelemetry/LangSmith." },
    { q: "How do you manage database schema changes?",
      s: "Early on, new columns were added with hand-run ALTER TABLE statements that drifted between environments.",
      t: "Make schema changes reproducible and safe.",
      a: "Adopted Alembic with the model metadata wired for autogeneration and a baseline revision; existing databases are stamped, fresh ones build from create_all then stamp, and every change after is a reviewed migration.",
      r: "No more manual SQL drift; schema is versioned and applied with alembic upgrade head." },
  ]],

  ["7. Multi-Tenancy & Production", [
    { q: "How did you make it multi-tenant and isolated?",
      s: "Targeting a hosted product meant runs and artifacts had to be isolated per customer, and the original singletons even cross-contaminated cost attribution under concurrency.",
      t: "Enforce tenant isolation everywhere without a per-endpoint hole, safely by default.",
      a: "First fixed the concurrency race by moving run/agent identity to request-scoped contextvars. Then added a tenant column, resolved the tenant from a Supabase JWT or an API key, and enforced ownership with a single router-level dependency applied to all run-scoped routers — plus per-tenant active-run quotas and LLM cost budgets. With no keys configured it stays single-tenant, so behavior is unchanged by default.",
      r: "Cross-tenant reads return 404, quotas return 429, budgets return 402 — all verified by unit tests; concurrent-run attribution is now correct." },
    { q: "How do runs survive an API restart?",
      answer: "Runs were originally fire-and-forget background tasks that died with the process. I added an opt-in durable queue: with a flag set, the API enqueues to an arq Redis queue processed by a dedicated worker container, so a run keeps executing even if the API restarts. Enqueue fails safe — if the queue is unreachable it falls back to in-process so a run is never stranded." },
  ]],

  ["8. Testing & Quality", [
    { q: "How do you test an LLM-driven system?",
      s: "LLM calls are non-deterministic and the full pipeline needs Docker/GPU, so naive end-to-end tests would be flaky and slow.",
      t: "Get high-confidence, deterministic coverage of the parts that actually break.",
      a: "Layered the tests: static template render/compile guards, a state-contract guard (an agent can't return a key the state doesn't declare), metric-registry parity tests, auth/tenant and guardrail tests, and a graph-level integration harness that drives the REAL LangGraph end-to-end with each agent's run() stubbed — no LLM, sandbox, or DB.",
      r: "132 deterministic tests, including end-to-end coverage of agent ordering, fail-fast, the significance gate, and the iteration cap — the regression class that previously only surfaced in live runs." },
    { q: "How does the integration harness test orchestration without the LLM or sandbox?",
      answer: "It builds the real compiled graph but monkeypatches each agent singleton's run() with a deterministic stub returning the state delta the real agent would. The graph, edges, and routing functions under test are the real ones, so it verifies the data-splitter sits before the baseline, a failed agent routes straight to END with no zombie cascade, a sub-noise gain doesn't trigger another iteration, and real improvement loops but the max-iteration cap terminates it." },
  ]],

  ["9. War Stories (Behavioral)", [
    { q: "Tell me about the hardest bug you fixed.",
      s: "Under concurrent runs, LLM cost and decision attribution were being logged against the wrong run — silently corrupting the audit trail that is the product's core value.",
      t: "Find why concurrency cross-contaminated attribution and fix it without a big rewrite.",
      a: "Traced it to run/agent identity stored as mutable attributes on process-wide singletons (the LLM client and agent instances). Replaced that with Python contextvars, which are copied per asyncio task, so each run sees its own values; removed all the shared mutable state.",
      r: "Concurrent runs no longer cross-contaminate; I added a regression test that interleaves two tasks and asserts isolation — and it unblocked the whole multi-tenant direction." },
    { q: "Tell me about a time you found a serious flaw in your own work.",
      s: "I claimed honest evaluation, but on review the 'hold-out' inside the evaluator had already been seen during feature selection, model selection, and tuning — so the headline score was optimistic.",
      t: "Decide between hiding it or fixing it properly.",
      a: "Called it out explicitly, then re-architected: carve the hold-out from raw data before any fitting, make all upstream agents train-only by repointing the dataset path, and score the untouched hold-out via the verified inference transform — with a safe fallback for tiny datasets.",
      r: "Reported scores dropped to honest numbers. I'd rather ship a lower true number than a higher leaked one — and being able to spot leakage is itself the senior signal." },
    { q: "Tell me about a hard tradeoff you made.",
      s: "Systems like MLE-STAR let agents write arbitrary code for maximum novelty; that maximizes capability but minimizes reliability and security.",
      t: "Choose where to sit on the autonomy-vs-reliability spectrum for a tool people must trust.",
      a: "Chose floor reliability over ceiling novelty: bound the action space to vetted templates and a curated model/metric registry, verify every decision empirically, and add an agentic self-repair path only for the edge cases templates miss.",
      r: "Predictable cost (a handful of LLM calls per run vs. hundreds), known failure modes, and an auditable, same-shape-every-run pipeline — the right trade for a trustworthy product." },
    { q: "Describe a time you disagreed with a requirement.",
      s: "The directive was 'everything dynamic, nothing hardcoded' alongside 'must never break' and 'minimize tokens' — three goals that conflict if taken literally.",
      t: "Reconcile them instead of blindly implementing a contradiction.",
      a: "Surfaced the tension in writing and proposed a doctrine that resolved it — the LLM owns ML decisions, code owns contracts and safety rails — then got explicit sign-off before building, and codified it in a doctrine doc to prevent regression.",
      r: "All three goals coexist: no hardcoded ML decisions, deterministic safety rails, and zero extra tokens on the happy path." },
  ]],

  ["10. Reflection, Scaling & Comparisons", [
    { q: "What would you do differently or what's still missing?",
      s: "The system is production-grade in architecture but not yet a deployed product.",
      t: "Be honest about the highest-leverage gaps.",
      a: "I'd generate a typed OpenAPI client to kill the frontend/backend contract-drift bug class (currently hand-managed), add CI that runs real training on many OpenML datasets with held-out scoring to back the generalization claim, add data versioning for full reproducibility, and stand up a persistent model server to cut the ~1s/prediction sandbox overhead.",
      r: "These are the items I'd sequence next; naming them unprompted is part of owning the system honestly." },
    { q: "How would you scale this to thousands of users?",
      answer: "The pieces are in place: stateless API behind the request-scoped context fix, the durable arq queue with horizontally-scalable worker containers, per-tenant quotas and cost budgets to protect shared capacity, and the rate-limit cooldown to spread LLM load. Next steps: a persistent model server for inference, autoscaling workers on queue depth, a fast paid LLM tier with the free tier as fallback, and per-tenant data retention/encryption." },
    { q: "How is this different from Vertex AutoML or MLE-STAR?",
      answer: "Versus Vertex AutoML: glass-box transparency, near-zero cost, minutes not hours, data sovereignty (self-hosted), and no lock-in — they win on scale, modalities, and SLAs. Versus MLE-STAR: the opposite trade — MLE-STAR writes novel code for a high novelty ceiling; this system bounds the action space for floor reliability and security, verifies every decision empirically, and adds self-repair for edge cases. Different tools for different risk tolerances." },
    { q: "Is this AI Engineering or ML Engineering?",
      answer: "Both, honestly. The hardest, most differentiated work is AI/LLM systems engineering — agentic orchestration, multi-provider resilience, sandboxed self-repair, output guardrails. But it's equally an ML Engineering project: leakage-free evaluation, sklearn pipeline contracts, Optuna tuning, MLflow tracking and a model registry, SHAP, and drift monitoring. It maps cleanly to an AI Engineer or ML Engineer role." },
  ]],
];

// ───────────────────────────── Rendering ─────────────────────────────
const ACCENT = "2E5AAC";
const children = [];

// Title page
children.push(
  new Paragraph({ spacing: { before: 2600 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "AutoML Orchestrator", bold: true, size: 56, color: ACCENT })] }),
  new Paragraph({ alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Interview Preparation — Questions & STAR Answers", size: 30 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200 },
    children: [new TextRun({ text: "Agentic ML pipeline · Python · FastAPI · LangGraph · Docker", italics: true, size: 22, color: "666666" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 1400 },
    children: [new TextRun({ text: "S — Situation   T — Task   A — Action   R — Result", size: 20, color: "666666" })] }),
  new Paragraph({ children: [new PageBreak()] }),
);

// TOC
children.push(
  new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Contents")] }),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-1" }),
  new Paragraph({ children: [new PageBreak()] }),
);

function starRuns(label, text) {
  return new Paragraph({
    spacing: { after: 120 }, indent: { left: 360 },
    children: [
      new TextRun({ text: label + "  ", bold: true, color: ACCENT }),
      new TextRun({ text }),
    ],
  });
}

let qNum = 0;
for (const [title, items] of SECTIONS) {
  children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(title)] }));
  for (const it of items) {
    qNum++;
    children.push(new Paragraph({
      heading: HeadingLevel.HEADING_2, spacing: { before: 220, after: 80 },
      children: [new TextRun({ text: `Q${qNum}. ${it.q}` })],
    }));
    if (it.answer) {
      children.push(new Paragraph({ spacing: { after: 120 }, indent: { left: 360 },
        children: [new TextRun({ text: "Answer.  ", bold: true, color: ACCENT }), new TextRun({ text: it.answer })] }));
    } else {
      children.push(starRuns("S.", it.s));
      children.push(starRuns("T.", it.t));
      children.push(starRuns("A.", it.a));
      children.push(starRuns("R.", it.r));
    }
  }
}

// Closing tips
children.push(
  new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Delivery Tips")] }),
);
for (const tip of [
  "Lead with the result, then explain how — interviewers reward outcome-first answers.",
  "Quantify wherever possible (132 tests, 10 agents, 6-provider fallback, ~0 cost happy path).",
  "Say 'production-grade architecture', not 'in production' — it isn't deployed with real users yet.",
  "Volunteer the gaps (typed client, real-dataset CI, reproducibility) — owning them is a senior signal.",
  "For technical 'explain' questions, give the one-line principle first, then one concrete detail.",
]) {
  children.push(new Paragraph({ numbering: { reference: "tips", level: 0 }, children: [new TextRun(tip)] }));
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, color: ACCENT, font: "Arial" },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 23, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: "tips", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  ]},
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("Interview_Prep.docx", buf);
  console.log("wrote Interview_Prep.docx  (" + qNum + " questions)");
});
