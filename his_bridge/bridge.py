# =============================================================================
# FILE: his_bridge/bridge.py
# MÔ TẢ: HisBridge — Orchestrator kết nối tất cả components.
#         Pipeline: barcode → cache → HIS search → gather(info, services)
#                   → normalize → emit signal → kiosk app nhận kết quả.
#
#         Bridge KHÔNG push vào room queue.
#         Bridge CHỈ trả về PatientInfo cho kiosk app hiển thị.
# =============================================================================

from __future__ import annotations

import asyncio
import time
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from his_bridge.barcode_listener import BarcodeListener
from his_bridge.cache import TTLCache
from his_bridge.config import HisConfig
from his_bridge.firestore_service import FirestorePublisher
from his_bridge.logger import get_logger, setup_logger
from his_bridge.models import PatientInfo
from his_bridge.vnpt_his_client import (
    HisConnectionError,
    SessionExpiredError,
    VNPTHisClient,
)


class _BridgeWorker(QThread):
    """Background thread chạy async event loop cho HIS Bridge.

    Tách biệt event loop asyncio khỏi Qt main thread để không block UI.
    """

    # Signals truyền kết quả về Qt main thread
    patient_found = Signal(object)    # PatientInfo
    publish_success = Signal(str)     # patient_code
    bridge_error = Signal(str)        # error message
    his_connected = Signal(bool)      # trạng thái kết nối HIS
    firestore_connected = Signal(bool)  # trạng thái kết nối Firestore
    processing = Signal(bool)         # đang xử lý hay không

    def __init__(
        self,
        config: HisConfig,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._barcode_queue: asyncio.Queue[str] = asyncio.Queue()
        self._logger = get_logger("his_bridge.worker")

    def run(self) -> None:
        """Entry point của background thread — chạy asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main_loop())
        except Exception as exc:
            self._logger.error("Bridge worker crashed: %s", exc)
        finally:
            self._loop.close()

    async def _main_loop(self) -> None:
        """Vòng lặp chính: chờ barcode → xử lý pipeline."""
        cache: TTLCache[PatientInfo] = TTLCache(
            ttl_seconds=self._config.cache.ttl_seconds,
        )
        publisher = FirestorePublisher(self._config)

        # Khởi động auto-sync pending queue
        await publisher.start_auto_sync()

        async with VNPTHisClient(self._config) as his_client:
            self.his_connected.emit(True)

            while True:
                try:
                    barcode = await self._barcode_queue.get()
                    await self._process_barcode(
                        barcode=barcode,
                        his_client=his_client,
                        cache=cache,
                        publisher=publisher,
                    )
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    self._logger.error(
                        "Lỗi không mong đợi trong main loop: %s", exc,
                    )
                    self.bridge_error.emit(str(exc))

        await publisher.stop_auto_sync()

    async def _process_barcode(
        self,
        barcode: str,
        his_client: VNPTHisClient,
        cache: TTLCache[PatientInfo],
        publisher: FirestorePublisher,
    ) -> None:
        """Xử lý một barcode qua toàn bộ pipeline.

        1. Kiểm tra cache (TTL 5s)
        2. Gọi HIS RestService
        3. Chuẩn hóa dữ liệu
        4. Emit kết quả về UI
        """
        self.processing.emit(True)
        start = time.perf_counter()

        try:
            # Bước 1: Cache check
            cached = cache.get(barcode)
            if cached is not None:
                self._logger.info(
                    "Cache hit cho barcode '%s' — bỏ qua gọi HIS",
                    barcode,
                )
                self.patient_found.emit(cached)
                self.processing.emit(False)
                return

            # Bước 2-4: Gọi HIS (search → gather → normalize)
            patient = await his_client.fetch_full_patient(barcode)

            # Lưu cache
            cache.set(barcode, patient)

            # Emit kết quả
            self.patient_found.emit(patient)

            elapsed = (time.perf_counter() - start) * 1000
            self._logger.info(
                "Pipeline hoàn thành: %s — %s — %.0f ms",
                barcode,
                patient.patient_name,
                elapsed,
            )

        except SessionExpiredError as exc:
            self._logger.error("Session HIS hết hạn: %s", exc)
            self.his_connected.emit(False)
            # Tự động reload config từ file (Session Watcher có thể đã cập nhật)
            try:
                new_config = self._config.__class__.load()
                new_session = new_config.his.session
                old_session = self._config.his.session
                if (new_session.jsessionid != old_session.jsessionid or
                        new_session.uuid_jwt != old_session.uuid_jwt):
                    self._logger.info(
                        "Phát hiện config.yaml có session mới — reload và thử lại..."
                    )
                    self._config = new_config
                    await his_client.close()
                    his_client._config = new_config
                    his_client._client = his_client._create_client()
                    # Thử lại lần cuối với session mới
                    patient = await his_client.fetch_full_patient(barcode)
                    cache.set(barcode, patient)
                    self.patient_found.emit(patient)
                    self.his_connected.emit(True)
                    return
                else:
                    self.bridge_error.emit(
                        "Session HIS đã hết hạn!\n"
                        "Session Watcher chưa cập nhật — vui lòng đảm bảo Chrome HIS đang mở."
                    )
            except Exception as reload_exc:
                self._logger.error("Reload config thất bại: %s", reload_exc)
                self.bridge_error.emit(str(exc))

        except HisConnectionError as exc:
            self._logger.error("Lỗi kết nối HIS: %s", exc)
            self.his_connected.emit(False)
            self.bridge_error.emit(
                f"Không thể kết nối VNPT HIS. Kiểm tra mạng và config.\n{exc}"
            )

        except Exception as exc:
            self._logger.error("Lỗi pipeline: %s", exc)
            self.bridge_error.emit(f"Lỗi tra cứu: {exc}")

        finally:
            self.processing.emit(False)

    def submit_barcode(self, barcode: str) -> None:
        """Thread-safe: gửi barcode vào queue để xử lý.

        Gọi từ Qt main thread — an toàn đa luồng.

        Args:
            barcode: Mã bệnh nhân từ scanner.
        """
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(
                self._barcode_queue.put_nowait, barcode,
            )
        else:
            self._logger.warning(
                "Bridge worker chưa sẵn sàng — bỏ qua barcode '%s'",
                barcode,
            )


class HisBridge(QObject):
    """Facade chính cho HIS Bridge module.

    Kết nối BarcodeListener → VNPTHisClient → FirestorePublisher
    thông qua _BridgeWorker chạy trong background thread.

    Signals:
        patient_found(PatientInfo): Bệnh nhân đã tra cứu thành công.
        publish_success(str): Đã publish lên Firestore.
        bridge_error(str): Lỗi xảy ra trong pipeline.
        his_connected(bool): Trạng thái kết nối HIS.
        firestore_connected(bool): Trạng thái kết nối Firestore.
        processing(bool): Đang xử lý hay không.

    Ví dụ::

        config = HisConfig.load("config.yaml")
        bridge = HisBridge(config)

        # Kết nối signals
        bridge.patient_found.connect(kiosk.on_patient_found)
        bridge.bridge_error.connect(kiosk.on_error)

        # Bắt đầu bridge
        bridge.start()

        # Khi nhận barcode
        bridge.lookup("BN00280291")
    """

    # Re-export signals từ worker
    patient_found = Signal(object)
    publish_success = Signal(str)
    bridge_error = Signal(str)
    his_connected = Signal(bool)
    firestore_connected = Signal(bool)
    processing = Signal(bool)

    def __init__(
        self,
        config: HisConfig | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Khởi tạo HisBridge.

        Args:
            config: Cấu hình HIS. Nếu None, tự load từ config.yaml.
            parent: QObject parent.
        """
        super().__init__(parent)

        if config is None:
            config = HisConfig.load()

        self._config = config
        self._logger = setup_logger(config.logging)

        # Tạo barcode listener
        self._barcode_listener = BarcodeListener(parent=self)

        # Tạo background worker
        self._worker = _BridgeWorker(config, parent=self)

        # Kết nối signals: listener → worker
        self._barcode_listener.barcode_received.connect(
            self._worker.submit_barcode,
        )

        # Forward signals: worker → HisBridge (public API)
        self._worker.patient_found.connect(self.patient_found.emit)
        self._worker.publish_success.connect(self.publish_success.emit)
        self._worker.bridge_error.connect(self.bridge_error.emit)
        self._worker.his_connected.connect(self.his_connected.emit)
        self._worker.firestore_connected.connect(
            self.firestore_connected.emit,
        )
        self._worker.processing.connect(self.processing.emit)

        # Log invalid barcodes
        self._barcode_listener.barcode_invalid.connect(
            lambda b: self.bridge_error.emit(
                f"Mã barcode không hợp lệ: '{b}'"
            ),
        )

        self._logger.info("HisBridge khởi tạo thành công")

    def start(self) -> None:
        """Khởi động bridge worker trong background thread."""
        if not self._worker.isRunning():
            self._worker.start()
            self._logger.info("HisBridge worker đã khởi động")

    def stop(self) -> None:
        """Dừng bridge worker."""
        if self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(5000)
            self._logger.info("HisBridge worker đã dừng")

    def lookup(self, barcode: str) -> None:
        """Tra cứu bệnh nhân bằng barcode.

        Barcode sẽ được validate bởi BarcodeListener trước khi xử lý.

        Args:
            barcode: Mã bệnh nhân từ scanner hoặc textbox.
        """
        self._barcode_listener.receive(barcode)

    @property
    def barcode_listener(self) -> BarcodeListener:
        """Trả về BarcodeListener instance để kết nối trực tiếp."""
        return self._barcode_listener

    @property
    def config(self) -> HisConfig:
        """Cấu hình hiện tại."""
        return self._config

    @property
    def is_running(self) -> bool:
        """Bridge worker có đang chạy không."""
        return self._worker.isRunning()
