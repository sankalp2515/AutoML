import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import Navbar from '@/components/Navbar';

const inter = Inter({ subsets: ['latin'], display: 'swap' });

export const metadata: Metadata = {
  title: 'AutoML Orchestrator',
  description: '10-agent autonomous ML pipeline — drop CSV, describe goal, get production model',
  icons: { icon: 'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🤖</text></svg>' },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} text-slate-100 min-h-screen antialiased`}>
        {/* Ambient animated background: gradient orbs + faint grid */}
        <div className="bg-ambient" aria-hidden>
          <div className="orb orb-violet" />
          <div className="orb orb-fuchsia" />
          <div className="orb orb-cyan" />
        </div>
        <Navbar />
        <main>{children}</main>
      </body>
    </html>
  );
}
