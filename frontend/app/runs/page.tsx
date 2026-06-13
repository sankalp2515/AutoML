'use client';
import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { listRuns } from '@/lib/api';
import type { Run } from '@/lib/types';

function StatusMark({ status }: { status: string }) {
  const map: Record<string, { color: string; label: string }> = {
    queued: { color: 'text-bone-ghost border-bone/15', label: 'Queued' },
    running: { color: 'text-gold-400 border-gold-500/40', label: 'In Progress' },
    completed: { color: 'text-jade-400 border-jade-500/40', label: 'Complete' },
    failed: { color: 'text-terra-400 border-terra-500/40', label: 'Failed' },
  };
  const m = map[status] ?? map.queued;
  return (
    <span
      className={`inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] border rounded-full px-3 py-1 ${m.color}`}
    >
      {status === 'running' && (
        <span className="w-1.5 h-1.5 rounded-full bg-gold-400 animate-breathe" />
      )}
      {m.label}
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
    const id = setInterval(fetchRuns, 5000);
    return () => clearInterval(id);
  }, [fetchRuns]);

  return (
    <div className="max-w-6xl mx-auto px-6 lg:px-8 py-12 space-y-10">
      {/* Header */}
      <div className="flex items-end justify-between animate-fade-up">
        <div className="space-y-2">
          <p className="eyebrow">The Gallery</p>
          <h1 className="font-display text-4xl text-bone tracking-tight">
            Commissioned Works
          </h1>
          <p className="font-mono text-[11px] text-bone-ghost uppercase tracking-[0.18em]">
            {total} piece{total !== 1 ? 's' : ''} in the collection
          </p>
        </div>
        <Link href="/" className="btn-gold font-mono text-[11px] uppercase tracking-[0.18em] px-6 py-3">
          + New Commission
        </Link>
      </div>

      {/* List */}
      {loading ? (
        <div className="flex items-center justify-center h-48">
          <span className="font-mono text-[11px] uppercase tracking-luxe text-bone-ghost animate-pulse">
            Retrieving…
          </span>
        </div>
      ) : error ? (
        <div className="text-terra-300 text-sm font-normal bg-terra-900/30 border border-terra-500/25 rounded-xl px-5 py-4">
          ◆ {error}
        </div>
      ) : runs.length === 0 ? (
        <div className="lux-card flex flex-col items-center justify-center py-20 space-y-4">
          <span className="font-display text-4xl text-gold-700 italic">∅</span>
          <p className="font-display text-lg text-bone-dim">The gallery awaits its first piece.</p>
          <Link href="/" className="font-mono text-[11px] uppercase tracking-luxe text-gold-400 hover:text-gold-300 transition-colors">
            Commission one →
          </Link>
        </div>
      ) : (
        <div className="space-y-3 animate-fade-up" style={{ animationDelay: '100ms' }}>
          {runs.map((run, i) => (
            <Link
              key={run.id}
              href={`/runs/${run.id}`}
              className="lux-card hover-lift group flex items-center gap-6 px-7 py-5"
            >
              {/* Index */}
              <span className="font-display text-2xl text-gold-700/70 italic w-10 flex-shrink-0 group-hover:text-gold-500 transition-colors">
                {String(total - i).padStart(2, '0')}
              </span>

              {/* Goal + meta */}
              <div className="flex-1 min-w-0">
                <p className="font-display text-lg text-bone truncate group-hover:text-gold-200 transition-colors">
                  {run.user_goal}
                </p>
                <div className="flex items-center gap-4 mt-1 font-mono text-[11px] text-bone-ghost uppercase tracking-wider">
                  <span>{run.dataset_filename}</span>
                  {run.task_type && <span className="text-gold-700">{run.task_type.replace(/_/g, ' ')}</span>}
                  <span>{timeAgo(run.created_at)}</span>
                </div>
              </div>

              {/* Model */}
              <div className="hidden md:block text-right flex-shrink-0 w-40">
                <p className="font-mono text-[11px] text-bone-dim truncate">
                  {run.winner_model ?? '—'}
                </p>
                <p className="font-mono text-[11px] text-bone-ghost mt-0.5">
                  {run.iteration_count ?? 0} iteration{run.iteration_count !== 1 ? 's' : ''}
                </p>
              </div>

              {/* Score */}
              <div className="text-right flex-shrink-0 w-24">
                {run.final_score != null ? (
                  <>
                    <p className="font-display text-2xl text-gold-300 tabular-nums leading-none">
                      {run.final_score.toFixed(3)}
                    </p>
                    <p className="font-mono text-[11px] text-bone-ghost uppercase tracking-luxe mt-1">
                      {run.primary_metric}
                    </p>
                  </>
                ) : (
                  <span className="font-display text-xl text-bone-ghost">—</span>
                )}
              </div>

              {/* Status */}
              <div className="flex-shrink-0">
                <StatusMark status={run.status} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
