import type { Results } from '@/lib/types';

function MetricCard({
  label,
  value,
  sub,
  highlight,
  trend,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
  trend?: 'up' | 'down' | 'neutral';
}) {
  return (
    <div
      className={`rounded-xl p-4 border ${
        highlight
          ? 'bg-violet-500/10 border-violet-500/30'
          : 'bg-slate-900 border-slate-800'
      }`}
    >
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p
        className={`text-2xl font-bold tabular-nums ${
          highlight ? 'text-violet-300' : 'text-slate-100'
        }`}
      >
        {value}
      </p>
      {sub && (
        <p
          className={`text-xs mt-1 ${
            trend === 'up'
              ? 'text-emerald-400'
              : trend === 'down'
              ? 'text-rose-400'
              : 'text-slate-500'
          }`}
        >
          {sub}
        </p>
      )}
    </div>
  );
}

function ScoreChart({
  scores,
  baseline,
  metric,
}: {
  scores: number[];
  baseline: number;
  metric: string;
}) {
  if (!scores || scores.length < 2) return null;

  const W = 360,
    H = 120,
    PAD = { top: 10, right: 12, bottom: 24, left: 40 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  const allVals = [...scores, baseline];
  const minV = Math.min(...allVals) * 0.97;
  const maxV = Math.max(...allVals) * 1.03;

  const toX = (i: number) =>
    PAD.left + (i / Math.max(scores.length - 1, 1)) * innerW;
  const toY = (v: number) =>
    PAD.top + (1 - (v - minV) / (maxV - minV)) * innerH;

  const baselineY = toY(baseline);
  const lineD = scores
    .map((s, i) => `${i === 0 ? 'M' : 'L'}${toX(i).toFixed(1)},${toY(s).toFixed(1)}`)
    .join(' ');

  // Y-axis ticks
  const yTicks = [minV, (minV + maxV) / 2, maxV];

  return (
    <div className="mt-4">
      <p className="text-xs text-slate-500 mb-2">
        Score over iterations ({metric})
      </p>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ maxHeight: '120px' }}
      >
        {/* Grid */}
        {yTicks.map((t) => (
          <line
            key={t}
            x1={PAD.left}
            y1={toY(t)}
            x2={W - PAD.right}
            y2={toY(t)}
            stroke="#1e293b"
            strokeWidth="1"
          />
        ))}

        {/* Y-axis labels */}
        {yTicks.map((t) => (
          <text
            key={t}
            x={PAD.left - 4}
            y={toY(t) + 3}
            textAnchor="end"
            fontSize="9"
            fill="#475569"
          >
            {t.toFixed(3)}
          </text>
        ))}

        {/* X-axis labels */}
        {scores.map((_, i) => (
          <text
            key={i}
            x={toX(i)}
            y={H - 6}
            textAnchor="middle"
            fontSize="9"
            fill="#475569"
          >
            {i + 1}
          </text>
        ))}

        {/* Baseline reference */}
        <line
          x1={PAD.left}
          y1={baselineY}
          x2={W - PAD.right}
          y2={baselineY}
          stroke="#6366f1"
          strokeDasharray="3,3"
          strokeWidth="1"
          opacity="0.5"
        />
        <text x={W - PAD.right + 2} y={baselineY + 3} fontSize="8" fill="#6366f1" opacity="0.7">
          base
        </text>

        {/* Score line */}
        <path d={lineD} fill="none" stroke="#8b5cf6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />

        {/* Data points */}
        {scores.map((s, i) => (
          <circle
            key={i}
            cx={toX(i)}
            cy={toY(s)}
            r="3.5"
            fill="#8b5cf6"
            stroke="#1e293b"
            strokeWidth="1.5"
          />
        ))}
      </svg>
    </div>
  );
}

export default function MetricsPanel({ results }: { results: Results }) {
  const {
    primary_metric,
    final_score,
    baseline_score,
    winner_model,
    iteration_count,
    evaluation_report,
    shap_top_features,
    task_type,
  } = results;

  const improvement =
    final_score != null && baseline_score != null
      ? final_score - baseline_score
      : null;

  const metrics = evaluation_report?.metrics ?? {};
  const calibration = evaluation_report?.calibration;

  // Build iteration scores array for chart — we only have final_score and baseline_score
  // If run has iteration_count, build approximate array
  const iterScores: number[] =
    baseline_score != null && final_score != null
      ? [baseline_score, final_score]
      : [];

  return (
    <div className="space-y-6">
      {/* ── Top metric cards ───────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <MetricCard
          label={`Final ${primary_metric ?? 'score'}`}
          value={final_score?.toFixed(4) ?? '—'}
          highlight
          sub={
            improvement != null
              ? `${improvement >= 0 ? '+' : ''}${improvement.toFixed(4)} vs baseline`
              : undefined
          }
          trend={
            improvement == null ? 'neutral' : improvement >= 0 ? 'up' : 'down'
          }
        />
        <MetricCard
          label="Baseline"
          value={baseline_score?.toFixed(4) ?? '—'}
          sub={`LogisticRegression / Ridge`}
        />
        <MetricCard
          label="Winner Model"
          value={winner_model ?? '—'}
          sub={`${iteration_count ?? 0} iteration${iteration_count !== 1 ? 's' : ''}`}
        />
      </div>

      {/* ── Score chart ────────────────────────────────────────────────────── */}
      {iterScores.length >= 2 && (
        <ScoreChart
          scores={iterScores}
          baseline={baseline_score!}
          metric={primary_metric ?? 'score'}
        />
      )}

      {/* ── All metrics ────────────────────────────────────────────────────── */}
      {Object.keys(metrics).length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
            All Metrics (20% hold-out)
          </h4>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {Object.entries(metrics).map(([k, v]) => (
              <div
                key={k}
                className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2.5"
              >
                <p className="text-[10px] text-slate-600 uppercase tracking-wider">{k}</p>
                <p className="text-base font-semibold text-slate-200 tabular-nums">
                  {typeof v === 'number' ? v.toFixed(4) : String(v)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Calibration ────────────────────────────────────────────────────── */}
      {calibration && (
        <div className="flex items-center gap-3 bg-slate-900 rounded-lg px-4 py-3 border border-slate-800">
          <span
            className={`text-lg ${
              calibration.well_calibrated ? '✅' : '⚠️'
            }`}
          >
            {calibration.well_calibrated ? '✅' : '⚠️'}
          </span>
          <div>
            <p className="text-xs font-medium text-slate-300">
              Calibration:{' '}
              <span className={calibration.well_calibrated ? 'text-emerald-400' : 'text-amber-400'}>
                {calibration.well_calibrated ? 'Well-calibrated' : 'Poorly calibrated'}
              </span>
            </p>
            <p className="text-xs text-slate-600">
              Mean calibration error: {calibration.mean_calibration_error.toFixed(4)}
            </p>
          </div>
        </div>
      )}

      {/* ── SHAP top features ──────────────────────────────────────────────── */}
      {shap_top_features && shap_top_features.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
            SHAP Top Features
          </h4>
          <div className="space-y-1.5">
            {shap_top_features.slice(0, 10).map((feat, i) => {
              const barW = Math.max(10, 100 - i * 9);
              return (
                <div key={feat} className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 w-4 text-right flex-shrink-0">
                    {i + 1}
                  </span>
                  <div className="flex-1 flex items-center gap-2">
                    <div
                      className="h-4 rounded-sm bg-violet-600/40"
                      style={{ width: `${barW}%` }}
                    />
                    <span className="text-xs text-slate-300 font-mono truncate max-w-[200px]">
                      {feat}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
