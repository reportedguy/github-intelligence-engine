#!/usr/bin/env python3
"""
scripts/autonomous_sync.py
GitHub Intelligence Engine - Autonomous Continuous Sync & Enrichment Loop

Runs an autonomous continuous loop:
1. Ingests repositories from GitHub Search API using adaptive bisection (25 req/min throttled).
2. Enriches pending repositories with 6-pillar taxonomy and 384-dim ONNX embeddings.
3. Idempotently handles duplicates and rate limits with automatic failover.
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.ingest_telemetry import AdaptiveBisectionIngestor
from scripts.enrich_taxonomy import TaxonomyEnrichmentPipeline, create_database_adapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [AutoSync] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("AutoSync")


def run_continuous_sync(
    min_stars: int = 2000,
    ingest_batch: int = 200,
    enrich_batch: int = 100,
    max_cycles: int = 20,
):
    logger.info("=================================================================")
    logger.info("COMMENCING AUTONOMOUS SYNC & ENRICHMENT SUPERVISOR LOOP")
    logger.info("Target: Repositories with >= %d stars", min_stars)
    logger.info("Ingest batch: %d | Enrich batch: %d | Max cycles: %d", ingest_batch, enrich_batch, max_cycles)
    logger.info("=================================================================")

    db_provider = os.getenv("DB_PROVIDER", "turso")
    db_url = os.getenv("TURSO_DATABASE_URL") or os.getenv("DATABASE_URL")
    turso_token = os.getenv("TURSO_AUTH_TOKEN")
    gh_token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT_TOKEN")

    total_ingested = 0
    total_enriched = 0

    for cycle in range(1, max_cycles + 1):
        logger.info(f"\n>>> [CYCLE {cycle}/{max_cycles}] <<<")

        # Step 1: Telemetry Ingestion Batch
        try:
            logger.info("Starting telemetry ingestion batch...")
            ingestor = AdaptiveBisectionIngestor(
                token=gh_token,
                db_provider=db_provider,
                database_url=db_url,
                turso_auth_token=turso_token,
                batch_size=100,
            )
            count = ingestor.ingest(min_stars=min_stars, limit=ingest_batch)
            total_ingested += count
            logger.info("Cycle %d Ingested: %d repos (Total so far: %d)", cycle, count, total_ingested)
        except Exception as e:
            logger.error("Ingestion error in cycle %d: %s", cycle, e)

        # Step 2: AI Taxonomy & Vector Embedding Enrichment Batch
        try:
            logger.info("Starting AI taxonomy & vector embedding enrichment batch...")
            pipeline = TaxonomyEnrichmentPipeline(
                db_adapter=create_database_adapter(db_provider, db_url)
            )
            enriched = pipeline.run_batch(batch_limit=enrich_batch)
            total_enriched += enriched
            logger.info("Cycle %d Enriched: %d repos (Total so far: %d)", cycle, enriched, total_enriched)
        except Exception as e:
            logger.error("Enrichment error in cycle %d: %s", cycle, e)

        # Rest briefly between cycles to respect provider rate limits
        logger.info("Cycle %d complete. Standing by for 10s before next cycle...", cycle)
        time.sleep(10)

    logger.info("=================================================================")
    logger.info("AUTONOMOUS SYNC FINISHED: Total Ingested: %d | Total Enriched: %d", total_ingested, total_enriched)
    logger.info("=================================================================")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous Continuous Sync")
    parser.add_argument("--min-stars", type=int, default=2000)
    parser.add_argument("--ingest-batch", type=int, default=200)
    parser.add_argument("--enrich-batch", type=int, default=100)
    parser.add_argument("--cycles", type=int, default=10)
    args = parser.parse_args()

    run_continuous_sync(
        min_stars=args.min_stars,
        ingest_batch=args.ingest_batch,
        enrich_batch=args.enrich_batch,
        max_cycles=args.cycles,
    )
