# =============================================================================
# FILE: his_bridge/barcode_listener.py
# MÔ TẢ: BarcodeListener — nhận barcode từ kiosk app hoặc UI qua PySide6 signal.
#         Validate format barcode trước khi chuyển cho bridge xử lý.
#
#         Module này KHÔNG tự bắt keyboard.
#         Barcode được truyền vào từ QLineEdit.returnPressed hoặc method receive().
# =============================================================================

from __future__ import annotations

import re

from PySide6.QtCore import QObject, Signal

from his_bridge.logger import get_logger


# Regex mặc định cho mã bệnh nhân VNPT HIS (BNxxxxxxxx)
_DEFAULT_BARCODE_PATTERN = r"^[A-Za-z0-9]{4,20}$"


class BarcodeListener(QObject):
    """Listener nhận và validate barcode trước khi chuyển cho HisBridge.

    Sử dụng PySide6 Signal pattern — không tự bắt input.
    Kiosk app hoặc UI gọi receive() hoặc connect trực tiếp.

    Signals:
        barcode_received(str): Emit khi barcode hợp lệ được nhận.
        barcode_invalid(str): Emit khi barcode không hợp lệ.

    Ví dụ::

        listener = BarcodeListener()
        listener.barcode_received.connect(bridge.on_barcode)

        # Từ QLineEdit:
        entry.returnPressed.connect(
            lambda: listener.receive(entry.text())
        )
    """

    barcode_received = Signal(str)
    barcode_invalid = Signal(str)

    def __init__(
        self,
        pattern: str = _DEFAULT_BARCODE_PATTERN,
        parent: QObject | None = None,
    ) -> None:
        """Khởi tạo BarcodeListener.

        Args:
            pattern: Regex pattern để validate barcode.
                     Mặc định chấp nhận 4-20 ký tự alphanumeric.
            parent: QObject parent (Qt ownership).
        """
        super().__init__(parent)
        self._pattern = re.compile(pattern)
        self._logger = get_logger("his_bridge.barcode")

    def receive(self, raw_input: str) -> bool:
        """Nhận và xử lý barcode input.

        Chuỗi barcode được strip, validate, rồi emit signal tương ứng.

        Args:
            raw_input: Chuỗi barcode thô từ scanner hoặc keyboard.

        Returns:
            True nếu barcode hợp lệ và đã emit barcode_received.
        """
        barcode = raw_input.strip()

        if not barcode:
            self._logger.warning("Barcode rỗng — bỏ qua")
            return False

        if not self._validate(barcode):
            self._logger.warning(
                "Barcode không hợp lệ: '%s' (không khớp pattern '%s')",
                barcode,
                self._pattern.pattern,
            )
            self.barcode_invalid.emit(barcode)
            return False

        self._logger.info("Barcode received: %s", barcode)
        self.barcode_received.emit(barcode)
        return True

    def _validate(self, barcode: str) -> bool:
        """Kiểm tra barcode có khớp pattern không.

        Args:
            barcode: Mã barcode đã strip.

        Returns:
            True nếu hợp lệ.
        """
        return bool(self._pattern.match(barcode))

    @property
    def pattern(self) -> str:
        """Regex pattern đang sử dụng."""
        return self._pattern.pattern

    def set_pattern(self, pattern: str) -> None:
        """Cập nhật regex pattern validation.

        Args:
            pattern: Regex pattern mới.
        """
        self._pattern = re.compile(pattern)
        self._logger.info("Barcode pattern updated: %s", pattern)
