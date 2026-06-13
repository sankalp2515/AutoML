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

type Tab = 'progress' | 'results' | 'notebook' | 'deploy' | 'artifacts' | 'llm';

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'progress', label: 'Live Progress', icon: '📡' },
  { id: 'results', label: 'Results', icon: '📈' },
  { id: 'notebook', label: 'Notebook', icon: '📓' },
  { id: 'deploy', label: 'Deploy', icon: '🚀' },
  { id: 'artifacts', label: 'Artifacts', icon: '📦' },
  { id: 'llm', label: 'LLM Stats', icon: '🧠' },
];

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    queued: 'bg-slate-700 text-slate-300',
    running: 'bg-blue-500/20 text-blue-300 animate-pulse',
    completed: 'bg-emerald-500/20 text-emerald-300',
    failed: 'bg-rose-500/20 text-rose-400',
  };
  const icons: Record<string, string> = {
    queued: '⏳',
    running: '⚡',
    completed: '✅',
    failed: '❌',
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
        styles[status] ?? 'bg-slate-700 text-slate-300'
      }`}
    >
      <span>{icons[status] ?? '?'}</span>
      {status}
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
  return <span className="text-xs text-slate-500">{elapsed}</span>;
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
        <p className="text-rose-400">{error}</p>
        <Link href="/runs" className="text-sm text-violet-400 hover:underline">
          ← Back to runs
        </Link>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-500 text-sm animate-pulse">Loading run…</div>
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
          <div className="flex items-center gap-2 text-xs text-slate-600 mb-1">
            <Link href="/runs" className="hover:text-slate-400">
              Runs
            </Link>
            <span>/</span>
            <span className="font-mono text-slate-500 truncate">{runId}</span>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <StatusBadge status={run.status} />
            <span className="text-sm text-slate-300 font-medium truncate max-w-md">
              {run.user_goal}
            </span>
          </div>
          <div className="flex items-center gap-4 mt-1.5 flex-wrap">
            <span className="text-xs text-slate-600">📁 {run.dataset_filename}</span>
            {run.target_column && (
              <span className="text-xs text-slate-600">
                🎯 {run.target_column}
              </span>
            )}
            {run.task_type && (
              <span className="text-xs text-violet-500 bg-violet-500/10 rounded px-1.5 py-0.5">
                {run.task_type}
              </span>
            )}
            <ElapsedTimer createdAt={run.created_at} status={run.status} />
            {run.mlflow_run_id && (
              <a
                href={`http://localhost:5000`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-slate-600 hover:text-violet-400 transition-colors"
              >
                MLflow ↗
              </a>
            )}
          </div>
        </div>

        {/* Quick score display on completion */}
        {isCompleted && run.final_score != null && (
          <div className="flex-shrink-0 text-right">
            <p className="text-xs text-slate-500">
              {run.primary_metric ?? 'score'}
            </p>
            <p className="text-3xl font-bold text-violet-300 tabular-nums">
              {run.final_score.toFixed(4)}
            </p>
            {run.winner_model && (
              <p className="text-xs text-slate-500 mt-0.5">{run.winner_model}</p>
            )}
          </div>
        )}
      </div>

      {/* ── Failed error banner ─────────────────────────────────────────────── */}
      {run.status === 'failed' && run.error_message && (
        <div className="bg-rose-500/10 border border-rose-500/20 rounded-lg px-4 py-3 text-sm text-rose-400">
          ⚠ {run.error_message}
        </div>
      )}

      {/* ── Main layout: timeline + content ─────────────────────────────────── */}
      <div className="flex gap-5">
        {/* Left: Agent Timeline */}
        <aside className="w-56 flex-shrink-0 hidden sm:block">
          <div className="glass-card p-3 sticky top-20">
            <p className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-3 px-1">
              Pipeline
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
          <div className="flex items-center gap-1 border-b border-slate-800 pb-0">
            {TABS.map((t) => {
              const isDisabled =
                (t.id === 'results' && !results && !isCompleted) ||
                (t.id === 'notebook' && !isCompleted) ||
                (t.id === 'deploy' && !isCompleted) ||
                (t.id === 'artifacts' && artifacts.length === 0 && !isCompleted) ||
                (t.id === 'llm' && !llmStats && !isCompleted);
              return (
                <button
                  key={t.id}
                  onClick={() => !isDisabled && setTab(t.id)}
                  className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium border-b-2 -mb-px transition-colors ${
                    tab === t.id
                      ? 'border-violet-500 text-violet-300'
                      : isDisabled
                      ? 'border-transparent text-slate-700 cursor-not-allowed'
                      : 'border-transparent text-slate-500 hover:text-slate-300 hover:border-slate-600'
                  }`}
                >
                  <span>{t.icon}</span>
                  {t.label}
                </button>
              );
            })}
          </div>

          {/* Tab content */}
          <div className="glass-card overflow-hidden">
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
                  <div className="flex items-center justify-center h-32 text-slate-600 text-sm">
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
                  <div className="flex items-center justify-center h-32 text-slate-600 text-sm">
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
    <div className="border border-slate-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-slate-800/20 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-300">
            🧾 Decision Log
          </span>
          <span className="text-xs text-slate-600">
            {logs.length} decisions
          </span>
        </div>
        <span
          className={`text-slate-500 transition-transform ${
            open ? 'rotate-180' : ''
          }`}
        >
          ▼
        </span>
      </button>

      {open && (
        <div className="border-t border-slate-800">
          <div className="p-3 border-b border-slate-800">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter decisions…"
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-300 placeholder-slate-600 focus:outline-none focus:border-violet-500"
            />
          </div>
          <div className="divide-y divide-slate-800 max-h-96 overflow-y-auto">
            {filtered.map((log, i) => (
              <div key={i} className="px-5 py-3 hover:bg-slate-800/20">
                <div className="flex items-start gap-3">
                  <span className="text-[10px] text-violet-500 bg-violet-500/10 rounded px-1.5 py-0.5 flex-shrink-0 mt-0.5 uppercase">
                    {log.agent_name.replace(/_/g, ' ')}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-slate-200">{log.decision}</p>
                    <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">
                      {log.reasoning}
                    </p>
                    {log.result_summary && (
                      <p className="text-xs text-slate-500 mt-1 font-mono">
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
