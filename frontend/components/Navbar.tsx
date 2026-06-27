'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import ThemeToggle from '@/components/ThemeToggle';
import AuthMenu from '@/components/AuthMenu';

export default function Navbar() {
  const path = usePathname();

  return (
    <nav className="sticky top-0 z-50 border-b hairline bg-obsidian-950/85 backdrop-blur-md">
      <div className="max-w-6xl mx-auto px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Wordmark */}
        <Link href="/" className="flex items-center gap-3 group">
          <div className="relative w-8 h-8 rounded-full border hairline-gold flex items-center justify-center transition-all duration-500 group-hover:rotate-180">
            <div className="w-2 h-2 rounded-full bg-gold-500 group-hover:bg-gold-300 transition-colors" />
          </div>
          <div className="leading-none">
            <span className="block font-display text-lg text-bone tracking-wide">
              AutoML <em className="text-gold-400 not-italic font-semibold">Orchestrator</em>
            </span>
            <span className="block font-mono text-[11px] uppercase tracking-luxe text-bone-faint mt-0.5">
              Automated ML pipeline
            </span>
          </div>
        </Link>

        {/* Navigation */}
        <div className="flex items-center gap-2">
          <NavLink href="/" active={path === '/'}>
            New Model
          </NavLink>
          <NavLink href="/runs" active={path === '/runs' || path.startsWith('/runs/')}>
            Runs
          </NavLink>
          <div className="w-px h-5 bg-bone/10 mx-2" />
          <ExtLink href="http://localhost:5000">MLflow</ExtLink>
          <ExtLink href="http://localhost:3001">Grafana</ExtLink>
          <div className="w-px h-5 bg-bone/10 mx-2" />
          <ThemeToggle />
          <AuthMenu />
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
      className={`relative px-4 py-2 font-mono text-[11px] uppercase tracking-[0.18em] transition-colors duration-300 ${
        active ? 'text-gold-300' : 'text-bone-faint hover:text-bone'
      }`}
    >
      {children}
      <span
        className={`absolute left-4 right-4 -bottom-[1px] h-px transition-opacity duration-300 ${
          active ? 'opacity-100' : 'opacity-0'
        }`}
        style={{ background: 'linear-gradient(90deg, transparent, rgb(var(--gold-500)), transparent)' }}
      />
    </Link>
  );
}

function ExtLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="px-3 py-2 font-mono text-[11px] uppercase tracking-[0.18em] text-bone-ghost hover:text-bone-dim transition-colors"
    >
      {children}<span className="text-gold-700 ml-1">↗</span>
    </a>
  );
}
