# =============================================================================
# FILE: his_bridge/cache.py
# MÔ TẢ: TTL Cache — tránh gọi VNPT HIS trùng lặp khi quét cùng barcode
#         trong khoảng thời gian ngắn (mặc định 5 giây).
#         Thread-safe, tự cleanup entries hết hạn.
# =============================================================================

from __future__ import annotations

import threading
import time
from typing import Any, Generic, TypeVar

T = TypeVar("T")

# Thời gian TTL mặc định (giây)
DEFAULT_TTL_SECONDS = 5


class TTLCache(Generic[T]):
    """Cache dict-based với thời gian sống (TTL) cho mỗi entry.

    Mỗi entry tự hết hạn sau ``ttl_seconds`` giây kể từ khi được set.
    Thread-safe nhờ ``threading.Lock``.

    Attributes:
        ttl_seconds: Thời gian sống của mỗi entry (giây).

    Ví dụ::

        cache: TTLCache[PatientInfo] = TTLCache(ttl_seconds=5)
        cache.set("BN00280291", patient_info)

        # Trong vòng 5 giây:
        result = cache.get("BN00280291")  # → PatientInfo

        # Sau 5 giây:
        result = cache.get("BN00280291")  # → None
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, tuple[float, T]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> T | None:
        """Lấy giá trị từ cache nếu chưa hết hạn.

        Args:
            key: Khóa tra cứu (ví dụ: mã barcode bệnh nhân).

        Returns:
            Giá trị được cache hoặc None nếu không tồn tại / đã hết hạn.
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None

            expire_at, value = entry
            if time.monotonic() > expire_at:
                # Entry đã hết hạn → xóa
                del self._store[key]
                return None

            return value

    def set(self, key: str, value: T) -> None:
        """Lưu giá trị vào cache với TTL hiện tại.

        Args:
            key: Khóa (ví dụ: mã barcode).
            value: Giá trị cần cache.
        """
        with self._lock:
            expire_at = time.monotonic() + self.ttl_seconds
            self._store[key] = (expire_at, value)

    def has(self, key: str) -> bool:
        """Kiểm tra key có tồn tại và chưa hết hạn.

        Args:
            key: Khóa cần kiểm tra.

        Returns:
            True nếu key tồn tại và còn hiệu lực.
        """
        return self.get(key) is not None

    def invalidate(self, key: str) -> None:
        """Xóa một entry khỏi cache.

        Args:
            key: Khóa cần xóa.
        """
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Xóa toàn bộ cache."""
        with self._lock:
            self._store.clear()

    def cleanup(self) -> int:
        """Xóa tất cả entries đã hết hạn.

        Returns:
            Số lượng entries đã được xóa.
        """
        with self._lock:
            now = time.monotonic()
            expired_keys = [
                k for k, (expire_at, _) in self._store.items()
                if now > expire_at
            ]
            for k in expired_keys:
                del self._store[k]
            return len(expired_keys)

    @property
    def size(self) -> int:
        """Số lượng entries hiện có (bao gồm cả đã hết hạn chưa cleanup)."""
        with self._lock:
            return len(self._store)

    def __contains__(self, key: str) -> bool:
        return self.has(key)

    def __repr__(self) -> str:
        return (
            f"TTLCache(ttl_seconds={self.ttl_seconds}, "
            f"entries={self.size})"
        )
