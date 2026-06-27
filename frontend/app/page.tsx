import UploadForm from '@/components/UploadForm';

const PILLARS = [
  {
    numeral: 'I',
    title: 'Autonomous Agents',
    desc: 'Ten specialist agents — auditor to exporter — each making and defending its own decisions, every claim verified by execution. When a step hits an edge case, the agent writes and runs its own fix.',
  },
  {
    numeral: 'II',
    title: 'Evidence, Narrated',
    desc: 'A Jupyter notebook written by the system itself: every executed line of code, every result, woven into prose a stakeholder can read.',
  },
  {
    numeral: 'III',
    title: 'Glass-Box Telemetry',
    desc: 'Every metric in MLflow, every second in Prometheus, every token and cent of LLM spend accounted for. Nothing hidden.',
  },
  {
    numeral: 'IV',
    title: 'Living Deployment',
    desc: 'One gesture deploys the model. Live predictions are logged, and drift against training data is measured continuously.',
  },
];

const AGENTS = [
  'Audit', 'Frame', 'Baseline', 'Explore', 'Preprocess',
  'Engineer', 'Select', 'Tune', 'Evaluate', 'Export',
];

export default function HomePage() {
  return (
    <div className="max-w-6xl mx-auto px-6 lg:px-8 py-12 space-y-16">
      {/* ── Hero + action, side by side so the upload is above the fold ────── */}
      <section className="grid lg:grid-cols-2 gap-10 lg:gap-14 items-center pt-2">
        {/* Left — headline */}
        <div className="space-y-5 animate-fade-up">
          <p className="eyebrow">Autonomous Machine Learning</p>
          <h1 className="font-display text-5xl sm:text-6xl text-bone tracking-tight leading-[1.02] font-medium">
            From a CSV to a
            <br />
            <span className="text-gold-shimmer italic">deployed model.</span>
          </h1>
          <p className="text-bone-dim text-base max-w-md leading-[1.8] font-normal">
            Present a dataset and state your goal. Ten agents audit, explore, engineer,
            train, and tune — then return a deployed model with its full reasoning on record.
          </p>
          <div className="flex items-center gap-4 pt-1">
            <span className="h-px w-16 bg-gradient-to-r from-transparent to-gold-600/60" />
            <span className="w-1.5 h-1.5 rotate-45 border border-gold-500/60" />
          </div>
        </div>

        {/* Right — action card (upload) */}
        <div className="animate-fade-up" style={{ animationDelay: '120ms' }}>
          <div className="lux-card-gold corner-ticks p-7">
            <div className="flex items-baseline justify-between mb-7">
              <h2 className="font-display text-2xl text-bone gold-rule">Train a Model</h2>
              <span className="font-mono text-[11px] uppercase tracking-luxe text-bone-ghost">
                CSV · ≤ 500 MB
              </span>
            </div>
            <UploadForm />
          </div>
        </div>
      </section>

      {/* ── The atelier process ───────────────────────────────────────────── */}
      <section className="space-y-8">
        <p className="eyebrow-dim text-center">The Pipeline — 10 Agents</p>
        <div className="flex flex-wrap justify-center items-center gap-y-3">
          {AGENTS.map((label, i) => (
            <div key={label} className="flex items-center">
              <div className="group flex flex-col items-center gap-1.5 px-3">
                <span className="font-mono text-[11px] text-gold-700 group-hover:text-gold-400 transition-colors">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span className="font-display text-base text-bone-dim group-hover:text-bone transition-colors">
                  {label}
                </span>
              </div>
              {i < AGENTS.length - 1 && (
                <span className="h-px w-6 bg-bone/10 hidden sm:block" />
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ── Pillars ───────────────────────────────────────────────────────── */}
      <section className="grid grid-cols-1 sm:grid-cols-2 gap-px bg-bone/[0.07] rounded-2xl overflow-hidden border hairline">
        {PILLARS.map((p) => (
          <div
            key={p.numeral}
            className="bg-obsidian-900/95 p-8 space-y-3 hover:bg-obsidian-850 transition-colors duration-500 group"
          >
            <span className="font-display text-3xl text-gold-700 group-hover:text-gold-500 transition-colors duration-500 italic">
              {p.numeral}
            </span>
            <h3 className="font-display text-xl text-bone">{p.title}</h3>
            <p className="text-[13px] text-bone-faint leading-[1.8] font-normal">{p.desc}</p>
          </div>
        ))}
      </section>

      {/* ── Instruments footer ────────────────────────────────────────────── */}
      <footer className="text-center space-y-5 pb-8">
        <p className="eyebrow-dim">Dashboards</p>
        <div className="flex justify-center gap-px bg-bone/[0.07] rounded-xl overflow-hidden border hairline max-w-md mx-auto">
          {[
            { label: 'MLflow', url: 'http://localhost:5000', sub: 'Experiments' },
            { label: 'Grafana', url: 'http://localhost:3001', sub: 'Dashboards' },
            { label: 'Prometheus', url: 'http://localhost:9090', sub: 'Metrics' },
          ].map((l) => (
            <a
              key={l.url}
              href={l.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 bg-obsidian-900 hover:bg-obsidian-850 px-4 py-4 transition-colors group"
            >
              <span className="block font-mono text-[11px] uppercase tracking-[0.18em] text-bone-dim group-hover:text-gold-400 transition-colors">
                {l.label}
              </span>
              <span className="block text-[11px] text-bone-ghost mt-1">{l.sub}</span>
            </a>
          ))}
        </div>
      </footer>
    </div>
  );
}
