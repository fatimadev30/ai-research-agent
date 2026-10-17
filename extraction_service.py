"""Extraction service — extracts structured fields from fetched page content.

Uses regex-based and HTML-structure-based heuristics. No LLM dependency required.
All extracted values are grounded in the fetched content — nothing is fabricated.
"""

from __future__ import annotations

import re
from typing import Any

from utils.security import strip_html_instructions

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
URL_PATTERN = re.compile(r'https?://[^\s<>"\')]+')
LINKEDIN_PATTERN = re.compile(r'https?://(?:www\.)?linkedin\.com/[^\s<>"\')]+', re.IGNORECASE)
PHONE_PATTERN = re.compile(r'(?:\+?\d[\d\s\-\(\)]{7,}\d)')
TITLE_TAG_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
H1_PATTERN = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
META_DESC_PATTERN = re.compile(r'<meta[^>]+(?:name|property)=["\']description["\'][^>]+content=["\'](.*?)["\']', re.IGNORECASE)
META_OG_TITLE_PATTERN = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', re.IGNORECASE)
TAG_STRIP_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")

MAX_FIELD_LENGTH = 2000


def extract_fields(content: str, url: str, field_names: list[str]) -> dict[str, Any]:
    """Extract the requested fields from the fetched page content.

    Returns a dict mapping field names to extracted values. Missing fields
    are explicitly set to None — never fabricated.
    """
    if not content:
        return {f: None for f in field_names} | {"source_url": url}

    # Sanitize content of injected instructions.
    safe_content = strip_html_instructions(content)
    text = _html_to_text(safe_content)
    title = _extract_title(safe_content)

    result: dict[str, Any] = {}

    for field in field_names:
        result[field] = _extract_single_field(field, safe_content, text, url, title)

    result["source_url"] = url
    if "page_title" not in result:
        result["page_title"] = title

    return result


def _extract_single_field(field: str, html: str, text: str, url: str, title: str) -> Any:
    field_lower = field.lower()

    if field_lower in ("source_url", "evidence_url", "reference_url"):
        return url
    if field_lower in ("page_title", "title"):
        return title
    if field_lower == "name":
        return title or _guess_name(text, url)
    if field_lower in ("website", "url", "homepage", "official_site"):
        return _find_website(html, url)
    if field_lower in ("email", "contact_email", "email_address"):
        return _find_email(text)
    if field_lower in ("phone", "phone_number", "contact_number", "telephone"):
        return _find_phone(text)
    if field_lower in ("linkedin_url", "linkedin", "linkedin_profile"):
        return _find_linkedin(html)
    if field_lower in ("profile_url", "profile", "official_profile"):
        return url
    if field_lower == "city":
        return _find_by_label(text, ["city", "location", "based in", "located in"])
    if field_lower == "country":
        return _find_by_label(text, ["country", "region", "nation"])
    if field_lower in ("services", "products", "offerings"):
        return _find_by_label(text, ["services", "products", "offerings", "we offer"])
    if field_lower in ("industry", "sector"):
        return _find_by_label(text, ["industry", "sector", "field"])
    if field_lower in ("department", "faculty"):
        return _find_by_label(text, ["department", "faculty", "school of"])
    if field_lower in ("university", "institution", "organization"):
        return _find_by_label(text, ["university", "institute", "college", "organization"])
    if field_lower in ("research_interests", "research_areas", "expertise"):
        return _find_by_label(text, ["research interests", "research areas", "expertise", "focus"])
    if field_lower in ("publications", "papers"):
        return _find_by_label(text, ["publications", "papers", "selected works"])
    if field_lower in ("address", "location"):
        return _find_by_label(text, ["address", "location", "office"])
    if field_lower in ("description", "about", "summary", "overview"):
        return _extract_description(html, text)

    # Generic fallback: search for a labeled value.
    return _find_by_label(text, [field_lower.replace("_", " ")])


# ---------------------------------------------------------------------------
# Individual extractors
# ---------------------------------------------------------------------------

def _find_email(text: str) -> str | None:
    match = EMAIL_PATTERN.search(text)
    if match:
        email = match.group(0).lower()
        # Filter out common false positives.
        if any(skip in email for skip in [".png", ".jpg", ".gif", "@example.", "@sentry", "@wixpress"]):
            return None
        return email
    return None


def _find_phone(text: str) -> str | None:
    match = PHONE_PATTERN.search(text)
    if match:
        phone = match.group(0).strip()
        if len(phone) >= 8:
            return phone
    return None


def _find_linkedin(html: str) -> str | None:
    match = LINKEDIN_PATTERN.search(html)
    if match:
        return match.group(0).rstrip(".,;)")
    return None


def _find_website(html: str, current_url: str) -> str | None:
    for match in URL_PATTERN.finditer(html):
        found = match.group(0).rstrip(".,;)")
        if "linkedin.com" in found:
            continue
        if found == current_url:
            continue
        if any(skip in found for skip in ["facebook.com", "twitter.com", "x.com", "instagram.com"]):
            continue
        return found
    return current_url


def _find_by_label(text: str, labels: list[str]) -> str | None:
    for label in labels:
        pattern = re.compile(
            rf"(?:{re.escape(label)})\s*[:\-]\s*(.{{0,200}}?)(?:\n|$|\.|;|,)",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if match:
            value = match.group(1).strip().rstrip(".,;")
            if value and len(value) > 1:
                return value[:MAX_FIELD_LENGTH]
    return None


def _extract_description(html: str, text: str) -> str | None:
    for pattern in [META_DESC_PATTERN, META_OG_TITLE_PATTERN]:
        match = pattern.search(html)
        if match:
            desc = _clean_text(match.group(1))
            if desc:
                return desc[:MAX_FIELD_LENGTH]
    # First meaningful paragraph.
    paragraphs = [p.strip() for p in text.split("\n") if len(p.strip()) > 50]
    if paragraphs:
        return paragraphs[0][:MAX_FIELD_LENGTH]
    return None


def _extract_title(html: str) -> str:
    for pattern in [META_OG_TITLE_PATTERN, TITLE_TAG_PATTERN, H1_PATTERN]:
        match = pattern.search(html)
        if match:
            title = _clean_text(match.group(1))
            if title:
                return title[:200]
    return ""


def _guess_name(text: str, url: str) -> str | None:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:10]:
        if 3 < len(line) < 100 and not line.startswith(("http", "@", "Copyright", "All rights")):
            return line[:100]
    # Fallback: domain name.
    try:
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
        return host.replace("www.", "").split(".")[0].capitalize() or None
    except Exception:
        return None


def _html_to_text(html: str) -> str:
    # Remove script/style blocks entirely.
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL)
    # Replace block tags with newlines.
    html = re.sub(r"<(br|p|div|li|h[1-6]|tr)[^>]*>", "\n", html, flags=re.IGNORECASE)
    text = TAG_STRIP_PATTERN.sub(" ", html)
    text = WHITESPACE_PATTERN.sub(" ", text)
    # Re-add newlines for readability.
    text = text.replace(" . ", ".\n")
    return _clean_text(text)


def _clean_text(text: str) -> str:
    text = WHITESPACE_PATTERN.sub(" ", text).strip()
    return text
