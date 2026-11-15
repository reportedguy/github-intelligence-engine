"""
tests/test_taxonomy_router.py
Unit test suite verifying Phase 3 deliverables:
1. Pydantic validation rejects hallucinated domains, archetypes, and invalid syntax.
2. LLM router fallback when provider 1 fails (HTTP 429, malformed JSON, timeouts, hallucinated outputs).
3. 384-dimensional vector embedding shape and type audit.
4. README sanitization and batch database enrichment.
"""

import os
import unittest
import json
from unittest.mock import MagicMock, patch
import requests

from scripts.schema import (
    RepositoryTaxonomySchema,
    validate_taxonomy,
    TaxonomyValidationError,
    MACRO_DOMAINS,
    ARCHETYPES,
)
from scripts.router import (
    MultiProviderLLMRouter,
    ProviderConfig,
    AllProvidersFailedError,
    clean_json_markdown_fences,
)
from scripts.enrich_taxonomy import (
    sanitize_readme,
    LocalEmbeddingEngine,
    TaxonomyEnrichmentPipeline,
    SqliteDatabaseAdapter,
    build_vector_representation_text,
)


class TestTaxonomySchemaValidation(unittest.TestCase):
    """Verifies strict adherence to the 6-pillar taxonomy and closed-domain invariants."""

    def setUp(self):
        self.valid_payload = {
            "macro_domain": "Databases & Storage",
            "sub_domain": "Distributed Key-Value Stores",
            "archetype": "Runnable Server / Engine",
            "problem_solved": "Eliminates high-latency disk I/O bottlenecks in data systems by maintaining an in-memory hash store with asynchronous persistence.",
            "use_cases": [
                "Distributed-Caching",
                "State-Synchronization",
                "Session-Storage",
            ],
            "primary_ecosystem": "C / Linux Kernel",
            "target_audience": [
                "Backend Engineers",
                "Platform / SRE Teams",
            ],
            "confidence_score": 98,
        }

    def test_valid_schema_instantiation(self):
        """Valid taxonomy payload should pass cleanly."""
        schema = validate_taxonomy(self.valid_payload)
        self.assertIsInstance(schema, RepositoryTaxonomySchema)
        self.assertEqual(schema.macro_domain, "Databases & Storage")
        self.assertEqual(schema.archetype, "Runnable Server / Engine")
        self.assertEqual(len(schema.use_cases), 3)
        self.assertEqual(schema.confidence_score, 98)

    def test_rejects_hallucinated_macro_domain(self):
        """Pydantic validation must strictly reject hallucinated or invalid macro domains."""
        hallucinated_domains = [
            "Crypto & Web3",
            "Random Artificial Intelligence",
            "General Software",
            "DevOps and Cloud",
            "Web Development",
            "Mobile Apps",
        ]
        for bad_domain in hallucinated_domains:
            with self.subTest(bad_domain=bad_domain):
                bad_payload = dict(self.valid_payload)
                bad_payload["macro_domain"] = bad_domain
                with self.assertRaises((TaxonomyValidationError, ValueError)):
                    validate_taxonomy(bad_payload)

    def test_rejects_hallucinated_archetype(self):
        """Pydantic validation must strictly reject non-standard archetypes."""
        hallucinated_archetypes = [
            "Microservice",
            "WordPress Plugin",
            "Software Application",
            "SaaS Product",
            "Script",
        ]
        for bad_arch in hallucinated_archetypes:
            with self.subTest(bad_arch=bad_arch):
                bad_payload = dict(self.valid_payload)
                bad_payload["archetype"] = bad_arch
                with self.assertRaises((TaxonomyValidationError, ValueError)):
                    validate_taxonomy(bad_payload)

    def test_accepts_all_15_macro_domains(self):
        """Verifies that all 15 defined macro domains are individually valid."""
        self.assertEqual(len(MACRO_DOMAINS), 15)
        for domain in MACRO_DOMAINS:
            payload = dict(self.valid_payload)
            payload["macro_domain"] = domain
            schema = validate_taxonomy(payload)
            self.assertEqual(schema.macro_domain, domain)

    def test_accepts_all_8_archetypes(self):
        """Verifies that all 8 defined archetypes are individually valid."""
        self.assertEqual(len(ARCHETYPES), 8)
        for archetype in ARCHETYPES:
            payload = dict(self.valid_payload)
            payload["archetype"] = archetype
            schema = validate_taxonomy(payload)
            self.assertEqual(schema.archetype, archetype)

    def test_use_cases_count_and_syntax(self):
        """Verifies use cases must be 3-5 items and follow [Verb-Noun] format."""
        # Under minimum (< 3)
        under_payload = dict(self.valid_payload)
        under_payload["use_cases"] = ["Distributed-Caching", "State-Sync"]
        with self.assertRaises((TaxonomyValidationError, ValueError)):
            validate_taxonomy(under_payload)

        # Over maximum (> 5)
        over_payload = dict(self.valid_payload)
        over_payload["use_cases"] = [
            "Distributed-Caching",
            "State-Sync",
            "Session-Storage",
            "Event-Streaming",
            "Memory-Management",
            "Rate-Limiting",
        ]
        with self.assertRaises((TaxonomyValidationError, ValueError)):
            validate_taxonomy(over_payload)

        # Non-verb-noun format (single word tags)
        single_word_payload = dict(self.valid_payload)
        single_word_payload["use_cases"] = ["Database", "Cache", "Fast"]
        with self.assertRaises((TaxonomyValidationError, ValueError)):
            validate_taxonomy(single_word_payload)

    def test_confidence_score_boundaries(self):
        """Confidence score must be strictly between 1 and 100."""
        # Negative / zero
        bad_low = dict(self.valid_payload, confidence_score=0)
        with self.assertRaises((TaxonomyValidationError, ValueError)):
            validate_taxonomy(bad_low)

        # Exceeds 100
        bad_high = dict(self.valid_payload, confidence_score=101)
        with self.assertRaises((TaxonomyValidationError, ValueError)):
            validate_taxonomy(bad_high)

        # Edge cases 1 and 100 should pass
        low_valid = dict(self.valid_payload, confidence_score=1)
        self.assertEqual(validate_taxonomy(low_valid).confidence_score, 1)

        high_valid = dict(self.valid_payload, confidence_score=100)
        self.assertEqual(validate_taxonomy(high_valid).confidence_score, 100)

    def test_problem_solved_validation(self):
        """Problem solved must not be empty or too short."""
        bad_short = dict(self.valid_payload, problem_solved="Too short.")
        with self.assertRaises((TaxonomyValidationError, ValueError)):
            validate_taxonomy(bad_short)


