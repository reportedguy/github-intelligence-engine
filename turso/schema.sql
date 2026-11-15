-- ==============================================================================
-- GitHub Intelligence Engine (2k+ Stars) — Turso / LibSQL Schema
-- File: turso/schema.sql
-- Description: LibSQL schema with native vector indexing (F32_BLOB(384))
--              and B-tree indexes for instant faceted filtering.
-- Strict Invariant: Dense vector embeddings are strictly 384 dimensions (bge-small-en-v1.5).
-- ==============================================================================

CREATE TABLE IF NOT EXISTS repositories (
    -- Immutable GitHub repository ID
    id INTEGER PRIMARY KEY,
    full_name TEXT UNIQUE NOT NULL,             -- e.g. "facebook/react"
    name TEXT NOT NULL,                         -- e.g. "react"
    owner TEXT NOT NULL,                        -- e.g. "facebook"
    url TEXT NOT NULL,                          -- e.g. "https://github.com/facebook/react"
    homepage TEXT,                              -- Project website or documentation
    description TEXT,                           -- Repository description
    
    -- Telemetry Metrics (Refreshed Daily via GitHub Actions)
    stars_count INTEGER NOT NULL,
    forks_count INTEGER NOT NULL,
    open_issues_count INTEGER NOT NULL,
    primary_language TEXT,
    license TEXT,
    is_archived INTEGER DEFAULT 0,              -- 0 = False, 1 = True (SQLite boolean convention)
    created_at TEXT,                            -- ISO-8601 UTC timestamp string
    pushed_at TEXT,                             -- ISO-8601 UTC timestamp string
    
    -- 6-Pillar Taxonomy Metadata (JSON strings for arrays)
    -- Pillar 1: Macro Domain (15 closed taxonomy categories)
    macro_domain TEXT NOT NULL,
    -- Pillar 2: Micro Sub-Domain (precise technical sub-field)
    sub_domain TEXT NOT NULL,
    -- Pillar 3: Functional Archetype (8 closed operational forms)
    archetype TEXT NOT NULL,
    -- Pillar 4: Target Problem Solved (1-2 sentences high-density technical summary)
    problem_solved TEXT NOT NULL,
    -- Pillar 5: Standardized Use-Case Tags (JSON array of strings e.g. '["Distributed-Caching"]')
    use_cases TEXT NOT NULL,
    -- Pillar 6: Primary Ecosystem & Target Audience (JSON array of strings)
    primary_ecosystem TEXT NOT NULL,
    target_audience TEXT NOT NULL,
    confidence_score INTEGER DEFAULT 100,
    is_enriched INTEGER DEFAULT 0,              -- 0 = Pending, 1 = Enriched
    
    -- Native LibSQL 384-Dimensional Vector (Float32 blob)
    -- Storage: 384 * 4 bytes = 1,536 bytes
    embedding F32_BLOB(384),
    last_synced_at TEXT DEFAULT (datetime('now'))
);

-- ==============================================================================
-- Indexes
-- ==============================================================================

-- Native LibSQL Vector Top-K Approximate Nearest Neighbor Index
CREATE INDEX IF NOT EXISTS idx_repos_vector ON repositories(libsql_vector_idx(embedding));

-- B-Tree Indexes for Instant Faceted Filtering and Metric Sorting
CREATE INDEX IF NOT EXISTS idx_repos_stars ON repositories(stars_count DESC);
CREATE INDEX IF NOT EXISTS idx_repos_domain ON repositories(macro_domain);
CREATE INDEX IF NOT EXISTS idx_repos_archetype ON repositories(archetype);
CREATE INDEX IF NOT EXISTS idx_repos_language ON repositories(primary_language);
CREATE INDEX IF NOT EXISTS idx_repos_enriched ON repositories(is_enriched);
CREATE INDEX IF NOT EXISTS idx_repos_pushed_at ON repositories(pushed_at DESC);

-- Composite Index for Common Domain + Stars Sorting
CREATE INDEX IF NOT EXISTS idx_repos_domain_stars ON repositories(macro_domain, stars_count DESC);

-- ==============================================================================
-- Query Examples & Reference Pattern for LibSQL Vector Search
-- ==============================================================================
-- To query top-K repositories by cosine similarity with optional metadata filters:
--
-- SELECT 
--     r.id,
--     r.full_name,
--     r.stars_count,
--     r.macro_domain,
--     r.archetype,
--     r.problem_solved,
--     r.use_cases,
--     r.primary_language,
--     vector_distance_cos(r.embedding, vector384(?1)) AS distance,
--     (1.0 - vector_distance_cos(r.embedding, vector384(?1))) AS similarity
-- FROM vector_top_k('idx_repos_vector', vector384(?1), ?2) v
-- JOIN repositories r ON r.rowid = v.id
-- WHERE r.is_enriched = 1
--   AND (?3 IS NULL OR r.macro_domain = ?3)
--   AND (?4 IS NULL OR r.archetype = ?4)
--   AND (?5 IS NULL OR r.primary_language = ?5)
-- ORDER BY distance ASC;
