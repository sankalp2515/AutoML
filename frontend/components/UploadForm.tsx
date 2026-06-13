'use client';
import { useRef, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { createRun } from '@/lib/api';

const EXAMPLE_GOALS = [
  'Predict whether a passenger survived the Titanic disaster',
  'Predict house sale prices from property features',
  'Classify customer churn for a subscription service',
  'Predict loan default risk from applicant data',
];

export default function UploadForm() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [goal, setGoal] = useState('');
  const [excludeColumns, setExcludeColumns] = useState('');
  const [fpFnPref, setFpFnPref] = useState('');
  const [interpretability, setInterpretability] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => setIsDragging(false), []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped?.name.endsWith('.csv')) {
      setFile(dropped);
      setError(null);
    } else {
      setError('Please present a CSV file');
    }
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      setFile(selected);
      setError(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) { setError('Please select a CSV file'); return; }
    if (goal.trim().length < 10) { setError('Please describe your goal (at least 10 characters)'); return; }

    setError(null);
    setIsSubmitting(true);

    const fd = new FormData();
    fd.append('file', file);
    fd.append('user_goal', goal.trim());
    fd.append('exclude_columns', excludeColumns.trim());
    fd.append('fp_fn_preference', fpFnPref.trim());
    fd.append('interpretability_required', String(interpretability));

    try {
      const run = await createRun(fd);
      router.push(`/runs/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create run');
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-7">
      {/* ── The dataset ─────────────────────────────────────────────────── */}
      <div>
        <p className="eyebrow-dim mb-3">i. The Dataset</p>
        <div
          className={`relative rounded-xl border border-dashed p-10 text-center cursor-pointer transition-all duration-500 ${
            isDragging
              ? 'border-gold-400 bg-gold-500/[0.06]'
              : file
              ? 'border-jade-500/50 bg-jade-500/[0.04]'
              : 'border-bone/15 hover:border-gold-600/50 bg-obsidian-900/40'
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={handleFileChange}
          />

          {file ? (
            <div className="space-y-1.5">
              <span className="font-mono text-[11px] uppercase tracking-luxe text-jade-400">
                ◈ received
              </span>
              <p className="font-display text-xl text-bone">{file.name}</p>
              <p className="font-mono text-[11px] text-bone-ghost">
                {(file.size / 1024).toFixed(0)} KB — select to replace
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <span className="font-display text-3xl text-gold-600 italic">⌑</span>
              <p className="font-display text-lg text-bone-dim">
                Place your CSV here
              </p>
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-bone-ghost">
                or select to browse
              </p>
            </div>
          )}
        </div>
      </div>

      {/* ── The intention ───────────────────────────────────────────────── */}
      <div className="space-y-3">
        <p className="eyebrow-dim">ii. The Intention</p>
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder={EXAMPLE_GOALS[0]}
          rows={3}
          className="w-full bg-obsidian-900/60 border hairline rounded-xl px-5 py-4 text-bone placeholder-bone-ghost font-normal text-[14px] leading-relaxed focus:outline-none focus:border-gold-600/60 focus:shadow-[0_0_0_3px_rgba(200,169,110,0.08)] resize-none transition-all"
        />
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_GOALS.slice(1).map((eg) => (
            <button
              key={eg}
              type="button"
              onClick={() => setGoal(eg)}
              className="font-mono text-[11px] text-bone-ghost hover:text-gold-400 border hairline hover:border-gold-700 rounded-full px-3.5 py-1.5 transition-all duration-300"
            >
              {eg.slice(0, 38)}…
            </button>
          ))}
        </div>
      </div>

      {/* ── Particulars (advanced) ──────────────────────────────────────── */}
      <div>
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-luxe text-bone-ghost hover:text-bone-dim transition-colors"
        >
          <span className={`text-gold-600 transition-transform duration-300 ${showAdvanced ? 'rotate-90' : ''}`}>
            ›
          </span>
          iii. Particulars
        </button>

        {showAdvanced && (
          <div className="mt-4 space-y-5 p-5 rounded-xl border hairline bg-obsidian-900/40 animate-fade-up">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <div className="space-y-2">
                <label className="eyebrow-dim block">Exclude columns</label>
                <input
                  type="text"
                  value={excludeColumns}
                  onChange={(e) => setExcludeColumns(e.target.value)}
                  placeholder="PassengerId, Name, Ticket"
                  className="w-full bg-obsidian-950/80 border hairline rounded-lg px-4 py-2.5 text-bone-dim placeholder-bone-ghost text-sm font-normal focus:outline-none focus:border-gold-600/50 transition-colors"
                />
              </div>
              <div className="space-y-2">
                <label className="eyebrow-dim block">Error preference</label>
                <input
                  type="text"
                  value={fpFnPref}
                  onChange={(e) => setFpFnPref(e.target.value)}
                  placeholder="minimize false negatives"
                  className="w-full bg-obsidian-950/80 border hairline rounded-lg px-4 py-2.5 text-bone-dim placeholder-bone-ghost text-sm font-normal focus:outline-none focus:border-gold-600/50 transition-colors"
                />
              </div>
            </div>

            <label className="flex items-center gap-3 cursor-pointer group">
              <div
                onClick={() => setInterpretability(!interpretability)}
                className={`w-10 h-5 rounded-full border transition-all duration-300 relative ${
                  interpretability
                    ? 'bg-gold-500/20 border-gold-500/60'
                    : 'bg-obsidian-800 border-bone/15'
                }`}
              >
                <div
                  className={`absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full transition-all duration-300 ${
                    interpretability ? 'left-[22px] bg-gold-400' : 'left-1 bg-bone-ghost'
                  }`}
                />
              </div>
              <span className="text-[13px] text-bone-faint font-normal group-hover:text-bone-dim transition-colors">
                Interpretability required — linear models only
              </span>
            </label>
          </div>
        )}
      </div>

      {/* ── Error ───────────────────────────────────────────────────────── */}
      {error && (
        <div className="flex items-start gap-3 text-terra-300 text-[13px] font-normal bg-terra-900/30 border border-terra-500/25 rounded-xl px-5 py-3.5">
          <span className="text-terra-400">◆</span>
          <span>{error}</span>
        </div>
      )}

      {/* ── Submit ──────────────────────────────────────────────────────── */}
      <button
        type="submit"
        disabled={isSubmitting || !file || goal.trim().length < 10}
        className="btn-gold w-full py-4 text-[13px] uppercase tracking-[0.2em] font-mono"
      >
        {isSubmitting ? (
          <>
            <Spinner /> Commissioning…
          </>
        ) : (
          <>Begin the Work</>
        )}
      </button>
    </form>
  );
}

function Spinner() {
  return (
    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
      <path fill="currentColor" className="opacity-75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}