class TestReadmeSanitizer(unittest.TestCase):
    """Verifies that README pre-processing strips HTML, SVGs, badges, and sponsor sections."""

    def test_sanitization_removes_noise(self):
        raw_markdown = """
# MyCoolProject [![Build Status](https://img.shields.io/travis/user/repo.svg)](https://travis-ci.org) [![Coverage](https://badgen.net/badge/cov/99%25/green)](https://coveralls.io)
<p align="center">
  <img src="https://example.com/logo.png" width="300" alt="Logo" />
  <svg><path d="M0 0h24v24H0z"/></svg>
</p>

<!-- Some hidden HTML comment -->
## Overview
MyCoolProject provides high-performance distributed vector indexing for production microservices.

## Key Features
- Sub-millisecond ANN search using HNSW graphs
- SIMD-accelerated dot product computations

## Sponsors & Backers
Please consider supporting us on Patreon!
- Sponsor 1
- Sponsor 2

## Contributors
Thanks to all contributors!

## License
MIT License Copyright (c) 2026
        """
        clean = sanitize_readme(raw_markdown, max_chars=3000)

        # Asserts noise removed
        self.assertNotIn("img.shields.io", clean)
        self.assertNotIn("badgen.net", clean)
        self.assertNotIn("<img", clean)
        self.assertNotIn("<svg", clean)
        self.assertNotIn("<!--", clean)
        self.assertNotIn("Sponsors & Backers", clean)
        self.assertNotIn("Patreon", clean)
        self.assertNotIn("MIT License Copyright", clean)

        # Asserts core overview and features preserved
        self.assertIn("MyCoolProject provides high-performance distributed vector indexing", clean)
        self.assertIn("Sub-millisecond ANN search", clean)
        self.assertLessEqual(len(clean), 3000)


