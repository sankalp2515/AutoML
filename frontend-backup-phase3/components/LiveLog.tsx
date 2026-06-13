'use client';
import { useEffect, useRef } from 'react';
import type { ProgressMessage } from '@/lib/types';

const AGENT_COLORS: Record<string, string> = {
  data_auditor: 'bg-blue-500/20 text-blue-300',
  problem_framer: 'bg-purple-500/20 text-purple-300',
  baseline_builder: 'bg-cyan-500/20 text-cyan-300',
  eda_agent: 'bg-teal-500/20 text-teal-300',
  preprocessor: 'bg-yellow-500/20 text-yellow-300',
  feature_engineer: 'bg-orange-500/20 text-orange-300',
  model_selector: 'bg-rose-500/20 text-rose-300',
  tuner: 'bg-fuchsia-500/20 text-fuchsia-300',
  evaluator: 'bg-violet-500/20 text-violet-300',
  exporter: 'bg-emerald-500/20 text-emerald-300',
  orchestrator: 'bg-slate-500/20 text-slate-400',
};

function agentLabel(agent: string): string {
  return agent.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

function DataBadge({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(
    ([, v]) => v !== null && v !== undefined && typeof v !== 'object'
  );
  if (!entries.length) return null;

  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {entries.slice(0, 6).map(([k, v]) => (
        <span
          key={k}
          className="text-xs bg-slate-800 text-slate-400 rounded px-2 py-0.5 font-mono"
        >
          {k}: <span className="text-slate-300">{String(v)}</span>
        </span>
      ))}
    </div>
  );
}

export default function LiveLog({
  messages,
  isConnected,
}: {
  messages: ProgressMessage[];
  isConnected: boolean;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800 flex-shrink-0">
        <div
          className={`w-2 h-2 rounded-full ${
            isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'
          }`}
        />
        <span className="text-xs font-medium text-slate-400">
          {isConnected ? 'Live — receiving updates' : 'Disconnected'}
        </span>
        <span className="ml-auto text-xs text-slate-600">
          {messages.length} messages
        </span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 font-mono text-sm">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-slate-600 space-y-2">
            <div className="text-2xl">⌛</div>
            <p className="text-xs">Waiting for pipeline to start…</p>
          </div>
        ) : (
          messages.map((msg, i) => {
            const colorClass =
              AGENT_COLORS[msg.agent] || 'bg-slate-800/50 text-slate-400';
            return (
              <div key={i} className="group">
                <div className="flex items-start gap-2.5">
                  {/* Agent badge */}
                  <span
                    className={`flex-shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wider ${colorClass}`}
                  >
                    {agentLabel(msg.agent)}
                  </span>

                  {/* Message */}
                  <div className="flex-1 min-w-0">
                    <span className="text-slate-300 text-xs leading-relaxed">
                      {msg.message}
                    </span>
                    {msg.data && Object.keys(msg.data).length > 0 && (
                      <DataBadge data={msg.data} />
                    )}
                  </div>

                  {/* Timestamp */}
                  <span className="text-[10px] text-slate-700 flex-shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    {formatTime(msg.timestamp)}
                  </span>
                </div>
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
