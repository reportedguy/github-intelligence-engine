"""
scripts/router.py
Multi-Provider LLM Router with automatic failover across 5 free-tier AI providers:
1. Groq Cloud (llama-3.3-70b-versatile) - Primary Tier-1 Engine
2. Google AI Studio (gemini-2.0-flash) - Tier-2 Engine
3. Cerebras Cloud (llama-3.1-70b) - Tier-3 High-Throughput Failover
4. GitHub Models API (gpt-4o-mini) - Tier-4 Developer Token Failover
5. OpenRouter Free Pool (meta-llama/llama-3.3-70b-instruct:free) - Tier-5 Final Safety Net

Enforces JSON object response format and performs automatic fallback upon:
- HTTP 429 Rate Limits
- HTTP 5xx Server Errors
- Connection Timeouts / Network Failures
- Malformed JSON / Unparseable Responses
- Pydantic Schema Validation Errors (Hallucinated domains/archetypes)
"""

import os
import re
import json
import time
import logging
from typing import List, Dict, Any, Optional, Callable
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scripts.schema import (
    RepositoryTaxonomySchema,
    validate_taxonomy,
    get_taxonomy_prompt_instructions,
    TaxonomyValidationError,
)

logger = logging.getLogger("LLMRouter")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [Router] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class ProviderError(Exception):
    """Base error for provider-specific failures."""
    pass


class RateLimitError(ProviderError):
    """Raised when an HTTP 429 rate limit is encountered."""
    pass


class MalformedResponseError(ProviderError):
    """Raised when provider returns unparseable or malformed output."""
    pass


class AllProvidersFailedError(Exception):
    """Raised when all configured providers in the rotation fail."""
    def __init__(self, message: str, audit_log: List[Dict[str, Any]]):
        super().__init__(message)
        self.message = message
        self.audit_log = audit_log

    def __str__(self) -> str:
        summary = "\n".join(
            f"  - Provider '{entry.get('provider')}': {entry.get('error')}"
            for entry in self.audit_log
        )
        return f"{self.message}\nAudit Trail:\n{summary}"


class ProviderConfig:
    """Configuration descriptor for an LLM provider endpoint."""
    def __init__(
        self,
        name: str,
        endpoint: str,
        model: str,
        api_key_envs: List[str],
        default_headers: Optional[Dict[str, str]] = None,
        timeout: int = 45,
        custom_payload_builder: Optional[Callable] = None,
        custom_response_extractor: Optional[Callable] = None,
    ):
        self.name = name
        self.endpoint = endpoint
        self.model = model
        self.api_key_envs = api_key_envs
        self.default_headers = default_headers or {}
        self.timeout = timeout
        self.custom_payload_builder = custom_payload_builder
        self.custom_response_extractor = custom_response_extractor

    def get_api_key(self, key_overrides: Optional[Dict[str, str]] = None) -> Optional[str]:
        if key_overrides and self.name in key_overrides:
            return key_overrides[self.name]
        for env_var in self.api_key_envs:
            val = os.getenv(env_var)
            if val and val.strip():
                return val.strip()
        return None


