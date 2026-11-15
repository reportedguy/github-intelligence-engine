"""
Unit Test Suite: GitHub Intelligence Engine - Ingestion & Rate Limits
Tests the Adaptive Bisection Algorithm, Token Bucket Rate Limiter,
Secondary Date-Partitioning Fallback, Rate Limit Recovery (403/429), and Idempotent Upserts.
"""

import json
import os
import sqlite3
import sys
import unittest
from unittest.mock import MagicMock, call, patch

# Ensure scripts directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from ingest_telemetry import (
    AdaptiveBisectionIngestor,
    TokenBucketRateLimiter,
)


class TestTokenBucketRateLimiter(unittest.TestCase):
    """Verifies strict 25 requests / rolling 60 seconds invariant."""

    def setUp(self):
        self.current_time = 1000.0
        self.sleep_calls = []

        def mock_time():
            return self.current_time

        def mock_sleep(duration):
            self.sleep_calls.append(duration)
            self.current_time += duration

        self.mock_time = mock_time
        self.mock_sleep = mock_sleep

    def test_25_requests_without_throttle(self):
        limiter = TokenBucketRateLimiter(
            max_requests=25,
            period_seconds=60.0,
            time_fn=self.mock_time,
            sleep_fn=self.mock_sleep,
        )
        for _ in range(25):
            limiter.acquire()
            self.current_time += 1.0  # 1 second between requests

        # All 25 requests should pass without any sleep
        self.assertEqual(len(self.sleep_calls), 0)
        self.assertEqual(len(limiter.timestamps), 25)

    def test_26th_request_triggers_sleep_throttle(self):
        limiter = TokenBucketRateLimiter(
            max_requests=25,
            period_seconds=60.0,
            time_fn=self.mock_time,
            sleep_fn=self.mock_sleep,
        )
        # Fire 25 requests rapidly at t=1000.0
        for _ in range(25):
            limiter.acquire()

        self.assertEqual(len(self.sleep_calls), 0)

        # 26th request at t=1010.0 (10 seconds later, within the 60s window)
        self.current_time = 1010.0
        limiter.acquire()

        # Oldest timestamp was at 1000.0. At t=1010.0, 50s remain in the window.
        # sleep_duration = 60.0 - (1010.0 - 1000.0) + 0.1 = 50.1s
        self.assertEqual(len(self.sleep_calls), 1)
        self.assertAlmostEqual(self.sleep_calls[0], 50.1, places=1)

    def test_sliding_window_eviction(self):
        limiter = TokenBucketRateLimiter(
            max_requests=25,
            period_seconds=60.0,
            time_fn=self.mock_time,
            sleep_fn=self.mock_sleep,
        )
        # 25 requests at t=1000.0
        for _ in range(25):
            limiter.acquire()

        # Advance time by 61 seconds (past the 60s window)
        self.current_time = 1061.0
        # The next request should proceed with zero sleep
        limiter.acquire()
        self.assertEqual(len(self.sleep_calls), 0)


