"""Live TinyFish integration smoke test.

This test is SKIPPED by default. To run it, set TINYFISH_API_KEY in your
environment and run with: pytest tests/test_smoke_live.py -s --no-header

This performs a REAL search and fetch against the TinyFish API.
"""

import os

import pytest

from services.tinyfish_client import TinyFishClient


@pytest.mark.skipif(
    not os.environ.get("TINYFISH_API_KEY"),
    reason="TINYFISH_API_KEY not set — skipping live integration test.",
)
class TestLiveSmoke:
    """Live integration tests. Only run when TINYFISH_API_KEY is configured."""

    def test_credentials_configured(self):
        client = TinyFishClient()
        assert client.is_configured, "TINYFISH_API_KEY must be set for live tests."

    def test_live_search(self):
        client = TinyFishClient()
        results = client.search("python programming language", num_results=3)
        assert len(results) > 0, "Live search should return results."
        assert results[0].url, "Search results should have URLs."

    def test_live_fetch(self):
        client = TinyFishClient()
        results = client.search("python programming language", num_results=1)
        if results:
            fetch_result = client.fetch(results[0].url)
            assert fetch_result.content, "Fetched page should have content."
            assert len(fetch_result.content) > 100, "Content should be non-trivial."

    def test_smoke_test_method(self):
        client = TinyFishClient()
        result = client.smoke_test()
        assert result["ok"], f"Smoke test failed: {result.get('error', 'unknown')}"
        assert result["search_results"] > 0
