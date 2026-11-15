#!/usr/bin/env python3
"""
==============================================================================
GitHub Intelligence Engine (2k+ Stars) — Database Storage Verification
File: scripts/verify_db_storage.py
Description: Mathematical storage sizing model for 30,000 GitHub repositories.
             Validates that metadata + 384-dim dense vectors + HNSW/B-tree indexes
             strictly stay under the 200 MB ceiling (Quality Gate 5).
==============================================================================
"""

import sys
from dataclasses import dataclass
from typing import List, Dict

REPO_COUNT = 30_000
VECTOR_DIMENSIONS = 384
BYTES_PER_FLOAT32 = 4

# Quality Gate Limits & Cloud Free Tier Thresholds (in Megabytes)
MAX_PERMISSIBLE_MB = 200.0
SUPABASE_FREE_TIER_MB = 500.0
TURSO_FREE_TIER_MB = 9_000.0  # 9 GB Free tier allowance


@dataclass
class ColumnSpec:
    name: str
    data_type: str
    avg_bytes: float
    description: str


# Column-by-column breakdown of table schema
METADATA_COLUMNS: List[ColumnSpec] = [
    ColumnSpec("id", "BIGINT / INT64", 8.0, "GitHub numerical repository ID"),
    ColumnSpec("full_name", "TEXT (varlena)", 26.0, "e.g. 'facebook/react'"),
    ColumnSpec("name", "TEXT (varlena)", 14.0, "e.g. 'react'"),
    ColumnSpec("owner", "TEXT (varlena)", 12.0, "e.g. 'facebook'"),
    ColumnSpec("url", "TEXT (varlena)", 44.0, "https://github.com/owner/repo"),
    ColumnSpec("homepage", "TEXT (varlena)", 28.0, "Project website / documentation"),
    ColumnSpec("description", "TEXT (varlena)", 115.0, "Raw GitHub description text"),
    ColumnSpec("stars_count", "INTEGER", 4.0, "Star count (int32)"),
    ColumnSpec("forks_count", "INTEGER", 4.0, "Forks count (int32)"),
    ColumnSpec("open_issues_count", "INTEGER", 4.0, "Open issues count (int32)"),
    ColumnSpec("primary_language", "TEXT (varlena)", 10.0, "e.g. 'TypeScript'"),
    ColumnSpec("license", "TEXT (varlena)", 12.0, "e.g. 'MIT License'"),
    ColumnSpec("is_archived", "BOOLEAN / INT", 1.0, "Archived state flag"),
    ColumnSpec("created_at", "TIMESTAMPTZ / TEXT", 8.0, "Repository creation timestamp"),
    ColumnSpec("pushed_at", "TIMESTAMPTZ / TEXT", 8.0, "Last commit push timestamp"),
    ColumnSpec("macro_domain", "TEXT (varlena)", 24.0, "15-item closed macro domain enum"),
    ColumnSpec("sub_domain", "TEXT (varlena)", 28.0, "Micro sub-domain classification"),
    ColumnSpec("archetype", "TEXT (varlena)", 26.0, "8-item closed functional archetype enum"),
    ColumnSpec("problem_solved", "TEXT (varlena)", 175.0, "1-2 sentence engineering problem statement"),
    ColumnSpec("use_cases", "TEXT[] / JSON", 85.0, "3-5 verb-noun use-case tags"),
    ColumnSpec("primary_ecosystem", "TEXT (varlena)", 18.0, "e.g. 'Node.js / React'"),
    ColumnSpec("target_audience", "TEXT[] / JSON", 42.0, "Target developer persona list"),
    ColumnSpec("confidence_score", "SMALLINT / INT", 2.0, "Model confidence rating (1-100)"),
    ColumnSpec("is_enriched", "BOOLEAN / INT", 1.0, "Enrichment pipeline completion status"),
    ColumnSpec("last_synced_at", "TIMESTAMPTZ / TEXT", 8.0, "Last sync timestamp"),
]

# PostgreSQL tuple overhead:
# HeapTupleHeaderData = 23 bytes + null bitmap (4 bytes) + padding (5 bytes) = 32 bytes
# Postgres page line pointer (ItemIdData) = 4 bytes
# Page fill factor allowance & fragmentation buffer = ~10%
POSTGRES_ROW_HEADER_BYTES = 36.0
POSTGRES_PAGE_FILL_FACTOR = 0.90


