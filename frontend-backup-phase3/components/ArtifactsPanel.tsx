'use client';
import { useEffect, useState } from 'react';
import type { Artifact } from '@/lib/types';
import { artifactUrl, fetchArtifactText } from '@/lib/api';

const ARTIFACT_META: Record<
  string,
  { icon: string; label: string; description: string; preview?: 'image' | 'text' | 'markdown' }
> = {
  notebook: {
    icon: '📓',
    label: 'Evidence Notebook',
    description: 'Jupyter notebook with LLM-generated narrative and executed code',
    preview: undefined,
  },
  model_card: {
    icon: '🪪',
    label: 'Model Card',
    description: 'Model performance, limitations, and usage guide',
    preview: 'markdown',
  },
  api: {
    icon: '🌐',
    label: 'FastAPI Server',
    description: 'Ready-to-deploy /predict endpoint for this model',
    preview: 'text',
  },
  pipeline: {
    icon: '⚙️',
    label: 'Inference Pipeline',
    description: 'Preprocessor + model bundle (joblib dict)',
    preview: undefined,
  },
  model: {
    icon: '🤖',
    label: 'Tuned Model',
    description: 'Best tuned sklearn/XGBoost model',
    preview: undefined,
  },
  preprocessor: {
    icon: '🔄',
    label: 'Preprocessor',
    description: 'Fitted sklearn ColumnTransformer',
    preview: undefined,
  },
  shap: {
    icon: '📊',
    label: 'SHAP Summary',
    description: 'Feature importance via SHAP values',
    preview: 'image',
  },
  confusion_matrix: {
    icon: '🟦',
    label: 'Confusion Matrix',
    description: 'Classification confusion matrix heatmap',
    preview: 'image',
  },
  target_dist: {
    icon: '📉',
    label: 'Target Distribution',
    description: 'Distribution of the target variable',
    preview: 'image',
  },
  correlation: {
    icon: '🗺️',
    label: 'Correlation Heatmap',
    description: 'Feature correlation heatmap (top 15 features)',
    preview: 'image',
  },
};

function MarkdownRenderer({ text }: { text: string }) {
  // Simple markdown: headers, bold, code blocks
  const lines = text.split('\n');
  return (
    <div className="prose prose-sm prose-invert max-w-none">
      <pre className="text-xs text-slate-300 whitespace-pre-wrap font-mono leading-relaxed">
        {text}
      </pre>
    </div>
  );
}

function ArtifactCard({
  artifact,
  runId,
}: {
  artifact: Artifact;
  runId: string;
}) {
  const meta = ARTIFACT_META[artifact.name] ?? {
    icon: '📄',
    label: artifact.name,
    description: artifact.filename,
    preview: undefined,
  };
  const [expanded, setExpanded] = useState(false);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const downloadUrl = artifactUrl(runId, artifact.name);
  const isImage = meta.preview === 'image';
  const isText = meta.preview === 'text' || meta.preview === 'markdown';

  const loadPreview = async () => {
    if (previewContent !== null) { setExpanded(!expanded); return; }
    if (!isText) { setExpanded(!expanded); return; }
    setLoading(true);
    try {
      const text = await fetchArtifactText(runId, artifact.name);
      setPreviewContent(text);
    } catch {}
    setLoading(false);
    setExpanded(true);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
      {/* Header row */}
      <div className="flex items-center gap-3 p-4">
        <div className="text-2xl flex-shrink-0">{meta.icon}</div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-200">{meta.label}</p>
          <p className="text-xs text-slate-500 truncate">{meta.description}</p>
          <p className="text-xs text-slate-700 mt-0.5">{artifact.size_kb} KB</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {(isText || isImage) && (
            <button
              onClick={isImage ? () => setExpanded(!expanded) : loadPreview}
              className="text-xs text-slate-400 hover:text-slate-200 border border-slate-700 rounded-md px-3 py-1.5 transition-colors"
            >
              {loading ? '…' : expanded ? 'Hide' : 'Preview'}
            </button>
          )}
          <a
            href={downloadUrl}
            download={artifact.filename}
            className="text-xs text-violet-400 hover:text-violet-300 border border-violet-800 hover:border-violet-600 rounded-md px-3 py-1.5 transition-colors"
          >
            Download
          </a>
        </div>
      </div>

      {/* Preview */}
      {expanded && (
        <div className="border-t border-slate-800">
          {isImage && (
            <div className="p-4 bg-black/20">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={downloadUrl}
                alt={meta.label}
                className="max-w-full mx-auto rounded"
              />
            </div>
          )}
          {isText && previewContent !== null && (
            <div className="p-4 bg-black/20 max-h-96 overflow-y-auto">
              <MarkdownRenderer text={previewContent} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ArtifactsPanel({
  artifacts,
  runId,
}: {
  artifacts: Artifact[];
  runId: string;
}) {
  const images = artifacts.filter((a) => ARTIFACT_META[a.name]?.preview === 'image');
  const files = artifacts.filter((a) => ARTIFACT_META[a.name]?.preview !== 'image');

  if (artifacts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-slate-600 space-y-2">
        <div className="text-3xl">📭</div>
        <p className="text-sm">No artifacts yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Key files */}
      {files.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Output Files
          </h4>
          <div className="space-y-2">
            {files.map((a) => (
              <ArtifactCard key={a.name} artifact={a} runId={runId} />
            ))}
          </div>
        </div>
      )}

      {/* Visualizations */}
      {images.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Visualizations
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {images.map((a) => (
              <ArtifactCard key={a.name} artifact={a} runId={runId} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
