'use client';

import React, { useState, useEffect, useCallback, useTransition } from 'react';
import {
  Sparkles,
  Database,
  Terminal,
  Activity,
  Github,
  Zap,
  Filter,
  Layers,
  Search,
  ExternalLink,
  Info,
} from 'lucide-react';
import { Omnibar } from '@/components/Omnibar';
import { FilterBar } from '@/components/FilterBar';
import { RepoCard } from '@/components/RepoCard';
import { Repository, SearchMode, SearchResponse } from '@/types/repo';
import { MOCK_REPOSITORIES } from '@/lib/mockData';
import { executeSearch } from '@/lib/db';

export default function DashboardPage() {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [mode, setMode] = useState<SearchMode>('semantic');
  const [selectedDomain, setSelectedDomain] = useState('All');
  const [selectedArchetype, setSelectedArchetype] = useState('All');
  const [selectedLanguage, setSelectedLanguage] = useState('All');
  const [minStars, setMinStars] = useState(2000);

  const [results, setResults] = useState<Repository[]>(MOCK_REPOSITORIES);
  const [totalCount, setTotalCount] = useState(MOCK_REPOSITORIES.length);
  const [latencyMs, setLatencyMs] = useState<number>(8);
  const [dbProvider, setDbProvider] = useState<string>('local-edge');
  const [isLoading, setIsLoading] = useState(false);
  const [, startTransition] = useTransition();

  // Debounce query input by 300ms
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  // Execute Search API call when any filter or debounced query changes
  const performSearch = useCallback(async () => {
    setIsLoading(true);
    try {
      const data: SearchResponse = await executeSearch({
        query: debouncedQuery,
        domain: selectedDomain,
        archetype: selectedArchetype,
        language: selectedLanguage,
        min_stars: minStars,
        mode,
      });

      startTransition(() => {
        setResults(data.results || []);
        setTotalCount(data.total || 0);
        setLatencyMs(data.latency_ms || 0);
        setDbProvider(data.provider || 'local-edge');
      });
    } catch (err) {
      console.warn('Live search execution failed, applying fallback:', err);
      const filtered = MOCK_REPOSITORIES.filter((r) => {
        if (r.stars_count < minStars) return false;
        if (selectedDomain !== 'All' && r.macro_domain !== selectedDomain) return false;
        if (selectedLanguage !== 'All' && r.primary_language !== selectedLanguage) return false;
        if (selectedArchetype !== 'All' && !r.archetype.includes(selectedArchetype)) return false;
        if (debouncedQuery.trim()) {
          const q = debouncedQuery.toLowerCase();
          const str = `${r.full_name} ${r.problem_solved} ${r.use_cases.join(' ')}`.toLowerCase();
          return str.includes(q);
        }
        return true;
      });
      setResults(filtered);
      setTotalCount(filtered.length);
    } finally {
      setIsLoading(false);
    }
  }, [debouncedQuery, selectedDomain, selectedArchetype, selectedLanguage, minStars, mode]);

  useEffect(() => {
    performSearch();
  }, [performSearch]);

  const activeFilterCount =
    (selectedDomain !== 'All' ? 1 : 0) +
    (selectedArchetype !== 'All' ? 1 : 0) +
    (selectedLanguage !== 'All' ? 1 : 0) +
    (minStars > 2000 ? 1 : 0) +
    (query.trim() ? 1 : 0);

  const handleResetFilters = () => {
    setQuery('');
    setDebouncedQuery('');
    setSelectedDomain('All');
    setSelectedArchetype('All');
    setSelectedLanguage('All');
    setMinStars(2000);
  };

  const handleSelectUseCase = (tag: string) => {
    setQuery(tag);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Top Navbar Header */}
      <header className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-sky-500 shadow-md shadow-indigo-500/20">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                GitHub Intelligence Engine
                <span className="rounded-full bg-indigo-500/10 px-2.5 py-0.5 text-xs font-semibold text-indigo-400 border border-indigo-500/20">
                  2k+ Stars
                </span>
              </h1>
              <p className="text-xs text-slate-400">
                Autonomous 6-Pillar Categorization & Dense Vector Search (~30,000 repositories)
              </p>
            </div>
          </div>
        </div>

        {/* Global Telemetry & Status Bar */}
        <div className="flex flex-wrap items-center gap-2.5 text-xs">
          <div className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900/80 px-3 py-1.5 font-mono text-slate-300">
            <Database className="h-3.5 w-3.5 text-indigo-400" />
            <span>Driver:</span>
            <span className="font-semibold text-white capitalize">{dbProvider}</span>
          </div>

          <div className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900/80 px-3 py-1.5 font-mono text-slate-300">
            <Zap className="h-3.5 w-3.5 text-amber-400" />
            <span>Query:</span>
            <span className="font-semibold text-white">{latencyMs}ms</span>
          </div>

          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900/80 px-3 py-1.5 text-slate-400 transition-colors hover:border-slate-700 hover:text-white"
          >
            <Github className="h-3.5 w-3.5" />
            <span>GitHub Sync</span>
          </a>
        </div>
      </header>

      {/* Main Interactive Search & Filtering Controls */}
      <section className="space-y-4">
        {/* Natural Language Omnibar with Live Debouncing & Dual Mode Switch */}
        <Omnibar
          query={query}
          onQueryChange={setQuery}
          mode={mode}
          onModeChange={setMode}
          isLoading={isLoading}
          onSelectSuggestion={(s) => setQuery(s)}
        />

        {/* Faceted Filter Bar (Archetypes, Macro Domains, Star Range Slider, Languages) */}
        <FilterBar
          selectedArchetype={selectedArchetype}
          onSelectArchetype={setSelectedArchetype}
          selectedDomain={selectedDomain}
          onSelectDomain={setSelectedDomain}
          selectedLanguage={selectedLanguage}
          onSelectLanguage={setSelectedLanguage}
          minStars={minStars}
          onMinStarsChange={setMinStars}
          onResetFilters={handleResetFilters}
          activeFilterCount={activeFilterCount}
        />
      </section>

      {/* Active Search Context & Count Banner */}
      <section className="mt-8 mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-200">
            Showing {results.length} {results.length === 1 ? 'repository' : 'repositories'}
          </span>
          {activeFilterCount > 0 && (
            <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">
              Filtered
            </span>
          )}
          {debouncedQuery && (
            <span className="text-slate-400">
              for &ldquo;<span className="text-indigo-300 font-medium">{debouncedQuery}</span>&rdquo;
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 text-slate-500 text-[11px]">
          <span>Index: 384-dim HNSW Cosine Distance</span>
          <span>•</span>
          <span>Zero Paid APIs</span>
        </div>
      </section>

      {/* Results Grid rendering Repository Intelligence Cards */}
      <main>
        {results.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {results.map((repo) => (
              <RepoCard
                key={repo.id}
                repo={repo}
                onSelectUseCase={handleSelectUseCase}
                onSelectLanguage={(lang) => setSelectedLanguage(lang)}
                onSelectArchetype={(arch) => setSelectedArchetype(arch)}
              />
            ))}
          </div>
        ) : (
          /* Empty Search State */
          <div className="mt-12 flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/30 p-12 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-slate-800/80 text-slate-400 mb-4">
              <Search className="h-6 w-6" />
            </div>
            <h3 className="text-lg font-semibold text-slate-200">
              No matching repositories found
            </h3>
            <p className="mt-1.5 max-w-md text-xs text-slate-400">
              Try adjusting your star floor slider, broadening your archetype filters, or switching to{' '}
              <button
                onClick={() => setMode(mode === 'semantic' ? 'keyword' : 'semantic')}
                className="text-indigo-400 underline underline-offset-2 hover:text-indigo-300"
              >
                {mode === 'semantic' ? 'Keyword Search mode' : 'Semantic Intent mode'}
              </button>
              .
            </p>
            <button
              type="button"
              onClick={handleResetFilters}
              className="mt-5 inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-md shadow-indigo-600/30 hover:bg-indigo-500"
            >
              Reset all filters
            </button>
          </div>
        )}
      </main>

      {/* Footer Specification & Architecture Overview */}
      <footer className="mt-16 border-t border-slate-800/80 pt-8 text-center text-xs text-slate-500">
        <p>
          GitHub Intelligence Engine &bull; Zero External API Costs ($0.00/month) &bull; 6-Pillar Taxonomy Standard
        </p>
        <p className="mt-1 text-[11px] text-slate-600">
          Daily autonomous ingestion bisection &bull; Multi-provider failover routing &bull; Vector search powered by bge-small-en-v1.5
        </p>
      </footer>
    </div>
  );
}
