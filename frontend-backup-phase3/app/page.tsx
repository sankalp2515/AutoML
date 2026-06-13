import Link from 'next/link';
import UploadForm from '@/components/UploadForm';

const FEATURES = [
  {
    icon: '🧠',
    title: 'Fully Agentic',
    desc: '10 specialized AI agents — from data audit to model export — run autonomously and explain every decision.',
  },
  {
    icon: '🔬',
    title: 'Evidence Notebook',
    desc: 'LLM-generated Jupyter notebook captures every executed code cell and writes adaptive narrative per problem type.',
  },
  {
    icon: '📊',
    title: 'Full Observability',
    desc: 'Prometheus metrics, Grafana dashboards, MLflow experiment tracking, and per-agent LLM cost breakdown.',
  },
  {
    icon: '⚡',
    title: 'Production Ready',
    desc: 'Outputs a FastAPI inference server, packaged inference pipeline, and model card — ready to deploy.',
  },
];

export default function HomePage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-12">
      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <div className="text-center space-y-5 pt-6 animate-fade-up">
        <div className="inline-flex items-center gap-2 glass text-violet-300 text-xs font-medium px-4 py-1.5 rounded-full">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-60" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-400" />
          </span>
          v1 · 10 agents · GPU-accelerated · full observability
        </div>
        <h1 className="text-5xl sm:text-6xl font-bold text-white tracking-tighter leading-[1.05]">
          Drop CSV. <span className="text-gradient">Describe Goal.</span>
          <br />
          Get a Production Model.
        </h1>
        <p className="text-slate-400 text-lg max-w-2xl mx-auto leading-relaxed">
          Ten AI agents audit your data, engineer features, train and tune models —
          then hand you a deployable inference pipeline, a narrated evidence notebook,
          and a live prediction endpoint with drift monitoring.
        </p>
      </div>

      {/* ── Upload card ────────────────────────────────────────────────────── */}
      <div className="max-w-2xl mx-auto animate-fade-up" style={{ animationDelay: '120ms' }}>
        <div className="glass-card p-6 ring-1 ring-violet-500/10">
          <div className="flex items-center gap-2 mb-6">
            <div className="w-2 h-2 rounded-full bg-rose-500/90" />
            <div className="w-2 h-2 rounded-full bg-amber-500/90" />
            <div className="w-2 h-2 rounded-full bg-emerald-500/90" />
            <span className="ml-2 text-xs text-slate-600 font-mono">automl-orchestrator — new run</span>
          </div>
          <UploadForm />
        </div>
      </div>

      {/* ── Pipeline steps ──────────────────────────────────────────────────── */}
      <div className="max-w-4xl mx-auto">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-widest text-center mb-6">
          What happens after you click Start
        </h2>
        <div className="flex flex-wrap justify-center gap-2">
          {[
            ['🔍', 'Data Audit'],
            ['🎯', 'Problem Frame'],
            ['📐', 'Baseline'],
            ['📊', 'EDA'],
            ['⚙️', 'Preprocess'],
            ['🔧', 'Feature Eng.'],
            ['🤖', 'Model Select'],
            ['🎛️', 'Tune'],
            ['📈', 'Evaluate'],
            ['📦', 'Export'],
          ].map(([icon, label], i) => (
            <div key={label} className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-400">
                <span>{icon}</span>
                <span>{label}</span>
              </div>
              {i < 9 && <span className="text-slate-700 text-xs">→</span>}
            </div>
          ))}
        </div>
      </div>

      {/* ── Features grid ───────────────────────────────────────────────────── */}
      <div className="max-w-4xl mx-auto grid grid-cols-1 sm:grid-cols-2 gap-4">
        {FEATURES.map((f) => (
          <div
            key={f.title}
            className="glass-card hover-lift p-5 space-y-2"
          >
            <div className="text-2xl">{f.icon}</div>
            <h3 className="text-sm font-semibold text-slate-200">{f.title}</h3>
            <p className="text-xs text-slate-500 leading-relaxed">{f.desc}</p>
          </div>
        ))}
      </div>

      {/* ── Observability links ─────────────────────────────────────────────── */}
      <div className="max-w-2xl mx-auto text-center space-y-3">
        <p className="text-xs text-slate-600">
          Observability stack running alongside
        </p>
        <div className="flex justify-center gap-3">
          {[
            { label: '📊 MLflow', url: 'http://localhost:5000', desc: 'Experiments' },
            { label: '📡 Grafana', url: 'http://localhost:3001', desc: 'Dashboards' },
            { label: '🔥 Prometheus', url: 'http://localhost:9090', desc: 'Metrics' },
          ].map((link) => (
            <a
              key={link.url}
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex flex-col items-center gap-0.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 rounded-xl px-4 py-3 transition-colors"
            >
              <span className="text-xs font-medium text-slate-300">{link.label}</span>
              <span className="text-[10px] text-slate-600">{link.desc}</span>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
