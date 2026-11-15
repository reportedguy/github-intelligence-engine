import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCompactNumber(num: number): string {
  if (num >= 1_000_000) {
    return (num / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
  }
  if (num >= 1_000) {
    return (num / 1_000).toFixed(1).replace(/\.0$/, '') + 'k';
  }
  return num.toLocaleString();
}

export type FreshnessStatus = 'Active' | 'Maintained' | 'Stale';

export interface FreshnessInfo {
  status: FreshnessStatus;
  label: string;
  dotColor: string;
  badgeBg: string;
  textColor: string;
}

export function getFreshnessInfo(pushedAt?: string | null): FreshnessInfo {
  if (!pushedAt) {
    return {
      status: 'Maintained',
      label: 'Maintained',
      dotColor: 'bg-amber-400',
      badgeBg: 'bg-amber-500/10 border-amber-500/30',
      textColor: 'text-amber-300',
    };
  }

  const pushedDate = new Date(pushedAt);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - pushedDate.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays <= 7) {
    return {
      status: 'Active',
      label: `Active (${diffDays === 0 ? 'today' : `${diffDays}d ago`})`,
      dotColor: 'bg-emerald-400 animate-pulse',
      badgeBg: 'bg-emerald-500/10 border-emerald-500/30',
      textColor: 'text-emerald-300',
    };
  }

  if (diffDays <= 60) {
    return {
      status: 'Maintained',
      label: `Maintained (${diffDays}d ago)`,
      dotColor: 'bg-sky-400',
      badgeBg: 'bg-sky-500/10 border-sky-500/30',
      textColor: 'text-sky-300',
    };
  }

  return {
    status: 'Stale',
    label: `Stale (${Math.floor(diffDays / 30)}mo ago)`,
    dotColor: 'bg-slate-400',
    badgeBg: 'bg-slate-700/20 border-slate-600/30',
    textColor: 'text-slate-400',
  };
}

export function getArchetypeColor(archetype: string): { bg: string; text: string; border: string } {
  const norm = archetype.toLowerCase();
  if (norm.includes('server') || norm.includes('daemon') || norm.includes('engine')) {
    return { bg: 'bg-purple-950/60', text: 'text-purple-300', border: 'border-purple-700/40' };
  }
  if (norm.includes('cli') || norm.includes('binary')) {
    return { bg: 'bg-amber-950/60', text: 'text-amber-300', border: 'border-amber-700/40' };
  }
  if (norm.includes('library') || norm.includes('sdk')) {
    return { bg: 'bg-blue-950/60', text: 'text-blue-300', border: 'border-blue-700/40' };
  }
  if (norm.includes('framework')) {
    return { bg: 'bg-indigo-950/60', text: 'text-indigo-300', border: 'border-indigo-700/40' };
  }
  if (norm.includes('curated') || norm.includes('awesome')) {
    return { bg: 'bg-emerald-950/60', text: 'text-emerald-300', border: 'border-emerald-700/40' };
  }
  if (norm.includes('book') || norm.includes('tutorial') || norm.includes('course')) {
    return { bg: 'bg-rose-950/60', text: 'text-rose-300', border: 'border-rose-700/40' };
  }
  return { bg: 'bg-slate-800/80', text: 'text-slate-300', border: 'border-slate-700/40' };
}
