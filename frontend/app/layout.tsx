import type { Metadata } from 'next';
import { Playfair_Display, Manrope, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import Navbar from '@/components/Navbar';

// Readability pass: Playfair Display replaces Cormorant Garamond — same luxury
// serif voice, but a far sturdier x-height and stroke contrast at screen sizes.
const display = Playfair_Display({
  subsets: ['latin'],
  weight: ['500', '600', '700'],
  style: ['normal', 'italic'],
  variable: '--font-display',
  display: 'swap',
});

const body = Manrope({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-body',
  display: 'swap',
});

const mono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-mono',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'AutoML Orchestrator',
  description: 'Ten autonomous agents. One CSV. A production model — explained.',
  icons: { icon: 'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><circle cx=%2250%22 cy=%2250%22 r=%2240%22 fill=%22%23c8a96e%22/></svg>' },
};

// Runs before paint — applies the saved theme so there is no flash of wrong theme.
const themeInitScript = `
(function() {
  try {
    var t = localStorage.getItem('atelier-theme');
    if (t === 'light') {
      document.documentElement.classList.add('light');
      document.documentElement.classList.remove('dark');
    } else {
      document.documentElement.classList.add('dark');
    }
  } catch (e) { document.documentElement.classList.add('dark'); }
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body
        className={`${display.variable} ${body.variable} ${mono.variable} font-sans text-bone min-h-screen antialiased`}
      >
        {/* Ambient: aurora ribbon + film grain + technical grid (theme-aware) */}
        <div className="bg-atelier" aria-hidden>
          <div className="aurora" />
        </div>
        <Navbar />
        <main>{children}</main>
      </body>
    </html>
  );
}
