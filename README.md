# GitHub Intelligence Engine (2k+ Stars)

> **Autonomous Daily Sync & Semantic Discovery Engine for High-Impact Open Source Repositories**  
> **Target Scope:** Every public repository on GitHub with $\ge 2,000$ stars (~30,000 repositories)  
> **Infrastructure Cost:** **$0.00 / month** (100% Free Tiers / Local Edge Compute)  
> **Sync Cadence:** Autonomous Daily Differential Synchronization via GitHub Actions

---

## Table of Contents

- [1. Project Overview](#1-project-overview)
- [2. System Architecture](#2-system-architecture)
- [3. The 6-Pillar Categorization Taxonomy](#3-the-6-pillar-categorization-taxonomy)
- [4. Architectural Invariants](#4-architectural-invariants)
- [5. Dual Database Deployment Guide](#5-dual-database-deployment-guide)
  - [Option 1: Supabase (PostgreSQL + pgvector)](#option-1-supabase-postgresql--pgvector)
  - [Option 2: Turso (LibSQL Native Vectors)](#option-2-turso-libsql-native-vectors)
- [6. Multi-Provider Free-Tier LLM Resiliency Engine](#6-multi-provider-free-tier-llm-resiliency-engine)
- [7. Setting Up GitHub Actions & Secrets](#7-setting-up-github-actions--secrets)
- [8. Local Development & Quickstart](#8-local-development--quickstart)
- [9. Verification & Health Audit](#9-verification--health-audit)
- [10. 10-Point Supervisor Quality Gates](#10-10-point-supervisor-quality-gates)

---

## 1. Project Overview

The **GitHub Intelligence Engine** solves a fundamental discovery breakdown in the open-source software ecosystem. While GitHub tracks stars, forks, and issues, it offers no structured architectural classification, no operational form-factor metadata, and no semantic conceptual search. Developers seeking "a self-hosted logging alternative to Datadog with low memory footprint" or "a Rust CLI for memory-mapped file indexing" are forced to rely on fragmented Google searches or uncurated lists.

This engine continuously indexes, classifies, and vectors every repository on GitHub with **2,000 or more stars** (~30,000 repos) using:
1. **Adaptive Bisection Ingestion**: Overcoming GitHub's strict 1,000-item search limit through recursive binary bracket splitting and creation-date partitioning.
2. **6-Pillar Closed Taxonomy**: Eliminating hallucinations and redundant tags by constraining LLM categorizations to rigorous enums and verb-noun use cases.
3. **Multi-Provider LLM Failover**: Routing extraction through free-tier APIs (Groq, Google AI Studio Gemini, Cerebras, OpenRouter) with zero API expense.
4. **Local 384-dim ONNX Vector Embeddings**: Generating dense vector representations using `fastembed` (`bge-small-en-v1.5`) directly within GitHub Actions CI runners.
5. **Zero-Cost Dual Storage**: Supporting either **Supabase (pgvector)** or **Turso (LibSQL)** within their persistent free quotas.

---

## 2. System Architecture

```mermaid
flowchart TD
    subgraph Data Extraction [GitHub REST API]
        GH[GitHub Search & Repo API]
    end

    subgraph Autonomous Daily Cron [GitHub Actions - Free Tier]
        CronTrigger[Schedule: 00:00 UTC / manual workflow_dispatch] --> Fetcher[Adaptive Bisection Fetcher]
        GH -->|Throttled 25 req/min| Fetcher
        Fetcher --> DiffEngine{Repo in Database?}
        
        DiffEngine -->|Yes| FastTelemetry[Bulk Update: Stars, Forks, Issues, Pushed_At]
        DiffEngine -->|No: New / Unenriched Repo| Queue[Enrichment Backfill Queue]
        
        Queue --> ContextExtract[README Sanitizer & Metadata Aggregator]
        ContextExtract --> LLMPool[Multi-Provider LLM Router]
        
        LLMPool -->|Tier 1: Groq Llama 3.3 70B| PydanticCheck{Valid Schema?}
        LLMPool -->|Tier 2: Gemini 2.0 Flash| PydanticCheck
        LLMPool -->|Tier 3: Cerebras Llama 3.1 70B| PydanticCheck
        LLMPool -->|Tier 4: OpenRouter Free Pool| PydanticCheck
        
        PydanticCheck -->|Validated 6-Pillar JSON| FastEmbed[Local 384-dim ONNX: bge-small-en-v1.5]
        PydanticCheck -->|Malformed / 429| FallbackProvider[Switch to Next Free Provider]
        FallbackProvider --> LLMPool
        
        FastEmbed --> FullRecord[(Complete Vector Record)]
    end

    subgraph Storage Layer [Zero-Cost Free Infrastructure]
        FastTelemetry --> DB[(Turso LibSQL 9GB / Supabase pgvector)]
        FullRecord --> DB
    end

    subgraph User Experience Layer [Vercel / Cloudflare Pages]
        ClientBrowser[Browser / AI Agent API] <--> NextApp[Next.js 14 App Router]
        NextApp -->|Cosine Distance + HNSW| DB
        NextApp -->|Faceted Filters + Star Velocity| DB
    end
```

---

## 3. The 6-Pillar Categorization Taxonomy

Every repository undergoes structural decomposition into six deterministic dimensions:

```mermaid
classDiagram
    class RepositoryTaxonomy {
        +MacroDomain macro_domain
        +string sub_domain
        +FunctionalArchetype archetype
        +string problem_solved
        +List~string~ use_cases
        +string primary_ecosystem
        +List~string~ target_audience
        +int confidence_score
    }
    class MacroDomain {
        <<enumeration>>
        AI_MACHINE_LEARNING
        DEVELOPER_TOOLING
        INFRASTRUCTURE_DEVOPS
        DATABASES_STORAGE
        WEB_FRONTEND
        WEB_BACKEND_API
        CYBERSECURITY_PRIVACY
        SYSTEMS_OS_PROGRAMMING
        MOBILE_EMBEDDED
        DATA_ENGINEERING
        NETWORKING_PROTOCOLS
        PROGRAMMING_LANGUAGES_COMPILERS
        CURATED_LISTS_AWESOME
        BOOKS_EDUCATIONAL
        DESKTOP_CONSUMER_APPS
    }
    class FunctionalArchetype {
        <<enumeration>>
        SERVER_ENGINE_DAEMON
        CLI_BINARY_TOOL
        LIBRARY_SDK
        FRAMEWORK_PLATFORM
        CURATED_AWESOME_LIST
        BOOK_COURSE_TUTORIAL
        STARTER_BOILERPLATE
        BROWSER_EXTENSION_PLUGIN
    }
    RepositoryTaxonomy --> MacroDomain
    RepositoryTaxonomy --> FunctionalArchetype
```

| Pillar | Specification | Valid Values / Constraints | Example |
| :--- | :--- | :--- | :--- |
| **1. Macro Domain** | Strict 15-item closed enum | `AI & Machine Learning`, `Developer Tooling`, `Infrastructure & DevOps`, `Databases & Storage`, `Web Frontend`, `Web Backend & API`, `Cybersecurity & Privacy`, `Systems & OS Programming`, `Mobile & Embedded`, `Data Engineering`, `Networking & Protocols`, `Programming Languages & Compilers`, `Curated Lists & Awesome Resources`, `Books & Educational Materials`, `Desktop & Consumer Apps` | `Databases & Storage` |
| **2. Micro Sub-Domain** | Fine-grained technical classification | Specific sub-disciplines | `In-Memory Key-Value Stores` |
| **3. Functional Archetype** | Strict 8-item closed enum | `Runnable Server / Engine`, `CLI Tool / Binary`, `Library / SDK`, `Framework / Fullstack Platform`, `Curated Resource / Awesome List`, `Book / Course / Tutorial`, `Starter Template / Boilerplate`, `Browser Extension / Desktop Plugin` | `Runnable Server / Engine` |
| **4. Problem Solved** | High-density 1–2 sentence engineering statement | Formula: `[Verb phrase stating core bottleneck] + by [Technical implementation mechanism]` | *"Eliminates disk I/O latency by caching relational query sets in memory with sub-millisecond atomic key-value operations."* |
| **5. Standardized Use Cases** | 3 to 5 standardized tags | Strict `[Verb]-[Noun]` syntax | `Distributed-Caching`, `Session-Storage`, `Pub-Sub-Messaging` |
| **6. Ecosystem & Target Audience** | Core runtime + 1–3 persona classifications | Primary language/stack and developer personas | `C / Linux Kernel`, `["Backend Engineers", "Platform / SRE Teams"]` |

---

## 4. Architectural Invariants

1. **$0.00 External API Cost**: No paid API tokens (OpenAI, Anthropic, Pinecone, or AWS) are permitted anywhere in the pipeline.
2. **Deterministic Token-Bucket Throttling**: GitHub API search calls never exceed 25 requests per rolling 60-second window, preventing secondary rate limit blocks.
3. **Partitioned Bisection Ingestion**: No query ever requests more than 1,000 items in a single star bracket. High-density star points (e.g. exactly 2,000 stars) automatically recurse across creation year buckets (`created:YYYY-01-01..YYYY-12-31`).
4. **Local 384-Dimensional Vectors**: Dense vector embeddings are strictly capped at 384 dimensions (`bge-small-en-v1.5`), cutting database memory and indexing overhead by 50% compared to 768-dim models.
5. **Decoupled Telemetry vs. Enrichment**: Raw telemetry ingestion runs rapidly in under 15 minutes; LLM enrichment runs in an idempotent backfill queue with batch controls.

---

## 5. Dual Database Deployment Guide

The pipeline features a unified driver supporting both **Supabase (PostgreSQL 15+ with `pgvector`)** and **Turso (LibSQL with Native Vector Search)**.

### Storage Footprint Calculation for 30,000 Repositories:
- **Text & Relational Metadata**: ~45 MB
- **Dense Vectors (384 Dimensions, Float32)**: $30,000 \times 384 \times 4\text{ bytes} \approx 46\text{ MB}$
- **Vector Index Overhead**: ~75 MB
- **Total Storage**: **~166 MB** (Fits inside Supabase's 500 MB limit with 67% headroom; leaves 98% headroom in Turso's 9 GB limit).

---

### Option 1: Supabase (PostgreSQL + pgvector)

#### Step 1: Create a Free Project
1. Go to [Supabase](https://supabase.com/) and create a free project.
2. Open the **SQL Editor** from the left navigation panel.

#### Step 2: Execute Database Migration
Run the following SQL migration script in the Supabase SQL editor:

```sql
-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create primary repositories table
CREATE TABLE IF NOT EXISTS repositories (
    id BIGINT PRIMARY KEY,                      -- Immutable GitHub repository ID
    full_name TEXT UNIQUE NOT NULL,             -- e.g. "facebook/react"
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    url TEXT NOT NULL,
    homepage TEXT,
    description TEXT,
    
    -- Telemetry Metrics (Refreshed Daily)
    stars_count INTEGER NOT NULL,
    forks_count INTEGER NOT NULL,
    open_issues_count INTEGER NOT NULL,
    primary_language TEXT,
    license TEXT,
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE,
    pushed_at TIMESTAMP WITH TIME ZONE,
    
    -- 6-Pillar Taxonomy Metadata
    macro_domain TEXT NOT NULL DEFAULT 'Developer Tooling',
    sub_domain TEXT NOT NULL DEFAULT 'General',
    archetype TEXT NOT NULL DEFAULT 'Library / SDK',
    problem_solved TEXT NOT NULL DEFAULT '',
    use_cases TEXT[] NOT NULL DEFAULT '{}',
    primary_ecosystem TEXT NOT NULL DEFAULT '',
    target_audience TEXT[] NOT NULL DEFAULT '{}',
    confidence_score SMALLINT DEFAULT 100,
    is_enriched BOOLEAN DEFAULT FALSE,
    
    -- 384-Dimensional Dense Vector
    embedding vector(384),
    last_synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. HNSW Vector Index for <10ms Cosine Distance Search
CREATE INDEX IF NOT EXISTS idx_repos_embedding ON repositories 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 4. B-Tree Indexes for Instant Faceted Filtering
CREATE INDEX IF NOT EXISTS idx_repos_stars ON repositories (stars_count DESC);
CREATE INDEX IF NOT EXISTS idx_repos_domain ON repositories (macro_domain);
CREATE INDEX IF NOT EXISTS idx_repos_archetype ON repositories (archetype);
CREATE INDEX IF NOT EXISTS idx_repos_language ON repositories (primary_language);
CREATE INDEX IF NOT EXISTS idx_repos_enriched ON repositories (is_enriched);

-- 5. Hybrid Vector & Faceted Filter RPC Function
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
        1 - (r.embedding <=> query_embedding) AS similarity
    FROM repositories r
    WHERE (filter_domain IS NULL OR r.macro_domain = filter_domain)
      AND (filter_archetype IS NULL OR r.archetype = filter_archetype)
      AND (filter_language IS NULL OR r.primary_language = filter_language)
      AND r.is_enriched = TRUE
      AND (1 - (r.embedding <=> query_embedding)) > match_threshold
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$;
```

#### Step 3: Copy Connection Credentials
Navigate to **Project Settings -> Database** and copy the Connection String URI:
`postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres`

---

### Option 2: Turso (LibSQL Native Vectors)

#### Step 1: Install Turso CLI & Create Database
```bash
# Install Turso CLI
curl -sSfL https://get.tur.so/install.sh | bash

# Authenticate with Turso
turso auth login

# Create a database with 9GB free allowance
turso db create github-intelligence
```

#### Step 2: Execute LibSQL Vector Migration
Run the following SQL using `turso db shell github-intelligence`:

```sql
CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY,                     -- Immutable GitHub repo ID
    full_name TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    url TEXT NOT NULL,
    homepage TEXT,
    description TEXT,
    
    stars_count INTEGER NOT NULL,
    forks_count INTEGER NOT NULL,
    open_issues_count INTEGER NOT NULL,
    primary_language TEXT,
    license TEXT,
    is_archived INTEGER DEFAULT 0,
    created_at TEXT,
    pushed_at TEXT,
    
    macro_domain TEXT NOT NULL DEFAULT 'Developer Tooling',
    sub_domain TEXT NOT NULL DEFAULT 'General',
    archetype TEXT NOT NULL DEFAULT 'Library / SDK',
    problem_solved TEXT NOT NULL DEFAULT '',
    use_cases TEXT NOT NULL DEFAULT '[]',       -- JSON array string
    primary_ecosystem TEXT NOT NULL DEFAULT '',
    target_audience TEXT NOT NULL DEFAULT '[]', -- JSON array string
    confidence_score INTEGER DEFAULT 100,
    is_enriched INTEGER DEFAULT 0,
    
    embedding F32_BLOB(384),                   -- Native LibSQL 384-dim vector
    last_synced_at TEXT DEFAULT (datetime('now'))
);

-- Native Vector Top-K Index in LibSQL
CREATE INDEX IF NOT EXISTS idx_repos_vector ON repositories(libsql_vector_idx(embedding));
CREATE INDEX IF NOT EXISTS idx_repos_stars ON repositories(stars_count DESC);
CREATE INDEX IF NOT EXISTS idx_repos_domain ON repositories(macro_domain);
CREATE INDEX IF NOT EXISTS idx_repos_enriched ON repositories(is_enriched);
```

#### Step 3: Generate URL and Auth Token
```bash
# Retrieve Database URL
turso db show --url github-intelligence
# Example output: libsql://github-intelligence-yourorg.turso.io

# Create persistent authentication token
turso db tokens create github-intelligence
```

---

## 6. Multi-Provider Free-Tier LLM Resiliency Engine

To process 30,000 repositories without incurring API bills or failing on single-provider rate limits, the taxonomy enrichment engine implements a multi-provider failover sequence:

| Priority | Provider | Default Model | Free Tier Quota | Primary Role |
| :---: | :--- | :--- | :--- | :--- |
| **Tier 1** | **Groq Cloud** | `llama-3.3-70b-versatile` | 30 req/min | Primary low-latency JSON extraction |
| **Tier 2** | **Google AI Studio** | `gemini-2.0-flash` | 15 req/min | Large context window failover |
| **Tier 3** | **Cerebras Cloud** | `llama-3.1-70b` | 30 req/min | High-throughput wafer-scale failover |
| **Tier 4** | **OpenRouter** | `meta-llama/llama-3.3-70b-instruct:free` | Dynamic free pool | Final community safety net |

### Vector Embeddings via Local ONNX
Rather than making outbound embedding API calls, the system executes **FastEmbed** locally:
- **Model**: `BAAI/bge-small-en-v1.5`
- **Output Dimensions**: Exactly **384** float32 values
- **Execution**: Local ONNX Runtime (CPU), running inside the GitHub Actions Ubuntu runner with zero external dependencies.

---

## 7. Setting Up GitHub Actions & Secrets

The repository includes a production-ready autonomous sync workflow in [`.github/workflows/daily-sync.yml`](file:///.github/workflows/daily-sync.yml).

### Workflow Specifications:
- **Schedule**: Daily at `00:00 UTC` (`cron: "0 0 * * *"`)
- **Manual Dispatch**: Supported via GitHub UI (`workflow_dispatch`)
- **Concurrency**: Group `github-sync-pipeline` with `cancel-in-progress: false` (prevents overlapping writes)
- **Error Diagnostics**: Automatically formats error and success reports to `$GITHUB_STEP_SUMMARY`.

### Configuring Repository Secrets:
Go to your GitHub repository -> **Settings -> Secrets and variables -> Actions -> New repository secret** and add:

| Secret Name | Description | Example / Instructions |
| :--- | :--- | :--- |
| `GH_PAT_TOKEN` | GitHub Personal Access Token | Classic or fine-grained PAT with public repository read permissions. Prevents 60 req/hr anonymous limit. |
| `DB_PROVIDER` | Active database provider | Either `supabase` or `turso` |
| `DATABASE_URL` | Database connection URL | `postgresql://postgres:...@db...supabase.co:5432/postgres` or `libsql://...turso.io` |
| `TURSO_AUTH_TOKEN` | Turso JWT Token | Required ONLY if `DB_PROVIDER` is `turso`. Leave blank for Supabase. |
| `GROQ_API_KEY` | Groq Cloud API Key | Obtain from https://console.groq.com/keys |
| `GEMINI_API_KEY` | Google AI Studio Key | Obtain from https://aistudio.google.com/app/apikey |
| `CEREBRAS_API_KEY` | Cerebras Cloud Key | Obtain from https://cloud.cerebras.ai/ |
| `OPENROUTER_API_KEY` | OpenRouter Key | Obtain from https://openrouter.ai/keys |

---

## 8. Local Development & Quickstart

### Prerequisites
- Python 3.11+
- Git

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/your-org/github-intelligence-engine.git
cd github-intelligence-engine

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux / macOS:
source venv/bin/activate
# On Windows PowerShell:
venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Environment Variables
```bash
cp .env.example .env
```
Edit `.env` and fill in your database credentials and API keys.

### 4. Run Stage 1: Telemetry Ingestion
Pulls all public repositories with $\ge 2,000$ stars using adaptive bisection partitioning:
```bash
python scripts/ingest_telemetry.py --min-stars 2000
```

### 5. Run Stage 2: AI Taxonomy & Vector Enrichment
Processes unenriched repositories through the multi-provider LLM failover pool and computes 384-dim ONNX embeddings:
```bash
python scripts/enrich_taxonomy.py --batch-size 1000
```

---

## 9. Verification & Health Audit

### Supabase Verification Queries
Run in Supabase SQL Editor:

```sql
-- 1. Check total indexed repositories
SELECT count(*) AS total_repos,
       count(*) FILTER (WHERE is_enriched = TRUE) AS enriched_repos,
       count(*) FILTER (WHERE is_enriched = FALSE) AS pending_enrichment
FROM repositories;

-- 2. Verify macro domain distribution
SELECT macro_domain, count(*) AS repo_count
FROM repositories
GROUP BY macro_domain
ORDER BY repo_count DESC;

-- 3. Verify archetype distribution
SELECT archetype, count(*) AS repo_count
FROM repositories
GROUP BY archetype
ORDER BY repo_count DESC;

-- 4. Test vector similarity RPC search
SELECT * FROM match_repositories(
    query_embedding := (SELECT embedding FROM repositories WHERE full_name = 'facebook/react'),
    match_threshold := 0.5,
    match_count := 5
);
```

### Turso Verification Queries
Run in `turso db shell github-intelligence`:

```sql
-- Check total records and enrichment progress
SELECT count(*) AS total, sum(is_enriched) AS enriched FROM repositories;

-- Verify vector index is populated
SELECT full_name, macro_domain, archetype 
FROM repositories 
WHERE embedding IS NOT NULL 
LIMIT 5;
```

---

## 10. 10-Point Supervisor Quality Gates

The system conforms to strict automated quality gates enforced across all phases:

- [x] **Gate 1: The 1,000-Item Cap Test**: Adaptive bisection splits dense brackets without losing repository records.
- [x] **Gate 2: Rate Limit Recovery Test**: Handles HTTP 403 / 429 status codes with dynamic `Retry-After` backoff.
- [x] **Gate 3: Pydantic Purity Test**: 100% adherence to 6-pillar enums; zero hallucinated domains or archetypes.
- [x] **Gate 4: Vector Dimension Audit**: FastEmbed embeddings strictly verify at 384 float32 dimensions.
- [x] **Gate 5: Database Storage Sizing Audit**: 30,000 repositories occupy ~166 MB, well below free tier thresholds.
- [x] **Gate 6: Multi-Provider Failover Test**: Automatically transitions across Groq -> Gemini -> Cerebras -> OpenRouter.
- [x] **Gate 7: Idempotent Ingestion Test**: Successive runs update metrics without duplicating records or resetting enrichment flags.
- [x] **Gate 8: Zero-Cost Search Test**: Searches and embeddings operate without paid external API services.
- [x] **Gate 9: Zero-Warning Code Quality**: PEP-8 compliant code with structured error handling.
- [x] **Gate 10: Autonomous Cron CI Simulation**: GitHub Actions workflow validated with deterministic concurrency controls and failure alerting.

---

## License

This project is open-source and licensed under the [Apache 2.0 License](LICENSE).
