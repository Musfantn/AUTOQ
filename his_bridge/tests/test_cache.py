# =============================================================================
# FILE: his_bridge/tests/test_cache.py
# MÔ TẢ: Unit tests cho TTLCache.
# =============================================================================

import time

import pytest
from his_bridge.cache import TTLCache


class TestTTLCache:
    """Tests cho TTLCache."""

    def test_set_and_get(self) -> None:
        """set() lưu giá trị, get() trả về đúng."""
        cache: TTLCache[str] = TTLCache(ttl_seconds=10)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self) -> None:
        """get() trả về None cho key không tồn tại."""
        cache: TTLCache[str] = TTLCache(ttl_seconds=10)
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self) -> None:
        """Entry hết hạn sau TTL — get() trả về None."""
        cache: TTLCache[str] = TTLCache(ttl_seconds=1)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        time.sleep(1.1)  # Chờ hết TTL
        assert cache.get("key1") is None

    def test_has_existing_key(self) -> None:
        """has() trả về True cho key còn hiệu lực."""
        cache: TTLCache[int] = TTLCache(ttl_seconds=10)
        cache.set("a", 42)
        assert cache.has("a") is True

    def test_has_expired_key(self) -> None:
        """has() trả về False cho key đã hết hạn."""
        cache: TTLCache[int] = TTLCache(ttl_seconds=1)
        cache.set("a", 42)
        time.sleep(1.1)
        assert cache.has("a") is False

    def test_contains_operator(self) -> None:
        """Toán tử 'in' hoạt động đúng."""
        cache: TTLCache[str] = TTLCache(ttl_seconds=10)
        cache.set("x", "y")
        assert "x" in cache
        assert "z" not in cache

    def test_invalidate(self) -> None:
        """invalidate() xóa entry cụ thể."""
        cache: TTLCache[str] = TTLCache(ttl_seconds=10)
        cache.set("key1", "value1")
        cache.invalidate("key1")
        assert cache.get("key1") is None

    def test_clear(self) -> None:
        """clear() xóa toàn bộ cache."""
        cache: TTLCache[str] = TTLCache(ttl_seconds=10)
        cache.set("a", "1")
        cache.set("b", "2")
        cache.set("c", "3")
        cache.clear()
        assert cache.size == 0
        assert cache.get("a") is None

    def test_cleanup_expired(self) -> None:
        """cleanup() xóa entries hết hạn và trả về số lượng."""
        cache: TTLCache[str] = TTLCache(ttl_seconds=1)
        cache.set("a", "1")
        cache.set("b", "2")

        time.sleep(1.1)

        # Thêm entry mới (chưa hết hạn)
        cache.set("c", "3")

        removed = cache.cleanup()
        assert removed == 2
        assert cache.get("c") == "3"

    def test_size(self) -> None:
        """size trả về số lượng entries hiện tại."""
        cache: TTLCache[str] = TTLCache(ttl_seconds=10)
        assert cache.size == 0
        cache.set("a", "1")
        assert cache.size == 1
        cache.set("b", "2")
        assert cache.size == 2

    def test_overwrite_existing_key(self) -> None:
        """set() cùng key ghi đè giá trị cũ và reset TTL."""
        cache: TTLCache[str] = TTLCache(ttl_seconds=10)
        cache.set("key1", "old")
        cache.set("key1", "new")
        assert cache.get("key1") == "new"
        assert cache.size == 1

    def test_repr(self) -> None:
        """__repr__ hiển thị thông tin hữu ích."""
        cache: TTLCache[str] = TTLCache(ttl_seconds=5)
        assert "TTLCache" in repr(cache)
        assert "ttl_seconds=5" in repr(cache)

    def test_different_types(self) -> None:
        """Cache hỗ trợ nhiều kiểu dữ liệu."""
        cache_dict: TTLCache[dict] = TTLCache(ttl_seconds=10)
        cache_dict.set("data", {"name": "test", "value": 123})
        result = cache_dict.get("data")
        assert result is not None
        assert result["name"] == "test"