def calculate_storage():
    # 1. Metadata calculation
    raw_columns_payload_bytes = sum(col.avg_bytes for col in METADATA_COLUMNS)
    effective_row_bytes = (raw_columns_payload_bytes + POSTGRES_ROW_HEADER_BYTES) / POSTGRES_PAGE_FILL_FACTOR
    total_metadata_bytes = effective_row_bytes * REPO_COUNT
    total_metadata_mb = total_metadata_bytes / (1024 * 1024)

    # 2. Dense Vector calculation (strictly 384 dimensions Float32)
    vector_payload_bytes = VECTOR_DIMENSIONS * BYTES_PER_FLOAT32  # 384 * 4 = 1,536 bytes
    # pgvector stores vector header (varlena 4 bytes + dimensions 2 bytes + reserved 2 bytes = 8 bytes)
    vector_total_bytes_per_row = vector_payload_bytes + 8.0
    total_vector_bytes = vector_total_bytes_per_row * REPO_COUNT
    total_vector_mb = total_vector_bytes / (1024 * 1024)

    # 3. HNSW Vector Index calculation (m = 16, ef_construction = 64)
    # In HNSW (pgvector):
    # - Each node stores the full 384-dim vector: 1,536 bytes
    # - Layer 0 stores up to 2 * m = 32 neighbor pointers (32 * 4 bytes = 128 bytes)
    # - Higher layers (avg 1.33 layers) store up to m = 16 pointers (~40 bytes)
    # - Node header + neighbor count + lock / metadata + page overhead = ~650 bytes
    # - Total HNSW node footprint: ~2,354 bytes per entry
    hnsw_bytes_per_node = 2354.0
    total_hnsw_bytes = hnsw_bytes_per_node * REPO_COUNT
    total_hnsw_mb = total_hnsw_bytes / (1024 * 1024)

    # 4. B-Tree Indexes calculation
    # - PK (id): 8 bytes key + 6 bytes ctid + 10 bytes overhead = ~24 bytes * 30,000 ≈ 0.8 MB
    # - full_name (unique): 26 bytes key + 6 bytes ctid + 10 bytes overhead = ~42 bytes * 30,000 ≈ 1.4 MB
    # - stars_count DESC: 4 bytes key + 6 bytes ctid + overhead ≈ 0.7 MB
    # - macro_domain: 24 bytes key + 6 bytes ctid + overhead ≈ 1.3 MB
    # - archetype: 26 bytes key + 6 bytes ctid + overhead ≈ 1.3 MB
    # - primary_language: 10 bytes key + 6 bytes ctid + overhead ≈ 0.9 MB
    # - is_enriched: 1 byte key + 6 bytes ctid + overhead ≈ 0.5 MB
    # - pushed_at: 8 bytes key + 6 bytes ctid + overhead ≈ 0.8 MB
    # - domain + stars composite: 28 bytes key + 6 bytes ctid + overhead ≈ 1.5 MB
    btree_indexes: Dict[str, float] = {
        "pk_repos_id": 0.82,
        "idx_repos_full_name_unique": 1.41,
        "idx_repos_stars": 0.72,
        "idx_repos_domain": 1.32,
        "idx_repos_archetype": 1.35,
        "idx_repos_language": 0.95,
        "idx_repos_is_enriched": 0.55,
        "idx_repos_pushed_at": 0.82,
        "idx_repos_domain_stars_composite": 1.52,
    }
    total_btree_mb = sum(btree_indexes.values())

    # 5. Grand Totals
    total_table_mb = total_metadata_mb + total_vector_mb
    total_indexes_mb = total_hnsw_mb + total_btree_mb
    total_database_mb = total_table_mb + total_indexes_mb

    return {
        "raw_columns_payload_bytes": raw_columns_payload_bytes,
        "effective_row_bytes": effective_row_bytes,
        "total_metadata_mb": total_metadata_mb,
        "vector_payload_bytes": vector_payload_bytes,
        "total_vector_mb": total_vector_mb,
        "total_hnsw_mb": total_hnsw_mb,
        "btree_indexes": btree_indexes,
        "total_btree_mb": total_btree_mb,
        "total_table_mb": total_table_mb,
        "total_indexes_mb": total_indexes_mb,
        "total_database_mb": total_database_mb,
    }


