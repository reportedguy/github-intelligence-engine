/**
 * ==============================================================================
 * GitHub Intelligence Engine (2k+ Stars) — Universal Drizzle ORM Schema
 * File: src/db/schema.ts
 * Description: Dual PostgreSQL (Supabase) & LibSQL (Turso) ORM Schema
 *              with strict 384-dimensional vector typing, 6-pillar taxonomy enums,
 *              and bi-directional conversion helpers.
 * Invariant: Vector embeddings are strictly 384 dimensions (bge-small-en-v1.5).
 * ==============================================================================
 */

import {
  pgTable,
  bigint,
  text,
  integer,
  smallint,
  boolean,
  timestamp,
  index,
  customType,
} from 'drizzle-orm/pg-core';

import {
  sqliteTable,
  integer as sqliteInteger,
  text as sqliteText,
  index as sqliteIndex,
  customType as sqliteCustomType,
} from 'drizzle-orm/sqlite-core';

// ==============================================================================
// 1. Strict 6-Pillar Categorization Enums & Const Types
// ==============================================================================

/**
 * Pillar 1: Macro Domain (Strict 15-Item Closed Enum)
 */
export const MACRO_DOMAINS = [
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
] as const;

export type MacroDomain = (typeof MACRO_DOMAINS)[number];

/**
 * Pillar 3: Functional Archetype (Strict 8-Item Closed Enum)
 */
export const FUNCTIONAL_ARCHETYPES = [
  'Runnable Server / Engine',
  'CLI Tool / Binary',
  'Library / SDK',
  'Framework / Fullstack Platform',
  'Curated Resource / Awesome List',
  'Book / Course / Tutorial',
  'Starter Template / Boilerplate',
  'Browser Extension / Desktop Plugin',
] as const;

export type FunctionalArchetype = (typeof FUNCTIONAL_ARCHETYPES)[number];

export const VECTOR_DIMENSIONS = 384 as const;

// ==============================================================================
// 2. Custom Vector Types
// ==============================================================================

/**
 * PostgreSQL pgvector custom type: vector(384)
 */
export const pgVector384 = customType<{
  data: number[];
  driverData: string;
}>({
  dataType() {
    return 'vector(384)';
  },
  toDriver(value: number[]): string {
    if (value.length !== VECTOR_DIMENSIONS) {
      throw new Error(
        `Invalid vector dimensions: expected ${VECTOR_DIMENSIONS}, received ${value.length}`
      );
    }
    return JSON.stringify(value);
  },
  fromDriver(value: unknown): number[] {
    if (typeof value === 'string') {
      try {
        return JSON.parse(value);
      } catch {
        // Fallback for pgvector string representation: [0.1, 0.2, ...]
        const sanitized = value.replace(/^\[/, '').replace(/\]$/, '');
        return sanitized.split(',').map((n) => parseFloat(n.trim()));
      }
    }
    if (Array.isArray(value)) {
      return value.map(Number);
    }
    return [];
  },
});

/**
 * LibSQL / SQLite custom type: F32_BLOB(384)
 */
export const libsqlF32Blob384 = sqliteCustomType<{
  data: number[] | Float32Array;
  driverData: Buffer | Uint8Array;
}>({
  dataType() {
    return 'F32_BLOB(384)';
  },
  toDriver(value: number[] | Float32Array): Uint8Array {
    let f32: Float32Array;
    if (value instanceof Float32Array) {
      f32 = value;
    } else {
      if (value.length !== VECTOR_DIMENSIONS) {
        throw new Error(
          `Invalid vector dimensions: expected ${VECTOR_DIMENSIONS}, received ${value.length}`
        );
      }
      f32 = new Float32Array(value);
    }
    return new Uint8Array(f32.buffer, f32.byteOffset, f32.byteLength);
  },
  fromDriver(value: unknown): number[] {
    if (value instanceof Uint8Array || (typeof Buffer !== 'undefined' && Buffer.isBuffer(value))) {
      const buf = value as Uint8Array;
      const f32 = new Float32Array(buf.buffer, buf.byteOffset, buf.byteLength / 4);
      return Array.from(f32);
    }
    if (Array.isArray(value)) {
      return value.map(Number);
    }
    return [];
  },
});

// ==============================================================================
// 3. PostgreSQL Schema (Option 1: Supabase + pgvector)
// ==============================================================================

