'use client';

import React from 'react';
import {
  Star,
  GitFork,
  AlertCircle,
  ExternalLink,
  Sparkles,
  TrendingUp,
  Tag,
  Clock,
  Layers,
} from 'lucide-react';
import { Repository } from '@/types/repo';
import {
  cn,
  formatCompactNumber,
  getFreshnessInfo,
  getArchetypeColor,
} from '@/lib/utils';

interface RepoCardProps {
  repo: Repository;
  onSelectUseCase?: (useCase: string) => void;
  onSelectLanguage?: (lang: string) => void;
  onSelectArchetype?: (arch: string) => void;
}

export const RepoCard: React.FC<RepoCardProps> = ({
  repo,
  onSelectUseCase,
  onSelectLanguage,
  onSelectArchetype,
}) => {
  const freshness = getFreshnessInfo(repo.pushed_at);
  const archetypeStyle = getArchetypeColor(repo.archetype);

  return (
    <div className="group relative flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/80 p-5 shadow-sm backdrop-blur-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-indigo-500/50 hover:bg-slate-900/95 hover:shadow-xl hover:shadow-indigo-500/10">
      {/* Top Header Row */}
      <div>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <a
                href={repo.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group/title inline-flex items-center gap-1.5 font-mono text-base font-semibold text-slate-100 transition-colors hover:text-indigo-400"
              >
                <span className="truncate">{repo.full_name}</span>
                <ExternalLink className="h-3.5 w-3.5 opacity-40 transition-opacity group-hover/title:opacity-100" />
              </a>

              {/* Semantic Similarity Match Badge (if provided by vector search) */}
              {repo.similarity !== undefined && (
                <span className="inline-flex items-center gap-1 rounded-full bg-indigo-500/15 px-2 py-0.5 text-xs font-medium text-indigo-300 border border-indigo-500/30">
                  <Sparkles className="h-3 w-3 text-indigo-400" />
                  {Math.round(repo.similarity * 100)}% match
                </span>
              )}
            </div>

            {/* Subdomain / Domain Path */}
            <div className="mt-1 flex items-center gap-1.5 text-xs text-slate-400">
              <span className="text-slate-500">{repo.macro_domain}</span>
              {repo.sub_domain && (
                <>
                  <span className="text-slate-600">/</span>
                  <span className="text-indigo-300/80 font-medium">{repo.sub_domain}</span>
                </>
              )}
            </div>
          </div>

          {/* Freshness / Activity Pill */}
          <div
            className={cn(
              'flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
              freshness.badgeBg,
              freshness.textColor
            )}
            title={`Last pushed: ${repo.pushed_at || 'Unknown'}`}
          >
            <span className={cn('h-2 w-2 rounded-full', freshness.dotColor)} />
            <span className="hidden sm:inline">{freshness.label}</span>
            <span className="sm:hidden">{freshness.status}</span>
          </div>
        </div>

        {/* Telemetry Metrics Bar */}
        <div className="mt-3.5 flex flex-wrap items-center gap-4 rounded-lg bg-slate-950/60 px-3 py-2 text-xs border border-slate-800/60">
          {/* Star Count + Delta */}
          <div className="flex items-center gap-1.5 font-medium text-amber-400">
            <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
            <span className="font-mono">{formatCompactNumber(repo.stars_count)}</span>
            {repo.stars_delta !== undefined && repo.stars_delta > 0 && (
              <span className="inline-flex items-center gap-0.5 rounded bg-emerald-500/15 px-1 py-0.2 text-[10px] font-semibold text-emerald-400 border border-emerald-500/30">
                <TrendingUp className="h-2.5 w-2.5" />+{repo.stars_delta}
              </span>
            )}
          </div>

          {/* Forks */}
          <div className="flex items-center gap-1 text-slate-400" title="Forks">
            <GitFork className="h-3.5 w-3.5 text-slate-500" />
            <span className="font-mono">{formatCompactNumber(repo.forks_count)}</span>
          </div>

          {/* Open Issues */}
          <div className="flex items-center gap-1 text-slate-400" title="Open Issues">
            <AlertCircle className="h-3.5 w-3.5 text-slate-500" />
            <span className="font-mono">{formatCompactNumber(repo.open_issues_count)}</span>
          </div>

          {/* Archetype Pill */}
          <button
            type="button"
            onClick={() => onSelectArchetype?.(repo.archetype)}
            className={cn(
              'ml-auto inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors hover:brightness-125',
              archetypeStyle.bg,
              archetypeStyle.text,
              archetypeStyle.border
            )}
            title="Operational Archetype"
          >
            <Layers className="h-3 w-3" />
            <span>{repo.archetype}</span>
          </button>
        </div>

        {/* Concrete AI Problem Solved (1-2 sentences) */}
        <div className="mt-3.5 rounded-lg border border-indigo-950/70 bg-gradient-to-br from-indigo-950/30 to-slate-900/60 p-3">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-indigo-400">
            <Sparkles className="h-3 w-3 text-indigo-400" />
            <span>Target Problem Solved</span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-slate-300">
            {repo.problem_solved}
          </p>
        </div>

        {/* Description fallback if different */}
        {repo.description && (
          <p className="mt-2 line-clamp-2 text-xs text-slate-400 leading-relaxed">
            {repo.description}
          </p>
        )}
      </div>

      {/* Card Footer: Use-Case Chips & Language */}
      <div className="mt-4 pt-3 border-t border-slate-800/80">
        {/* Standardized Use-Case Tags */}
        <div className="flex flex-wrap items-center gap-1.5">
          {(repo.use_cases || []).map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => onSelectUseCase?.(tag)}
              className="inline-flex items-center gap-1 rounded-md border border-slate-800 bg-slate-950/70 px-2 py-0.5 text-[11px] font-medium text-slate-300 transition-colors hover:border-indigo-500/60 hover:bg-indigo-950/40 hover:text-indigo-200"
              title={`Filter by use case: ${tag}`}
            >
              <Tag className="h-2.5 w-2.5 text-slate-500" />
              <span>{tag}</span>
            </button>
          ))}
        </div>

        {/* Bottom Metadata: Primary Language & Ecosystem */}
        <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-2">
            {repo.primary_language && (
              <button
                type="button"
                onClick={() => onSelectLanguage?.(repo.primary_language!)}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-800 bg-slate-950 px-2.5 py-0.5 font-medium text-slate-300 hover:border-slate-700 hover:text-indigo-300"
              >
                <span className="h-2 w-2 rounded-full bg-indigo-400" />
                <span>{repo.primary_language}</span>
              </button>
            )}

            {repo.primary_ecosystem && (
              <span className="hidden sm:inline text-slate-500 text-[11px]">
                {repo.primary_ecosystem}
              </span>
            )}
          </div>

          {repo.confidence_score !== undefined && (
            <span
              className="text-[11px] text-slate-500 font-mono"
              title="Taxonomy Extraction Confidence"
            >
              {repo.confidence_score}% conf
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
