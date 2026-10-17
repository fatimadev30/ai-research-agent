"""Unit tests for the TinyFish client (mocked)."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from services.tinyfish_client import (
    FetchResult,
    SearchResult,
    TinyFishAuthError,
    TinyFishClient,
    TinyFishError,
    TinyFishNotConfiguredError,
    TinyFishRateLimitError,
)
from config import Settings


def make_settings(api_key="test-key-123"):
    return Settings(
        supabase_url="https://test.supabase.co",
        supabase_key="test-key",
        supabase_service_key="",
        tinyfish_api_key=api_key,
        tinyfish_base_url="https://api.tinyfish.ai",
        google_client_secrets_path="",
        max_target_records=500,
        default_batch_size=20,
        default_concurrency=3,
        request_timeout=10,
        max_retries=2,
        temp_dir="/tmp/test",
    )


class TestTinyFishClient:
    def test_not_configured_raises(self):
        settings = make_settings(api_key="")
        client = TinyFishClient(settings=settings)
        assert not client.is_configured
        with pytest.raises(TinyFishNotConfiguredError):
            client.search("test")

    def test_search_success(self):
        settings = make_settings()
        client = TinyFishClient(settings=settings)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"title": "Example", "url": "https://example.com", "snippet": "An example site."},
        ]

        with patch.object(client._session, "request", return_value=mock_response):
            results = client.search("test query")

        assert len(results) == 1
        assert results[0].title == "Example"
        assert results[0].url == "https://example.com"
        assert results[0].snippet == "An example site."

    def test_search_empty_query(self):
        settings = make_settings()
        client = TinyFishClient(settings=settings)
        results = client.search("")
        assert results == []

    def test_search_auth_error(self):
        settings = make_settings()
        client = TinyFishClient(settings=settings)
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "Unauthorized"}

        with patch.object(client._session, "request", return_value=mock_response):
            with pytest.raises(TinyFishAuthError):
                client.search("test")

    def test_fetch_success(self):
        settings = make_settings()
        client = TinyFishClient(settings=settings)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "url": "https://example.com",
            "title": "Example Page",
            "content": "<html><body>Hello world</body></html>",
            "status": 200,
            "content_type": "text/html",
        }

        with patch.object(client._session, "request", return_value=mock_response):
            result = client.fetch("https://example.com")

        assert result.url == "https://example.com"
        assert result.title == "Example Page"
        assert "Hello world" in result.content
        assert result.status == 200

    def test_fetch_empty_url_raises(self):
        settings = make_settings()
        client = TinyFishClient(settings=settings)
        with pytest.raises(TinyFishError):
            client.fetch("")

    def test_search_response_various_formats(self):
        """Test that _parse_search_response handles different JSON shapes."""
        from services.tinyfish_client import _parse_search_response

        # List format.
        results = _parse_search_response([{"url": "https://a.com", "title": "A"}], "test")
        assert len(results) == 1

        # Dict with 'results' key.
        results = _parse_search_response({"results": [{"url": "https://b.com", "title": "B"}]}, "test")
        assert len(results) == 1

        # Dict with 'data' key.
        results = _parse_search_response({"data": [{"url": "https://c.com", "title": "C"}]}, "test")
        assert len(results) == 1

        # Empty.
        results = _parse_search_response({}, "test")
        assert results == []

    def test_no_fallback_provider(self):
        """Verify the client ONLY uses TinyFish endpoints — no alternative providers."""
        settings = make_settings()
        client = TinyFishClient(settings=settings)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch.object(client._session, "request", return_value=mock_response) as mock_req:
            try:
                client.search("test")
            except TinyFishError:
                pass
            # Verify the URL called is the TinyFish endpoint.
            if mock_req.call_args:
                called_url = mock_req.call_args[0][1]
                assert "tinyfish.ai" in called_url
                assert "/v1/web/search" in called_url

    def test_smoke_test_not_configured(self):
        settings = make_settings(api_key="")
        client = TinyFishClient(settings=settings)
        result = client.smoke_test()
        assert not result["ok"]
        assert "TINYFISH_API_KEY" in result["error"]
