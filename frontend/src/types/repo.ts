export type MacroDomain =
  | 'AI & Machine Learning'
  | 'Developer Tooling'
  | 'Infrastructure & DevOps'
  | 'Databases & Storage'
  | 'Web Frontend'
  | 'Web Backend & API'
  | 'Cybersecurity & Privacy'
  | 'Systems & OS Programming'
  | 'Mobile & Embedded'
  | 'Data Engineering'
  | 'Networking & Protocols'
  | 'Programming Languages & Compilers'
  | 'Curated Lists & Awesome Resources'
  | 'Books & Educational Materials'
  | 'Desktop & Consumer Apps';

export const MACRO_DOMAINS: MacroDomain[] = [
  'AI & Machine Learning',
  'Developer Tooling',
  'Infrastructure & DevOps',
  'Databases & Storage',
  'Web Frontend',
  'Web Backend & API',
  'Cybersecurity & Privacy',
  'Systems & OS Programming',
  'Mobile & Embedded',
  'Data Engineering',
  'Networking & Protocols',
  'Programming Languages & Compilers',
  'Curated Lists & Awesome Resources',
  'Books & Educational Materials',
  'Desktop & Consumer Apps',
];

export type FunctionalArchetype =
  | 'Runnable Server / Engine'
  | 'CLI Tool / Binary'
  | 'Library / SDK'
  | 'Framework / Fullstack Platform'
  | 'Curated Resource / Awesome List'
  | 'Book / Course / Tutorial'
  | 'Starter Template / Boilerplate'
  | 'Browser Extension / Desktop Plugin';

export interface ArchetypeOption {
  id: string;
  label: string;
  dbValues: FunctionalArchetype[];
}

export const ARCHETYPE_OPTIONS: ArchetypeOption[] = [
  { id: 'all', label: 'All', dbValues: [] },
  { id: 'server', label: 'Server/Daemon', dbValues: ['Runnable Server / Engine'] },
  { id: 'cli', label: 'CLI Binary', dbValues: ['CLI Tool / Binary'] },
  { id: 'library', label: 'Library/SDK', dbValues: ['Library / SDK'] },
  { id: 'framework', label: 'Framework', dbValues: ['Framework / Fullstack Platform'] },
  { id: 'curated', label: 'Curated List', dbValues: ['Curated Resource / Awesome List'] },
  { id: 'tutorial', label: 'Tutorial/Book', dbValues: ['Book / Course / Tutorial'] },
];

export const POPULAR_LANGUAGES = [
  'All',
  'Python',
  'TypeScript',
  'Rust',
  'Go',
  'C++',
  'JavaScript',
  'Java',
  'C',
  'Swift',
  'Kotlin',
  'Ruby',
  'C#',
];

export interface Repository {
  id: number;
  full_name: string;
  name: string;
  owner: string;
  url: string;
  homepage?: string | null;
  description?: string | null;
  stars_count: number;
  stars_delta?: number;
  forks_count: number;
  open_issues_count: number;
  primary_language?: string | null;
  license?: string | null;
  is_archived?: boolean;
  created_at?: string;
  pushed_at?: string;
  macro_domain: string;
  sub_domain?: string;
  archetype: string;
  problem_solved: string;
  use_cases: string[];
  primary_ecosystem?: string;
  target_audience?: string[];
  confidence_score?: number;
  is_enriched?: boolean;
  similarity?: number;
}

export type SearchMode = 'semantic' | 'keyword';

export interface SearchFilters {
  query: string;
  domain: string;
  archetype: string;
  language: string;
  min_stars: number;
  mode: SearchMode;
}

export interface SearchResponse {
  results: Repository[];
  total: number;
  latency_ms: number;
  provider: 'supabase' | 'turso' | 'mock-memory';
  mode: SearchMode;
}
