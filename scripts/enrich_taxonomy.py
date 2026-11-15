"""
scripts/enrich_taxonomy.py
Phase 3: AI Categorization & Local Embeddings Enrichment Engine.

Pipeline Flow:
1. Fetch unenriched repositories from database (is_enriched = FALSE / 0).
2. Fetch & sanitize README (strips HTML, SVG badges, sponsor/license links, truncates to 3000 chars).
3. Extract validated 6-Pillar RepositoryTaxonomySchema using MultiProviderLLMRouter.
4. Generate local 384-dimensional dense vectors using FastEmbed (BAAI/bge-small-en-v1.5).
5. Batch database update writing taxonomy metadata, 384-dim vector, and setting is_enriched = True.
"""

import os
import re
import sys
import json
import struct
import logging
import argparse
from typing import List, Dict, Any, Optional, Tuple
import requests

from dotenv import load_dotenv
load_dotenv()

# Ensure parent directory is on sys.path for direct script execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.schema import (
    RepositoryTaxonomySchema,
    validate_taxonomy,
    TaxonomyValidationError,
)
from scripts.router import MultiProviderLLMRouter

logger = logging.getLogger("EnrichTaxonomy")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [Enricher] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# README Sanitizer & Context Extractor
# ---------------------------------------------------------------------------

