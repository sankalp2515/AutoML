'use client';
import { useState } from 'react';
import { askModel, fairnessAudit, retrainChallenger, batchPredictUrl, API_BASE } from '@/lib/api';

// Bundles the backlog tools (P12 retrain · P13 batch · P14 ask · P15 fairness)
// into one run-page tab. Each section calls the matching backend endpoint.
export default function ModelToolsPanel({ runId }: { runId: string }) {
  return (
    <div className="space-y-8">
      <AskSection runId={runId} />
      <FairnessSection runId={runId} />
      <BatchSection runId={runId} />
      <RetrainSection runId={runId} />
    </div>
  );
}

function SectionShell({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) {
  return (
    <div className="lux-card p-6 space-y-4">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h3 className="font-display text-xl text-bone mt-1">{title}</h3>
      </div>
      {children}
    </div>
  );
}

// ── P14: Ask your model ───────────────────────────────────────────────────────
function AskSection({ runId }: { runId: string }) {
  const [q, setQ] = useState('');
  const [ans, setAns] = useState<string | null>(null);
  const [cited, setCited] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const ask = async () => {
    if (q.trim().length < 3) return;
    setBusy(true); setErr(null); setAns(null);
    try {
      const r = await askModel(runId, q.trim());
      setAns(r.answer); setCited(r.cited_agents ?? []);
    } catch (e) { setErr(e instanceof Error ? e.message : 'Ask failed'); }
    setBusy(false);
  };

  return (
    <SectionShell eyebrow="P14 · Grounded Q&A" title="Ask Your Model">
      <p className="text-[13px] text-bone-faint">Answers come only from this run’s decisions, metrics, and SHAP.</p>
      <div className="flex gap-2">
        <input
          value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && ask()}
          placeholder="e.g. Why was the Cabin column dropped?"
          className="flex-1 bg-obsidian-950/80 border hairline rounded-lg px-4 py-2.5 text-bone-dim placeholder-bone-ghost text-sm focus:outline-none focus:border-gold-600/50"
        />
        <button onClick={ask} disabled={busy} className="btn-gold px-5 py-2.5 text-[11px] uppercase tracking-luxe font-mono">
          {busy ? '…' : 'Ask'}
        </button>
      </div>
      {err && <p className="text-terra-300 text-xs">◆ {err}</p>}
      {ans && (
        <div className="rounded-lg border hairline bg-obsidian-900/60 p-4 space-y-2">
          <p className="text-[13.5px] text-bone-dim leading-relaxed">{ans}</p>
          {cited.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {cited.map((c) => (
                <span key={c} className="font-mono text-[9px] uppercase tracking-wider text-gold-400 border border-gold-700/50 rounded-full px-2 py-0.5">{c}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </SectionShell>
  );
}

// ── P15: Fairness audit ───────────────────────────────────────────────────────
function FairnessSection({ runId }: { runId: string }) {
  const [cols, setCols] = useState('');
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    if (!cols.trim()) return;
    setBusy(true); setErr(null); setData(null);
    try {
      const r = await fairnessAudit(runId, cols.trim());
      setData((r as any).fairness ?? {});
    } catch (e) { setErr(e instanceof Error ? e.message : 'Fairness audit failed'); }
    setBusy(false);
  };

  return (
    <SectionShell eyebrow="P15 · Disparate Impact" title="Fairness Audit">
      <div className="flex gap-2">
        <input
          value={cols} onChange={(e) => setCols(e.target.value)}
          placeholder="sensitive columns, comma-separated (e.g. Sex, Age)"
          className="flex-1 bg-obsidian-950/80 border hairline rounded-lg px-4 py-2.5 text-bone-dim placeholder-bone-ghost text-sm focus:outline-none focus:border-gold-600/50"
        />
        <button onClick={run} disabled={busy} className="btn-ghost px-5 py-2.5 text-[11px] uppercase tracking-luxe font-mono">
          {busy ? '…' : 'Audit'}
        </button>
      </div>
      {err && <p className="text-terra-300 text-xs">◆ {err}</p>}
      {data && Object.entries(data).map(([col, info]: [string, any]) => (
        <div key={col} className="rounded-lg border hairline p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[11px] uppercase tracking-wider text-bone-dim">{col}</span>
            <span className={`font-mono text-[10px] px-2 py-0.5 rounded-full border ${info.passes_80pct_rule ? 'text-jade-400 border-jade-500/40' : 'text-terra-400 border-terra-500/40'}`}>
              DI {info.disparate_impact_ratio ?? '—'} · {info.passes_80pct_rule ? 'passes 80% rule' : 'fails 80% rule'}
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {Object.entries(info.by_group ?? {}).map(([g, m]: [string, any]) => (
              <div key={g} className="text-[11px] text-bone-faint">
                <span className="text-bone-dim">{g}</span> — sel {m.selection_rate ?? '—'}, acc {m.accuracy ?? '—'} (n={m.n})
              </div>
            ))}
          </div>
        </div>
      ))}
    </SectionShell>
  );
}

// ── P13: Batch scoring ────────────────────────────────────────────────────────
function BatchSection({ runId }: { runId: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const score = async () => {
    if (!file) return;
    setBusy(true); setErr(null);
    try {
      const fd = new FormData(); fd.append('file', file);
      const res = await fetch(batchPredictUrl(runId), { method: 'POST', body: fd });
      if (!res.ok) throw new Error((await res.json()).detail || 'Batch failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `scored_${runId.slice(0, 8)}.csv`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { setErr(e instanceof Error ? e.message : 'Batch failed'); }
    setBusy(false);
  };

  return (
    <SectionShell eyebrow="P13 · Batch Scoring" title="Score a CSV">
      <p className="text-[13px] text-bone-faint">Upload a CSV of rows; download it with prediction + confidence columns appended. (Deploy the model first.)</p>
      <div className="flex gap-2 items-center">
        <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-xs text-bone-faint file:mr-3 file:rounded-lg file:border file:border-bone/15 file:bg-obsidian-900 file:px-3 file:py-2 file:text-bone-dim file:text-[11px]" />
        <button onClick={score} disabled={busy || !file} className="btn-gold px-5 py-2.5 text-[11px] uppercase tracking-luxe font-mono">
          {busy ? '…' : 'Score & Download'}
        </button>
      </div>
      {err && <p className="text-terra-300 text-xs">◆ {err}</p>}
    </SectionShell>
  );
}

// ── P12: Champion/challenger retrain ──────────────────────────────────────────
function RetrainSection({ runId }: { runId: string }) {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<{ challenger_run_id: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const go = async () => {
    setBusy(true); setErr(null);
    try { setRes(await retrainChallenger(runId)); }
    catch (e) { setErr(e instanceof Error ? e.message : 'Retrain failed'); }
    setBusy(false);
  };

  return (
    <SectionShell eyebrow="P12 · Champion / Challenger" title="Retrain">
      <p className="text-[13px] text-bone-faint">Starts a challenger on the same dataset. Promote only if it beats this champion.</p>
      <button onClick={go} disabled={busy} className="btn-ghost px-5 py-2.5 text-[11px] uppercase tracking-luxe font-mono">
        {busy ? 'Starting…' : 'Train Challenger'}
      </button>
      {err && <p className="text-terra-300 text-xs">◆ {err}</p>}
      {res && (
        <a href={`/runs/${res.challenger_run_id}`} className="block text-gold-400 hover:text-gold-300 text-sm font-mono">
          → challenger started: {res.challenger_run_id.slice(0, 8)} (open)
        </a>
      )}
    </SectionShell>
  );
}