def get_default_provider_pool() -> List[ProviderConfig]:
    """Returns the ordered 5-tier provider pool matching the Master Plan."""
    return [
        ProviderConfig(
            name="Groq Cloud",
            endpoint="https://api.groq.com/openai/v1/chat/completions",
            model="llama-3.3-70b-versatile",
            api_key_envs=["GROQ_API_KEY"],
            timeout=30,
        ),
        ProviderConfig(
            name="Google AI Studio",
            endpoint="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            model="gemini-2.0-flash",
            api_key_envs=["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            timeout=35,
        ),
        ProviderConfig(
            name="Cerebras Cloud",
            endpoint="https://api.cerebras.ai/v1/chat/completions",
            model="llama-3.1-70b",
            api_key_envs=["CEREBRAS_API_KEY"],
            timeout=30,
        ),
        ProviderConfig(
            name="GitHub Models API",
            endpoint="https://models.inference.ai.azure.com/chat/completions",
            model="gpt-4o-mini",
            api_key_envs=["GITHUB_TOKEN", "GH_PAT_TOKEN", "GITHUB_MODELS_TOKEN"],
            timeout=35,
        ),
        ProviderConfig(
            name="OpenRouter Free Pool",
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            model="meta-llama/llama-3.3-70b-instruct:free",
            api_key_envs=["OPENROUTER_API_KEY"],
            default_headers={
                "HTTP-Referer": "https://github-intelligence.engine",
                "X-Title": "GitHub Intelligence Engine",
            },
            timeout=45,
        ),
    ]


def clean_json_markdown_fences(content: str) -> str:
    """Strips markdown ```json ... ``` code fences and extraneous whitespace."""
    if not content:
        return ""
    cleaned = content.strip()
    # Strip opening fence
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
    else:
        # If closing tag is at end
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    return cleaned


class MultiProviderLLMRouter:
    """
    Robust Multi-Provider LLM Router with prioritized failover,
    strict JSON schema enforcement, and validation verification.
    """
    def __init__(
        self,
        providers: Optional[List[ProviderConfig]] = None,
        api_keys: Optional[Dict[str, str]] = None,
        session: Optional[requests.Session] = None,
    ):
        self.providers = providers if providers is not None else get_default_provider_pool()
        self.api_keys = api_keys or {}
        if session:
            self.session = session
        else:
            self.session = requests.Session()
            adapter = HTTPAdapter(max_retries=Retry(total=1, backoff_factor=0.5, status_forcelist=[502, 503, 504]))
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)

    def _execute_provider_call(
        self,
        provider: ProviderConfig,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Invokes an OpenAI-compatible endpoint with JSON format enforcement.
        Raises RateLimitError, MalformedResponseError, or ProviderError on failure.
        """
        api_key = provider.get_api_key(self.api_keys)
        if not api_key:
            raise ProviderError(f"Missing API key for provider '{provider.name}' (checked: {provider.api_key_envs})")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        headers.update(provider.default_headers)

        payload = {
            "model": provider.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": temperature,
        }

        try:
            response = self.session.post(
                provider.endpoint,
                headers=headers,
                json=payload,
                timeout=provider.timeout,
            )
        except requests.exceptions.Timeout as e:
            raise ProviderError(f"Timeout connecting to {provider.name} ({provider.timeout}s): {e}") from e
        except requests.exceptions.RequestException as e:
            raise ProviderError(f"Network error calling {provider.name}: {e}") from e

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "unknown")
            raise RateLimitError(f"Rate limit HTTP 429 on {provider.name} (Retry-After: {retry_after})")

        if response.status_code != 200:
            error_body = response.text[:400]
            raise ProviderError(
                f"HTTP {response.status_code} error from {provider.name}: {error_body}"
            )

        try:
            resp_json = response.json()
        except Exception as e:
            raise MalformedResponseError(f"Failed to decode response JSON from {provider.name}: {e}") from e

        # Extract message content
        choices = resp_json.get("choices", [])
        if not choices or not isinstance(choices, list):
            raise MalformedResponseError(f"No choices array in response from {provider.name}: {resp_json}")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not content:
            raise MalformedResponseError(f"Empty message content from {provider.name}")

        cleaned_content = clean_json_markdown_fences(content)
        try:
            parsed_data = json.loads(cleaned_content)
        except json.JSONDecodeError as e:
            raise MalformedResponseError(
                f"Content from {provider.name} is not valid JSON ({e}). Raw content snippet: {cleaned_content[:200]}"
            ) from e

        if not isinstance(parsed_data, dict):
            raise MalformedResponseError(f"Expected JSON object/dict from {provider.name}, got {type(parsed_data).__name__}")

        return parsed_data

    def complete(
        self,
        messages: List[Dict[str, str]],
        validator: Optional[Callable[[Dict[str, Any]], Any]] = None,
        temperature: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Executes an LLM chat completion across the provider pool with automatic failover.
        If a validator callable is provided, output is checked; if validation fails,
        the router fails over to the next provider.
        """
        audit_log: List[Dict[str, Any]] = []

        for provider in self.providers:
            start_time = time.time()
            logger.info(f"Attempting inference via [{provider.name}] (model: {provider.model})...")

            try:
                result = self._execute_provider_call(provider, messages, temperature=temperature)
                
                # If a validator is supplied, enforce schema correctness
                if validator is not None:
                    try:
                        validator(result)
                    except (TaxonomyValidationError, ValueError, Exception) as val_err:
                        raise MalformedResponseError(
                            f"Output from {provider.name} failed schema validation: {val_err}"
                        ) from val_err

                duration = time.time() - start_time
                logger.info(f"Success from [{provider.name}] in {duration:.2f}s")
                return result

            except Exception as e:
                duration = time.time() - start_time
                error_msg = str(e)
                logger.warning(f"Failover triggered: Provider [{provider.name}] failed after {duration:.2f}s: {error_msg}")
                audit_log.append({
                    "provider": provider.name,
                    "model": provider.model,
                    "duration_sec": duration,
                    "error": error_msg,
                    "error_class": e.__class__.__name__,
                })

        raise AllProvidersFailedError(
            f"All {len(self.providers)} providers in LLM router pool failed.",
            audit_log=audit_log,
        )

    def extract_taxonomy(
        self,
        repo_name: str,
        context_text: str,
        primary_language: str = "",
        topics: Optional[List[str]] = None,
    ) -> RepositoryTaxonomySchema:
        """
        Extracts and strictly validates RepositoryTaxonomySchema from repository context.
        Injects the closed taxonomy constraints into system prompt.
        """
        system_prompt = get_taxonomy_prompt_instructions()

        topics_str = ", ".join(topics) if topics else "None"
        user_prompt = f"""Target Repository: {repo_name}
Primary Language: {primary_language or 'Not specified'}
GitHub Topics: {topics_str}

SANITIZED REPOSITORY OVERVIEW & FEATURES:
{context_text}

Analyze the technical overview above and classify this repository into the 6-pillar JSON taxonomy.
Ensure `macro_domain` and `archetype` exactly match the allowed closed lists.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        def taxonomy_validator(data: Dict[str, Any]) -> RepositoryTaxonomySchema:
            return validate_taxonomy(data)

        raw_result = self.complete(messages=messages, validator=taxonomy_validator)
        return validate_taxonomy(raw_result)
