"""
scripts/schema.py
Complete Pydantic schema specification for the GitHub Intelligence Engine 6-Pillar Taxonomy.
Enforces closed-domain validation for 15 Macro Domains and 8 Functional Archetypes,
along with strict constraints on use cases, problem solved, target audience, and confidence score.
"""

from typing import List, Literal, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator, ValidationError
import re
import json

# Pillar 1: Macro Domain (Strict 15-Item Closed Enum)
MACRO_DOMAINS = (
    "AI & Machine Learning",
    "Developer Tooling",
    "Infrastructure & DevOps",
    "Databases & Storage",
    "Web Frontend",
    "Web Backend & API",
    "Cybersecurity & Privacy",
    "Systems & OS Programming",
    "Mobile & Embedded",
    "Data Engineering",
    "Networking & Protocols",
    "Programming Languages & Compilers",
    "Curated Lists & Awesome Resources",
    "Books & Educational Materials",
    "Desktop & Consumer Apps",
)

MacroDomainType = Literal[
    "AI & Machine Learning",
    "Developer Tooling",
    "Infrastructure & DevOps",
    "Databases & Storage",
    "Web Frontend",
    "Web Backend & API",
    "Cybersecurity & Privacy",
    "Systems & OS Programming",
    "Mobile & Embedded",
    "Data Engineering",
    "Networking & Protocols",
    "Programming Languages & Compilers",
    "Curated Lists & Awesome Resources",
    "Books & Educational Materials",
    "Desktop & Consumer Apps",
]

# Pillar 3: Functional Archetype (Strict 8-Item Closed Enum)
ARCHETYPES = (
    "Runnable Server / Engine",
    "CLI Tool / Binary",
    "Library / SDK",
    "Framework / Fullstack Platform",
    "Curated Resource / Awesome List",
    "Book / Course / Tutorial",
    "Starter Template / Boilerplate",
    "Browser Extension / Desktop Plugin",
)

ArchetypeType = Literal[
    "Runnable Server / Engine",
    "CLI Tool / Binary",
    "Library / SDK",
    "Framework / Fullstack Platform",
    "Curated Resource / Awesome List",
    "Book / Course / Tutorial",
    "Starter Template / Boilerplate",
    "Browser Extension / Desktop Plugin",
]


