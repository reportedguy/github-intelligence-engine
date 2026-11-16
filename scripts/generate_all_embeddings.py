#!/usr/bin/env python3
"""
scripts/generate_all_embeddings.py
Fast Batch Vector Embedding Engine for Turso LibSQL

Generates local 384-dimensional dense vectors (bge-small-en-v1.5)
for all repositories missing embeddings (embedding IS NULL).
Runs 100% locally via ONNX Runtime at ~200+ repos/second ($0.00 compute cost, 0 rate limits).
"""

import os
import sys
import json
import time
import logging
import requests
from typing import List, Dict, Any
from dotenv import load_dotenv
from fastembed import TextEmbedding

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [EmbedEngine] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("EmbedEngine")

TURSO_URL = os.getenv("TURSO_DATABASE_URL", "https://github-intelligence-reportedguy.aws-ap-south-1.turso.io")
if TURSO_URL.startswith("libsql://"):
    TURSO_URL = TURSO_URL.replace("libsql://", "https://")
PIPELINE_URL = f"{TURSO_URL.rstrip('/')}/v2/pipeline"
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

HEADERS = {
    "Authorization": f"Bearer {TURSO_TOKEN}",
    "Content-Type": "application/json",
}


def build_search_text(repo: Dict[str, Any]) -> str:
    full_name = repo.get("full_name") or ""
    desc = repo.get("description") or ""
    domain = repo.get("macro_domain") or ""
    sub = repo.get("sub_domain") or ""
    archetype = repo.get("archetype") or ""
    problem = repo.get("problem_solved") or ""
    use_cases = repo.get("use_cases") or "[]"
    lang = repo.get("primary_language") or ""
    
    parts = [f"Repository: {full_name}."]
    if desc:
        parts.append(f"Description: {desc}.")
    if domain and domain != "Unassigned":
        parts.append(f"Domain: {domain} ({sub}).")
    if archetype and archetype != "Library / SDK":
        parts.append(f"Archetype: {archetype}.")
    if problem and "Pending" not in problem:
        parts.append(f"Problem Solved: {problem}.")
    if use_cases and use_cases != "[]":
        parts.append(f"Use Cases: {use_cases}.")
    if lang and lang != "Unknown":
        parts.append(f"Language: {lang}.")
    return " ".join(parts)


def fetch_unembedded_batch(limit: int = 200) -> List[Dict[str, Any]]:
    sql = """
        SELECT id, full_name, description, macro_domain, sub_domain, archetype,
               problem_solved, use_cases, primary_language
        FROM repositories
        WHERE embedding IS NULL
        ORDER BY stars_count DESC
        LIMIT ?
    """
    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": sql,
                    "args": [{"type": "integer", "value": str(limit)}],
                },
            }
        ]
    }
    resp = requests.post(PIPELINE_URL, headers=HEADERS, json=payload, timeout=20)
    if resp.status_code != 200:
        logger.error("Failed to fetch unembedded batch: %s", resp.text)
        return []
    res_list = resp.json().get("results", [])
    if not res_list or res_list[0].get("type") != "ok":
        return []
    
    result = res_list[0]["response"]["result"]
    cols = [c["name"] for c in result["cols"]]
    rows = []
    for r in result["rows"]:
        row = {}
        for idx, col in enumerate(cols):
            row[col] = r[idx].get("value")
        rows.append(row)
    return rows


def update_embeddings_batch(batch_updates: List[tuple], max_retries: int = 3) -> bool:
    """batch_updates: list of (repo_id, embedding_list) with automatic retry and backoff."""
    sql = "UPDATE repositories SET embedding = vector(?), last_synced_at = datetime('now') WHERE id = ?"
    requests_payload = []
    for repo_id, vec in batch_updates:
        requests_payload.append({
            "type": "execute",
            "stmt": {
                "sql": sql,
                "args": [
                    {"type": "text", "value": json.dumps(vec)},
                    {"type": "integer", "value": str(repo_id)},
                ],
            },
        })
    
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(PIPELINE_URL, headers=HEADERS, json={"requests": requests_payload}, timeout=90)
            if resp.status_code == 200:
                return True
            logger.warning(f"Turso update attempt {attempt} returned status {resp.status_code}: {resp.text[:200]}")
        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            logger.warning(f"Turso update attempt {attempt} encountered network error: {e}. Retrying in {attempt * 2}s...")
        time.sleep(attempt * 2)

    return False


def run_embedding_pipeline(batch_size: int = 50):
    logger.info("Initializing FastEmbed ONNX Engine (BAAI/bge-small-en-v1.5)...")
    embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    logger.info("FastEmbed loaded successfully.")

    total_updated = 0
    consecutive_failures = 0
    while True:
        repos = fetch_unembedded_batch(limit=batch_size)
        if not repos:
            logger.info("No unembedded repositories remaining in database.")
            break

        texts = [build_search_text(r) for r in repos]
        embeddings = list(embedder.embed(texts))
        
        updates = [(int(repos[i]["id"]), embeddings[i].tolist()) for i in range(len(repos))]
        success = update_embeddings_batch(updates)
        if success:
            total_updated += len(updates)
            consecutive_failures = 0
            logger.info(f"Updated {len(updates)} embeddings in Turso (Total so far: {total_updated}).")
            sys.stdout.flush()
        else:
            consecutive_failures += 1
            logger.error(f"Failed to commit batch to Turso (Failure #{consecutive_failures}).")
            if consecutive_failures >= 5:
                logger.error("Too many consecutive failures. Aborting embedding pipeline.")
                break
            time.sleep(5)

    logger.info(f"Finished embedding pipeline! Total embeddings generated: {total_updated}")


if __name__ == "__main__":
    run_embedding_pipeline()
