"""TinyFish web search and fetch client.

Uses ONLY the official TinyFish API:
  - tinyfish.web.search  → POST /v1/web/search
  - tinyfish.web.fetch   → POST /v1/web/fetch

No alternative providers, no fallback scraping, no paid search engines.
If TinyFish fails, the error is reported — never silently substituted.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from config import Settings, get_settings

logger = logging.getLogger(__name__)

SEARCH_ENDPOINT = "/v1/web/search"
FETCH_ENDPOINT = "/v1/web/fetch"


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = "tinyfish"


@dataclass
class FetchResult:
    url: str
    status: int
    title: str
    content: str
    content_type: str
    error: str = ""


class TinyFishError(Exception):
    """Base error for TinyFish API failures."""


class TinyFishAuthError(TinyFishError):
    """Authentication failure (401/403)."""


class TinyFishRateLimitError(TinyFishError):
    """Rate limit hit (429)."""


class TinyFishNotConfiguredError(TinyFishError):
    """No API key configured."""


class TinyFishClient:
    """Thin client wrapping the TinyFish search and fetch endpoints."""

    def __init__(self, settings: Settings | None = None, session: requests.Session | None = None):
        self.settings = settings or get_settings()
        self._session = session or requests.Session()

    @property
    def is_configured(self) -> bool:
        return self.settings.has_tinyfish

    def _headers(self) -> dict[str, str]:
        if not self.is_configured:
            raise TinyFishNotConfiguredError(
                "TinyFish API key is not configured. Set TINYFISH_API_KEY in your .env or Streamlit secrets."
            )
        return {
            "Authorization": f"Bearer {self.settings.tinyfish_api_key}",
            "Content-Type": "application/json",
        }

    def _request_with_retry(self, method: str, url: str, json: dict, max_retries: int | None = None) -> requests.Response:
        retries = max_retries if max_retries is not None else self.settings.max_retries
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = self._session.request(
                    method,
                    url,
                    json=json,
                    headers=self._headers(),
                    timeout=self.settings.request_timeout,
                )
                if resp.status_code == 401 or resp.status_code == 403:
                    raise TinyFishAuthError(f"Authentication failed ({resp.status_code}). Check your TINYFISH_API_KEY.")
                if resp.status_code == 429:
                    backoff = min(2 ** attempt, 16)
                    logger.warning("TinyFish rate limited, backing off %ds (attempt %d/%d)", backoff, attempt + 1, retries)
                    time.sleep(backoff)
                    last_exc = TinyFishRateLimitError("Rate limit exceeded.")
                    continue
                if resp.status_code >= 500:
                    backoff = min(2 ** attempt, 16)
                    logger.warning("TinyFish server error %d, retrying in %ds", resp.status_code, backoff)
                    time.sleep(backoff)
                    last_exc = TinyFishError(f"Server error {resp.status_code}")
                    continue
                return resp
            except (requests.Timeout, requests.ConnectionError) as exc:
                backoff = min(2 ** attempt, 16)
                logger.warning("TinyFish request failed (%s), retrying in %ds", exc, backoff)
                time.sleep(backoff)
                last_exc = exc
                continue
        raise TinyFishError(f"Request failed after {retries} retries: {last_exc}")

    # -- tinyfish.web.search ------------------------------------------------

    def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        """Execute a web search via TinyFish. Returns a list of SearchResult."""
        if not query.strip():
            return []
        url = f"{self.settings.tinyfish_base_url}{SEARCH_ENDPOINT}"
        payload = {"query": query, "num_results": min(num_results, 20)}
        resp = self._request_with_retry("POST", url, payload)
        body = resp.json()
        return _parse_search_response(body, query)

    # -- tinyfish.web.fetch -------------------------------------------------

    def fetch(self, url: str) -> FetchResult:
        """Fetch a single web page via TinyFish. Returns FetchResult with content."""
        if not url.strip():
            raise TinyFishError("Cannot fetch an empty URL.")
        endpoint = f"{self.settings.tinyfish_base_url}{FETCH_ENDPOINT}"
        payload = {"url": url}
        resp = self._request_with_retry("POST", endpoint, payload)
        body = resp.json()
        return _parse_fetch_response(body, url)

    # -- Smoke test ---------------------------------------------------------

    def smoke_test(self) -> dict[str, Any]:
        """Run a quick connectivity + auth test. Returns a status dict."""
        if not self.is_configured:
            return {"ok": False, "error": "TINYFISH_API_KEY is not set."}
        try:
            results = self.search("example.com", num_results=1)
            if not results:
                return {"ok": False, "error": "Search returned no results (check key validity)."}
            fetch = self.fetch(results[0].url)
            return {
                "ok": True,
                "search_results": len(results),
                "fetched_url": fetch.url,
                "fetched_title": fetch.title,
                "content_length": len(fetch.content),
            }
        except TinyFishError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"Unexpected error: {exc}"}


# ---------------------------------------------------------------------------
# Response parsing — validates the shape returned by TinyFish.
# ---------------------------------------------------------------------------

def _parse_search_response(body: Any, query: str) -> list[SearchResult]:
    """Parse and validate a TinyFish search response.

    Accepts both a top-level list and an object with 'results'.
    """
    items: list[dict] = []
    if isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        items = body.get("results") or body.get("data") or []
        if isinstance(items, dict):
            items = items.get("results", [])
    if not isinstance(items, list):
        raise TinyFishError(f"Unexpected search response format for query '{query}': {type(body)}")

    results: list[SearchResult] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("link") or ""
        title = item.get("title") or item.get("name") or ""
        snippet = item.get("snippet") or item.get("description") or item.get("summary") or ""
        if url:
            results.append(SearchResult(title=title, url=url, snippet=snippet))
    return results


def _parse_fetch_response(body: Any, url: str) -> FetchResult:
    """Parse and validate a TinyFish fetch response."""
    if not isinstance(body, dict):
        raise TinyFishError(f"Unexpected fetch response format for {url}: {type(body)}")

    content = body.get("content") or body.get("text") or body.get("html") or ""
    title = body.get("title") or ""
    status = body.get("status") or body.get("status_code") or 200
    content_type = body.get("content_type") or body.get("mime_type") or "text/html"
    error = body.get("error") or ""

    if not content and error:
        return FetchResult(url=url, status=int(status) if status else 0, title=title, content="", content_type=content_type, error=error)

    return FetchResult(
        url=url,
        status=int(status) if status else 200,
        title=title,
        content=content,
        content_type=content_type,
        error=error,
    )