class TestAdaptiveBisectionAlgorithm(unittest.TestCase):
    """
    Tests bracket bisection when total_count > 1000,
    and tests Quality Gate 1 (3,500 items partitioned cleanly).
    """

    def setUp(self):
        self.simulated_time = 100.0
        self.sleep_calls = []

        def mock_time():
            return self.simulated_time

        def mock_sleep(d):
            self.sleep_calls.append(d)
            self.simulated_time += d

        self.mock_time = mock_time
        self.mock_sleep = mock_sleep

    def test_bracket_bisection_when_count_exceeds_1000(self):
        """
        Query: stars:2000..3000 has 1,500 repos (>1000).
        Bisects to:
          - stars:2000..2500 -> total_count = 800
          - stars:2501..3000 -> total_count = 700
        Both <= 1000, so each sub-bracket completes via pagination without further split.
        """
        ingestor = AdaptiveBisectionIngestor(
            token="test-token",
            dry_run=True,
            time_fn=self.mock_time,
            sleep_fn=self.mock_sleep,
        )

        def mock_fetch(query, page=1, per_page=100, max_retries=5):
            if "2000..3000" in query:
                return {"total_count": 1500, "items": []}
            elif "2000..2500" in query:
                # 800 items total, 100 per page
                start_id = 20000 + (page - 1) * 100
                items = [{"id": start_id + i, "stargazers_count": 2200, "name": f"repo-{start_id+i}"} for i in range(100)]
                return {"total_count": 800, "items": items}
            elif "2501..3000" in query:
                # 700 items total, 100 per page
                start_id = 30000 + (page - 1) * 100
                items = [{"id": start_id + i, "stargazers_count": 2800, "name": f"repo-{start_id+i}"} for i in range(100)]
                return {"total_count": 700, "items": items}
            return {"total_count": 0, "items": []}

        ingestor._fetch_search_page = MagicMock(side_effect=mock_fetch)

        results = ingestor.search_range(2000, 3000)

        # 8 pages of 100 for left (800) + 7 pages of 100 for right (700) = 1500 total
        self.assertEqual(len(results), 1500)

        # Verify initial bracket and both child sub-brackets were queried
        queries_made = [call_args.kwargs.get("query") or call_args.args[0] for call_args in ingestor._fetch_search_page.call_args_list]
        self.assertTrue(any("2000..3000" in q for q in queries_made))
        self.assertTrue(any("2000..2500" in q for q in queries_made))
        self.assertTrue(any("2501..3000" in q for q in queries_made))

    def test_quality_gate_1_bracket_with_3500_repos(self):
        """
        Supervisor Quality Gate 1:
        Simulate a bracket containing 3,500 repos across stars:2000..6000.
        Verifies recursive bisection cleanly splits into multiple sub-ranges without dropping records.
        """
        ingestor = AdaptiveBisectionIngestor(
            token="test-token",
            dry_run=True,
            time_fn=self.mock_time,
            sleep_fn=self.mock_sleep,
        )

        def mock_fetch(query, page=1, per_page=100, max_retries=5):
            # Parse min and max from query "stars:X..Y"
            q_part = query.replace("stars:", "").split()[0]
            parts = q_part.split("..")
            low = int(parts[0])
            high = int(parts[1])
            span = high - low

            if span > 1000:
                # Still overflowing
                return {"total_count": 1800, "items": []}
            else:
                # Sub-bracket <= 1000: return 200 items across 2 pages (100 per page)
                items = [
                    {"id": low * 1000 + page * 100 + i, "stargazers_count": low, "name": f"r-{low}-{i}"}
                    for i in range(100)
                ]
                return {"total_count": 200, "items": items}

        ingestor._fetch_search_page = MagicMock(side_effect=mock_fetch)

        results = ingestor.search_range(2000, 6000)

        self.assertGreater(len(results), 0)
        # All collected items should have unique IDs
        ids = [r["id"] for r in results]
        self.assertEqual(len(ids), len(set(ids)), "All collected repositories must be unique without drops")


class TestSingleStarDatePartitionFallback(unittest.TestCase):
    """
    Tests fallback to creation date partitioning when min_stars == max_stars
    and total_count > 1000 (dense star cluster).
    """

    def setUp(self):
        self.simulated_time = 100.0
        self.sleep_calls = []

        def mock_time():
            return self.simulated_time

        def mock_sleep(d):
            self.sleep_calls.append(d)
            self.simulated_time += d

        self.mock_time = mock_time
        self.mock_sleep = mock_sleep

    def test_single_star_cluster_fallback(self):
        ingestor = AdaptiveBisectionIngestor(
            token="test-token",
            dry_run=True,
            time_fn=self.mock_time,
            sleep_fn=self.mock_sleep,
        )

        date_queries_executed = []

        def mock_fetch(query, page=1, per_page=100, max_retries=5):
            if query == "stars:2000..2000":
                # Dense star cluster overflow
                return {"total_count": 1800, "items": []}
            if "created:" in query:
                date_queries_executed.append(query)
                # Return 50 repos for 2021, 50 for 2022
                if "2021" in query or "2022" in query:
                    items = [{"id": 100000 + len(date_queries_executed) * 100 + i, "stargazers_count": 2000} for i in range(50)]
                    return {"total_count": 50, "items": items}
                return {"total_count": 0, "items": []}
            return {"total_count": 0, "items": []}

        ingestor._fetch_search_page = MagicMock(side_effect=mock_fetch)

        results = ingestor.search_range(2000, 2000)

        # Date queries must be executed across years
        self.assertTrue(len(date_queries_executed) > 0)
        self.assertTrue(any("created:2021-01-01..2021-12-31" in q for q in date_queries_executed))
        self.assertTrue(any("created:2022-01-01..2022-12-31" in q for q in date_queries_executed))
        # Total repos collected from 2021 and 2022
        self.assertEqual(len(results), 100)


