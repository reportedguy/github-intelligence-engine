'use client';

import React from 'react';
import {
  SlidersHorizontal,
  RotateCcw,
  Star,
  Layers,
  Code2,
  FolderTree,
} from 'lucide-react';
import {
  ARCHETYPE_OPTIONS,
  MACRO_DOMAINS,
  POPULAR_LANGUAGES,
} from '@/types/repo';
import { cn, formatCompactNumber } from '@/lib/utils';

interface FilterBarProps {
  selectedArchetype: string;
  onSelectArchetype: (arch: string) => void;
  selectedDomain: string;
  onSelectDomain: (domain: string) => void;
  selectedLanguage: string;
  onSelectLanguage: (lang: string) => void;
  minStars: number;
  onMinStarsChange: (stars: number) => void;
  onResetFilters: () => void;
  activeFilterCount: number;
}

export const FilterBar: React.FC<FilterBarProps> = ({
  selectedArchetype,
  onSelectArchetype,
  selectedDomain,
  onSelectDomain,
  selectedLanguage,
  onSelectLanguage,
  minStars,
  onMinStarsChange,
  onResetFilters,
  activeFilterCount,
}) => {
  return (
    <div className="w-full space-y-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-4 backdrop-blur-md">
      {/* Top Controls: Archetype Segmented Pills */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
            <Layers className="h-3.5 w-3.5 text-indigo-400" />
            <span>Functional Archetype</span>
          </div>

          {activeFilterCount > 0 && (
            <button
              type="button"
              onClick={onResetFilters}
              className="inline-flex items-center gap-1 text-xs text-indigo-400 transition-colors hover:text-indigo-300"
            >
              <RotateCcw className="h-3 w-3" />
              <span>Reset Filters ({activeFilterCount})</span>
            </button>
          )}
        </div>

        {/* Archetype segmented pill group */}
        <div className="flex flex-wrap items-center gap-1.5">
          {ARCHETYPE_OPTIONS.map((opt) => {
            const isSelected =
              (opt.id === 'all' && (!selectedArchetype || selectedArchetype === 'All')) ||
              selectedArchetype === opt.label ||
              opt.dbValues.some((v) => selectedArchetype === v);

            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => onSelectArchetype(opt.id === 'all' ? 'All' : opt.label)}
                className={cn(
                  'rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-150',
                  isSelected
                    ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/30 ring-1 ring-indigo-400/50'
                    : 'border border-slate-800 bg-slate-950/60 text-slate-400 hover:border-slate-700 hover:bg-slate-800/80 hover:text-slate-200'
                )}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Second Row: Domain Dropdown & Star Range Slider */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-2 border-t border-slate-800/60">
        {/* Macro Domain Dropdown */}
        <div>
          <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-slate-400">
            <FolderTree className="h-3.5 w-3.5 text-indigo-400" />
            <span>Macro Domain (15 Closed Domains)</span>
          </label>
          <select
            value={selectedDomain}
            onChange={(e) => onSelectDomain(e.target.value)}
            className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="All">All Macro Domains</option>
            {MACRO_DOMAINS.map((domain) => (
              <option key={domain} value={domain}>
                {domain}
              </option>
            ))}
          </select>
        </div>

        {/* Star Range Slider (2,000 to 300,000+) */}
        <div>
          <div className="mb-1.5 flex items-center justify-between text-xs">
            <label className="flex items-center gap-1.5 font-medium text-slate-400">
              <Star className="h-3.5 w-3.5 text-amber-400" />
              <span>Minimum Star Floor</span>
            </label>
            <span className="font-mono font-semibold text-amber-400">
              ≥ {formatCompactNumber(minStars)} stars
            </span>
          </div>

          <div className="space-y-1">
            <input
              type="range"
              min="2000"
              max="150000"
              step="1000"
              value={minStars}
              onChange={(e) => onMinStarsChange(Number(e.target.value))}
              className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-slate-800 accent-indigo-500 focus:outline-none"
            />
            <div className="flex justify-between text-[10px] text-slate-500 font-mono">
              <span>2k (Baseline)</span>
              <span>25k</span>
              <span>50k</span>
              <span>100k+</span>
            </div>
          </div>
        </div>

        {/* Fast Reset / Stats Pill in larger layouts */}
        <div className="hidden lg:flex flex-col justify-end">
          <div className="rounded-xl border border-slate-800/80 bg-slate-950/60 p-2.5 text-xs text-slate-400 flex items-center justify-between">
            <span className="text-slate-400">Scope:</span>
            <span className="font-mono text-indigo-300 font-medium">30,000+ Repos (≥ 2k Stars)</span>
          </div>
        </div>
      </div>

      {/* Third Row: Popular Language Chips */}
      <div className="pt-2 border-t border-slate-800/60">
        <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-slate-400">
          <Code2 className="h-3.5 w-3.5 text-indigo-400" />
          <span>Programming Ecosystem & Languages</span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {POPULAR_LANGUAGES.map((lang) => {
            const isSelected =
              (lang === 'All' && (!selectedLanguage || selectedLanguage === 'All')) ||
              selectedLanguage === lang;

            return (
              <button
                key={lang}
                type="button"
                onClick={() => onSelectLanguage(lang)}
                className={cn(
                  'rounded-full px-2.5 py-1 text-xs font-medium transition-all duration-150',
                  isSelected
                    ? 'bg-slate-200 text-slate-950 shadow-sm font-semibold'
                    : 'border border-slate-800 bg-slate-950/70 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                )}
              >
                {lang}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
