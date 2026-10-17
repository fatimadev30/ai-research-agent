"""Research planner — converts a natural-language prompt into a structured job plan.

Uses lightweight heuristic parsing (no LLM dependency required). For more complex
prompts the user can edit the generated plan in the UI before starting the job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

DEFAULT_FIELDS = ["name", "website", "description", "source_url"]

FIELD_HINTS: dict[str, list[str]] = {
    "name": ["name", "company name", "person name", "title"],
    "website": ["website", "url", "official site", "homepage"],
    "email": ["email", "contact email", "email address"],
    "phone": ["phone", "phone number", "contact number", "telephone"],
    "city": ["city", "location", "town"],
    "country": ["country", "region", "nation"],
    "services": ["services", "products", "offerings", "categories"],
    "industry": ["industry", "sector", "field"],
    "department": ["department", "faculty", "school"],
    "university": ["university", "institution", "college", "organization"],
    "linkedin_url": ["linkedin", "linkedin url", "linkedin profile"],
    "research_interests": ["research interests", "research areas", "expertise", "focus"],
    "publications": ["publications", "papers", "articles", "research"],
    "profile_url": ["profile", "profile url", "official profile", "page"],
    "address": ["address", "location", "street"],
    "description": ["description", "about", "summary", "overview"],
    "source_url": ["source url", "source", "evidence url", "reference"],
}

COUNT_PATTERN = re.compile(r"\b(\d{1,4})\b")
GEOGRAPHY_HINTS = re.compile(
    r"\b(in|from|across|based in|located in)\s+([A-Z][a-zA-Z\s,]+?)(?:\.|,|;|:|$|collecting|collect|find|search)",
    re.IGNORECASE,
)


@dataclass
class ResearchPlan:
    prompt: str
    objective: str
    search_queries: list[str]
    fields: list[str]
    target_count: int
    batch_size: int
    max_concurrency: int
    inclusion_rules: list[str]
    exclusion_rules: list[str]
    dedup_keys: list[str]
    geography: str
    export_format: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "objective": self.objective,
            "search_queries": self.search_queries,
            "fields": self.fields,
            "target_count": self.target_count,
            "batch_size": self.batch_size,
            "max_concurrency": self.max_concurrency,
            "inclusion_rules": self.inclusion_rules,
            "exclusion_rules": self.exclusion_rules,
            "dedup_keys": self.dedup_keys,
            "geography": self.geography,
            "export_format": self.export_format,
        }


def parse_prompt(
    prompt: str,
    *,
    target_count: int | None = None,
    batch_size: int = 20,
    max_concurrency: int = 3,
    export_format: str = "xlsx",
) -> ResearchPlan:
    """Parse a natural-language prompt into a structured ResearchPlan."""
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("Prompt cannot be empty.")

    count = target_count or _extract_count(prompt)
    fields = _extract_fields(prompt)
    geography = _extract_geography(prompt)
    queries = _generate_queries(prompt, geography, fields)
    dedup_keys = _guess_dedup_keys(fields)
    inclusion, exclusion = _extract_rules(prompt)

    return ResearchPlan(
        prompt=prompt,
        objective=_extract_objective(prompt),
        search_queries=queries,
        fields=fields,
        target_count=min(count, 500),
        batch_size=min(batch_size, 50),
        max_concurrency=min(max_concurrency, 10),
        inclusion_rules=inclusion,
        exclusion_rules=exclusion,
        dedup_keys=dedup_keys,
        geography=geography,
        export_format=export_format,
    )


# ---------------------------------------------------------------------------
# Heuristic extraction helpers
# ---------------------------------------------------------------------------

def _extract_count(prompt: str) -> int:
    match = COUNT_PATTERN.search(prompt)
    if match:
        n = int(match.group(1))
        if n >= 1:
            return min(n, 500)
    return 50


def _extract_fields(prompt: str) -> list[str]:
    prompt_lower = prompt.lower()
    found: list[str] = []
    for field_name, hints in FIELD_HINTS.items():
        for hint in hints:
            if hint in prompt_lower:
                if field_name not in found:
                    found.append(field_name)
                break
    if not found:
        found = list(DEFAULT_FIELDS)
    if "source_url" not in found:
        found.append("source_url")
    return found


def _extract_geography(prompt: str) -> str:
    match = GEOGRAPHY_HINTS.search(prompt)
    if match:
        geo = match.group(2).strip().rstrip(",.")
        return geo
    return ""


def _extract_objective(prompt: str) -> str:
    sentence = prompt.split(".")[0].strip()
    return sentence[:300] if sentence else prompt[:300]


def _extract_rules(prompt: str) -> tuple[list[str], list[str]]:
    inclusion: list[str] = []
    exclusion: list[str] = []
    lower = prompt.lower()
    # "excluding X" / "exclude X"
    for pattern in [r"excluding (.+?)(?:\.|,|;|$)", r"exclude (.+?)(?:\.|,|;|$)"]:
        for m in re.finditer(pattern, lower):
            exclusion.append(m.group(1).strip())
    # "only X" / "including X"
    for pattern in [r"only (.+?)(?:\.|,|;|$)", r"including (.+?)(?:\.|,|;|$)"]:
        for m in re.finditer(pattern, lower):
            inclusion.append(m.group(1).strip())
    return inclusion, exclusion


def _generate_queries(prompt: str, geography: str, fields: list[str]) -> list[str]:
    """Generate 3-5 varied search queries from the prompt."""
    subject = _extract_subject(prompt)
    queries: list[str] = []
    base = subject
    if geography:
        queries.append(f"{base} in {geography}")
        queries.append(f'list of {base} {geography}')
    else:
        queries.append(f"list of {base}")
        queries.append(f"top {base}")
    # Field-specific queries
    if "email" in fields or "contact" in str(fields):
        queries.append(f"{base} contact email {geography}".strip())
    if "linkedin_url" in fields:
        queries.append(f"{base} linkedin {geography}".strip())
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        q_clean = " ".join(q.split())
        if q_clean and q_clean not in seen:
            seen.add(q_clean)
            unique.append(q_clean)
    return unique[:5]


def _extract_subject(prompt: str) -> str:
    """Heuristically extract the core subject (what to find)."""
    lower = prompt.lower()
    for verb in ["find", "collect", "search for", "gather", "lookup", "identify"]:
        idx = lower.find(verb)
        if idx >= 0:
            after = prompt[idx + len(verb):].strip()
            # Take up to a number or "in"
            cut = re.split(r"\b(\d+)\b|\bin\b|\bfrom\b|\blocated\b|\bbased\b", after, maxsplit=1)
            subject = cut[0].strip().rstrip(",.")
            if subject:
                return subject
    return prompt[:60].strip().rstrip(".,")


def _guess_dedup_keys(fields: list[str]) -> list[str]:
    for key in ["name", "website", "profile_url", "email"]:
        if key in fields:
            return [key]
    return ["name"]
