import type { LLMStat } from '@/lib/types';

function agentLabel(name: string) {
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function CostBadge({ cost }: { cost: number }) {
  if (cost === 0)
    return (
      <span className="text-xs text-emerald-500 bg-emerald-500/10 rounded px-1.5 py-0.5">
        Free
      </span>
    );
  return (
    <span className="text-xs text-slate-300 font-mono">
      ${cost.toFixed(5)}
    </span>
  );
}

export default function LLMStatsPanel({
  stats,
  totals,
}: {
  stats: LLMStat[];
  totals: LLMStat;
}) {
  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <p className="text-xs text-slate-500">Total LLM Calls</p>
          <p className="text-2xl font-bold text-slate-100 tabular-nums mt-1">
            {totals.n_calls}
          </p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <p className="text-xs text-slate-500">Total Tokens</p>
          <p className="text-2xl font-bold text-slate-100 tabular-nums mt-1">
            {totals.total_tokens.toLocaleString()}
          </p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <p className="text-xs text-slate-500">Avg Latency</p>
          <p className="text-2xl font-bold text-slate-100 tabular-nums mt-1">
            {totals.avg_latency_ms?.toFixed(0) ?? '—'} ms
          </p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <p className="text-xs text-slate-500">Estimated Cost</p>
          <p className="text-2xl font-bold tabular-nums mt-1">
            {totals.total_cost_usd === 0 ? (
              <span className="text-emerald-400">$0.00</span>
            ) : (
              <span className="text-slate-100">
                ${totals.total_cost_usd.toFixed(4)}
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Per-agent table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-800">
              {['Agent', 'Calls', 'Prompt Tokens', 'Completion Tokens', 'Total', 'Avg Latency', 'Cost'].map(
                (h) => (
                  <th
                    key={h}
                    className="text-left py-2 px-3 text-xs font-semibold text-slate-500 uppercase tracking-wider"
                  >
                    {h}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody>
            {stats.map((s) => (
              <tr
                key={s.agent_name}
                className="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors"
              >
                <td className="py-2.5 px-3 text-xs text-slate-300">
                  {agentLabel(s.agent_name)}
                </td>
                <td className="py-2.5 px-3 text-xs text-slate-400 tabular-nums">
                  {s.n_calls}
                </td>
                <td className="py-2.5 px-3 text-xs text-slate-400 tabular-nums">
                  {s.total_prompt_tokens.toLocaleString()}
                </td>
                <td className="py-2.5 px-3 text-xs text-slate-400 tabular-nums">
                  {s.total_completion_tokens.toLocaleString()}
                </td>
                <td className="py-2.5 px-3 text-xs text-slate-300 font-medium tabular-nums">
                  {s.total_tokens.toLocaleString()}
                </td>
                <td className="py-2.5 px-3 text-xs text-slate-400 tabular-nums">
                  {s.avg_latency_ms?.toFixed(0) ?? '—'} ms
                </td>
                <td className="py-2.5 px-3">
                  <CostBadge cost={s.total_cost_usd} />
                </td>
              </tr>
            ))}

            {/* Totals row */}
            <tr className="border-t-2 border-slate-700 bg-slate-800/30">
              <td className="py-2.5 px-3 text-xs font-semibold text-slate-200">
                Total
              </td>
              <td className="py-2.5 px-3 text-xs font-semibold text-slate-300 tabular-nums">
                {totals.n_calls}
              </td>
              <td className="py-2.5 px-3 text-xs font-semibold text-slate-300 tabular-nums">
                {totals.total_prompt_tokens.toLocaleString()}
              </td>
              <td className="py-2.5 px-3 text-xs font-semibold text-slate-300 tabular-nums">
                {totals.total_completion_tokens.toLocaleString()}
              </td>
              <td className="py-2.5 px-3 text-xs font-semibold text-slate-100 tabular-nums">
                {totals.total_tokens.toLocaleString()}
              </td>
              <td className="py-2.5 px-3 text-xs font-semibold text-slate-300 tabular-nums">
                —
              </td>
              <td className="py-2.5 px-3">
                <CostBadge cost={totals.total_cost_usd} />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p className="text-xs text-slate-600">
        Cost is estimated based on public pricing. Groq free-tier calls are shown as $0.00.
      </p>
    </div>
  );
}
