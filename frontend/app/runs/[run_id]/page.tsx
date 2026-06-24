'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  getRun,
  getResults,
  listArtifacts,
  getLLMStats,
  connectWebSocket,
  API_BASE,
} from '@/lib/api';
import type {
  RunDetail,
  Results,
  Artifact,
  LLMStat,
  ProgressMessage,
} from '@/lib/types';
import AgentTimeline from '@/components/AgentTimeline';
import LiveLog from '@/components/LiveLog';
import MetricsPanel from '@/components/MetricsPanel';
import ArtifactsPanel from '@/components/ArtifactsPanel';
import LLMStatsPanel from '@/components/LLMStatsPanel';
import NotebookViewer from '@/components/NotebookViewer';
import DeployPanel from '@/components/DeployPanel';
import ModelToolsPanel from '@/components/ModelToolsPanel';

type Tab = 'progress' | 'results' | 'notebook' | 'deploy' | 'tools' | 'artifacts' | 'llm';

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'progress', label: 'Live Progress', icon: '📡' },
  { id: 'results', label: 'Results', icon: '📈' },
  { id: 'notebook', label: 'Notebook', icon: '📓' },
  { id: 'deploy', label: 'Deploy', icon: '🚀' },
  { id: 'tools', label: 'Tools', icon: '🛠' },
  { id: 'artifacts', label: 'Artifacts', icon: '📦' },
  { id: 'llm', label: 'LLM Stats', icon: '🧠' },
];

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    queued: 'text-bone-ghost border-bone/15',
    running: 'text-gold-300 border-gold-500/40',
    completed: 'text-jade-300 border-jade-500/40',
    failed: 'text-terra-400 border-terra-500/40',
  };
  const labels: Record<string, string> = {
    queued: 'Queued',
    running: 'In Progress',
    completed: 'Complete',
    failed: 'Failed',
  };
  return (
    <span
      className={`inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] border rounded-full px-3 py-1 ${
        styles[status] ?? styles.queued
      }`}
    >
      {status === 'running' && (
        <span className="w-1.5 h-1.5 rounded-full bg-gold-400 animate-breathe" />
      )}
      {labels[status] ?? status}
    </span>
  );
}

function ElapsedTimer({ createdAt, status }: { createdAt: string; status: string }) {
  const [elapsed, setElapsed] = useState('');
  useEffect(() => {
    const update = () => {
      const s = Math.floor((Date.now() - new Date(createdAt).getTime()) / 1000);
      if (s < 60) setElapsed(`${s}s`);
      else if (s < 3600) setElapsed(`${Math.floor(s / 60)}m ${s % 60}s`);
      else setElapsed(`${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`);
    };
    update();
    if (status === 'running' || status === 'queued') {
      const id = setInterval(update, 1000);
      return () => clearInterval(id);
    }
  }, [createdAt, status]);
  return <span className="text-xs text-bone-faint">{elapsed}</span>;
}

