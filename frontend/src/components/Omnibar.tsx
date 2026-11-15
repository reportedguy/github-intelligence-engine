'use client';

import React from 'react';
import { Search, Sparkles, Binary, X, Loader2 } from 'lucide-react';
import { SearchMode } from '@/types/repo';
import { cn } from '@/lib/utils';

interface OmnibarProps {
  query: string;
  onQueryChange: (q: string) => void;
  mode: SearchMode;
  onModeChange: (m: SearchMode) => void;
  isLoading: boolean;
  onSelectSuggestion?: (s: string) => void;
}

const SAMPLE_SUGGESTIONS = [
  'high throughput LLM inference serving engine',
  'fast rust terminal code search alternative to grep',
  'declarative distributed state caching',
  'asynchronous Python REST microservices',
  'supply chain container artifact signing',
];

export const Omnibar: React.FC<OmnibarProps> = ({
  query,
  onQueryChange,
  mode,
  onModeChange,
  isLoading,
  onSelectSuggestion,
}) => {
  return (
    <div className="w-full">
      {/* Search Input Container */}
      <div className="relative flex flex-col md:flex-row items-stretch gap-2.5 rounded-2xl border border-slate-700/80 bg-slate-900/90 p-2 shadow-2xl backdrop-blur-md transition-all focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500/20">
        {/* Search Icon & Input */}
        <div className="relative flex flex-1 items-center">
          <div className="pointer-events-none pl-3 text-slate-400">
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-indigo-400" />
            ) : mode === 'semantic' ? (
              <Sparkles className="h-5 w-5 text-indigo-400" />
            ) : (
              <Search className="h-5 w-5 text-slate-400" />
            )}
          </div>

          <input
            type="text"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder={
              mode === 'semantic'
                ? 'Describe the engineering problem or capability (e.g. "low-memory vector search engine")...'
                : 'Exact match query, repo name, description, or use cases...'
            }
            className="w-full bg-transparent px-3 py-2.5 text-sm md:text-base text-slate-100 placeholder:text-slate-500 focus:outline-none"
          />

          {query && (
            <button
              type="button"
              onClick={() => onQueryChange('')}
              className="mr-2 rounded-lg p-1 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200"
              title="Clear search"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Mode Toggle Switch */}
        <div className="flex shrink-0 items-center justify-end rounded-xl bg-slate-950/80 p-1 border border-slate-800">
          <button
            type="button"
            onClick={() => onModeChange('semantic')}
            className={cn(
              'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-150',
              mode === 'semantic'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                : 'text-slate-400 hover:text-slate-200'
            )}
            title="Search by concept & meaning using 384-dim dense vectors"
          >
            <Sparkles className="h-3.5 w-3.5" />
            <span>Semantic Intent</span>
          </button>

          <button
            type="button"
            onClick={() => onModeChange('keyword')}
            className={cn(
              'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-150',
              mode === 'keyword'
                ? 'bg-slate-800 text-indigo-300 shadow-md border border-slate-700'
                : 'text-slate-400 hover:text-slate-200'
            )}
            title="Search by literal keyword & exact trigram matching"
          >
            <Binary className="h-3.5 w-3.5" />
            <span>Keyword Search</span>
          </button>
        </div>
      </div>

      {/* Suggested Search Prompts (Prompt ideas for users) */}
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
        <span className="font-medium text-slate-500">Try asking:</span>
        {SAMPLE_SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => onSelectSuggestion?.(suggestion)}
            className="rounded-full border border-slate-800 bg-slate-900/60 px-2.5 py-0.5 text-[11px] text-slate-400 transition-colors hover:border-indigo-500/50 hover:bg-indigo-950/30 hover:text-indigo-300"
          >
            &quot;{suggestion}&quot;
          </button>
        ))}
      </div>
    </div>
  );
};
