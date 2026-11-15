import { createClient as createSupabaseClient } from '@supabase/supabase-js';
import { createClient as createTursoClient } from '@libsql/client';
import { Repository, SearchFilters, SearchResponse } from '@/types/repo';
import { MOCK_REPOSITORIES } from './mockData';
import { generateQueryEmbedding } from './embedder';

// Configurable DB Provider
const DB_PROVIDER = (process.env.DB_PROVIDER || 'supabase').toLowerCase();

// Supabase credentials
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || '';
const SUPABASE_KEY =
  process.env.SUPABASE_SERVICE_ROLE_KEY ||
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
  process.env.SUPABASE_ANON_KEY ||
  '';

// Turso credentials
const TURSO_URL = process.env.TURSO_DATABASE_URL || '';
const TURSO_AUTH_TOKEN = process.env.TURSO_AUTH_TOKEN || '';

const hasSupabase = Boolean(SUPABASE_URL && SUPABASE_KEY);
const hasTurso = Boolean(TURSO_URL && TURSO_AUTH_TOKEN);

export async function executeSearch(filters: SearchFilters): Promise<SearchResponse> {
  const startTime = Date.now();

  try {
    if (DB_PROVIDER === 'turso' && hasTurso) {
      const results = await searchTurso(filters);
      return {
        results,
        total: results.length,
        latency_ms: Date.now() - startTime,
        provider: 'turso',
        mode: filters.mode,
      };
    }

    if (hasSupabase) {
      const results = await searchSupabase(filters);
      return {
        results,
        total: results.length,
        latency_ms: Date.now() - startTime,
        provider: 'supabase',
        mode: filters.mode,
      };
    }
  } catch (err) {
    console.warn('[db] External database search failed, falling back to local memory engine:', err);
  }

  // Graceful zero-cost fallback: memory engine
  const results = searchMemory(filters);
  return {
    results,
    total: results.length,
    latency_ms: Date.now() - startTime,
    provider: 'mock-memory',
    mode: filters.mode,
  };
}

/**
 * Supabase Hybrid Search (pgvector + faceted SQL)
 */
async function searchSupabase(filters: SearchFilters): Promise<Repository[]> {
  const supabase = createSupabaseClient(SUPABASE_URL, SUPABASE_KEY);

  if (filters.mode === 'semantic' && filters.query.trim()) {
    const queryEmbedding = await generateQueryEmbedding(filters.query);

    if (queryEmbedding) {
      const { data, error } = await supabase.rpc('match_repositories', {
        query_embedding: queryEmbedding,
        match_threshold: 0.25,
        match_count: 50,
        filter_domain: filters.domain && filters.domain !== 'All' ? filters.domain : null,
        filter_archetype: filters.archetype && filters.archetype !== 'All' ? filters.archetype : null,
        filter_language: filters.language && filters.language !== 'All' ? filters.language : null,
      });

      if (!error && Array.isArray(data)) {
        return data
          .filter((repo: any) => (repo.stars_count || 0) >= filters.min_stars)
          .map(normalizeRepositoryRecord);
      }
    }
  }

  // Keyword / Faceted standard query in Supabase
  let queryBuilder = supabase.from('repositories').select('*');

  if (filters.min_stars > 0) {
    queryBuilder = queryBuilder.gte('stars_count', filters.min_stars);
  }
  if (filters.domain && filters.domain !== 'All') {
    queryBuilder = queryBuilder.eq('macro_domain', filters.domain);
  }
  if (filters.language && filters.language !== 'All') {
    queryBuilder = queryBuilder.eq('primary_language', filters.language);
  }
  if (filters.archetype && filters.archetype !== 'All') {
    queryBuilder = queryBuilder.ilike('archetype', `%${filters.archetype}%`);
  }

  if (filters.query.trim()) {
    const q = filters.query.trim();
    queryBuilder = queryBuilder.or(
      `full_name.ilike.%${q}%,description.ilike.%${q}%,problem_solved.ilike.%${q}%`
    );
  }

  queryBuilder = queryBuilder.order('stars_count', { ascending: false }).limit(50);

  const { data, error } = await queryBuilder;
  if (error) throw error;
  return (data || []).map(normalizeRepositoryRecord);
}

/**
 * Turso LibSQL Hybrid Search
 */
async function searchTurso(filters: SearchFilters): Promise<Repository[]> {
  const turso = createTursoClient({
    url: TURSO_URL,
    authToken: TURSO_AUTH_TOKEN,
  });

  const conditions: string[] = ['stars_count >= ?'];
  const args: any[] = [filters.min_stars];

  if (filters.domain && filters.domain !== 'All') {
    conditions.push('macro_domain = ?');
    args.push(filters.domain);
  }
  if (filters.language && filters.language !== 'All') {
    conditions.push('primary_language = ?');
    args.push(filters.language);
  }
  if (filters.archetype && filters.archetype !== 'All') {
    conditions.push('archetype LIKE ?');
    args.push(`%${filters.archetype}%`);
  }

  if (filters.query.trim()) {
    const term = `%${filters.query.trim()}%`;
    conditions.push('(full_name LIKE ? OR description LIKE ? OR problem_solved LIKE ? OR use_cases LIKE ?)');
    args.push(term, term, term, term);
  }

  const sql = `
    SELECT * FROM repositories
    WHERE ${conditions.join(' AND ')}
    ORDER BY stars_count DESC
    LIMIT 50
  `;

  const result = await turso.execute({ sql, args });
  return result.rows.map((row) => normalizeTursoRecord(row));
}

