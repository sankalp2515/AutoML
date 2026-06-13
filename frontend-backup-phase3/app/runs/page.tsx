'use client';
import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { listRuns } from '@/lib/api';
import type { Run } from '@/lib/types';

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    queued: 'bg-slate-700 text-slate-300',
    running: 'bg-blue-500/20 text-blue-300',
    completed: 'bg-emerald-500/20 text-emerald-400',
    failed: 'bg-rose-500/20 text-rose-400',
  };
  const icons: Record<string, string> = {
    queued: '⏳', running: '⚡', completed: '✅', failed: '❌',
  };
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${map[status] ?? map.queued}`}>
      {icons[status] ?? '?'} {status}
    </span>
  );
}

function timeAgo(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function ScoreDelta({ final, baseline }: { final: number | null; baseline: number | null }) {
  if (final == null || baseline == null) return <span className="text-slate-600">—</span>;
  const delta = final - baseline;
  return (
    <span className={`text-xs font-mono ${delta >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
      {delta >= 0 ? '+' : ''}{delta.toFixed(3)}
    </span>
  );
}

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRuns = useCallback(async () => {
    try {
      const data = await listRuns(0, 50);
      setRuns(data.runs);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load runs');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRuns();
    // Auto-refresh while any run is active
    const id = setInterval(() => {
      fetchRuns();
    }, 5000);
    return () => clearInterval(id);
  }, [fetchRuns]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Run History</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {total} total run{total !== 1 ? 's' : ''}
          </p>
        </div>
        <Link
          href="/"
          className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          + New Run
        </Link>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center h-48 text-slate-600 animate-pulse text-sm">
          Loading runs…
        </div>
      ) : error ? (
        <div className="text-rose-400 text-sm bg-rose-500/10 border border-rose-500/20 rounded-lg px-4 py-3">
          ⚠ {error}
        </div>
      ) : runs.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-48 text-slate-600 space-y-3">
          <div className="text-4xl">🤖</div>
          <p className="text-sm">No runs yet.</p>
          <Link href="/" className="text-sm text-violet-400 hover:underline">
            Start your first AutoML run →
          </Link>
        </div>
      ) : (
        <div className="bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden">
          {/* Table header */}
          <div className="grid grid-cols-[1fr_80px_120px_100px_90px_80px_80px_80px] gap-3 px-5 py-3 border-b border-slate-800 text-xs font-semibold text-slate-500 uppercase tracking-wider">
            <span>Goal</span>
            <span>Status</span>
            <span>Dataset</span>
            <span>Model</span>
            <span className="text-center">Score</span>
            <span className="text-center">Δ</span>
            <span className="text-center">Iters</span>
            <span className="text-right">Age</span>
          </div>

          {/* Rows */}
          <div className="divide-y divide-slate-800/60">
            {runs.map((run) => (
              <Link
                key={run.id}
                href={`/runs/${run.id}`}
                className="grid grid-cols-[1fr_80px_120px_100px_90px_80px_80px_80px] gap-3 px-5 py-3.5 items-center hover:bg-slate-800/30 transition-colors group"
              >
                {/* Goal */}
                <div className="min-w-0">
                  <p className="text-sm text-slate-200 truncate group-hover:text-violet-300 transition-colors">
                    {run.user_goal}
                  </p>
                  <p className="text-xs text-slate-600 font-mono mt-0.5 truncate">
                    {run.id.slice(0, 8)}…
                    {run.target_column && (
                      <span className="ml-2 text-slate-600">→ {run.target_column}</span>
                    )}
                  </p>
                </div>

                {/* Status */}
                <div>
                  <StatusBadge status={run.status} />
                </div>

                {/* Dataset */}
                <div className="text-xs text-slate-500 truncate">{run.dataset_filename}</div>

                {/* Model */}
                <div className="text-xs text-slate-400 truncate">
                  {run.winner_model ?? '—'}
                </div>

                {/* Score */}
                <div className="text-center">
                  {run.final_score != null ? (
                    <span className="text-sm font-semibold text-violet-300 tabular-nums">
                      {run.final_score.toFixed(4)}
                    </span>
                  ) : (
                    <span className="text-slate-600 text-sm">—</span>
                  )}
                  {run.primary_metric && (
                    <p className="text-[10px] text-slate-600">{run.primary_metric}</p>
                  )}
                </div>

                {/* Delta */}
                <div className="text-center">
                  <ScoreDelta final={run.final_score} baseline={run.baseline_score} />
                </div>

                {/* Iterations */}
                <div className="text-center text-xs text-slate-500">
                  {run.iteration_count ?? '—'}
                </div>

                {/* Age */}
                <div className="text-right text-xs text-slate-600">
                  {timeAgo(run.created_at)}
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Stats bar */}
      {runs.length > 0 && (
        <div className="flex flex-wrap gap-6 text-xs text-slate-600">
          <span>
            ✅ {runs.filter((r) => r.status === 'completed').length} completed
          </span>
          <span>
            ⚡ {runs.filter((r) => r.status === 'running').length} running
          </span>
          <span>
            ❌ {runs.filter((r) => r.status === 'failed').length} failed
          </span>
          {runs.some((r) => r.final_score != null) && (
            <span>
              🏆 Best:{' '}
              {Math.max(
                ...runs
                  .filter((r) => r.final_score != null)
                  .map((r) => r.final_score!)
              ).toFixed(4)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