class TestMultiProviderLLMRouter(unittest.TestCase):
    """Tests automatic provider failover across HTTP 429, malformed JSON, and validation failures."""

    def setUp(self):
        self.valid_taxonomy_json = json.dumps({
            "macro_domain": "AI & Machine Learning",
            "sub_domain": "LLM Inference Engines",
            "archetype": "CLI Tool / Binary",
            "problem_solved": "Accelerates local LLM execution by running quantized GGUF weights on consumer GPUs.",
            "use_cases": ["Local-Inference", "Model-Quantization", "Hardware-Acceleration"],
            "primary_ecosystem": "C++ / CUDA",
            "target_audience": ["AI Engineers", "Self-Hosters"],
            "confidence_score": 95,
        })

    def test_clean_json_markdown_fences(self):
        """Verifies clean extraction of JSON when LLM wraps in markdown codeblocks."""
        raw_wrapped = f"```json\n{self.valid_taxonomy_json}\n```"
        cleaned = clean_json_markdown_fences(raw_wrapped)
        data = json.loads(cleaned)
        self.assertEqual(data["macro_domain"], "AI & Machine Learning")

    def test_router_fallback_on_http_429_rate_limit(self):
        """When provider 1 encounters HTTP 429, router must seamlessly fail over to provider 2."""
        mock_p1 = ProviderConfig(
            name="Tier-1 Groq",
            endpoint="https://api.groq.com/v1",
            model="llama-3.3-70b-versatile",
            api_key_envs=["MOCK_KEY_1"],
        )
        mock_p2 = ProviderConfig(
            name="Tier-2 Gemini",
            endpoint="https://gemini.googleapis.com/v1",
            model="gemini-2.0-flash",
            api_key_envs=["MOCK_KEY_2"],
        )

        mock_session = MagicMock()

        # Provider 1 returns HTTP 429 (Rate Limit)
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "15"}
        resp_429.text = "Rate limit reached"

        # Provider 2 returns HTTP 200 with valid schema
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "choices": [{"message": {"content": self.valid_taxonomy_json}}]
        }

        mock_session.post.side_effect = [resp_429, resp_200]

        router = MultiProviderLLMRouter(
            providers=[mock_p1, mock_p2],
            api_keys={"Tier-1 Groq": "key1", "Tier-2 Gemini": "key2"},
            session=mock_session,
        )

        result = router.extract_taxonomy("test/repo", "Overview context")
        self.assertIsInstance(result, RepositoryTaxonomySchema)
        self.assertEqual(result.macro_domain, "AI & Machine Learning")
        self.assertEqual(mock_session.post.call_count, 2)

    def test_router_fallback_on_malformed_json(self):
        """When provider 1 outputs unparseable text, router must fail over to provider 2."""
        mock_p1 = ProviderConfig(
            name="Tier-1 Provider",
            endpoint="https://provider1.test",
            model="model-1",
            api_key_envs=["KEY_1"],
        )
        mock_p2 = ProviderConfig(
            name="Tier-2 Provider",
            endpoint="https://provider2.test",
            model="model-2",
            api_key_envs=["KEY_2"],
        )

        mock_session = MagicMock()

        # Provider 1 returns malformed content
        resp_malformed = MagicMock()
        resp_malformed.status_code = 200
        resp_malformed.json.return_value = {
            "choices": [{"message": {"content": "This is definitely not JSON {broken"}}]
        }

        # Provider 2 returns valid JSON
        resp_valid = MagicMock()
        resp_valid.status_code = 200
        resp_valid.json.return_value = {
            "choices": [{"message": {"content": self.valid_taxonomy_json}}]
        }

        mock_session.post.side_effect = [resp_malformed, resp_valid]

        router = MultiProviderLLMRouter(
            providers=[mock_p1, mock_p2],
            api_keys={"Tier-1 Provider": "k1", "Tier-2 Provider": "k2"},
            session=mock_session,
        )

        result = router.extract_taxonomy("test/repo", "Context")
        self.assertEqual(result.sub_domain, "LLM Inference Engines")
        self.assertEqual(mock_session.post.call_count, 2)

    def test_router_fallback_on_hallucinated_domain(self):
        """When provider 1 returns a hallucinated domain, router validation fails and falls over."""
        mock_p1 = ProviderConfig(name="P1", endpoint="https://p1", model="m1", api_key_envs=["K1"])
        mock_p2 = ProviderConfig(name="P2", endpoint="https://p2", model="m2", api_key_envs=["K2"])

        mock_session = MagicMock()

        # Provider 1 returns hallucinated domain "Quantum Cryptography"
        hallucinated_json = json.dumps({
            "macro_domain": "Quantum Cryptography",  # INVALID DOMAIN
            "sub_domain": "QKD",
            "archetype": "Library / SDK",
            "problem_solved": "Secures communications by implementing quantum key distribution.",
            "use_cases": ["Quantum-Encryption", "Key-Distribution", "Secure-Communication"],
            "primary_ecosystem": "Python",
            "target_audience": ["Security Researchers"],
            "confidence_score": 90,
        })
        resp_hallucinated = MagicMock()
        resp_hallucinated.status_code = 200
        resp_hallucinated.json.return_value = {
            "choices": [{"message": {"content": hallucinated_json}}]
        }

        # Provider 2 returns valid domain
        resp_valid = MagicMock()
        resp_valid.status_code = 200
        resp_valid.json.return_value = {
            "choices": [{"message": {"content": self.valid_taxonomy_json}}]
        }

        mock_session.post.side_effect = [resp_hallucinated, resp_valid]

        router = MultiProviderLLMRouter(
            providers=[mock_p1, mock_p2],
            api_keys={"P1": "k1", "P2": "k2"},
            session=mock_session,
        )

        result = router.extract_taxonomy("test/repo", "Context")
        self.assertEqual(result.macro_domain, "AI & Machine Learning")
        self.assertEqual(mock_session.post.call_count, 2)

    def test_router_all_providers_fail(self):
        """When all providers fail, router raises AllProvidersFailedError with audit details."""
        mock_p1 = ProviderConfig(name="P1", endpoint="https://p1", model="m1", api_key_envs=["K1"])
        mock_session = MagicMock()

        resp_500 = MagicMock()
        resp_500.status_code = 500
        resp_500.text = "Internal Server Error"
        mock_session.post.return_value = resp_500

        router = MultiProviderLLMRouter(
            providers=[mock_p1],
            api_keys={"P1": "k1"},
            session=mock_session,
        )

        with self.assertRaises(AllProvidersFailedError) as ctx:
            router.extract_taxonomy("test/repo", "Context")

        self.assertIn("Audit Trail", str(ctx.exception))
        self.assertEqual(len(ctx.exception.audit_log), 1)