/**
 * In-Memory Search Engine (Fallback & Local Dev Experience)
 */
function searchMemory(filters: SearchFilters): Repository[] {
  const queryLower = filters.query.trim().toLowerCase();
  const queryTokens = queryLower ? queryLower.split(/\s+/).filter(Boolean) : [];

  return MOCK_REPOSITORIES.filter((repo) => {
    // 1. Minimum stars filter
    if (repo.stars_count < filters.min_stars) return false;

    // 2. Macro Domain filter
    if (filters.domain && filters.domain !== 'All' && repo.macro_domain !== filters.domain) {
      return false;
    }

    // 3. Language filter
    if (
      filters.language &&
      filters.language !== 'All' &&
      repo.primary_language?.toLowerCase() !== filters.language.toLowerCase()
    ) {
      return false;
    }

    // 4. Archetype filter
    if (filters.archetype && filters.archetype !== 'All') {
      const archLower = repo.archetype.toLowerCase();
      const targetLower = filters.archetype.toLowerCase();
      if (!archLower.includes(targetLower)) return false;
    }

    // 5. Query matching
    if (!queryLower) return true;

    if (filters.mode === 'keyword') {
      const searchableText = `${repo.full_name} ${repo.description || ''} ${repo.problem_solved} ${repo.use_cases.join(' ')} ${repo.primary_language || ''}`.toLowerCase();
      return queryTokens.every((token) => searchableText.includes(token));
    }

    // Semantic Intent Simulation in Memory
    const searchableText = `${repo.full_name} ${repo.problem_solved} ${repo.sub_domain || ''} ${repo.use_cases.join(' ')} ${repo.macro_domain} ${repo.description || ''}`.toLowerCase();
    
    // Check if any token matches concepts
    const matchCount = queryTokens.filter((token) => searchableText.includes(token)).length;
    return matchCount > 0 || searchableText.includes(queryLower);
  })
    .map((repo) => {
      // Calculate relevance score
      if (queryLower) {
        let score = 0.5;
        const searchableText = `${repo.full_name} ${repo.problem_solved} ${repo.use_cases.join(' ')}`.toLowerCase();
        queryTokens.forEach((t) => {
          if (searchableText.includes(t)) score += 0.15;
        });
        return { ...repo, similarity: Math.min(Number(score.toFixed(2)), 0.99) };
      }
      return repo;
    })
    .sort((a, b) => {
      if (filters.mode === 'semantic' && queryLower) {
        return (b.similarity || 0) - (a.similarity || 0);
      }
      return b.stars_count - a.stars_count;
    });
}

function normalizeRepositoryRecord(raw: any): Repository {
  let useCases: string[] = [];
  if (Array.isArray(raw.use_cases)) {
    useCases = raw.use_cases;
  } else if (typeof raw.use_cases === 'string') {
    try {
      useCases = JSON.parse(raw.use_cases);
    } catch {
      useCases = raw.use_cases.split(',').map((s: string) => s.trim());
    }
  }

  let targetAudience: string[] = [];
  if (Array.isArray(raw.target_audience)) {
    targetAudience = raw.target_audience;
  } else if (typeof raw.target_audience === 'string') {
    try {
      targetAudience = JSON.parse(raw.target_audience);
    } catch {
      targetAudience = [raw.target_audience];
    }
  }

  return {
    id: Number(raw.id),
    full_name: raw.full_name,
    name: raw.name || raw.full_name.split('/')[1] || raw.full_name,
    owner: raw.owner || raw.full_name.split('/')[0] || '',
    url: raw.url || `https://github.com/${raw.full_name}`,
    homepage: raw.homepage,
    description: raw.description,
    stars_count: Number(raw.stars_count || 0),
    stars_delta: raw.stars_delta || Math.floor((raw.stars_count || 1000) * 0.003),
    forks_count: Number(raw.forks_count || 0),
    open_issues_count: Number(raw.open_issues_count || 0),
    primary_language: raw.primary_language || 'Other',
    license: raw.license,
    is_archived: Boolean(raw.is_archived),
    created_at: raw.created_at,
    pushed_at: raw.pushed_at,
    macro_domain: raw.macro_domain || 'Developer Tooling',
    sub_domain: raw.sub_domain,
    archetype: raw.archetype || 'Library / SDK',
    problem_solved: raw.problem_solved || 'High-performance engineering software repository.',
    use_cases: useCases,
    primary_ecosystem: raw.primary_ecosystem,
    target_audience: targetAudience,
    confidence_score: raw.confidence_score || 95,
    is_enriched: Boolean(raw.is_enriched),
    similarity: raw.similarity ? Number(raw.similarity.toFixed(3)) : undefined,
  };
}

function normalizeTursoRecord(row: any): Repository {
  return normalizeRepositoryRecord({
    id: row.id,
    full_name: row.full_name,
    name: row.name,
    owner: row.owner,
    url: row.url,
    homepage: row.homepage,
    description: row.description,
    stars_count: row.stars_count,
    forks_count: row.forks_count,
    open_issues_count: row.open_issues_count,
    primary_language: row.primary_language,
    license: row.license,
    is_archived: row.is_archived === 1,
    created_at: row.created_at,
    pushed_at: row.pushed_at,
    macro_domain: row.macro_domain,
    sub_domain: row.sub_domain,
    archetype: row.archetype,
    problem_solved: row.problem_solved,
    use_cases: row.use_cases,
    primary_ecosystem: row.primary_ecosystem,
    target_audience: row.target_audience,
    confidence_score: row.confidence_score,
    is_enriched: row.is_enriched === 1,
  });
}
