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

  // ── Drag & drop ────────────────────────────────────────────────────────────
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
      setError('Please drop a CSV file');
    }
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      setFile(selected);
      setError(null);
    }
  };

  // ── Submit ─────────────────────────────────────────────────────────────────
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
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* ── CSV Drop Zone ──────────────────────────────────────────────────── */}
      <div
        className={`relative border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all ${
          isDragging
            ? 'border-violet-500 bg-violet-500/10'
            : file
            ? 'border-emerald-500/60 bg-emerald-500/5'
            : 'border-slate-700 hover:border-slate-500 bg-slate-900'
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
          <div className="space-y-1">
            <div className="text-3xl">📊</div>
            <p className="text-emerald-400 font-medium">{file.name}</p>
            <p className="text-slate-500 text-sm">
              {(file.size / 1024).toFixed(0)} KB — click to change
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="text-4xl">📂</div>
            <p className="text-slate-300 font-medium">Drop your CSV file here</p>
            <p className="text-slate-500 text-sm">or click to browse — max 500 MB</p>
          </div>
        )}
      </div>

      {/* ── Goal Input ─────────────────────────────────────────────────────── */}
      <div className="space-y-2">
        <label className="block text-sm font-medium text-slate-300">
          What do you want to predict?
        </label>
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder={EXAMPLE_GOALS[0]}
          rows={3}
          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500/30 resize-none text-sm"
        />
        {/* Example goals */}
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_GOALS.slice(1).map((eg) => (
            <button
              key={eg}
              type="button"
              onClick={() => setGoal(eg)}
              className="text-xs text-slate-500 hover:text-violet-400 border border-slate-700 hover:border-violet-700 rounded-full px-3 py-1 transition-colors"
            >
              {eg.slice(0, 40)}…
            </button>
          ))}
        </div>
      </div>

      {/* ── Advanced Options ───────────────────────────────────────────────── */}
      <div>
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-300 transition-colors"
        >
          <span className={`transition-transform ${showAdvanced ? 'rotate-90' : ''}`}>▶</span>
          Advanced options
        </button>

        {showAdvanced && (
          <div className="mt-4 space-y-4 p-4 bg-slate-900 rounded-lg border border-slate-800">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-400">
                  Exclude columns (comma-separated)
                </label>
                <input
                  type="text"
                  value={excludeColumns}
                  onChange={(e) => setExcludeColumns(e.target.value)}
                  placeholder="e.g. PassengerId, Name, Ticket"
                  className="w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-slate-300 placeholder-slate-600 text-sm focus:outline-none focus:border-violet-500"
                />
                <p className="text-xs text-slate-600">Columns that should not be features</p>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-400">
                  FP / FN preference
                </label>
                <input
                  type="text"
                  value={fpFnPref}
                  onChange={(e) => setFpFnPref(e.target.value)}
                  placeholder="e.g. minimize false negatives"
                  className="w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-slate-300 placeholder-slate-600 text-sm focus:outline-none focus:border-violet-500"
                />
                <p className="text-xs text-slate-600">Threshold optimization hint</p>
              </div>
            </div>

            <label className="flex items-center gap-3 cursor-pointer">
              <div
                onClick={() => setInterpretability(!interpretability)}
                className={`w-9 h-5 rounded-full transition-colors relative ${
                  interpretability ? 'bg-violet-600' : 'bg-slate-700'
                }`}
              >
                <div
                  className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                    interpretability ? 'translate-x-4' : 'translate-x-0.5'
                  }`}
                />
              </div>
              <span className="text-sm text-slate-400">
                Interpretability required (enforces linear models)
              </span>
            </label>
          </div>
        )}
      </div>

      {/* ── Error ──────────────────────────────────────────────────────────── */}
      {error && (
        <div className="flex items-start gap-2 text-rose-400 text-sm bg-rose-500/10 border border-rose-500/20 rounded-lg px-4 py-3">
          <span>⚠</span>
          <span>{error}</span>
        </div>
      )}

      {/* ── Submit ─────────────────────────────────────────────────────────── */}
      <button
        type="submit"
        disabled={isSubmitting || !file || goal.trim().length < 10}
        className={`w-full py-3.5 rounded-xl font-semibold text-sm transition-all ${
          isSubmitting || !file || goal.trim().length < 10
            ? 'bg-violet-900/40 text-slate-500 cursor-not-allowed'
            : 'bg-violet-600 hover:bg-violet-500 text-white shadow-lg shadow-violet-900/30 active:scale-[0.99]'
        }`}
      >
        {isSubmitting ? (
          <span className="flex items-center justify-center gap-2">
            <Spinner /> Launching pipeline…
          </span>
        ) : (
          '🚀 Start AutoML Pipeline'
        )}
      </button>
    </form>
  );
}

function Spinner() {
  return (
    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
      <path fill="currentColor" className="opacity-75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}
