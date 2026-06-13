'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Navbar() {
  const path = usePathname();

  return (
    <nav className="glass sticky top-0 z-50 border-b border-white/[0.06]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="relative w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-600 flex items-center justify-center text-white text-[10px] font-black tracking-tight shadow-lg shadow-violet-900/50 group-hover:shadow-violet-700/50 transition-shadow">
            AI
            <div className="absolute inset-0 rounded-lg bg-white/20 opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
          <span className="text-white font-semibold text-sm tracking-tight">
            AutoML <span className="text-gradient font-bold">Orchestrator</span>
          </span>
        </Link>

        {/* Nav links */}
        <div className="flex items-center gap-1">
          <NavLink href="/" active={path === '/'}>
            New Run
          </NavLink>
          <NavLink href="/runs" active={path === '/runs' || path.startsWith('/runs/')}>
            Runs
          </NavLink>
          <div className="w-px h-4 bg-slate-700/60 mx-1.5" />
          <ExtLink href="http://localhost:5000">MLflow</ExtLink>
          <ExtLink href="http://localhost:3001">Grafana</ExtLink>
        </div>
      </div>
    </nav>
  );
}

function NavLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`relative px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
        active
          ? 'text-white bg-white/[0.08] shadow-inner'
          : 'text-slate-400 hover:text-slate-100 hover:bg-white/[0.04]'
      }`}
    >
      {children}
      {active && (
        <span className="absolute -bottom-[13px] left-3 right-3 h-px bg-gradient-to-r from-transparent via-violet-400 to-transparent" />
      )}
    </Link>
  );
}

function ExtLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="px-2.5 py-1.5 text-xs text-slate-500 hover:text-slate-200 transition-colors"
    >
      {children} <span className="text-[9px] opacity-60">↗</span>
    </a>
  );
}
