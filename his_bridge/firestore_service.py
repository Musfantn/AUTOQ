# =============================================================================
# FILE: his_bridge/firestore_service.py
# MÔ TẢ: Async Firestore publisher cho HIS Bridge.
#         Push dữ liệu bệnh nhân lên Firestore.
#         Retry + local queue fallback khi mạng lỗi.
#         Auto-sync pending queue khi mạng phục hồi.
# =============================================================================

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from his_bridge.config import HisConfig
from his_bridge.logger import get_logger, log_timing
from his_bridge.models import PatientInfo

# Đường dẫn lưu pending queue khi Firestore không khả dụng
_PENDING_QUEUE_DIR = Path(__file__).parent / "queue"
_PENDING_QUEUE_FILE = _PENDING_QUEUE_DIR / "pending.json"


class FirestorePublishError(Exception):
    """Lỗi khi publish lên Firestore thất bại sau tất cả retry."""


class FirestorePublisher:
    """Async publisher đẩy dữ liệu bệnh nhân lên Firestore.

    Features:
    - Retry 3 lần với exponential backoff
    - Local queue fallback: ghi file JSON khi Firestore lỗi
    - Auto-sync: tự đồng bộ pending queue khi mạng ổn

    Reuse firestore_client.py hiện có của AUTOQ project cho REST helpers.

    Attributes:
        config: Cấu hình Firestore từ HisConfig.

    Ví dụ::

        publisher = FirestorePublisher(config)
        success = await publisher.publish(patient_info)
    """

    def __init__(self, config: HisConfig) -> None:
        self._config = config
        self._logger = get_logger("his_bridge.firestore")
        self._sync_task: asyncio.Task[None] | None = None

    async def start_auto_sync(self) -> None:
        """Bắt đầu background task tự đồng bộ pending queue mỗi 30 giây."""
        if self._sync_task is None or self._sync_task.done():
            self._sync_task = asyncio.create_task(
                self._auto_sync_loop(),
                name="firestore_auto_sync",
            )
            self._logger.info("Đã khởi động auto-sync pending queue")

    async def stop_auto_sync(self) -> None:
        """Dừng background auto-sync task."""
        if self._sync_task is not None and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._logger.info("Đã dừng auto-sync pending queue")

    @log_timing
    async def publish(self, patient: PatientInfo) -> bool:
        """Publish thông tin bệnh nhân lên Firestore.

        Thử publish trực tiếp → retry → fallback local queue.

        Args:
            patient: Thông tin bệnh nhân đã chuẩn hóa.

        Returns:
            True nếu publish thành công (online hoặc queued).
        """
        fs_dict = patient.to_firestore_dict()
        net = self._config.network

        for attempt in range(1, net.max_retries + 1):
            try:
                success = await self._publish_to_firestore(fs_dict)
                if success:
                    self._logger.info(
                        "Publish Firestore thành công: %s",
                        patient.patient_code,
                    )
                    return True

            except Exception as exc:
                self._logger.warning(
                    "Publish lần %d/%d thất bại: %s",
                    attempt,
                    net.max_retries,
                    exc,
                )
                if attempt < net.max_retries:
                    delay = net.retry_delay_seconds * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)

        # Tất cả retry thất bại → ghi vào local queue
        self._logger.error(
            "Publish thất bại sau %d lần thử. Ghi vào pending queue: %s",
            net.max_retries,
            patient.patient_code,
        )
        self._save_to_pending_queue(fs_dict)
        return False

    async def _publish_to_firestore(
        self,
        data: dict[str, Any],
    ) -> bool:
        """Publish dict lên Firestore collection (non-blocking).

        Sử dụng firestore_client hiện có của AUTOQ project.
        Wrap synchronous call trong thread pool executor.
        """
        loop = asyncio.get_event_loop()

        # Import firestore_client tại đây để tránh circular import
        # và chỉ phụ thuộc khi thực sự publish
        return await loop.run_in_executor(
            None,
            self._sync_publish,
            data,
        )

    def _sync_publish(self, data: dict[str, Any]) -> bool:
        """Synchronous publish — chạy trong thread pool.

        Sử dụng firestore_client.firestore_set() hiện có.
        """
        try:
            # Import firestore_client module hiện có
            import firestore_client  # type: ignore[import-untyped]

            # Tạo document path duy nhất cho bệnh nhân
            patient_code = data.get("patientCode", "unknown")
            timestamp = int(time.time())
            doc_path = (
                f"{self._config.firestore.collection}/"
                f"his_bridge_{patient_code}_{timestamp}"
            )

            return firestore_client.firestore_set(doc_path, data)

        except ImportError:
            self._logger.error(
                "Không tìm thấy module firestore_client.py. "
                "Đảm bảo file nằm trong thư mục gốc AUTOQ."
            )
            return False
        except Exception as exc:
            self._logger.error("Lỗi publish Firestore: %s", exc)
            return False

    def _save_to_pending_queue(self, data: dict[str, Any]) -> None:
        """Lưu document vào local pending queue (JSON file).

        Mỗi entry bao gồm timestamp và dữ liệu bệnh nhân.
        """
        try:
            _PENDING_QUEUE_DIR.mkdir(parents=True, exist_ok=True)

            # Đọc queue hiện tại
            pending: list[dict[str, Any]] = []
            if _PENDING_QUEUE_FILE.exists():
                try:
                    pending = json.loads(
                        _PENDING_QUEUE_FILE.read_text(encoding="utf-8"),
                    )
                except (json.JSONDecodeError, OSError):
                    pending = []

            # Thêm entry mới
            pending.append({
                "queued_at": time.time(),
                "data": data,
            })

            _PENDING_QUEUE_FILE.write_text(
                json.dumps(pending, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._logger.info(
                "Đã lưu vào pending queue (%d entries)",
                len(pending),
            )

        except OSError as exc:
            self._logger.error(
                "Không thể ghi pending queue: %s", exc,
            )

    async def sync_pending_queue(self) -> int:
        """Đồng bộ tất cả entries trong pending queue lên Firestore.

        Returns:
            Số lượng entries đã đồng bộ thành công.
        """
        if not _PENDING_QUEUE_FILE.exists():
            return 0

        try:
            pending: list[dict[str, Any]] = json.loads(
                _PENDING_QUEUE_FILE.read_text(encoding="utf-8"),
            )
        except (json.JSONDecodeError, OSError):
            return 0

        if not pending:
            return 0

        self._logger.info(
            "Bắt đầu đồng bộ %d entries từ pending queue",
            len(pending),
        )

        synced = 0
        remaining: list[dict[str, Any]] = []

        for entry in pending:
            data = entry.get("data", {})
            try:
                success = await self._publish_to_firestore(data)
                if success:
                    synced += 1
                else:
                    remaining.append(entry)
            except Exception:
                remaining.append(entry)

        # Cập nhật file queue — chỉ giữ lại entries chưa sync
        if remaining:
            _PENDING_QUEUE_FILE.write_text(
                json.dumps(remaining, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        elif _PENDING_QUEUE_FILE.exists():
            _PENDING_QUEUE_FILE.unlink()

        self._logger.info(
            "Đồng bộ pending queue: %d/%d thành công, còn %d chờ",
            synced,
            len(pending),
            len(remaining),
        )
        return synced

    @property
    def pending_count(self) -> int:
        """Số lượng entries đang chờ trong pending queue."""
        if not _PENDING_QUEUE_FILE.exists():
            return 0
        try:
            pending = json.loads(
                _PENDING_QUEUE_FILE.read_text(encoding="utf-8"),
            )
            return len(pending)
        except (json.JSONDecodeError, OSError):
            return 0

    async def _auto_sync_loop(self) -> None:
        """Background loop tự đồng bộ pending queue mỗi 30 giây."""
        sync_interval_seconds = 30
        while True:
            try:
                await asyncio.sleep(sync_interval_seconds)
                if self.pending_count > 0:
                    await self.sync_pending_queue()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._logger.warning(
                    "Auto-sync lỗi: %s", exc,
                )
