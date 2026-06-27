'use client';
import { useEffect, useState } from 'react';

type Theme = 'dark' | 'light';

export default function ThemeToggle() {
  // Initialized from the <html> class set by the inline script in layout.tsx,
  // so there is never a server/client mismatch flash.
  const [theme, setTheme] = useState<Theme>('dark');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setTheme(document.documentElement.classList.contains('light') ? 'light' : 'dark');
  }, []);

  const toggle = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.classList.toggle('light', next === 'light');
    document.documentElement.classList.toggle('dark', next === 'dark');
    localStorage.setItem('atelier-theme', next);
    setTheme(next);
  };

  return (
    <button
      onClick={toggle}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      className="relative w-12 h-6 rounded-full border hairline-gold transition-colors duration-300 flex-shrink-0"
      style={{ background: 'rgb(var(--obsidian-800))' }}
    >
      {/* Track icons */}
      <span className="absolute left-1.5 top-1/2 -translate-y-1/2 text-[11px] opacity-60">☾</span>
      <span className="absolute right-1.5 top-1/2 -translate-y-1/2 text-[11px] opacity-60">☀</span>
      {/* Thumb */}
      <span
        className={`absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-gold-500 shadow-md transition-all duration-300 ${
          mounted && theme === 'light' ? 'left-[26px]' : 'left-1'
        }`}
      />
    </button>
  );
}
