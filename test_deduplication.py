"""Unit tests for deduplication."""

from services.deduplication import compute_dedup_key, deduplicate_records, is_duplicate


class TestDeduplication:
    def test_same_name_same_key(self):
        r1 = {"name": "Acme AI", "website": "https://acme.ai"}
        r2 = {"name": "Acme AI", "website": "https://different.ai"}
        key1 = compute_dedup_key(r1, ["name"])
        key2 = compute_dedup_key(r2, ["name"])
        assert key1 == key2

    def test_different_name_different_key(self):
        r1 = {"name": "Acme AI"}
        r2 = {"name": "Beta Corp"}
        key1 = compute_dedup_key(r1, ["name"])
        key2 = compute_dedup_key(r2, ["name"])
        assert key1 != key2

    def test_normalization(self):
        r1 = {"name": "  Acme  AI  "}
        r2 = {"name": "acme ai"}
        key1 = compute_dedup_key(r1, ["name"])
        key2 = compute_dedup_key(r2, ["name"])
        assert key1 == key2

    def test_is_duplicate(self):
        seen = {"abc123"}
        assert is_duplicate("abc123", seen)
        assert not is_duplicate("xyz", seen)

    def test_deduplicate_records(self):
        records = [
            {"fields": {"name": "Acme AI"}, "dedup_key": None},
            {"fields": {"name": "Acme AI"}, "dedup_key": None},
            {"fields": {"name": "Beta Corp"}, "dedup_key": None},
        ]
        unique, dup_count = deduplicate_records(records, ["name"])
        assert len(unique) == 2
        assert dup_count == 1

    def test_fallback_dedup_key(self):
        """When dedup key fields are missing, fall back to hashing all values."""
        r = {"website": "https://acme.ai", "city": "Karachi"}
        key = compute_dedup_key(r, ["name"])  # 'name' not in fields.
        assert key  # Should still produce a key.