class TaxonomyValidationError(ValueError):
    """Custom error raised when repository taxonomy fails domain, archetype, or syntax constraints."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class RepositoryTaxonomySchema(BaseModel):
    """
    Pydantic schema enforcing the 6-Pillar Closed Categorization Taxonomy.
    Prevents hallucinated categories, malformed tags, or ungrounded classifications.
    """
    macro_domain: MacroDomainType = Field(
        ...,
        description="Strict high-level domain from the 15 closed categories."
    )
    sub_domain: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Precise technical sub-field (e.g., 'LLM Inference Engines', 'Container Orchestration')."
    )
    archetype: ArchetypeType = Field(
        ...,
        description="Strict operational form factor from the 8 closed archetypes."
    )
    problem_solved: str = Field(
        ...,
        min_length=15,
        max_length=600,
        description="1-2 sentences stating the concrete engineering problem solved and mechanism."
    )
    use_cases: List[str] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="Exactly 3 to 5 standardized use-case tags following [Verb-Noun] format (e.g., 'Distributed-Caching')."
    )
    primary_ecosystem: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Main language or runtime environment (e.g. 'Python / PyTorch', 'Rust / Native', 'Go / Cloud Native')."
    )
    target_audience: List[str] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="Target developer personas (1 to 3 items, e.g. ['Backend Engineers', 'SRE Teams'])."
    )
    confidence_score: int = Field(
        ...,
        ge=1,
        le=100,
        description="Model self-assessed confidence score between 1 and 100."
    )

    @field_validator("macro_domain")
    @classmethod
    def validate_macro_domain(cls, v: str) -> str:
        if v not in MACRO_DOMAINS:
            raise ValueError(
                f"Invalid macro_domain '{v}'. Must be exactly one of the 15 closed domains: {list(MACRO_DOMAINS)}"
            )
        return v

    @field_validator("archetype")
    @classmethod
    def validate_archetype(cls, v: str) -> str:
        if v not in ARCHETYPES:
            raise ValueError(
                f"Invalid archetype '{v}'. Must be exactly one of the 8 closed archetypes: {list(ARCHETYPES)}"
            )
        return v

    @field_validator("sub_domain")
    @classmethod
    def validate_sub_domain(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("sub_domain must not be empty or whitespace.")
        return cleaned

    @field_validator("problem_solved")
    @classmethod
    def validate_problem_solved(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 15:
            raise ValueError("problem_solved must be at least 15 characters long (1-2 sentences).")
        return cleaned

    @field_validator("use_cases")
    @classmethod
    def validate_use_cases(cls, v: List[str]) -> List[str]:
        if not (3 <= len(v) <= 5):
            raise ValueError(f"use_cases must contain between 3 and 5 items, got {len(v)}.")
        cleaned_tags = []
        for tag in v:
            tag_clean = tag.strip()
            if not tag_clean:
                raise ValueError("use_case tag cannot be empty.")
            # Verb-Noun format: check that tag has at least two tokens separated by hyphen or space
            parts = re.split(r"[\s\-_/]+", tag_clean)
            if len(parts) < 2 or any(len(p) == 0 for p in parts):
                raise ValueError(
                    f"Use-case tag '{tag_clean}' does not conform to [Verb-Noun] format. "
                    f"Examples: 'Distributed-Caching', 'Distributed Caching', 'Packet-Sniffing'."
                )
            cleaned_tags.append(tag_clean)
        return cleaned_tags

    @field_validator("target_audience")
    @classmethod
    def validate_target_audience(cls, v: List[str]) -> List[str]:
        if not (1 <= len(v) <= 3):
            raise ValueError(f"target_audience must contain between 1 and 3 developer personas, got {len(v)}.")
        cleaned = [item.strip() for item in v if item.strip()]
        if len(cleaned) != len(v):
            raise ValueError("target_audience items cannot be blank.")
        return cleaned


def validate_taxonomy(data: Any) -> RepositoryTaxonomySchema:
    """
    Validates dictionary or JSON string against RepositoryTaxonomySchema with custom error diagnostics.
    """
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            raise TaxonomyValidationError(f"Invalid JSON provided to validate_taxonomy: {e}", {"raw": data})

    if not isinstance(data, dict):
        raise TaxonomyValidationError(f"Expected dict or JSON string, got {type(data).__name__}")

    try:
        return RepositoryTaxonomySchema.model_validate(data)
    except ValidationError as err:
        errors = err.errors()
        error_msgs = [f"{e.get('loc')}: {e.get('msg')} (type={e.get('type')})" for e in errors]
        raise TaxonomyValidationError(
            f"Taxonomy validation failed with {len(errors)} error(s): " + "; ".join(error_msgs),
            {"validation_errors": errors, "input_data": data}
        ) from err


def get_taxonomy_prompt_instructions() -> str:
    """
    Returns concise, strict schema instructions to inject into LLM system prompts.
    """
    domains_str = "\n".join(f"  - \"{d}\"" for d in MACRO_DOMAINS)
    archetypes_str = "\n".join(f"  - \"{a}\"" for a in ARCHETYPES)
    return f"""You are an elite software classification engine. Classify the repository into this strict closed schema.

CLOSED MACRO DOMAINS (must match one exactly):
{domains_str}

CLOSED ARCHETYPES (must match one exactly):
{archetypes_str}

RULES:
1. `macro_domain`: MUST be one of the 15 exact domains above. Never invent domains.
2. `sub_domain`: Specific technical sub-category (e.g. 'LLM Inference Engines', 'Container Orchestration').
3. `archetype`: MUST be one of the 8 exact archetypes above. Never invent archetypes.
4. `problem_solved`: 1-2 objective, technical sentences: '[Verb phrase stating core bottleneck] + by [Technical implementation mechanism]'. No marketing hype.
5. `use_cases`: Array of 3 to 5 tags in strict [Verb-Noun] format (e.g. ['Distributed-Caching', 'State-Synchronization', 'Query-Optimization']).
6. `primary_ecosystem`: Main language or runtime (e.g. 'Python / PyTorch', 'Rust / Native', 'Go / Cloud Native').
7. `target_audience`: Array of 1 to 3 developer personas (e.g. ['Backend Engineers', 'Platform / SRE Teams']).
8. `confidence_score`: Integer between 1 and 100 assessing model confidence.

Respond ONLY with valid JSON conforming to the schema.
"""