def sanitize_readme(readme_text: str, max_chars: int = 3000) -> str:
    """
    Sanitizes raw GitHub README markdown to prevent context-window bloat:
    1. Strips HTML comments, <img>, <svg>, <picture>, and formatting tags.
    2. Strips markdown badges [![...](...)] and image links.
    3. Strips sponsor, financial contribution, donor, contributor, and license sections.
    4. Truncates cleanly to top max_chars (default 3000) preserving word boundaries.
    """
    if not readme_text:
        return ""

    text = readme_text

    # 1. Remove HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # 2. Remove SVGs, images, picture tags, and general HTML tags
    text = re.sub(r"<svg.*?</svg>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<picture.*?</picture>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<img[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)

    # 3. Remove Markdown badges: [![alt](img)](link) or ![alt](img)
    text = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

    # 4. Remove Sponsor, Backer, and Donator sections
    text = re.sub(
        r"(?i)##+\s*(sponsors?|donations?|financial contributors|backers|donate|funding).*?(?=\n##|\Z)",
        "",
        text,
        flags=re.DOTALL,
    )

    # 5. Remove Contributors / Stargazers sections
    text = re.sub(
        r"(?i)##+\s*(contributors?|acknowledgements?|stargazers over time).*?(?=\n##|\Z)",
        "",
        text,
        flags=re.DOTALL,
    )

    # 6. Remove License section
    text = re.sub(
        r"(?i)##+\s*(license|licensing|copyright).*?(?=\n##|\Z)",
        "",
        text,
        flags=re.DOTALL,
    )

    # 7. Normalize whitespace and newlines
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    # 8. Truncate to top max_chars cleanly
    if len(text) > max_chars:
        truncated = text[:max_chars]
        last_break = max(truncated.rfind("\n"), truncated.rfind(". "), truncated.rfind(" "))
        if last_break > max_chars * 0.8:
            text = truncated[:last_break]
        else:
            text = truncated

    return text.strip()


def build_vector_representation_text(
    full_name: str,
    description: Optional[str],
    taxonomy: RepositoryTaxonomySchema,
) -> str:
    """
    Constructs high-density semantic text representation for 384-dimensional vector embedding.
    """
    desc = (description or "").strip()
    use_cases_str = ", ".join(taxonomy.use_cases)
    target_str = ", ".join(taxonomy.target_audience)
    return (
        f"Repository: {full_name}. "
        f"Description: {desc}. "
        f"Domain: {taxonomy.macro_domain} ({taxonomy.sub_domain}). "
        f"Archetype: {taxonomy.archetype}. "
        f"Problem Solved: {taxonomy.problem_solved}. "
        f"Capabilities: {use_cases_str}. "
        f"Ecosystem: {taxonomy.primary_ecosystem}. "
        f"Target Audience: {target_str}."
    )


# ---------------------------------------------------------------------------
# Local 384-Dimensional Embedding Generator
# ---------------------------------------------------------------------------

class LocalEmbeddingEngine:
    """
    Generates local 384-dimensional dense vectors using FastEmbed (BAAI/bge-small-en-v1.5).
    Runs 100% locally via ONNX Runtime at $0.00 compute cost.
    """
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                from fastembed import TextEmbedding
                logger.info(f"Loading local embedding model: {self.model_name}...")
                self._embedder = TextEmbedding(model_name=self.model_name)
            except Exception as e:
                logger.error(f"Failed to load fastembed TextEmbedding: {e}")
                raise
        return self._embedder

    def embed_text(self, text: str) -> List[float]:
        """Generates a strict 384-dimensional dense vector for a single text."""
        results = self.embed_batch([text])
        return results[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates 384-dimensional dense vectors for a batch of texts."""
        if not texts:
            return []
        raw_embeddings = list(self.embedder.embed(texts))
        processed = []
        for vec in raw_embeddings:
            float_list = [float(x) for x in vec]
            if len(float_list) != 384:
                raise ValueError(
                    f"Dimension mismatch: expected 384-dim vector, got {len(float_list)} dimensions."
                )
            processed.append(float_list)
        return processed


# ---------------------------------------------------------------------------
# GitHub Content Retriever
# ---------------------------------------------------------------------------

class GitHubReadmeFetcher:
    """Fetches raw README content directly from GitHub REST API."""
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github.raw",
            "User-Agent": "GitHub-Intelligence-Engine/1.0",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def fetch_readme(self, full_name: str) -> str:
        """Fetches raw repository README text."""
        url = f"https://api.github.com/repos/{full_name}/readme"
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 404:
                logger.warning(f"No README found for {full_name} (HTTP 404).")
                return ""
            elif resp.status_code == 403 or resp.status_code == 429:
                logger.warning(f"GitHub API rate limit struck fetching README for {full_name}.")
                return ""
            else:
                logger.warning(f"Failed to fetch README for {full_name}: HTTP {resp.status_code}")
                return ""
        except Exception as e:
            logger.warning(f"Network error fetching README for {full_name}: {e}")
            return ""


# ---------------------------------------------------------------------------
# Database Adapters: Dual Support (Supabase PostgreSQL & Turso / SQLite)
# ---------------------------------------------------------------------------

class BaseDatabaseAdapter:
    def get_unenriched_repositories(self, limit: int = 1000) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def update_repository_taxonomy(
        self,
        repo_id: int,
        taxonomy: RepositoryTaxonomySchema,
        embedding: List[float],
    ) -> bool:
        raise NotImplementedError

    def close(self):
        pass


class SqliteDatabaseAdapter(BaseDatabaseAdapter):
    """Local SQLite & Turso-compatible database adapter."""
    def __init__(self, db_path: str = "github_intelligence.db"):
        import sqlite3
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_table()

    def _ensure_table(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS repositories (
                id INTEGER PRIMARY KEY,
                full_name TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                owner TEXT NOT NULL,
                url TEXT NOT NULL,
                homepage TEXT,
                description TEXT,
                stars_count INTEGER NOT NULL DEFAULT 0,
                forks_count INTEGER NOT NULL DEFAULT 0,
                open_issues_count INTEGER NOT NULL DEFAULT 0,
                primary_language TEXT,
                license TEXT,
                is_archived INTEGER DEFAULT 0,
                created_at TEXT,
                pushed_at TEXT,
                macro_domain TEXT,
                sub_domain TEXT,
                archetype TEXT,
                problem_solved TEXT,
                use_cases TEXT,
                primary_ecosystem TEXT,
                target_audience TEXT,
                confidence_score INTEGER DEFAULT 100,
                is_enriched INTEGER DEFAULT 0,
                embedding BLOB,
                last_synced_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self.conn.commit()

    def get_unenriched_repositories(self, limit: int = 1000) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, full_name, name, owner, description, primary_language
            FROM repositories
            WHERE is_enriched = 0 OR is_enriched IS NULL
            ORDER BY stars_count DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def update_repository_taxonomy(
        self,
        repo_id: int,
        taxonomy: RepositoryTaxonomySchema,
        embedding: List[float],
    ) -> bool:
        # Pack 384 floats into binary float32 blob (384 * 4 = 1536 bytes)
        embedding_blob = struct.pack(f"{len(embedding)}f", *embedding)
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE repositories
            SET macro_domain = ?,
                sub_domain = ?,
                archetype = ?,
                problem_solved = ?,
                use_cases = ?,
                primary_ecosystem = ?,
                target_audience = ?,
                confidence_score = ?,
                is_enriched = 1,
                embedding = ?,
                last_synced_at = datetime('now')
            WHERE id = ?
        """, (
            taxonomy.macro_domain,
            taxonomy.sub_domain,
            taxonomy.archetype,
            taxonomy.problem_solved,
            json.dumps(taxonomy.use_cases),
            taxonomy.primary_ecosystem,
            json.dumps(taxonomy.target_audience),
            taxonomy.confidence_score,
            embedding_blob,
            repo_id,
        ))
        self.conn.commit()
        return cursor.rowcount > 0

    def close(self):
        if self.conn:
            self.conn.close()


class PostgresDatabaseAdapter(BaseDatabaseAdapter):
    """PostgreSQL (Supabase pgvector) database adapter."""
    def __init__(self, db_url: str):
        self.db_url = db_url
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            self.conn = psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)
        except Exception as e:
            logger.error(f"Cannot initialize PostgreSQL connection: {e}")
            raise

    def get_unenriched_repositories(self, limit: int = 1000) -> List[Dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT id, full_name, name, owner, description, primary_language
                FROM repositories
                WHERE is_enriched = FALSE OR is_enriched IS NULL
                ORDER BY stars_count DESC
                LIMIT %s
            """, (limit,))
            return list(cur.fetchall())

    def update_repository_taxonomy(
        self,
        repo_id: int,
        taxonomy: RepositoryTaxonomySchema,
        embedding: List[float],
    ) -> bool:
        # Format embedding as pgvector string: '[0.1, 0.2, ...]'
        vector_str = "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE repositories
                SET macro_domain = %s,
                    sub_domain = %s,
                    archetype = %s,
                    problem_solved = %s,
                    use_cases = %s,
                    primary_ecosystem = %s,
                    target_audience = %s,
                    confidence_score = %s,
                    is_enriched = TRUE,
                    embedding = %s::vector,
                    last_synced_at = NOW()
                WHERE id = %s
            """, (
                taxonomy.macro_domain,
                taxonomy.sub_domain,
                taxonomy.archetype,
                taxonomy.problem_solved,
                taxonomy.use_cases,
                taxonomy.primary_ecosystem,
                taxonomy.target_audience,
                taxonomy.confidence_score,
                vector_str,
                repo_id,
            ))
            self.conn.commit()
            return cur.rowcount > 0

    def close(self):
        if self.conn:
            self.conn.close()


