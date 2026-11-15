import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'GitHub Intelligence Engine | Deep 6-Pillar Search for 2k+ Star Repos',
  description:
    'Autonomous zero-cost AI categorization and vector search dashboard indexing every public GitHub repository with 2,000+ stars.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 antialiased selection:bg-indigo-500/30 selection:text-indigo-200">
        <div className="relative min-h-screen flex flex-col overflow-x-hidden">
          {/* Subtle Ambient Radial Glow */}
          <div className="pointer-events-none fixed inset-0 z-0">
            <div className="absolute -top-40 left-1/2 -translate-x-1/2 h-[500px] w-[900px] rounded-full bg-gradient-to-tr from-indigo-900/20 via-purple-900/20 to-sky-900/10 blur-[130px]" />
          </div>

          <div className="relative z-10 flex-1">{children}</div>
        </div>
      </body>
    </html>
  );
}
