import type { LLMStat } from '@/lib/types';

function agentLabel(name: string) {
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function CostBadge({ cost }: { cost: number }) {
  if (cost === 0)
    return (
      <span className="text-xs text-jade-500 bg-jade-500/10 rounded px-1.5 py-0.5">
        Free
      </span>
    );
  return (
    <span className="text-xs text-bone-dim font-mono">
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
        <div className="bg-obsidian-900 border border-bone/10 rounded-xl p-4">
          <p className="text-xs text-bone-faint">Total LLM Calls</p>
          <p className="text-2xl font-bold text-bone tabular-nums mt-1">
            {totals.n_calls}
          </p>
        </div>
        <div className="bg-obsidian-900 border border-bone/10 rounded-xl p-4">
          <p className="text-xs text-bone-faint">Total Tokens</p>
          <p className="text-2xl font-bold text-bone tabular-nums mt-1">
            {totals.total_tokens.toLocaleString()}
          </p>
        </div>
        <div className="bg-obsidian-900 border border-bone/10 rounded-xl p-4">
          <p className="text-xs text-bone-faint">Avg Latency</p>
          <p className="text-2xl font-bold text-bone tabular-nums mt-1">
            {totals.avg_latency_ms?.toFixed(0) ?? '—'} ms
          </p>
        </div>
        <div className="bg-obsidian-900 border border-bone/10 rounded-xl p-4">
          <p className="text-xs text-bone-faint">Estimated Cost</p>
          <p className="text-2xl font-bold tabular-nums mt-1">
            {totals.total_cost_usd === 0 ? (
              <span className="text-jade-400">$0.00</span>
            ) : (
              <span className="text-bone">
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
            <tr className="border-b border-bone/10">
              {['Agent', 'Calls', 'Prompt Tokens', 'Completion Tokens', 'Total', 'Avg Latency', 'Cost'].map(
                (h) => (
                  <th
                    key={h}
                    className="text-left py-2 px-3 text-xs font-semibold text-bone-faint uppercase tracking-wider"
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
                className="border-b border-bone/5 hover:bg-obsidian-700/20 transition-colors"
              >
                <td className="py-2.5 px-3 text-xs text-bone-dim">
                  {agentLabel(s.agent_name)}
                </td>
                <td className="py-2.5 px-3 text-xs text-bone-dim tabular-nums">
                  {s.n_calls}
                </td>
                <td className="py-2.5 px-3 text-xs text-bone-dim tabular-nums">
                  {s.total_prompt_tokens.toLocaleString()}
                </td>
                <td className="py-2.5 px-3 text-xs text-bone-dim tabular-nums">
                  {s.total_completion_tokens.toLocaleString()}
                </td>
                <td className="py-2.5 px-3 text-xs text-bone-dim font-medium tabular-nums">
                  {s.total_tokens.toLocaleString()}
                </td>
                <td className="py-2.5 px-3 text-xs text-bone-dim tabular-nums">
                  {s.avg_latency_ms?.toFixed(0) ?? '—'} ms
                </td>
                <td className="py-2.5 px-3">
                  <CostBadge cost={s.total_cost_usd} />
                </td>
              </tr>
            ))}

            {/* Totals row */}
            <tr className="border-t-2 border-bone/15 bg-obsidian-700/30">
              <td className="py-2.5 px-3 text-xs font-semibold text-bone">
                Total
              </td>
              <td className="py-2.5 px-3 text-xs font-semibold text-bone-dim tabular-nums">
                {totals.n_calls}
              </td>
              <td className="py-2.5 px-3 text-xs font-semibold text-bone-dim tabular-nums">
                {totals.total_prompt_tokens.toLocaleString()}
              </td>
              <td className="py-2.5 px-3 text-xs font-semibold text-bone-dim tabular-nums">
                {totals.total_completion_tokens.toLocaleString()}
              </td>
              <td className="py-2.5 px-3 text-xs font-semibold text-bone tabular-nums">
                {totals.total_tokens.toLocaleString()}
              </td>
              <td className="py-2.5 px-3 text-xs font-semibold text-bone-dim tabular-nums">
                —
              </td>
              <td className="py-2.5 px-3">
                <CostBadge cost={totals.total_cost_usd} />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p className="text-xs text-bone-faint">
        Cost is estimated based on public pricing. Groq free-tier calls are shown as $0.00.
      </p>
    </div>
  );
}