def print_report(res: dict):
    print("=" * 80)
    print("GITHUB INTELLIGENCE ENGINE — DATABASE STORAGE SIZING AUDIT (30,000 REPOS)")
    print("=" * 80)
    print(f"Target Repository Volume : {REPO_COUNT:,} repositories (>= 2,000 stars)")
    print(f"Embedding Architecture   : strictly {VECTOR_DIMENSIONS} dimensions (bge-small-en-v1.5, Float32)")
    print(f"PostgreSQL/Supabase Model: pgvector with HNSW (m=16, ef_construction=64)")
    print(f"Turso/LibSQL Model       : F32_BLOB(384) with native libsql_vector_idx")
    print("-" * 80)
    
    print("\n[1] TABLE STORAGE (HEAP & TUPLES):")
    print(f"  • Relational Metadata Avg Payload : {res['raw_columns_payload_bytes']:.1f} bytes / row")
    print(f"  • Effective Row with Tuple Headers: {res['effective_row_bytes']:.1f} bytes / row (36B header + 10% page buffer)")
    print(f"  • Total Relational Metadata Storage: {res['total_metadata_mb']:>7.2f} MB")
    print(f"  • Dense Vector (384-dim Float32)  : {res['total_vector_mb']:>7.2f} MB ({res['vector_payload_bytes']} bytes/vector * 30k)")
    print(f"  -> Total Table Storage (Heap)     : {res['total_table_mb']:>7.2f} MB")

    print("\n[2] INDEX OVERHEAD (HNSW & B-TREES):")
    print(f"  • HNSW Approximate Vector Index   : {res['total_hnsw_mb']:>7.2f} MB (m=16, ef_construction=64)")
    for name, mb in res['btree_indexes'].items():
        print(f"    - B-Tree {name:<32}: {mb:>5.2f} MB")
    print(f"  • Total B-Tree Index Footprint    : {res['total_btree_mb']:>7.2f} MB")
    print(f"  -> Total Indexes Storage          : {res['total_indexes_mb']:>7.2f} MB")

    print("\n[3] GRAND TOTALS & CLOUD FREE-TIER HEADROOM:")
    print(f"  =======================================================")
    print(f"  PROJECTED TOTAL DATABASE FOOTPRINT : {res['total_database_mb']:>7.2f} MB")
    print(f"  MAXIMUM PERMISSIBLE CEILING (GATE 5): {MAX_PERMISSIBLE_MB:>7.2f} MB")
    print(f"  =======================================================")

    supabase_used_pct = (res['total_database_mb'] / SUPABASE_FREE_TIER_MB) * 100
    supabase_headroom_mb = SUPABASE_FREE_TIER_MB - res['total_database_mb']
    print(f"\n  Supabase PostgreSQL Free Tier (500 MB):")
    print(f"    • Utilization : {supabase_used_pct:.1f}%")
    print(f"    • Headroom    : {supabase_headroom_mb:.2f} MB ({100 - supabase_used_pct:.1f}% free buffer)")

    turso_used_pct = (res['total_database_mb'] / TURSO_FREE_TIER_MB) * 100
    turso_headroom_mb = TURSO_FREE_TIER_MB - res['total_database_mb']
    print(f"\n  Turso LibSQL Free Tier (9,000 MB / 9 GB):")
    print(f"    • Utilization : {turso_used_pct:.2f}%")
    print(f"    • Headroom    : {turso_headroom_mb:.2f} MB ({100 - turso_used_pct:.2f}% free buffer)")

    print("\n" + "=" * 80)
    if res['total_database_mb'] < MAX_PERMISSIBLE_MB:
        diff = MAX_PERMISSIBLE_MB - res['total_database_mb']
        print(f" [PASS] QUALITY GATE 5 PASSED: Total size ({res['total_database_mb']:.2f} MB) is strictly < {MAX_PERMISSIBLE_MB:.0f} MB")
        print(f"        Safety margin below ceiling: {diff:.2f} MB ({(diff / MAX_PERMISSIBLE_MB) * 100:.1f}%)")
        print("=" * 80)
        return True
    else:
        print(f" [FAIL] QUALITY GATE 5 VIOLATED: Total size ({res['total_database_mb']:.2f} MB) exceeds {MAX_PERMISSIBLE_MB:.0f} MB ceiling!")
        print("=" * 80)
        return False


def main():
    results = calculate_storage()
    passed = print_report(results)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