export const repositoriesPg = pgTable(
  'repositories',
  {
    id: bigint('id', { mode: 'number' }).primaryKey(),
    fullName: text('full_name').notNull().unique(),
    name: text('name').notNull(),
    owner: text('owner').notNull(),
    url: text('url').notNull(),
    homepage: text('homepage'),
    description: text('description'),

    // Telemetry Metrics
    starsCount: integer('stars_count').notNull(),
    forksCount: integer('forks_count').notNull(),
    openIssuesCount: integer('open_issues_count').notNull(),
    primaryLanguage: text('primary_language'),
    license: text('license'),
    isArchived: boolean('is_archived').default(false).notNull(),
    createdAt: timestamp('created_at', { withTimezone: true }),
    pushedAt: timestamp('pushed_at', { withTimezone: true }),

    // 6-Pillar Taxonomy Metadata
    macroDomain: text('macro_domain').notNull().$type<MacroDomain>(),
    subDomain: text('sub_domain').notNull(),
    archetype: text('archetype').notNull().$type<FunctionalArchetype>(),
    problemSolved: text('problem_solved').notNull(),
    useCases: text('use_cases').array().notNull(),
    primaryEcosystem: text('primary_ecosystem').notNull(),
    targetAudience: text('target_audience').array().notNull(),
    confidenceScore: smallint('confidence_score').default(100).notNull(),
    isEnriched: boolean('is_enriched').default(false).notNull(),

    // Dense Vector (384 Dimensions)
    embedding: pgVector384('embedding'),
    lastSyncedAt: timestamp('last_synced_at', { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    starsIdx: index('idx_repos_stars').on(table.starsCount),
    domainIdx: index('idx_repos_domain').on(table.macroDomain),
    archetypeIdx: index('idx_repos_archetype').on(table.archetype),
    languageIdx: index('idx_repos_language').on(table.primaryLanguage),
    enrichedIdx: index('idx_repos_is_enriched').on(table.isEnriched),
    pushedAtIdx: index('idx_repos_pushed_at').on(table.pushedAt),
  })
);

export type RepositoryPg = typeof repositoriesPg.$inferSelect;
export type NewRepositoryPg = typeof repositoriesPg.$inferInsert;

// ==============================================================================
// 4. LibSQL / SQLite Schema (Option 2: Turso + Native Vector Index)
// ==============================================================================

export const repositoriesLibsql = sqliteTable(
  'repositories',
  {
    id: sqliteInteger('id').primaryKey(),
    fullName: sqliteText('full_name').notNull().unique(),
    name: sqliteText('name').notNull(),
    owner: sqliteText('owner').notNull(),
    url: sqliteText('url').notNull(),
    homepage: sqliteText('homepage'),
    description: sqliteText('description'),

    // Telemetry Metrics
    starsCount: sqliteInteger('stars_count').notNull(),
    forksCount: sqliteInteger('forks_count').notNull(),
    openIssuesCount: sqliteInteger('open_issues_count').notNull(),
    primaryLanguage: sqliteText('primary_language'),
    license: sqliteText('license'),
    isArchived: sqliteInteger('is_archived').default(0).notNull(),
    createdAt: sqliteText('created_at'),
    pushedAt: sqliteText('pushed_at'),

    // 6-Pillar Taxonomy Metadata (Stored as JSON text strings in SQLite)
    macroDomain: sqliteText('macro_domain').notNull().$type<MacroDomain>(),
    subDomain: sqliteText('sub_domain').notNull(),
    archetype: sqliteText('archetype').notNull().$type<FunctionalArchetype>(),
    problemSolved: sqliteText('problem_solved').notNull(),
    useCases: sqliteText('use_cases').notNull(), // JSON string: ["Tag1", "Tag2"]
    primaryEcosystem: sqliteText('primary_ecosystem').notNull(),
    targetAudience: sqliteText('target_audience').notNull(), // JSON string: ["Audience1"]
    confidenceScore: sqliteInteger('confidence_score').default(100).notNull(),
    isEnriched: sqliteInteger('is_enriched').default(0).notNull(),

    // Dense Vector (384 Dimensions, Float32 BLOB)
    embedding: libsqlF32Blob384('embedding'),
    lastSyncedAt: sqliteText('last_synced_at'),
  },
  (table) => ({
    starsIdx: sqliteIndex('idx_repos_stars_libsql').on(table.starsCount),
    domainIdx: sqliteIndex('idx_repos_domain_libsql').on(table.macroDomain),
    archetypeIdx: sqliteIndex('idx_repos_archetype_libsql').on(table.archetype),
    languageIdx: sqliteIndex('idx_repos_language_libsql').on(table.primaryLanguage),
    enrichedIdx: sqliteIndex('idx_repos_enriched_libsql').on(table.isEnriched),
    pushedAtIdx: sqliteIndex('idx_repos_pushed_at_libsql').on(table.pushedAt),
  })
);

export type RepositoryLibsql = typeof repositoriesLibsql.$inferSelect;
export type NewRepositoryLibsql = typeof repositoriesLibsql.$inferInsert;

// ==============================================================================
// 5. Unified Repository Domain Model & Normalization Adapters
// ==============================================================================

export interface Repository {
  id: number;
  fullName: string;
  name: string;
  owner: string;
  url: string;
  homepage: string | null;
  description: string | null;
  starsCount: number;
  forksCount: number;
  openIssuesCount: number;
  primaryLanguage: string | null;
  license: string | null;
  isArchived: boolean;
  createdAt: string | null;
  pushedAt: string | null;
  macroDomain: MacroDomain;
  subDomain: string;
  archetype: FunctionalArchetype;
  problemSolved: string;
  useCases: string[];
  primaryEcosystem: string;
  targetAudience: string[];
  confidenceScore: number;
  isEnriched: boolean;
  embedding: number[] | null;
  lastSyncedAt: string | null;
}

/**
 * Converts a Supabase / PostgreSQL row into the universal Repository format.
 */
export function fromPgRecord(record: RepositoryPg): Repository {
  return {
    id: record.id,
    fullName: record.fullName,
    name: record.name,
    owner: record.owner,
    url: record.url,
    homepage: record.homepage,
    description: record.description,
    starsCount: record.starsCount,
    forksCount: record.forksCount,
    openIssuesCount: record.openIssuesCount,
    primaryLanguage: record.primaryLanguage,
    license: record.license,
    isArchived: record.isArchived,
    createdAt: record.createdAt ? record.createdAt.toISOString() : null,
    pushedAt: record.pushedAt ? record.pushedAt.toISOString() : null,
    macroDomain: record.macroDomain,
    subDomain: record.subDomain,
    archetype: record.archetype,
    problemSolved: record.problemSolved,
    useCases: record.useCases,
    primaryEcosystem: record.primaryEcosystem,
    targetAudience: record.targetAudience,
    confidenceScore: record.confidenceScore,
    isEnriched: record.isEnriched,
    embedding: record.embedding,
    lastSyncedAt: record.lastSyncedAt ? record.lastSyncedAt.toISOString() : null,
  };
}

/**
 * Converts a Turso / LibSQL row into the universal Repository format.
 */
export function fromLibsqlRecord(record: RepositoryLibsql): Repository {
  const parseJsonArray = (val: string): string[] => {
    try {
      const parsed = JSON.parse(val);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  };

  return {
    id: record.id,
    fullName: record.fullName,
    name: record.name,
    owner: record.owner,
    url: record.url,
    homepage: record.homepage,
    description: record.description,
    starsCount: record.starsCount,
    forksCount: record.forksCount,
    openIssuesCount: record.openIssuesCount,
    primaryLanguage: record.primaryLanguage,
    license: record.license,
    isArchived: Boolean(record.isArchived),
    createdAt: record.createdAt,
    pushedAt: record.pushedAt,
    macroDomain: record.macroDomain,
    subDomain: record.subDomain,
    archetype: record.archetype,
    problemSolved: record.problemSolved,
    useCases: parseJsonArray(record.useCases),
    primaryEcosystem: record.primaryEcosystem,
    targetAudience: parseJsonArray(record.targetAudience),
    confidenceScore: record.confidenceScore,
    isEnriched: Boolean(record.isEnriched),
    embedding: (record.embedding as number[]) ?? null,
    lastSyncedAt: record.lastSyncedAt,
  };
}

/**
 * Formats a domain repository into a LibSQL insert payload.
 */
export function toLibsqlInsert(repo: Repository): NewRepositoryLibsql {
  return {
    id: repo.id,
    fullName: repo.fullName,
    name: repo.name,
    owner: repo.owner,
    url: repo.url,
    homepage: repo.homepage,
    description: repo.description,
    starsCount: repo.starsCount,
    forksCount: repo.forksCount,
    openIssuesCount: repo.openIssuesCount,
    primaryLanguage: repo.primaryLanguage,
    license: repo.license,
    isArchived: repo.isArchived ? 1 : 0,
    createdAt: repo.createdAt,
    pushedAt: repo.pushedAt,
    macroDomain: repo.macroDomain,
    subDomain: repo.subDomain,
    archetype: repo.archetype,
    problemSolved: repo.problemSolved,
    useCases: JSON.stringify(repo.useCases),
    primaryEcosystem: repo.primaryEcosystem,
    targetAudience: JSON.stringify(repo.targetAudience),
    confidenceScore: repo.confidenceScore,
    isEnriched: repo.isEnriched ? 1 : 0,
    embedding: repo.embedding ? new Float32Array(repo.embedding) : null,
    lastSyncedAt: repo.lastSyncedAt ?? new Date().toISOString(),
  };
}
