'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase, authEnabled } from '@/lib/supabase';

// Navbar profile: shows the signed-in user's email + a sign-out button, or a
// "Sign in" link. Renders nothing when auth is disabled (public mode).
export default function AuthMenu() {
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!authEnabled || !supabase) return;
    supabase.auth.getUser().then(({ data }) => setEmail(data.user?.email ?? null));
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user?.email ?? null);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  if (!authEnabled) return null;

  if (!email) {
    return (
      <Link
        href="/login"
        className="px-3 py-2 font-mono text-[11px] uppercase tracking-[0.18em] text-bone-faint hover:text-bone transition-colors"
      >
        Sign in
      </Link>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="hidden sm:block font-mono text-[11px] text-bone-faint max-w-[160px] truncate">
        {email}
      </span>
      <button
        onClick={() => supabase!.auth.signOut()}
        className="btn-ghost text-[11px] px-3 py-1.5"
      >
        Sign out
      </button>
    </div>
  );
}