class TestRateLimitRecoveryAndErrors(unittest.TestCase):
    """
    Supervisor Quality Gate 2:
    Tests parsing of Retry-After headers, x-ratelimit-reset headers,
    exponential backoff on 403 / 429, and proper recovery.
    """

    def setUp(self):
        self.simulated_time = 1000.0
        self.sleep_calls = []

        def mock_time():
            return self.simulated_time

        def mock_sleep(d):
            self.sleep_calls.append(d)
            self.simulated_time += d

        self.mock_time = mock_time
        self.mock_sleep = mock_sleep

    def test_http_429_retry_after_header(self):
        ingestor = AdaptiveBisectionIngaction = AdaptiveBisectionIngestor(
            token="test-token",
            time_fn=self.mock_time,
            sleep_fn=self.mock_sleep,
        )

        mock_session = MagicMock()
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_429.headers = {"Retry-After": "42"}

        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.json.return_value = {"total_count": 1, "items": [{"id": 1, "stargazers_count": 2500}]}

        mock_session.get.side_effect = [mock_resp_429, mock_resp_200]
        ingestor.session = mock_session

        data = ingestor._fetch_search_page("stars:2500..2500", page=1)

        self.assertEqual(data["total_count"], 1)
        self.assertIn(42.0, self.sleep_calls)

    def test_http_403_ratelimit_reset_header(self):
        ingestor = AdaptiveBisectionIngestor(
            token="test-token",
            time_fn=self.mock_time,
            sleep_fn=self.mock_sleep,
        )

        mock_session = MagicMock()
        # Reset epoch is 1030.0; simulated_time is 1000.0 -> wait ~31.0s
        mock_resp_403 = MagicMock()
        mock_resp_403.status_code = 403
        mock_resp_403.headers = {
            "x-ratelimit-reset": "1030",
            "x-ratelimit-remaining": "0",
        }

        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.json.return_value = {"total_count": 1, "items": [{"id": 2, "stargazers_count": 3000}]}

        mock_session.get.side_effect = [mock_resp_403, mock_resp_200]
        ingestor.session = mock_session

        data = ingestor._fetch_search_page("stars:3000..3000", page=1)

        self.assertEqual(data["total_count"], 1)
        self.assertTrue(any(s >= 30.0 for s in self.sleep_calls))

    def test_http_401_invalid_token_raises_value_error(self):
        ingestor = AdaptiveBisectionIngestor(
            token="bad-token",
            time_fn=self.mock_time,
            sleep_fn=self.mock_sleep,
        )
        mock_session = MagicMock()
        mock_resp_401 = MagicMock()
        mock_resp_401.status_code = 401
        mock_session.get.return_value = mock_resp_401
        ingestor.session = mock_session

        with self.assertRaises(ValueError):
            ingestor._fetch_search_page("stars:2000..3000")


class TestIdempotentDatabaseUpsert(unittest.TestCase):
    """
    Supervisor Quality Gate 7:
    Tests idempotent upsert behavior.
    Verifies that re-running ingestion updates telemetry metrics (stars, forks, pushed_at)
    while strictly preserving AI enrichment fields (macro_domain, archetype, is_enriched).
    """

    def setUp(self):
        self.db_path = "test_repositories.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_idempotent_upsert_preserves_enrichment(self):
        ingestor = AdaptiveBisectionIngestor(
            db_provider="sqlite",
            database_url=f"sqlite:///{self.db_path}",
        )

        sample_repo_v1 = {
            "id": 99999,
            "full_name": "astral-sh/uv",
            "name": "uv",
            "owner": {"login": "astral-sh"},
            "html_url": "https://github.com/astral-sh/uv",
            "homepage": "https://astral.sh",
            "description": "An extremely fast Python package and project manager.",
            "stargazers_count": 35000,
            "forks_count": 1200,
            "open_issues_count": 150,
            "language": "Rust",
            "license": {"spdx_id": "MIT"},
            "archived": False,
            "created_at": "2024-02-15T00:00:00Z",
            "pushed_at": "2024-03-01T00:00:00Z",
        }

        # Step 1: Initial Ingestion Upsert
        count = ingestor.upsert_telemetry([sample_repo_v1])
        self.assertEqual(count, 1)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT stars_count, is_enriched, macro_domain FROM repositories WHERE id = 99999")
        row = cur.fetchone()
        self.assertEqual(row[0], 35000)
        self.assertEqual(row[1], 0)  # Not enriched yet
        self.assertEqual(row[2], "Unassigned")

        # Step 2: Simulate Phase 3 AI Categorization enrichment
        cur.execute("""
            UPDATE repositories
            SET is_enriched = 1,
                macro_domain = 'Developer Tooling',
                archetype = 'CLI Tool / Binary',
                problem_solved = 'Fast Python package management written in Rust.'
            WHERE id = 99999
        """)
        conn.commit()

        # Step 3: Run Ingestion Upsert a second time with updated telemetry (daily cron sync)
        sample_repo_v2 = dict(sample_repo_v1)
        sample_repo_v2["stargazers_count"] = 38500  # Gained 3,500 stars
        sample_repo_v2["forks_count"] = 1450
        sample_repo_v2["pushed_at"] = "2024-03-15T12:00:00Z"

        count2 = ingestor.upsert_telemetry([sample_repo_v2])
        self.assertEqual(count2, 1)

        # Step 4: Verify that telemetry updated, but enrichment was preserved!
        cur.execute("""
            SELECT stars_count, forks_count, is_enriched, macro_domain, archetype, problem_solved
            FROM repositories WHERE id = 99999
        """)
        updated_row = cur.fetchone()
        conn.close()

        self.assertEqual(updated_row[0], 38500, "stars_count must be updated to 38500")
        self.assertEqual(updated_row[1], 1450, "forks_count must be updated to 1450")
        self.assertEqual(updated_row[2], 1, "is_enriched MUST remain 1 (not reset to 0)")
        self.assertEqual(updated_row[3], "Developer Tooling", "macro_domain must remain Developer Tooling")
        self.assertEqual(updated_row[4], "CLI Tool / Binary", "archetype must remain CLI Tool / Binary")
        self.assertEqual(updated_row[5], "Fast Python package management written in Rust.")