class TestVectorEmbeddingEngine(unittest.TestCase):
    """Verifies that local FastEmbed produces strict 384-dimensional dense vectors."""

    @classmethod
    def setUpClass(cls):
        cls.engine = LocalEmbeddingEngine(model_name="BAAI/bge-small-en-v1.5")

    def test_384_dimensional_vector_output_shape(self):
        """Dense vector must strictly be 384 dimensions of float32 values."""
        text = "Fast in-memory key-value cache with asynchronous snapshotting."
        embedding = self.engine.embed_text(text)

        self.assertIsInstance(embedding, list)
        self.assertEqual(len(embedding), 384, f"Expected 384 dimensions, got {len(embedding)}")
        self.assertTrue(all(isinstance(x, float) for x in embedding))
        # Ensure values are non-trivial floats
        self.assertTrue(any(abs(x) > 0.0001 for x in embedding))

    def test_batch_vector_generation(self):
        """Batch vector generation preserves 384-dimensional shape for every item."""
        texts = [
            "Next.js App Router fullstack template with Tailwind CSS.",
            "Linux kernel eBPF observability and tracing agent.",
            "Distributed stream processor with exactly-once delivery guarantees.",
        ]
        embeddings = self.engine.embed_batch(texts)
        self.assertEqual(len(embeddings), 3)
        for vec in embeddings:
            self.assertEqual(len(vec), 384)


class TestBatchEnrichmentDatabaseUpdate(unittest.TestCase):
    """Verifies batch database pipeline updates taxonomy fields, vectors, and sets is_enriched=1."""

    def setUp(self):
        # Use an in-memory SQLite database
        self.adapter = SqliteDatabaseAdapter(":memory:")
        cursor = self.adapter.conn.cursor()
        cursor.execute("""
            INSERT INTO repositories (
                id, full_name, name, owner, url, description, stars_count, primary_language, is_enriched
            ) VALUES (
                101, 'redis/redis', 'redis', 'redis', 'https://github.com/redis/redis',
                'In-memory database that persists on disk', 65000, 'C', 0
            )
        """)
        self.adapter.conn.commit()

    def tearDown(self):
        self.adapter.close()

    def test_batch_pipeline_flow(self):
        """Simulates end-to-end enrichment on a mock database row."""
        mock_router = MagicMock()
        mock_router.extract_taxonomy.return_value = RepositoryTaxonomySchema(
            macro_domain="Databases & Storage",
            sub_domain="In-Memory Databases",
            archetype="Runnable Server / Engine",
            problem_solved="Eliminates disk I/O latency bottlenecks by managing key-value data structures in memory.",
            use_cases=["Distributed-Caching", "Message-Brokering", "Session-Storage"],
            primary_ecosystem="C / POSIX",
            target_audience=["Backend Engineers", "Database Administrators"],
            confidence_score=99,
        )

        mock_fetcher = MagicMock()
        mock_fetcher.fetch_readme.return_value = "# Redis\nIn-memory data structure store."

        pipeline = TaxonomyEnrichmentPipeline(
            router=mock_router,
            embedder=LocalEmbeddingEngine(),
            db_adapter=self.adapter,
            readme_fetcher=mock_fetcher,
        )

        enriched_count = pipeline.run_batch(batch_limit=10)
        self.assertEqual(enriched_count, 1)

        # Verify database record updated
        cursor = self.adapter.conn.cursor()
        cursor.execute("SELECT is_enriched, macro_domain, archetype, confidence_score, embedding FROM repositories WHERE id = 101")
        row = cursor.fetchone()
        self.assertEqual(row["is_enriched"], 1)
        self.assertEqual(row["macro_domain"], "Databases & Storage")
        self.assertEqual(row["archetype"], "Runnable Server / Engine")
        self.assertEqual(row["confidence_score"], 99)
        # 384 floats * 4 bytes per float = 1536 bytes
        self.assertEqual(len(row["embedding"]), 384 * 4)


if __name__ == "__main__":
    unittest.main()
