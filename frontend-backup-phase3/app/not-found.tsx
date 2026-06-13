import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4 text-center px-4">
      <div className="text-6xl">🔍</div>
      <h2 className="text-xl font-semibold text-slate-200">Page not found</h2>
      <p className="text-slate-500 text-sm">
        The page you&apos;re looking for doesn&apos;t exist.
      </p>
      <Link
        href="/"
        className="text-sm text-violet-400 hover:text-violet-300 border border-violet-800 hover:border-violet-600 px-4 py-2 rounded-lg transition-colors"
      >
        Go home
      </Link>
    </div>
  );
}