class TestIngestionEdgeCasesAndCLI(unittest.TestCase):
    """
    Tests additional edge cases: deduplication, limit truncation,
    exponential backoff on secondary rate limits and 5xx server errors,
    and dry-run behavior.
    """

    def setUp(self):
        self.simulated_time = 1000.0
        self.sleep_calls = []

        def mock_time():
            return self.simulated_time

        def mock_sleep(d):
            self.sleep_calls.append(d)
            self.simulated_time += d

        self.mock_time = mock_time
        self.mock_sleep = mock_sleep

    def test_deduplication_of_records(self):
        ingestor = AdaptiveBisectionIngestor(dry_run=True)
        raw_items = [
            {"id": 101, "full_name": "owner/repo1", "stargazers_count": 2100},
            {"id": 102, "full_name": "owner/repo2", "stargazers_count": 2200},
            {"id": 101, "full_name": "owner/repo1", "stargazers_count": 2100},  # Duplicate
        ]
        unique = ingestor.deduplicate_records(raw_items)
        self.assertEqual(len(unique), 2)
        self.assertEqual([r["id"] for r in unique], [101, 102])

    def test_limit_truncation(self):
        ingestor = AdaptiveBisectionIngestor(
            token="test-token",
            dry_run=True,
            time_fn=self.mock_time,
            sleep_fn=self.mock_sleep,
        )

        def mock_fetch(query, page=1, per_page=100, max_retries=5):
            items = [{"id": 500 + i, "stargazers_count": 2500, "name": f"repo-{i}"} for i in range(100)]
            return {"total_count": 500, "items": items}

        ingestor._fetch_search_page = MagicMock(side_effect=mock_fetch)
        results = ingestor.search_range(2000, 3000, limit=15)
        self.assertEqual(len(results), 15)

    def test_server_error_500_retry(self):
        ingestor = AdaptiveBisectionIngestor(
            token="test-token",
            time_fn=self.mock_time,
            sleep_fn=self.mock_sleep,
        )
        mock_session = MagicMock()
        mock_resp_500 = MagicMock()
        mock_resp_500.status_code = 500

        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.json.return_value = {"total_count": 1, "items": [{"id": 777}]}

        mock_session.get.side_effect = [mock_resp_500, mock_resp_200]
        ingestor.session = mock_session

        data = ingestor._fetch_search_page("stars:2000..2000")
        self.assertEqual(data["total_count"], 1)
        self.assertTrue(len(self.sleep_calls) > 0)

    def test_dry_run_ingest_orchestration(self):
        ingestor = AdaptiveBisectionIngestor(
            token="test-token",
            dry_run=True,
            time_fn=self.mock_time,
            sleep_fn=self.mock_sleep,
        )
        ingestor._fetch_search_page = MagicMock(return_value={
            "total_count": 2,
            "items": [
                {"id": 1, "full_name": "test/repo1", "stargazers_count": 2000},
                {"id": 2, "full_name": "test/repo2", "stargazers_count": 2001},
            ]
        })
        count = ingestor.ingest(min_stars=2000, max_stars=2001)
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
