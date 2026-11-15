-- ==============================================================================
-- GitHub Intelligence Engine (2k+ Stars) — Supabase / PostgreSQL Migration
-- Migration: 20260101_init_schema.sql
-- Description: Initializes pgvector, repositories table, HNSW & B-Tree indexes,
--              and the hybrid vector search RPC function (match_repositories).
-- Strict Invariant: Dense vector embeddings are strictly 384 dimensions (bge-small-en-v1.5).
-- ==============================================================================

-- 1. Enable the pgvector extension for high-performance vector operations
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Repositories Table Definition
CREATE TABLE IF NOT EXISTS repositories (
    -- Immutable GitHub repository ID
    id BIGINT PRIMARY KEY,
    full_name TEXT UNIQUE NOT NULL,             -- e.g. "facebook/react"
    name TEXT NOT NULL,                         -- e.g. "react"
    owner TEXT NOT NULL,                        -- e.g. "facebook"
    url TEXT NOT NULL,                          -- e.g. "https://github.com/facebook/react"
    homepage TEXT,                              -- Project website or docs
    description TEXT,                           -- Raw GitHub description
    
    -- Telemetry Metrics (Refreshed Daily via GitHub Actions)
    stars_count INTEGER NOT NULL,
    forks_count INTEGER NOT NULL,
    open_issues_count INTEGER NOT NULL,
    primary_language TEXT,
    license TEXT,
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE,
    pushed_at TIMESTAMP WITH TIME ZONE,
    
    -- 6-Pillar Taxonomy Metadata (Extracted via Resilient Multi-Provider LLM Pool)
    -- Pillar 1: Macro Domain (15 closed taxonomy categories)
    macro_domain TEXT NOT NULL,
    -- Pillar 2: Micro Sub-Domain (precise technical sub-field)
    sub_domain TEXT NOT NULL,
    -- Pillar 3: Functional Archetype (8 closed operational forms)
    archetype TEXT NOT NULL,
    -- Pillar 4: Target Problem Solved (1-2 sentences high-density technical summary)
    problem_solved TEXT NOT NULL,
    -- Pillar 5: Standardized Use-Case Tags (3-5 [Verb-Noun] tags)
    use_cases TEXT[] NOT NULL,
    -- Pillar 6: Primary Ecosystem & Target Audience
    primary_ecosystem TEXT NOT NULL,
    target_audience TEXT[] NOT NULL,
    confidence_score SMALLINT DEFAULT 100,
    is_enriched BOOLEAN DEFAULT FALSE,
    
    -- 384-Dimensional Dense Vector Embedding (BAAI/bge-small-en-v1.5)
    -- Storage: 384 * 4 bytes = 1,536 bytes per vector
    embedding vector(384),
    last_synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Comments on table and columns for documentation & schema governance
COMMENT ON TABLE repositories IS 'Catalog of all public GitHub repositories with >= 2,000 stars enriched with 6-pillar taxonomy and 384-dim embeddings';
COMMENT ON COLUMN repositories.id IS 'GitHub numerical repository ID';
COMMENT ON COLUMN repositories.embedding IS '384-dimensional dense vector generated via bge-small-en-v1.5';
COMMENT ON COLUMN repositories.macro_domain IS 'Closed 15-category macro domain classification';
COMMENT ON COLUMN repositories.archetype IS 'Closed 8-category functional archetype classification';

-- ==============================================================================
-- 3. Indexes
-- ==============================================================================

-- HNSW Vector Index for sub-10ms Cosine Distance Approximate Nearest Neighbor Search
-- Uses vector_cosine_ops with m=16 bidirectional links and ef_construction=64
CREATE INDEX IF NOT EXISTS idx_repos_embedding ON repositories 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- B-Tree Indexes for Instant Faceted Filtering and Sorting
CREATE INDEX IF NOT EXISTS idx_repos_stars ON repositories (stars_count DESC);
CREATE INDEX IF NOT EXISTS idx_repos_domain ON repositories (macro_domain);
CREATE INDEX IF NOT EXISTS idx_repos_archetype ON repositories (archetype);
CREATE INDEX IF NOT EXISTS idx_repos_language ON repositories (primary_language);
CREATE INDEX IF NOT EXISTS idx_repos_is_enriched ON repositories (is_enriched);
CREATE INDEX IF NOT EXISTS idx_repos_pushed_at ON repositories (pushed_at DESC);

-- Composite Index for Common Faceted Filter Queries (domain + stars)
CREATE INDEX IF NOT EXISTS idx_repos_domain_stars ON repositories (macro_domain, stars_count DESC);

-- ==============================================================================
-- 4. Hybrid Vector & Faceted Filter RPC Function
-- ==============================================================================
-- Supports semantic cosine similarity matching combined with dynamic metadata
-- filtering (macro_domain, archetype, primary_language).
CREATE OR REPLACE FUNCTION match_repositories(
    query_embedding vector(384),
    match_threshold float DEFAULT 0.45,
    match_count int DEFAULT 25,
    filter_domain text DEFAULT NULL,
    filter_archetype text DEFAULT NULL,
    filter_language text DEFAULT NULL
)
RETURNS TABLE (
    id BIGINT,
    full_name TEXT,
    stars_count INTEGER,
    macro_domain TEXT,
    archetype TEXT,
    problem_solved TEXT,
    use_cases TEXT[],
    primary_language TEXT,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id,
        r.full_name,
        r.stars_count,
        r.macro_domain,
        r.archetype,
        r.problem_solved,
        r.use_cases,
        r.primary_language,
        (1 - (r.embedding <=> query_embedding))::float AS similarity
    FROM repositories r
    WHERE (filter_domain IS NULL OR r.macro_domain = filter_domain)
      AND (filter_archetype IS NULL OR r.archetype = filter_archetype)
      AND (filter_language IS NULL OR r.primary_language = filter_language)
      AND r.is_enriched = TRUE
      AND r.embedding IS NOT NULL
      AND (1 - (r.embedding <=> query_embedding)) > match_threshold
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$;

-- Detailed Hybrid Vector Search RPC (Includes all card display fields)
CREATE OR REPLACE FUNCTION match_repositories_detailed(
    query_embedding vector(384),
    match_threshold float DEFAULT 0.45,
    match_count int DEFAULT 25,
    filter_domain text DEFAULT NULL,
    filter_archetype text DEFAULT NULL,
    filter_language text DEFAULT NULL
)
RETURNS TABLE (
    id BIGINT,
    full_name TEXT,
    name TEXT,
    owner TEXT,
    url TEXT,
    homepage TEXT,
    description TEXT,
    stars_count INTEGER,
    forks_count INTEGER,
    open_issues_count INTEGER,
    primary_language TEXT,
    license TEXT,
    is_archived BOOLEAN,
    pushed_at TIMESTAMP WITH TIME ZONE,
    macro_domain TEXT,
    sub_domain TEXT,
    archetype TEXT,
    problem_solved TEXT,
    use_cases TEXT[],
    primary_ecosystem TEXT,
    target_audience TEXT[],
    confidence_score SMALLINT,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id,
        r.full_name,
        r.name,
        r.owner,
        r.url,
        r.homepage,
        r.description,
        r.stars_count,
        r.forks_count,
        r.open_issues_count,
        r.primary_language,
        r.license,
        r.is_archived,
        r.pushed_at,
        r.macro_domain,
        r.sub_domain,
        r.archetype,
        r.problem_solved,
        r.use_cases,
        r.primary_ecosystem,
        r.target_audience,
        r.confidence_score,
        (1 - (r.embedding <=> query_embedding))::float AS similarity
    FROM repositories r
    WHERE (filter_domain IS NULL OR r.macro_domain = filter_domain)
      AND (filter_archetype IS NULL OR r.archetype = filter_archetype)
      AND (filter_language IS NULL OR r.primary_language = filter_language)
      AND r.is_enriched = TRUE
      AND r.embedding IS NOT NULL
      AND (1 - (r.embedding <=> query_embedding)) > match_threshold
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$;
