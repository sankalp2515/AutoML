'use client';
import { useCallback, useEffect, useState } from 'react';
import {
  API_BASE,
  deployModel,
  stopDeployment,
  listDeployments,
  getFeatureSchema,
  predictRows,
  getPredictionLog,
  getDriftReport,
} from '@/lib/api';
import type {
  FeatureSchema,
  Prediction,
  PredictionLogEntry,
  DriftReport,
} from '@/lib/types';

// ════════════════════════════════════════════════════════════════════════════
// Deploy toggle + status
// ════════════════════════════════════════════════════════════════════════════

function DeployCard({
  runId,
  isDeployed,
  nPredictions,
  onToggle,
  busy,
}: {
  runId: string;
  isDeployed: boolean;
  nPredictions: number;
  onToggle: () => void;
  busy: boolean;
}) {
  const curl = `curl -X POST ${API_BASE}/api/v1/runs/${runId}/predict \\
  -H "Content-Type: application/json" \\
  -d '{"rows": [{"feature1": "value", ...}]}'`;

  const [copied, setCopied] = useState(false);

  return (
    <div
      className={`relative rounded-2xl p-5 border overflow-hidden transition-all duration-500 ${
        isDeployed
          ? 'border-jade-500/40 bg-gradient-to-br from-jade-500/10 via-transparent to-transparent'
          : 'border-bone/10 bg-obsidian-900/60'
      }`}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          {/* Status orb */}
          <div className="relative">
            <div
              className={`w-12 h-12 rounded-2xl flex items-center justify-center text-xl ${
                isDeployed ? 'bg-jade-500/20' : 'bg-obsidian-700'
              }`}
            >
              {isDeployed ? '🟢' : '⚪'}
            </div>
            {isDeployed && (
              <div className="absolute inset-0 rounded-2xl bg-jade-400/20 animate-ping" style={{ animationDuration: '2.5s' }} />
            )}
          </div>
          <div>
            <p className="text-sm font-semibold text-bone">
              {isDeployed ? 'Model is live' : 'Model not deployed'}
            </p>
            <p className="text-xs text-bone-faint mt-0.5">
              {isDeployed
                ? `Serving predictions · ${nPredictions} served so far`
                : 'Deploy to enable the prediction endpoint'}
            </p>
          </div>
        </div>

        <button
          onClick={onToggle}
          disabled={busy}
          className={`px-5 py-2.5 rounded-xl text-sm font-semibold transition-all active:scale-95 ${
            busy
              ? 'bg-obsidian-700 text-bone-faint cursor-wait'
              : isDeployed
              ? 'bg-terra-500/10 text-terra-400 border border-terra-500/30 hover:bg-terra-500/20'
              : 'bg-gradient-to-r from-jade-600 to-teal-600 text-white shadow-lg shadow-jade-900/40 hover:shadow-jade-600/50 hover:brightness-110'
          }`}
        >
          {busy ? '…' : isDeployed ? 'Stop' : '🚀 Deploy'}
        </button>
      </div>

      {isDeployed && (
        <div className="mt-4 relative">
          <pre className="text-[11px] font-mono text-bone-faint bg-black/30 rounded-lg p-3 overflow-x-auto leading-relaxed">
            {curl}
          </pre>
          <button
            onClick={() => {
              navigator.clipboard.writeText(curl);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
            className="absolute top-2 right-2 text-[11px] text-bone-faint hover:text-bone-dim bg-obsidian-900/90 rounded px-2 py-1"
          >
            {copied ? '✓' : 'Copy'}
          </button>
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Predict playground — form auto-generated from the dataset schema
// ════════════════════════════════════════════════════════════════════════════

function PredictPlayground({
  runId,
  schema,
  onPredicted,
}: {
  runId: string;
  schema: FeatureSchema[];
  onPredicted: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(schema.map((f) => [f.name, f.example]))
  );
  const [result, setResult] = useState<Prediction | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [predicting, setPredicting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const predict = async () => {
    setPredicting(true);
    setError(null);
    setResult(null);
    try {
      const row: Record<string, unknown> = {};
      for (const f of schema) {
        const v = values[f.name];
        row[f.name] = f.type === 'number' && v !== '' ? Number(v) : v;
      }
      const res = await predictRows(runId, [row]);
      setResult(res.predictions[0]);
      setLatency(res.latency_ms);
      onPredicted();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Prediction failed');
    } finally {
      setPredicting(false);
    }
  };

  return (
    <div className="rounded-2xl border border-bone/10 bg-obsidian-900/60 p-5">
      <h4 className="text-xs font-semibold text-bone-dim uppercase tracking-widest mb-4 flex items-center gap-2">
        <span className="text-base">🎮</span> Prediction Playground
      </h4>

      {/* Auto-generated form */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
        {schema.map((f) => (
          <div key={f.name} className="space-y-1">
            <label className="block text-[11px] font-medium text-bone-faint uppercase tracking-wider truncate">
              {f.name}
            </label>
            <input
              type={f.type === 'number' ? 'number' : 'text'}
              step="any"
              value={values[f.name] ?? ''}
              onChange={(e) =>
                setValues((prev) => ({ ...prev, [f.name]: e.target.value }))
              }
              className="w-full bg-obsidian-950/80 border border-bone/15 rounded-lg px-3 py-2 text-sm text-bone focus:outline-none focus:border-gold-500 focus:shadow-[0_0_0_3px_rgba(200,169,110,0.12)] transition-shadow"
            />
          </div>
        ))}
      </div>

      <button
        onClick={predict}
        disabled={predicting}
        className={`w-full py-3 rounded-xl text-sm font-semibold transition-all active:scale-[0.99] ${
          predicting
            ? 'bg-gold-900/40 text-bone-faint cursor-wait'
            : 'bg-gradient-to-r from-gold-600 to-gold-600 text-white shadow-lg shadow-gold-900/40 hover:brightness-110'
        }`}
      >
        {predicting ? '⚡ Running inference…' : '⚡ Predict'}
      </button>

      {error && (
        <p className="mt-3 text-xs text-terra-400 bg-terra-500/10 border border-terra-500/20 rounded-lg px-3 py-2">
          ⚠ {error}
        </p>
      )}

      {/* Result */}
      {result && (
        <div className="mt-4 rounded-xl bg-gradient-to-r from-gold-500/15 to-gold-500/10 border border-gold-500/30 p-5 text-center animate-[fadeSlideUp_.4s_ease]">
          <p className="text-[11px] text-gold-400 uppercase tracking-widest mb-1">
            Prediction
          </p>
          <p className="text-3xl font-bold text-white tracking-tight">
            {result.prediction}
          </p>
          <div className="flex items-center justify-center gap-4 mt-2 text-xs text-bone-dim">
            {result.confidence != null && (
              <span>
                confidence{' '}
                <span className="text-gold-300 font-semibold">
                  {(result.confidence * 100).toFixed(1)}%
                </span>
              </span>
            )}
            {latency != null && <span>· {latency.toFixed(0)} ms</span>}
          </div>
          {/* Confidence bar */}
          {result.confidence != null && (
            <div className="mt-3 h-1.5 rounded-full bg-obsidian-700 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-gold-500 to-gold-400 transition-all duration-700"
                style={{ width: `${result.confidence * 100}%` }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Drift report — PSI bars per feature
// ════════════════════════════════════════════════════════════════════════════

function DriftSection({ runId, refreshKey }: { runId: string; refreshKey: number }) {
  const [report, setReport] = useState<DriftReport | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    getDriftReport(runId)
      .then(setReport)
      .catch(() => setReport(null))
      .finally(() => setLoading(false));
  }, [runId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const statusColor = {
    stable: 'text-jade-400 bg-jade-500/10 border-jade-500/30',
    moderate: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
    drifted: 'text-terra-400 bg-terra-500/10 border-terra-500/30',
  };

  return (
    <div className="rounded-2xl border border-bone/10 bg-obsidian-900/60 p-5">
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-xs font-semibold text-bone-dim uppercase tracking-widest flex items-center gap-2">
          <span className="text-base">🌊</span> Data Drift Monitor
        </h4>
        <button
          onClick={load}
          disabled={loading}
          className="text-[11px] text-bone-faint hover:text-bone-dim border border-bone/15 rounded-md px-2.5 py-1 transition-colors"
        >
          {loading ? '…' : '↻ Refresh'}
        </button>
      </div>

      {!report || report.status === 'insufficient_data' ? (
        <div className="text-center py-6 space-y-2">
          <div className="text-2xl opacity-50">📉</div>
          <p className="text-xs text-bone-faint">
            {report?.message ??
              'Drift analysis compares live traffic against training data — make at least 10 predictions to unlock it.'}
          </p>
        </div>
      ) : (
        <>
          {/* Overall badge */}
          <div className="flex items-center gap-3 mb-5">
            <span
              className={`text-xs font-semibold px-3 py-1.5 rounded-full border uppercase tracking-wider ${
                statusColor[report.overall_status ?? 'stable']
              }`}
            >
              {report.overall_status === 'stable' && '✓ '}
              {report.overall_status === 'drifted' && '⚠ '}
              {report.overall_status}
            </span>
            <span className="text-xs text-bone-faint">
              max PSI {report.max_psi?.toFixed(3)} · {report.n_drifted}/{report.n_features_checked} drifted ·{' '}
              {report.n_samples_current} live vs {report.n_samples_reference} training samples
            </span>
          </div>

          {/* PSI bars */}
          <div className="space-y-2.5">
            {report.features?.map((f) => {
              const psi = f.psi ?? 0;
              // Scale: PSI 0.5+ = full width
              const w = Math.min(100, (psi / 0.5) * 100);
              const barColor =
                f.status === 'stable'
                  ? 'bg-jade-500'
                  : f.status === 'moderate'
                  ? 'bg-amber-500'
                  : 'bg-terra-500';
              return (
                <div key={f.feature} className="flex items-center gap-3">
                  <span className="text-[11px] font-mono text-bone-dim w-36 truncate text-right">
                    {f.feature}
                  </span>
                  <div className="flex-1 h-2.5 rounded-full bg-obsidian-700/80 overflow-hidden relative">
                    {/* threshold markers at 0.1 and 0.25 */}
                    <div className="absolute left-[20%] top-0 bottom-0 w-px bg-obsidian-600/60" />
                    <div className="absolute left-[50%] top-0 bottom-0 w-px bg-obsidian-600/60" />
                    <div
                      className={`h-full rounded-full ${barColor} transition-all duration-700`}
                      style={{ width: `${Math.max(w, 2)}%` }}
                    />
                  </div>
                  <span className="text-[11px] font-mono text-bone-faint w-14 tabular-nums">
                    {f.psi?.toFixed(3) ?? '—'}
                  </span>
                </div>
              );
            })}
          </div>
          <p className="text-[11px] text-bone-ghost mt-3">
            PSI thresholds: &lt;0.10 stable · 0.10–0.25 moderate · &gt;0.25 drifted (markers shown on bars)
          </p>
        </>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Recent predictions table
// ════════════════════════════════════════════════════════════════════════════

function RecentPredictions({ runId, refreshKey }: { runId: string; refreshKey: number }) {
  const [logs, setLogs] = useState<PredictionLogEntry[]>([]);

  useEffect(() => {
    getPredictionLog(runId, 15)
      .then((d) => setLogs(d.predictions))
      .catch(() => {});
  }, [runId, refreshKey]);

  if (logs.length === 0) return null;

  return (
    <div className="rounded-2xl border border-bone/10 bg-obsidian-900/60 p-5">
      <h4 className="text-xs font-semibold text-bone-dim uppercase tracking-widest mb-3 flex items-center gap-2">
        <span className="text-base">🧾</span> Recent Predictions
      </h4>
      <div className="space-y-1.5 max-h-64 overflow-y-auto">
        {logs.map((p) => (
          <div
            key={p.id}
            className="flex items-center gap-3 text-xs px-3 py-2 rounded-lg bg-obsidian-950/60 hover:bg-obsidian-700/40 transition-colors"
          >
            <span className="font-semibold text-gold-300 min-w-[80px]">
              {p.prediction}
            </span>
            {p.confidence != null && (
              <span className="text-bone-faint">
                {(p.confidence * 100).toFixed(0)}%
              </span>
            )}
            <span className="text-bone-faint font-mono text-[11px] truncate flex-1">
              {JSON.stringify(p.features).slice(0, 80)}…
            </span>
            <span className="text-bone-ghost text-[11px] flex-shrink-0">
              {p.latency_ms?.toFixed(0)}ms
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Main panel
// ════════════════════════════════════════════════════════════════════════════

export default function DeployPanel({ runId }: { runId: string }) {
  const [isDeployed, setIsDeployed] = useState(false);
  const [nPredictions, setNPredictions] = useState(0);
  const [schema, setSchema] = useState<FeatureSchema[]>([]);
  const [busy, setBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(() => {
    listDeployments()
      .then((d) => {
        const dep = d.deployments.find((x) => x.run_id === runId);
        setIsDeployed(dep?.status === 'active');
        setNPredictions(dep?.n_predictions ?? 0);
      })
      .catch(() => {});
  }, [runId]);

  useEffect(() => {
    refresh();
    getFeatureSchema(runId)
      .then((d) => setSchema(d.features))
      .catch(() => {});
  }, [runId, refresh]);

  const toggle = async () => {
    setBusy(true);
    try {
      if (isDeployed) {
        await stopDeployment(runId);
      } else {
        await deployModel(runId);
      }
      refresh();
    } catch {
      // surfaced via state refresh
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <DeployCard
        runId={runId}
        isDeployed={isDeployed}
        nPredictions={nPredictions}
        onToggle={toggle}
        busy={busy}
      />

      {isDeployed && schema.length > 0 && (
        <PredictPlayground
          runId={runId}
          schema={schema}
          onPredicted={() => {
            setRefreshKey((k) => k + 1);
            refresh();
          }}
        />
      )}

      {isDeployed && (
        <>
          <DriftSection runId={runId} refreshKey={refreshKey} />
          <RecentPredictions runId={runId} refreshKey={refreshKey} />
        </>
      )}
    </div>
  );
}
