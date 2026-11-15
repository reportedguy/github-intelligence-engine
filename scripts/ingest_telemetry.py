#!/usr/bin/env python3
"""
GitHub Intelligence Engine - Phase 2: Ingestion & Rate Limits
Production Script: Adaptive Bisection Ingestor

Architectural Invariants Enforced:
1. Deterministic Rate Control: Maximum 25 requests per rolling 60 seconds (Token Bucket / Sliding Window).
2. Partitioned Bisection Ingestion: Never requests >1,000 items in a single bracket.
3. Secondary Partition Fallback: If min_stars == max_stars and count > 1,000, partitions by creation date.
4. Rate Limit Resilience: Parses `Retry-After` and `x-ratelimit-reset` headers on 403/429 with exponential backoff.
5. Idempotent Upsert: Preserves existing AI enrichment fields (macro_domain, embedding, is_enriched).
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
load_dotenv()

# Set up structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ingest_telemetry")

GITHUB_API_SEARCH = "https://api.github.com/search/repositories"

# Optional database drivers
try:
    import psycopg2
    from psycopg2.extras import execute_values
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

try:
    from supabase import Client as SupabaseClient, create_client as create_supabase_client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False

try:
    import libsql_client
    HAS_LIBSQL = True
except ImportError:
    HAS_LIBSQL = False

import sqlite3


class TokenBucketRateLimiter:
    """
    Strict Token-Bucket / Sliding-Window Rate Limiter.
    Guarantees no more than `max_requests` occur in any rolling `period_seconds`.
    """

    def __init__(
        self,
        max_requests: int = 25,
        period_seconds: float = 60.0,
        time_fn: Optional[Callable[[], float]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ):
        self.max_requests = max_requests
        self.period_seconds = period_seconds
        self.time_fn = time_fn or time.time
        self.sleep_fn = sleep_fn or time.sleep
        self.timestamps: List[float] = []

    def acquire(self) -> float:
        """
        Blocks until a request slot is available.
        Returns the duration slept (0.0 if not throttled).
        """
        slept_duration = 0.0
        now = self.time_fn()
        # Discard timestamps outside rolling period
        self.timestamps = [t for t in self.timestamps if (now - t) < self.period_seconds]

        if len(self.timestamps) >= self.max_requests:
            oldest = self.timestamps[0]
            sleep_duration = self.period_seconds - (now - oldest) + 0.1
            if sleep_duration > 0:
                logger.info(
                    "Rate limit window full (%d/%d reqs). Throttling for %.2fs...",
                    len(self.timestamps),
                    self.max_requests,
                    sleep_duration,
                )
                self.sleep_fn(sleep_duration)
                slept_duration = sleep_duration
            # Refresh timestamps after sleep
            now = self.time_fn()
            self.timestamps = [t for t in self.timestamps if (now - t) < self.period_seconds]

        self.timestamps.append(self.time_fn())
        return slept_duration


class AdaptiveBisectionIngestor:
    """
    Production Adaptive Bisection Ingestion Engine for GitHub Repositories.
    Overcomes GitHub's 1,000 search result ceiling via dynamic recursive partitioning.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        db_provider: Optional[str] = None,
        database_url: Optional[str] = None,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        turso_auth_token: Optional[str] = None,
        dry_run: bool = False,
        batch_size: int = 100,
        max_requests_per_minute: int = 25,
        time_fn: Optional[Callable[[], float]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        session: Optional[requests.Session] = None,
    ):
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_PAT_TOKEN")
        self.db_provider = (
            db_provider or os.environ.get("DB_PROVIDER") or "sqlite"
        ).lower().strip()
        self.database_url = database_url or os.environ.get("DATABASE_URL")
        self.supabase_url = supabase_url or os.environ.get("SUPABASE_URL")
        self.supabase_key = (
            supabase_key
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_KEY")
        )
        self.turso_auth_token = turso_auth_token or os.environ.get("TURSO_AUTH_TOKEN")
        self.dry_run = dry_run
        self.batch_size = max(1, batch_size)

        self.time_fn = time_fn or time.time
        self.sleep_fn = sleep_fn or time.sleep
        self.session = session or requests.Session()

        self.rate_limiter = TokenBucketRateLimiter(
            max_requests=max_requests_per_minute,
            period_seconds=60.0,
            time_fn=self.time_fn,
            sleep_fn=self.sleep_fn,
        )
        self.request_timestamps = self.rate_limiter.timestamps

        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Intelligence-Engine/1.0",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"
        else:
            logger.warning(
                "No GitHub token provided. Rate limits will be constrained to unauthenticated tier."
            )

        self.seen_repo_ids: Set[int] = set()

    def _rate_limit_throttle(self) -> float:
        """Enforces rate limit through the TokenBucketRateLimiter."""
        slept = self.rate_limiter.acquire()
        self.request_timestamps = self.rate_limiter.timestamps
        return slept

    def _fetch_search_page(
        self,
        query: str,
        page: int = 1,
        per_page: int = 100,
        max_retries: int = 5,
    ) -> Dict[str, Any]:
        """
        Executes a single search request against GitHub API with retry and rate-limit recovery.
        """
        params = {"q": query, "per_page": per_page, "page": page, "sort": "stars", "order": "desc"}
        attempt = 0

        while attempt < max_retries:
            self._rate_limit_throttle()
            attempt += 1

            try:
                resp = self.session.get(
                    GITHUB_API_SEARCH,
                    headers=self.headers,
                    params=params,
                    timeout=30,
                )
            except requests.RequestException as exc:
                wait_time = min(2.0 ** attempt * 2.0, 60.0)
                logger.warning(
                    "Network error during query '%s' page %d: %s. Retrying in %.1fs (attempt %d/%d)...",
                    query,
                    page,
                    exc,
                    wait_time,
                    attempt,
                    max_retries,
                )
                self.sleep_fn(wait_time)
                continue

            # Handle 200 OK
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError as err:
                    logger.error("JSON decode error on 200 response: %s", err)
                    return {"total_count": 0, "items": []}

            # Handle Rate Limit (HTTP 403 or 429)
            if resp.status_code in (403, 429):
                retry_after_hdr = resp.headers.get("Retry-After")
                reset_hdr = resp.headers.get("x-ratelimit-reset") or resp.headers.get("X-RateLimit-Reset")
                remaining_hdr = resp.headers.get("x-ratelimit-remaining") or resp.headers.get("X-RateLimit-Remaining")

                if retry_after_hdr:
                    try:
                        sleep_duration = max(float(retry_after_hdr), 1.0)
                    except ValueError:
                        sleep_duration = 60.0
                    logger.warning(
                        "HTTP %d Rate Limited. 'Retry-After' header received. Sleeping for %.1fs...",
                        resp.status_code,
                        sleep_duration,
                    )
                elif reset_hdr and (remaining_hdr == "0" or remaining_hdr is None):
                    try:
                        reset_epoch = float(reset_hdr)
                        now_epoch = self.time_fn()
                        sleep_duration = max(reset_epoch - now_epoch + 1.0, 1.0)
                    except ValueError:
                        sleep_duration = 60.0
                    logger.warning(
                        "HTTP %d Rate Limited. 'x-ratelimit-reset' header received. Sleeping for %.1fs...",
                        resp.status_code,
                        sleep_duration,
                    )
                else:
                    sleep_duration = min(2.0 ** attempt * 5.0, 60.0)
                    logger.warning(
                        "HTTP %d Secondary rate limit hit. Exponential backoff for %.1fs...",
                        resp.status_code,
                        sleep_duration,
                    )

                self.sleep_fn(sleep_duration)
                continue

            # Handle 422 (Unprocessable - e.g. beyond 1000 items or invalid query syntax)
            if resp.status_code == 422:
                logger.warning(
                    "HTTP 422 Unprocessable Entity for query '%s' page %d: %s",
                    query,
                    page,
                    resp.text[:200],
                )
                return {"total_count": 0, "items": []}

            # Handle 401 Unauthorized
            if resp.status_code == 401:
                logger.error("HTTP 401 Unauthorized: Invalid GitHub Token.")
                raise ValueError("Authentication failed: GitHub Token is invalid or expired.")

            # Server error 5xx
            if resp.status_code >= 500:
                wait_time = min(2.0 ** attempt * 3.0, 60.0)
                logger.warning(
                    "HTTP %d Server Error from GitHub. Retrying in %.1fs...",
                    resp.status_code,
                    wait_time,
                )
                self.sleep_fn(wait_time)
                continue

            # Other unexpected errors
            resp.raise_for_status()

        raise RuntimeError(f"Exhausted {max_retries} retries for query '{query}' page {page}")

    def search_range(
        self,
        min_stars: int,
        max_stars: int,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Adaptive Bisection Ingestion:
        Queries stars:min..max. If total_count > 1000, recursively splits into
        min..mid and mid+1..max.
        If min == max and total_count > 1000, triggers date-partition fallback.
        """
        if limit is not None and limit <= 0:
            return []

        query = f"stars:{min_stars}..{max_stars}"
        logger.info("Inspecting star bracket: %s", query)
        first_page = self._fetch_search_page(query=query, page=1, per_page=100)
        total_count = first_page.get("total_count", 0)
        logger.info("Star bracket '%s' reported total_count=%d", query, total_count)

        # Base Case 1: Empty bracket
        if total_count == 0:
            return []

        # Base Case 2: Bracket safely fits within GitHub's 1,000 item limit
        if total_count <= 1000:
            repos = list(first_page.get("items", []))
            total_pages = (total_count + 99) // 100
            total_pages = min(total_pages, 10)  # GitHub search API hard ceiling

            for page in range(2, total_pages + 1):
                if limit is not None and len(repos) >= limit:
                    return repos[:limit]
                p_resp = self._fetch_search_page(query=query, page=page, per_page=100)
                items = p_resp.get("items", [])
                if not items:
                    break
                repos.extend(items)

            if limit is not None and len(repos) > limit:
                return repos[:limit]
            return repos

        # Base Case 3: Range overflow on single star number (dense star cluster)
        if min_stars >= max_stars:
            logger.warning(
                "Dense star cluster detected at stars=%d (total_count=%d > 1000). Falling back to date partitioning.",
                min_stars,
                total_count,
            )
            return self._partition_by_creation_date(min_stars, limit=limit)

        # Recursive Case: Bisect bracket
        midpoint = (min_stars + max_stars) // 2
        logger.info(
            "total_count=%d exceeds 1,000 cap! Bisecting [%d..%d] -> [%d..%d] & [%d..%d]",
            total_count,
            min_stars,
            max_stars,
            min_stars,
            midpoint,
            midpoint + 1,
            max_stars,
        )

        # Explore higher star bracket first (right branch) so top repositories are ingested first
        right_repos = self.search_range(midpoint + 1, max_stars, limit=limit)
        if limit is not None and len(right_repos) >= limit:
            return right_repos[:limit]

        remaining_limit = (limit - len(right_repos)) if limit is not None else None
        left_repos = self.search_range(min_stars, midpoint, limit=remaining_limit)

        return right_repos + left_repos

    def _partition_by_creation_date(
        self,
        star_count: int,
        start_year: int = 2008,
        end_year: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Secondary partition fallback for dense star clusters.
        Partitions by repository creation year: created:YYYY-01-01..YYYY-12-31.
        """
        if end_year is None:
            end_year = datetime.now(timezone.utc).year + 1

        repos: List[Dict[str, Any]] = []

        for year in range(start_year, end_year + 1):
            if limit is not None and len(repos) >= limit:
                break

            query = f"stars:{star_count} created:{year}-01-01..{year}-12-31"
            logger.info("Querying date partition: %s", query)
            resp_data = self._fetch_search_page(query=query, page=1, per_page=100)
            year_count = resp_data.get("total_count", 0)

            if year_count == 0:
                continue

            items = list(resp_data.get("items", []))

            if year_count <= 1000:
                total_pages = min((year_count + 99) // 100, 10)
                for page in range(2, total_pages + 1):
                    if limit is not None and (len(repos) + len(items)) >= limit:
                        break
                    p_data = self._fetch_search_page(query=query, page=page, per_page=100)
                    p_items = p_data.get("items", [])
                    if not p_items:
                        break
                    items.extend(p_items)
                repos.extend(items)
            else:
                # If a single year exceeds 1,000 items, partition into half-years
                logger.warning(
                    "Year %d partition exceeded 1000 items (%d). Partitioning into half-years...",
                    year,
                    year_count,
                )
                half_year_items = self._partition_year_by_months(star_count, year, limit=limit)
                repos.extend(half_year_items)

        if limit is not None and len(repos) > limit:
            return repos[:limit]
        return repos

    def _partition_year_by_months(
        self,
        star_count: int,
        year: int,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Splits a year into quarters for extreme density cases."""
        windows = [
            (f"{year}-01-01", f"{year}-03-31"),
            (f"{year}-04-01", f"{year}-06-30"),
            (f"{year}-07-01", f"{year}-09-30"),
            (f"{year}-10-01", f"{year}-12-31"),
        ]
        results: List[Dict[str, Any]] = []
        for start_date, end_date in windows:
            if limit is not None and len(results) >= limit:
                break
            query = f"stars:{star_count} created:{start_date}..{end_date}"
            p1 = self._fetch_search_page(query=query, page=1, per_page=100)
            cnt = p1.get("total_count", 0)
            if cnt == 0:
                continue
            results.extend(p1.get("items", []))
            pages = min((cnt + 99) // 100, 10)
            for page in range(2, pages + 1):
                if limit is not None and len(results) >= limit:
                    break
                p = self._fetch_search_page(query=query, page=page, per_page=100)
                results.extend(p.get("items", []))
        return results

    @staticmethod
    def transform_repo(item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalizes a raw GitHub API repository JSON into the database schema format.
        """
        owner = item.get("owner") or {}
        owner_name = owner.get("login", "")
        license_obj = item.get("license") or {}
        license_name = license_obj.get("spdx_id") or license_obj.get("name") or "None"
        if license_name == "NOASSERTION":
            license_name = "Custom"

        return {
            "id": int(item["id"]),
            "full_name": item.get("full_name", ""),
            "name": item.get("name", ""),
            "owner": owner_name,
            "url": item.get("html_url", ""),
            "homepage": item.get("homepage") or "",
            "description": item.get("description") or "",
            "stars_count": int(item.get("stargazers_count", 0)),
            "forks_count": int(item.get("forks_count", 0)),
            "open_issues_count": int(item.get("open_issues_count", 0)),
            "primary_language": item.get("language") or "Unknown",
            "license": license_name,
            "is_archived": bool(item.get("archived", False)),
            "created_at": item.get("created_at"),
            "pushed_at": item.get("pushed_at"),
            # Invariant default values for AI fields (never overwrite if record already exists)
            "macro_domain": "Unassigned",
            "sub_domain": "Unassigned",
            "archetype": "Library / SDK",
            "problem_solved": "Pending AI taxonomy enrichment.",
            "use_cases": "[]",
            "primary_ecosystem": "Unassigned",
            "target_audience": "[]",
            "confidence_score": 0,
            "is_enriched": False,
        }

    def deduplicate_records(self, repos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicates repository items by ID."""
        unique_repos = []
        for r in repos:
            rid = r.get("id")
            if rid not in self.seen_repo_ids:
                self.seen_repo_ids.add(rid)
                unique_repos.append(r)
        return unique_repos

    def upsert_telemetry(self, raw_repos: List[Dict[str, Any]]) -> int:
        """
        Bulk upsert raw telemetry into database (Supabase or Turso/SQLite).
        Enforces idempotency: updates stars, forks, issues, pushed_at while
        strictly preserving existing AI enrichment columns (is_enriched, embedding).
        """
        if not raw_repos:
            return 0

        transformed = [self.transform_repo(r) for r in raw_repos]

        if self.dry_run:
            logger.info(
                "[DRY RUN] Skipping database upsert for %d repositories. Sample: %s (%d stars)",
                len(transformed),
                transformed[0]["full_name"] if transformed else "None",
                transformed[0]["stars_count"] if transformed else 0,
            )
            return len(transformed)

        provider = self.db_provider

        # Supabase / PostgreSQL Upsert via psycopg2
        if provider == "supabase" or (self.database_url and "postgres" in self.database_url):
            return self._upsert_postgresql(transformed)

        # Turso / LibSQL Native HTTP Pipeline Upsert
        if provider == "turso" or (self.database_url and "turso.io" in self.database_url):
            return self._upsert_turso(transformed)

        # SQLite / Local Fallback Upsert
        return self._upsert_sqlite(transformed)

    def _upsert_postgresql(self, records: List[Dict[str, Any]]) -> int:
        """PostgreSQL / Supabase upsert using psycopg2 with ON CONFLICT DO UPDATE."""
        if not HAS_PSYCOPG2:
            logger.warning("psycopg2 is not installed. Checking for supabase-py client...")
            if HAS_SUPABASE and self.supabase_url and self.supabase_key:
                return self._upsert_supabase_client(records)
            logger.warning("No PostgreSQL driver available. Falling back to local SQLite upsert.")
            return self._upsert_sqlite(records)

        conn_str = self.database_url
        if not conn_str:
            logger.warning("DATABASE_URL not set for Supabase. Falling back to SQLite.")
            return self._upsert_sqlite(records)

        sql = """
        INSERT INTO repositories (
            id, full_name, name, owner, url, homepage, description,
            stars_count, forks_count, open_issues_count, primary_language,
            license, is_archived, created_at, pushed_at,
            macro_domain, sub_domain, archetype, problem_solved,
            use_cases, primary_ecosystem, target_audience,
            confidence_score, is_enriched, last_synced_at
        ) VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            stars_count = EXCLUDED.stars_count,
            forks_count = EXCLUDED.forks_count,
            open_issues_count = EXCLUDED.open_issues_count,
            pushed_at = EXCLUDED.pushed_at,
            description = EXCLUDED.description,
            homepage = EXCLUDED.homepage,
            primary_language = EXCLUDED.primary_language,
            license = EXCLUDED.license,
            is_archived = EXCLUDED.is_archived,
            last_synced_at = NOW();
        """

        upserted_count = 0
        with psycopg2.connect(conn_str) as conn:
            with conn.cursor() as cur:
                for i in range(0, len(records), self.batch_size):
                    batch = records[i : i + self.batch_size]
                    rows = [
                        (
                            r["id"],
                            r["full_name"],
                            r["name"],
                            r["owner"],
                            r["url"],
                            r["homepage"],
                            r["description"],
                            r["stars_count"],
                            r["forks_count"],
                            r["open_issues_count"],
                            r["primary_language"],
                            r["license"],
                            r["is_archived"],
                            r["created_at"],
                            r["pushed_at"],
                            r["macro_domain"],
                            r["sub_domain"],
                            r["archetype"],
                            r["problem_solved"],
                            ["Unassigned"],
                            r["primary_ecosystem"],
                            ["Developers"],
                            r["confidence_score"],
                            r["is_enriched"],
                            datetime.now(timezone.utc),
                        )
                        for r in batch
                    ]
                    execute_values(cur, sql, rows)
                    upserted_count += len(batch)
            conn.commit()

        logger.info("Successfully upserted %d repositories to Supabase (PostgreSQL).", upserted_count)
        return upserted_count

    def _upsert_supabase_client(self, records: List[Dict[str, Any]]) -> int:
        """Upsert using official supabase-py client."""
        client: SupabaseClient = create_supabase_client(self.supabase_url, self.supabase_key)
        upserted = 0
        for i in range(0, len(records), self.batch_size):
            batch = records[i : i + self.batch_size]
            data = []
            for r in batch:
                data.append({
                    "id": r["id"],
                    "full_name": r["full_name"],
                    "name": r["name"],
                    "owner": r["owner"],
                    "url": r["url"],
                    "homepage": r["homepage"],
                    "description": r["description"],
                    "stars_count": r["stars_count"],
                    "forks_count": r["forks_count"],
                    "open_issues_count": r["open_issues_count"],
                    "primary_language": r["primary_language"],
                    "license": r["license"],
                    "is_archived": r["is_archived"],
                    "created_at": r["created_at"],
                    "pushed_at": r["pushed_at"],
                    "last_synced_at": datetime.now(timezone.utc).isoformat(),
                })
            client.table("repositories").upsert(data, on_conflict="id").execute()
            upserted += len(batch)
        logger.info("Upserted %d repositories via Supabase-py REST client.", upserted)
        return upserted

    def _upsert_turso(self, records: List[Dict[str, Any]]) -> int:
        """Upsert using Turso native HTTP REST Pipeline API."""
        base_url = self.database_url
        if base_url.startswith("libsql://"):
            base_url = base_url.replace("libsql://", "https://")
        if not base_url.startswith("http"):
            base_url = f"https://{base_url}"
        
        # Strip trailing slashes and ensure /v2/pipeline endpoint
        pipeline_url = f"{base_url.rstrip('/')}/v2/pipeline"
        headers = {
            "Authorization": f"Bearer {self.turso_auth_token}",
            "Content-Type": "application/json",
        }

        sql = """
        INSERT INTO repositories (
            id, full_name, name, owner, url, homepage, description,
            stars_count, forks_count, open_issues_count, primary_language,
            license, is_archived, created_at, pushed_at,
            macro_domain, sub_domain, archetype, problem_solved,
            use_cases, primary_ecosystem, target_audience,
            confidence_score, is_enriched, last_synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            stars_count = excluded.stars_count,
            forks_count = excluded.forks_count,
            open_issues_count = excluded.open_issues_count,
            pushed_at = excluded.pushed_at,
            description = excluded.description,
            homepage = excluded.homepage,
            primary_language = excluded.primary_language,
            license = excluded.license,
            is_archived = excluded.is_archived,
            last_synced_at = datetime('now');
        """

        def to_hrana_val(v):
            if v is None:
                return {"type": "null"}
            elif isinstance(v, bool):
                return {"type": "integer", "value": str(1 if v else 0)}
            elif isinstance(v, int):
                return {"type": "integer", "value": str(v)}
            elif isinstance(v, float):
                return {"type": "float", "value": v}
            else:
                return {"type": "text", "value": str(v)}

        upserted = 0
        for i in range(0, len(records), self.batch_size):
            batch = records[i : i + self.batch_size]
            requests_payload = []
            for r in batch:
                params = [
                    to_hrana_val(r["id"]),
                    to_hrana_val(r["full_name"]),
                    to_hrana_val(r["name"]),
                    to_hrana_val(r["owner"]),
                    to_hrana_val(r["url"]),
                    to_hrana_val(r["homepage"]),
                    to_hrana_val(r["description"]),
                    to_hrana_val(r["stars_count"]),
                    to_hrana_val(r["forks_count"]),
                    to_hrana_val(r["open_issues_count"]),
                    to_hrana_val(r["primary_language"]),
                    to_hrana_val(r["license"]),
                    to_hrana_val(1 if r["is_archived"] else 0),
                    to_hrana_val(r["created_at"]),
                    to_hrana_val(r["pushed_at"]),
                    to_hrana_val(r["macro_domain"]),
                    to_hrana_val(r["sub_domain"]),
                    to_hrana_val(r["archetype"]),
                    to_hrana_val(r["problem_solved"]),
                    to_hrana_val(r["use_cases"]),
                    to_hrana_val(r["primary_ecosystem"]),
                    to_hrana_val(r["target_audience"]),
                    to_hrana_val(r["confidence_score"]),
                    to_hrana_val(1 if r["is_enriched"] else 0),
                ]
                requests_payload.append({
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": params,
                    }
                })

            resp = requests.post(pipeline_url, headers=headers, json={"requests": requests_payload}, timeout=30)
            if resp.status_code != 200:
                logger.error("Turso HTTP pipeline failed with code %d: %s", resp.status_code, resp.text)
                raise RuntimeError(f"Turso pipeline failed: {resp.text}")
            
            upserted += len(batch)
            logger.info("Batch upserted %d repositories to Turso (HTTP pipeline).", len(batch))

        logger.info("Successfully upserted %d repositories to Turso LibSQL.", upserted)
        return upserted

    def _upsert_sqlite(self, records: List[Dict[str, Any]], db_path: Optional[str] = None) -> int:
        """Local SQLite fallback / test upsert."""
        target_path = db_path or (
            self.database_url.replace("sqlite:///", "") if self.database_url and "sqlite" in self.database_url else "repositories.db"
        )
        conn = sqlite3.connect(target_path)
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS repositories (
            id INTEGER PRIMARY KEY,
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
            macro_domain TEXT NOT NULL DEFAULT 'Unassigned',
            sub_domain TEXT NOT NULL DEFAULT 'Unassigned',
            archetype TEXT NOT NULL DEFAULT 'Library / SDK',
            problem_solved TEXT NOT NULL DEFAULT '',
            use_cases TEXT NOT NULL DEFAULT '[]',
            primary_ecosystem TEXT NOT NULL DEFAULT '',
            target_audience TEXT NOT NULL DEFAULT '[]',
            confidence_score INTEGER DEFAULT 0,
            is_enriched INTEGER DEFAULT 0,
            embedding TEXT,
            last_synced_at TEXT DEFAULT (datetime('now'))
        );
        """)

        sql = """
        INSERT INTO repositories (
            id, full_name, name, owner, url, homepage, description,
            stars_count, forks_count, open_issues_count, primary_language,
            license, is_archived, created_at, pushed_at,
            macro_domain, sub_domain, archetype, problem_solved,
            use_cases, primary_ecosystem, target_audience,
            confidence_score, is_enriched, last_synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            stars_count = excluded.stars_count,
            forks_count = excluded.forks_count,
            open_issues_count = excluded.open_issues_count,
            pushed_at = excluded.pushed_at,
            description = excluded.description,
            homepage = excluded.homepage,
            primary_language = excluded.primary_language,
            license = excluded.license,
            is_archived = excluded.is_archived,
            last_synced_at = datetime('now');
        """

        rows = [
            (
                r["id"], r["full_name"], r["name"], r["owner"], r["url"],
                r["homepage"], r["description"], r["stars_count"], r["forks_count"],
                r["open_issues_count"], r["primary_language"], r["license"],
                1 if r["is_archived"] else 0, r["created_at"], r["pushed_at"],
                r["macro_domain"], r["sub_domain"], r["archetype"], r["problem_solved"],
                r["use_cases"], r["primary_ecosystem"], r["target_audience"],
                r["confidence_score"], 1 if r["is_enriched"] else 0
            )
            for r in records
        ]
        cur.executemany(sql, rows)
        conn.commit()
        conn.close()
        logger.info("Upserted %d repositories to SQLite (%s).", len(records), target_path)
        return len(records)

    def ingest(
        self,
        min_stars: int = 2000,
        max_stars: int = 500000,
        limit: Optional[int] = None,
    ) -> int:
        """
        Orchestrates full ingestion across the configured star boundaries.
        Returns total number of processed repositories.
        """
        start_time = self.time_fn()
        logger.info(
            "Commencing Adaptive Bisection Ingestion: stars=[%d..%d], limit=%s, dry_run=%s, provider=%s",
            min_stars,
            max_stars,
            limit,
            self.dry_run,
            self.db_provider,
        )

        raw_items = self.search_range(min_stars=min_stars, max_stars=max_stars, limit=limit)
        logger.info("Raw items fetched from GitHub API: %d", len(raw_items))

        unique_items = self.deduplicate_records(raw_items)
        logger.info("Unique repositories after deduplication: %d", len(unique_items))

        if limit is not None and len(unique_items) > limit:
            unique_items = unique_items[:limit]

        upserted_total = self.upsert_telemetry(unique_items)
        elapsed = self.time_fn() - start_time
        logger.info(
            "Ingestion completed in %.2fs. Total repositories upserted: %d",
            elapsed,
            upserted_total,
        )
        return upserted_total


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GitHub Intelligence Engine - Adaptive Bisection Ingestion Pipeline"
    )
    parser.add_argument(
        "--min-stars",
        type=int,
        default=2000,
        help="Minimum stargazers count boundary (default: 2000)",
    )
    parser.add_argument(
        "--max-stars",
        type=int,
        default=500000,
        help="Maximum stargazers count boundary (default: 500000)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum total repositories to ingest (optional, useful for testing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform search and rate-limiting without writing to database",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="GitHub Personal Access Token (defaults to GITHUB_TOKEN or GH_PAT_TOKEN env)",
    )
    parser.add_argument(
        "--db-provider",
        type=str,
        default=None,
        choices=["supabase", "turso", "sqlite"],
        help="Database target provider (defaults to DB_PROVIDER env)",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Database connection URI string (defaults to DATABASE_URL env)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Bulk database upsert batch size (default: 100)",
    )
    parser.add_argument(
        "--turso-auth-token",
        type=str,
        default=None,
        help="Turso authentication JWT token (defaults to TURSO_AUTH_TOKEN env)",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    ingestor = AdaptiveBisectionIngestor(
        token=args.token,
        db_provider=args.db_provider,
        database_url=args.database_url,
        turso_auth_token=args.turso_auth_token,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )
    try:
        count = ingestor.ingest(
            min_stars=args.min_stars,
            max_stars=args.max_stars,
            limit=args.limit,
        )
        print(f"Ingestion finished successfully: {count} repositories processed.")
    except Exception as exc:
        logger.error("Ingestion failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
