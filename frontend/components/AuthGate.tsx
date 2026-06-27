'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { supabase, authEnabled } from '@/lib/supabase';

// Redirects to /login when auth is enabled and the visitor isn't signed in.
// No-op when Supabase isn't configured (public mode) — renders children directly.
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(!authEnabled);

  useEffect(() => {
    if (!authEnabled || !supabase) {
      setReady(true);
      return;
    }
    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      if (!data.session && pathname !== '/login') {
        router.replace('/login');
      } else {
        setReady(true);
      }
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!session && pathname !== '/login') router.replace('/login');
      else setReady(true);
    });
    return () => {
      active = false;
      sub.subscription.unsubscribe();
    };
  }, [pathname, router]);

  if (!ready) return null;
  return <>{children}</>;
}