class TursoDatabaseAdapter(BaseDatabaseAdapter):
    """Turso LibSQL native HTTP REST Pipeline adapter."""
    def __init__(self, db_url: str, auth_token: Optional[str] = None):
        base_url = db_url
        if base_url.startswith("libsql://"):
            base_url = base_url.replace("libsql://", "https://")
        if not base_url.startswith("http"):
            base_url = f"https://{base_url}"
        self.pipeline_url = f"{base_url.rstrip('/')}/v2/pipeline"
        self.auth_token = auth_token or os.getenv("TURSO_AUTH_TOKEN", "")
        self.headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }

    def get_unenriched_repositories(self, limit: int = 1000) -> List[Dict[str, Any]]:
        sql = "SELECT id, full_name, name, owner, description, primary_language FROM repositories WHERE is_enriched = 0 ORDER BY stars_count DESC LIMIT ?"
        payload = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": [{"type": "integer", "value": str(limit)}],
                    }
                }
            ]
        }
        resp = requests.post(self.pipeline_url, headers=self.headers, json=payload, timeout=20)
        if resp.status_code != 200:
            logger.error("Failed to query unenriched repos from Turso: %s", resp.text)
            return []
        data = resp.json()
        results = data.get("results", [])
        if not results or results[0].get("type") != "ok":
            return []
        
        result_set = results[0]["response"]["result"]
        cols = [c["name"] for c in result_set["cols"]]
        rows = []
        for r in result_set["rows"]:
            row_dict = {}
            for i, col in enumerate(cols):
                val = r[i].get("value")
                row_dict[col] = val
            rows.append(row_dict)
        return rows

    def update_repository_taxonomy(
        self,
        repo_id: int,
        taxonomy: RepositoryTaxonomySchema,
        embedding: List[float],
    ) -> bool:
        sql = """
            UPDATE repositories
            SET macro_domain = ?,
                sub_domain = ?,
                archetype = ?,
                problem_solved = ?,
                use_cases = ?,
                primary_ecosystem = ?,
                target_audience = ?,
                confidence_score = ?,
                is_enriched = 1,
                embedding = vector(?),
                last_synced_at = datetime('now')
            WHERE id = ?
        """
        args = [
            {"type": "text", "value": taxonomy.macro_domain},
            {"type": "text", "value": taxonomy.sub_domain},
            {"type": "text", "value": taxonomy.archetype},
            {"type": "text", "value": taxonomy.problem_solved},
            {"type": "text", "value": json.dumps(taxonomy.use_cases)},
            {"type": "text", "value": taxonomy.primary_ecosystem},
            {"type": "text", "value": json.dumps(taxonomy.target_audience)},
            {"type": "integer", "value": str(taxonomy.confidence_score)},
            {"type": "text", "value": json.dumps(embedding)},
            {"type": "integer", "value": str(repo_id)},
        ]
        payload = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": args,
                    }
                }
            ]
        }
        resp = requests.post(self.pipeline_url, headers=self.headers, json=payload, timeout=20)
        return resp.status_code == 200

    def close(self):
        pass


