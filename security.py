"""Security and URL validation utilities.

Protects against SSRF, malicious content, and formula injection.
"""

from __future__ import annotations

import ipaddress
import re
import urllib.parse
from dataclasses import dataclass

BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",  # AWS / GCP metadata
    "metadata",
    "0.0.0.0",
}

BLOCKED_CIDRS = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "127.0.0.0/8",
    "0.0.0.0/8",
    "fd00::/8",  # IPv6 private
    "::1/128",
]

ALLOWED_SCHEMES = {"http", "https"}


@dataclass
class ValidationResult:
    is_valid: bool
    error: str = ""


def validate_url(raw_url: str) -> ValidationResult:
    """Validate that a URL is safe to fetch (SSRF protection)."""
    if not raw_url or not isinstance(raw_url, str):
        return ValidationResult(False, "URL is empty.")

    try:
        parsed = urllib.parse.urlparse(raw_url.strip())
    except Exception as exc:
        return ValidationResult(False, f"Invalid URL format: {exc}")

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return ValidationResult(False, f"URL scheme '{parsed.scheme}' is not allowed. Only http/https are permitted.")

    hostname = parsed.hostname
    if not hostname:
        return ValidationResult(False, "URL has no hostname.")

    if hostname.lower() in BLOCKED_HOSTS:
        return ValidationResult(False, f"Host '{hostname}' is blocked (internal/metadata endpoint).")

    # Resolve and check IP literals.
    try:
        ip = ipaddress.ip_address(hostname)
        if _is_blocked_ip(ip):
            return ValidationResult(False, f"IP address {ip} is in a blocked private/reserved range.")
    except ValueError:
        pass  # hostname is a domain, not an IP literal — allowed.

    return ValidationResult(True)


def _is_blocked_ip(ip: ipaddress) -> bool:
    for cidr in BLOCKED_CIDRS:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            if ip in network:
                return True
        except ValueError:
            continue
    return False


def sanitize_cell_value(value: str) -> str:
    """Sanitize a string before placing it in a spreadsheet cell.

    Prevents formula injection by prefixing dangerous leading characters.
    """
    if not isinstance(value, str):
        return str(value)
    stripped = value.lstrip()
    if stripped and stripped[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{value}"
    return value


def strip_html_instructions(text: str) -> str:
    """Remove content that looks like injected instructions inside fetched HTML.

    This is a basic guard. The real protection is treating all fetched content
    as data and never executing it.
    """
    if not text:
        return text
    # Remove common prompt-injection patterns from text.
    patterns = [
        r"(?i)ignore (all )?previous instructions.*?(?=\n|$|\.)",
        r"(?i)disregard the (above|following|system) (rules|instructions|prompt).*?(?=\n|$|\.)",
        r"(?i)you are now (a|an) \w+.*?(?=\n|$|\.)",
        r"(?i)act as (if )?(you are )?(a|an) \w+.*?(?=\n|$|\.)",
        r"(?i)reveal (your |the )?(secret|system prompt|instructions|api key)?.*?(?=\n|$|\.)",
        r"(?i)output (your |the )?(api key|secret|token|password).*?(?=\n|$|\.)",
        r"(?i)system prompt[: ].*?(?=\n|$)",
    ]
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, "[filtered]", cleaned)
    return cleaned