export default function RunPage() {
  const params = useParams<{ run_id: string }>();
  const runId = params.run_id;

  const [run, setRun] = useState<RunDetail | null>(null);
  const [messages, setMessages] = useState<ProgressMessage[]>([]);
  const [isWsConnected, setIsWsConnected] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | undefined>(undefined);
  const [tab, setTab] = useState<Tab>('progress');
  const [results, setResults] = useState<Results | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [llmStats, setLlmStats] = useState<{ stats: LLMStat[]; totals: LLMStat } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Fetch run detail ───────────────────────────────────────────────────────
  const fetchRun = useCallback(async () => {
    try {
      const data = await getRun(runId);
      setRun(data);
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load run');
      return null;
    }
  }, [runId]);

  // ── Fetch completion data ──────────────────────────────────────────────────
  const fetchCompletionData = useCallback(async () => {
    try {
      const [res, arts, stats] = await Promise.all([
        getResults(runId).catch(() => null),
        listArtifacts(runId).catch(() => [] as Artifact[]),
        getLLMStats(runId).catch(() => null),
      ]);
      if (res) setResults(res);
      setArtifacts(arts);
      if (stats) setLlmStats(stats);
    } catch {}
  }, [runId]);

  // ── WebSocket ──────────────────────────────────────────────────────────────
  const connectWS = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = connectWebSocket(
      runId,
      (msg) => {
        // Skip control frames (connected / heartbeat / pong) — only render
        // actual agent progress messages
        if (!msg.agent || !msg.message) return;
        const pm = msg as unknown as ProgressMessage;
        setMessages((prev) => [...prev, pm]);
        if (pm.agent && pm.agent !== 'orchestrator') {
          setActiveAgent(pm.agent);
        }
        // If this is a terminal message, trigger run refresh
        if (
          typeof pm.message === 'string' &&
          (pm.message.includes('completed') || pm.message.includes('failed'))
        ) {
          fetchRun().then((updated) => {
            if (
              updated?.status === 'completed' ||
              updated?.status === 'failed'
            ) {
              fetchCompletionData();
              setTab('results');
              setActiveAgent(undefined);
            }
          });
        }
      },
      () => {
        setIsWsConnected(false);
        // Reconnect after 2s if still running
        setTimeout(() => {
          if (wsRef.current?.readyState !== WebSocket.OPEN) connectWS();
        }, 2000);
      }
    );
    ws.onopen = () => setIsWsConnected(true);
    wsRef.current = ws;
  }, [runId, fetchRun, fetchCompletionData]);

  // ── Mount ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    fetchRun().then((initial) => {
      if (!initial) return;
      if (initial.status === 'running' || initial.status === 'queued') {
        connectWS();
        // Poll agent steps every 4s while running
        pollRef.current = setInterval(() => fetchRun(), 4000);
      } else if (
        initial.status === 'completed' ||
        initial.status === 'failed'
      ) {
        fetchCompletionData();
        setTab('results');
      }
    });

    return () => {
      wsRef.current?.close();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [runId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Stop polling once run finishes
  useEffect(() => {
    if (run?.status === 'completed' || run?.status === 'failed') {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
  }, [run?.status]);

  // ── Render ─────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-12 text-center space-y-4">
        <div className="text-5xl">❌</div>
        <p className="text-terra-400">{error}</p>
        <Link href="/runs" className="text-sm text-gold-400 hover:underline">
          ← Back to runs
        </Link>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-bone-faint text-sm animate-pulse">Loading run…</div>
      </div>
    );
  }

  const isActive = run.status === 'running' || run.status === 'queued';
  const isCompleted = run.status === 'completed';

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-xs text-bone-faint mb-1">
            <Link href="/runs" className="hover:text-bone-dim">
              Runs
            </Link>
            <span>/</span>
            <span className="font-mono text-bone-faint truncate">{runId}</span>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <StatusBadge status={run.status} />
            <span className="text-sm text-bone-dim font-medium truncate max-w-md">
              {run.user_goal}
            </span>
          </div>
          <div className="flex items-center gap-4 mt-1.5 flex-wrap">
            <span className="text-xs text-bone-faint">📁 {run.dataset_filename}</span>
            {run.target_column && (
              <span className="text-xs text-bone-faint">
                🎯 {run.target_column}
              </span>
            )}
            {run.task_type && (
              <span className="text-xs text-gold-500 bg-gold-500/10 rounded px-1.5 py-0.5">
                {run.task_type}
              </span>
            )}
            <ElapsedTimer createdAt={run.created_at} status={run.status} />
            {run.mlflow_run_id && (
              <a
                href={`http://localhost:5000`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-bone-faint hover:text-gold-400 transition-colors"
              >
                MLflow ↗
              </a>
            )}
          </div>
        </div>

        {/* Quick score display on completion */}
        {isCompleted && run.final_score != null && (
          <div className="flex-shrink-0 text-right">
            <p className="eyebrow-dim">
              {run.primary_metric ?? 'score'}
            </p>
            <p className="font-display text-5xl text-gold-300 tabular-nums leading-none mt-1">
              {run.final_score.toFixed(4)}
            </p>
            {run.winner_model && (
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-bone-faint mt-2">{run.winner_model}</p>
            )}
          </div>
        )}
      </div>

      {/* ── Failed error banner ─────────────────────────────────────────────── */}
      {run.status === 'failed' && run.error_message && (
        <div className="bg-terra-500/10 border border-terra-500/20 rounded-lg px-4 py-3 text-sm text-terra-400">
          ⚠ {run.error_message}
        </div>
      )}

      {/* ── Main layout: timeline + content ─────────────────────────────────── */}
      <div className="flex gap-5">
        {/* Left: Agent Timeline */}
        <aside className="w-56 flex-shrink-0 hidden sm:block">
          <div className="lux-card p-3 sticky top-20">
            <p className="eyebrow-dim mb-3 px-1">
              The Process
            </p>
            <AgentTimeline
              steps={run.agent_steps ?? []}
              activeAgent={activeAgent}
            />
          </div>
        </aside>

        {/* Right: Tabs + Content */}
        <div className="flex-1 min-w-0 space-y-4">
          {/* Tab bar */}
          <div className="flex items-center gap-1 border-b border-bone/10 pb-0">
            {TABS.map((t) => {
              const isDisabled =
                (t.id === 'results' && !results && !isCompleted) ||
                (t.id === 'notebook' && !isCompleted) ||
                (t.id === 'deploy' && !isCompleted) ||
                (t.id === 'tools' && !isCompleted) ||
                (t.id === 'artifacts' && artifacts.length === 0 && !isCompleted) ||
                (t.id === 'llm' && !llmStats && !isCompleted);
              return (
                <button
                  key={t.id}
                  onClick={() => !isDisabled && setTab(t.id)}
                  className={`flex items-center gap-1.5 px-4 py-3 font-mono text-[11px] uppercase tracking-[0.16em] border-b -mb-px transition-all duration-300 ${
                    tab === t.id
                      ? 'border-gold-500 text-gold-300'
                      : isDisabled
                      ? 'border-transparent text-bone-ghost/60 cursor-not-allowed'
                      : 'border-transparent text-bone-faint hover:text-bone-dim hover:border-gold-700/50'
                  }`}
                >
                  {t.label}
                </button>
              );
            })}
          </div>

          {/* Tab content */}
          <div className="lux-card overflow-hidden">
            {tab === 'progress' && (
              <div style={{ height: '520px' }}>
                <LiveLog messages={messages} isConnected={isWsConnected} />
              </div>
            )}

            {tab === 'results' && (
              <div className="p-5">
                {results ? (
                  <MetricsPanel results={results} />
                ) : (
                  <div className="flex items-center justify-center h-32 text-bone-faint text-sm">
                    {isActive ? 'Results available after pipeline completes…' : 'Loading results…'}
                  </div>
                )}
              </div>
            )}

            {tab === 'notebook' && (
              <div className="p-5">
                <NotebookViewer runId={runId} />
              </div>
            )}

            {tab === 'deploy' && (
              <div className="p-5">
                <DeployPanel runId={runId} />
              </div>
            )}

            {tab === 'tools' && (
              <div className="p-5">
                <ModelToolsPanel runId={runId} />
              </div>
            )}

            {tab === 'artifacts' && (
              <div className="p-5">
                <ArtifactsPanel artifacts={artifacts} runId={runId} />
              </div>
            )}

            {tab === 'llm' && (
              <div className="p-5">
                {llmStats ? (
                  <LLMStatsPanel stats={llmStats.stats} totals={llmStats.totals} />
                ) : (
                  <div className="flex items-center justify-center h-32 text-bone-faint text-sm">
                    {isActive ? 'LLM stats available after pipeline completes…' : 'Loading LLM stats…'}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Decision log (collapsible) */}
          {run.decision_logs && run.decision_logs.length > 0 && (
            <DecisionLogSection logs={run.decision_logs} />
          )}
        </div>
      </div>
    </div>
  );
}

function DecisionLogSection({ logs }: { logs: RunDetail['decision_logs'] }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');

  const filtered = search
    ? logs.filter(
        (l) =>
          l.decision.toLowerCase().includes(search.toLowerCase()) ||
          l.agent_name.toLowerCase().includes(search.toLowerCase())
      )
    : logs;

  return (
    <div className="border border-bone/10 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-obsidian-700/20 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-bone-dim">
            🧾 Decision Log
          </span>
          <span className="text-xs text-bone-faint">
            {logs.length} decisions
          </span>
        </div>
        <span
          className={`text-bone-faint transition-transform ${
            open ? 'rotate-180' : ''
          }`}
        >
          ▼
        </span>
      </button>

      {open && (
        <div className="border-t border-bone/10">
          <div className="p-3 border-b border-bone/10">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter decisions…"
              className="w-full bg-obsidian-900 border border-bone/10 rounded-lg px-3 py-2 text-xs text-bone-dim placeholder-bone-ghost focus:outline-none focus:border-gold-500"
            />
          </div>
          <div className="divide-y divide-bone/10 max-h-96 overflow-y-auto">
            {filtered.map((log, i) => (
              <div key={i} className="px-5 py-3 hover:bg-obsidian-700/20">
                <div className="flex items-start gap-3">
                  <span className="text-[11px] text-gold-500 bg-gold-500/10 rounded px-1.5 py-0.5 flex-shrink-0 mt-0.5 uppercase">
                    {log.agent_name.replace(/_/g, ' ')}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-bone">{log.decision}</p>
                    <p className="text-xs text-bone-faint mt-0.5 leading-relaxed">
                      {log.reasoning}
                    </p>
                    {log.result_summary && (
                      <p className="text-xs text-bone-faint mt-1 font-mono">
                        → {log.result_summary}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