def create_database_adapter(
    provider: Optional[str] = None,
    db_url: Optional[str] = None,
) -> BaseDatabaseAdapter:
    """Factory to instantiate the appropriate database adapter."""
    prov = (provider or os.getenv("DB_PROVIDER", "sqlite")).lower()
    url = db_url or os.getenv("DATABASE_URL", "")

    if prov == "turso" or "turso.io" in url or url.startswith("libsql://"):
        logger.info("Initializing Turso LibSQL HTTP pipeline database adapter...")
        return TursoDatabaseAdapter(url)
    elif prov == "supabase" or url.startswith("postgres://") or url.startswith("postgresql://"):
        logger.info("Initializing Supabase/PostgreSQL database adapter...")
        return PostgresDatabaseAdapter(url)
    else:
        db_path = url.replace("sqlite:///", "") if url.startswith("sqlite:///") else (url or "github_intelligence.db")
        logger.info(f"Initializing SQLite database adapter (path: {db_path})...")
        return SqliteDatabaseAdapter(db_path)


# ---------------------------------------------------------------------------
# Batch Taxonomy Enrichment Pipeline
# ---------------------------------------------------------------------------

class TaxonomyEnrichmentPipeline:
    """
    Coordinates README sanitation, multi-provider LLM categorization,
    local 384-dim vector embedding, and batch database upsertion.
    """
    def __init__(
        self,
        router: Optional[MultiProviderLLMRouter] = None,
        embedder: Optional[LocalEmbeddingEngine] = None,
        db_adapter: Optional[BaseDatabaseAdapter] = None,
        readme_fetcher: Optional[GitHubReadmeFetcher] = None,
    ):
        self.router = router or MultiProviderLLMRouter()
        self.embedder = embedder or LocalEmbeddingEngine()
        self.db = db_adapter or create_database_adapter()
        self.readme_fetcher = readme_fetcher or GitHubReadmeFetcher()

    def enrich_repository(
        self,
        repo: Dict[str, Any],
        raw_readme: Optional[str] = None,
    ) -> Tuple[RepositoryTaxonomySchema, List[float]]:
        """
        Enriches a single repository:
        1. Prepares sanitized README context.
        2. Routes to MultiProviderLLMRouter to obtain validated RepositoryTaxonomySchema.
        3. Generates 384-dimensional dense vector using FastEmbed.
        """
        full_name = repo.get("full_name") or f"{repo.get('owner')}/{repo.get('name')}"
        description = repo.get("description") or ""
        primary_lang = repo.get("primary_language") or ""
        topics = repo.get("topics") or []

        # 1. Fetch README if not supplied
        if raw_readme is None:
            raw_readme = self.readme_fetcher.fetch_readme(full_name)

        # 2. Sanitize context
        clean_context = sanitize_readme(raw_readme, max_chars=3000)
        if not clean_context:
            clean_context = f"Overview: {description}\nPrimary Language: {primary_lang}"

        # 3. LLM Multi-Provider Extraction with Pydantic validation
        taxonomy = self.router.extract_taxonomy(
            repo_name=full_name,
            context_text=clean_context,
            primary_language=primary_lang,
            topics=topics,
        )

        # 4. Generate 384-dimensional dense vector
        vector_text = build_vector_representation_text(full_name, description, taxonomy)
        embedding = self.embedder.embed_text(vector_text)

        return taxonomy, embedding

    def run_batch(self, batch_limit: int = 1000) -> int:
        """
        Executes batch enrichment on pending repositories in database.
        Returns the number of successfully enriched repositories.
        """
        logger.info(f"Starting taxonomy enrichment run (Batch limit: {batch_limit})...")
        repos = self.db.get_unenriched_repositories(limit=batch_limit)
        if not repos:
            logger.info("No unenriched repositories found in database queue.")
            return 0

        logger.info(f"Discovered {len(repos)} unenriched repositories to process.")
        success_count = 0

        for idx, repo in enumerate(repos, 1):
            repo_id = repo.get("id")
            full_name = repo.get("full_name", f"Repo-{repo_id}")
            logger.info(f"[{idx}/{len(repos)}] Enriching '{full_name}' (ID: {repo_id})...")

            try:
                taxonomy, embedding = self.enrich_repository(repo)
                self.db.update_repository_taxonomy(repo_id, taxonomy, embedding)
                success_count += 1
                logger.info(
                    f"Enriched '{full_name}': Domain='{taxonomy.macro_domain}', "
                    f"Archetype='{taxonomy.archetype}', Confidence={taxonomy.confidence_score}%"
                )
            except Exception as e:
                logger.error(f"Failed to enrich '{full_name}': {e}", exc_info=False)
                continue

        logger.info(f"Batch completed: {success_count}/{len(repos)} repositories successfully enriched.")
        return success_count


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="GitHub Intelligence Engine - AI Taxonomy & Vector Enrichment")
    parser.add_argument("--batch-limit", type=int, default=1000, help="Maximum repos to process in single run")
    parser.add_argument("--db-provider", type=str, default=None, help="Database provider: 'sqlite', 'turso', 'supabase'")
    parser.add_argument("--db-url", type=str, default=None, help="Database connection URL")
    args = parser.parse_args()

    pipeline = TaxonomyEnrichmentPipeline(
        db_adapter=create_database_adapter(args.db_provider, args.db_url)
    )
    pipeline.run_batch(batch_limit=args.batch_limit)


if __name__ == "__main__":
    main()
