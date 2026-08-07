# =============================================================================
# FILE: his_bridge/main.py
# MÔ TẢ: Standalone UI cho HIS Bridge (PySide6).
#         Giao diện đơn giản: textbox barcode, hiển thị kết quả, trạng thái.
#         Có thể chạy độc lập hoặc tích hợp vào kiosk app.
# =============================================================================

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont

from his_bridge.bridge import HisBridge
from his_bridge.config import HisConfig
from his_bridge.models import PatientInfo


class HisBridgeUI(QWidget):
    """Giao diện standalone cho VNPT HIS Bridge.

    Features:
    - TextBox nhập/quét barcode (Enter để tra cứu)
    - Hiển thị: Tên, Tuổi, Giới tính, Địa chỉ
    - Danh sách dịch vụ chỉ định
    - Trạng thái Firestore publish
    - Icon kết nối: HIS / Firestore
    - Ưu tiên ổn định, không cần giao diện đẹp
    """

    def __init__(
        self,
        config: HisConfig | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("VNPT HIS Bridge")
        self.setFixedSize(500, 600)
        self._setup_styles()
        self._setup_ui()

        # Khởi tạo bridge
        self._bridge = HisBridge(config=config, parent=self)
        self._connect_signals()
        self._bridge.start()

    def _setup_styles(self) -> None:
        """Thiết lập stylesheet tối giản, ổn định."""
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a2e;
                color: #e0e0e0;
                font-family: "Segoe UI", Arial, sans-serif;
            }
            QLabel {
                font-size: 13px;
            }
            QLineEdit {
                background-color: #16213e;
                border: 1px solid #0f3460;
                border-radius: 6px;
                padding: 8px 12px;
                color: #e0e0e0;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #e94560;
            }
            QListWidget {
                background-color: #16213e;
                border: 1px solid #0f3460;
                border-radius: 6px;
                padding: 6px;
                font-size: 12px;
            }
            QGroupBox {
                border: 1px solid #0f3460;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
                font-weight: bold;
                font-size: 13px;
                color: #e94560;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

    def _setup_ui(self) -> None:
        """Xây dựng layout giao diện."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ─── Header ──────────────────────────────────────────────
        header = QLabel("VNPT HIS BRIDGE")
        header.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("color: #e94560; margin-bottom: 4px;")
        layout.addWidget(header)

        # ─── Connection Status ───────────────────────────────────
        status_bar = QHBoxLayout()

        self._lbl_his_status = QLabel("⚪ HIS: Đang kết nối...")
        self._lbl_his_status.setFont(QFont("Segoe UI", 10))
        status_bar.addWidget(self._lbl_his_status)

        self._lbl_fs_status = QLabel("⚪ Firestore: Chờ")
        self._lbl_fs_status.setFont(QFont("Segoe UI", 10))
        status_bar.addWidget(self._lbl_fs_status)

        layout.addLayout(status_bar)

        # ─── Barcode Input ───────────────────────────────────────
        self._entry_barcode = QLineEdit()
        self._entry_barcode.setPlaceholderText(
            "Quét hoặc nhập mã bệnh nhân (Enter)..."
        )
        self._entry_barcode.setFixedHeight(42)
        self._entry_barcode.setFont(QFont("Segoe UI", 13))
        self._entry_barcode.returnPressed.connect(self._on_barcode_enter)
        layout.addWidget(self._entry_barcode)

        # ─── Patient Info ────────────────────────────────────────
        group_info = QGroupBox("Thông tin Bệnh nhân")
        info_layout = QVBoxLayout(group_info)
        info_layout.setSpacing(6)

        self._lbl_name = QLabel("Họ tên: —")
        self._lbl_name.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        info_layout.addWidget(self._lbl_name)

        self._lbl_age = QLabel("Tuổi: —")
        info_layout.addWidget(self._lbl_age)

        self._lbl_gender = QLabel("Giới tính: —")
        info_layout.addWidget(self._lbl_gender)

        self._lbl_address = QLabel("Địa chỉ: —")
        self._lbl_address.setWordWrap(True)
        info_layout.addWidget(self._lbl_address)

        self._lbl_patient_code = QLabel("Mã BN: —")
        info_layout.addWidget(self._lbl_patient_code)

        layout.addWidget(group_info)

        # ─── Services ────────────────────────────────────────────
        group_services = QGroupBox("Dịch vụ chỉ định")
        svc_layout = QVBoxLayout(group_services)

        self._list_services = QListWidget()
        self._list_services.setFixedHeight(130)
        svc_layout.addWidget(self._list_services)

        layout.addWidget(group_services)

        # ─── Status Log ──────────────────────────────────────────
        self._lbl_status = QLabel("Sẵn sàng. Chờ quét barcode.")
        self._lbl_status.setFont(QFont("Consolas", 10))
        self._lbl_status.setWordWrap(True)
        self._lbl_status.setStyleSheet(
            "color: #94a3b8; border: 1px solid #0f3460; "
            "padding: 8px; background-color: #0d1117; border-radius: 6px;"
        )
        layout.addWidget(self._lbl_status)

        # Focus vào barcode input
        self._entry_barcode.setFocus()

    def _connect_signals(self) -> None:
        """Kết nối signals từ HisBridge → UI slots."""
        self._bridge.patient_found.connect(self._on_patient_found)
        self._bridge.bridge_error.connect(self._on_bridge_error)
        self._bridge.his_connected.connect(self._on_his_connected)
        self._bridge.firestore_connected.connect(
            self._on_firestore_connected,
        )
        self._bridge.processing.connect(self._on_processing)

    def _log(self, text: str) -> None:
        """Cập nhật dòng trạng thái."""
        now = datetime.now().strftime("%H:%M:%S")
        self._lbl_status.setText(f"[{now}] {text}")

    @Slot()
    def _on_barcode_enter(self) -> None:
        """Xử lý khi nhấn Enter trong textbox barcode."""
        barcode = self._entry_barcode.text().strip()
        if barcode:
            self._log(f"Đang tra cứu '{barcode}' trên VNPT HIS...")
            self._bridge.lookup(barcode)
            self._entry_barcode.clear()

    @Slot(object)
    def _on_patient_found(self, patient: PatientInfo) -> None:
        """Hiển thị thông tin bệnh nhân đã tra cứu thành công."""
        self._lbl_name.setText(f"Họ tên: {patient.patient_name}")
        self._lbl_age.setText(f"Tuổi: {patient.age}")
        self._lbl_gender.setText(f"Giới tính: {patient.gender}")
        self._lbl_address.setText(f"Địa chỉ: {patient.address}")
        self._lbl_patient_code.setText(f"Mã BN: {patient.patient_code}")

        # Cập nhật danh sách dịch vụ
        self._list_services.clear()
        if patient.services:
            for svc in patient.services:
                display = f"{svc.code} — {svc.name}"
                if svc.note:
                    display += f" ({svc.note})"
                self._list_services.addItem(QListWidgetItem(display))
        else:
            self._list_services.addItem(
                QListWidgetItem("Không có dịch vụ chỉ định")
            )

        self._log(
            f"Tìm thấy: {patient.patient_name} "
            f"(Tuổi: {patient.age}, {len(patient.services)} dịch vụ)"
        )
        self._entry_barcode.setFocus()

    @Slot(str)
    def _on_bridge_error(self, error_msg: str) -> None:
        """Hiển thị lỗi từ bridge."""
        self._log(f"LỖI: {error_msg}")

    @Slot(bool)
    def _on_his_connected(self, connected: bool) -> None:
        """Cập nhật trạng thái kết nối HIS."""
        if connected:
            self._lbl_his_status.setText("🟢 HIS: Đã kết nối")
            self._lbl_his_status.setStyleSheet("color: #4ade80;")
        else:
            self._lbl_his_status.setText("🔴 HIS: Mất kết nối")
            self._lbl_his_status.setStyleSheet("color: #f87171;")

    @Slot(bool)
    def _on_firestore_connected(self, connected: bool) -> None:
        """Cập nhật trạng thái kết nối Firestore."""
        if connected:
            self._lbl_fs_status.setText("🟢 Firestore: Đã kết nối")
            self._lbl_fs_status.setStyleSheet("color: #4ade80;")
        else:
            self._lbl_fs_status.setText("🔴 Firestore: Mất kết nối")
            self._lbl_fs_status.setStyleSheet("color: #f87171;")

    @Slot(bool)
    def _on_processing(self, is_processing: bool) -> None:
        """Vô hiệu hóa input khi đang xử lý."""
        self._entry_barcode.setEnabled(not is_processing)

    def closeEvent(self, event: Any) -> None:
        """Dừng bridge worker khi đóng cửa sổ."""
        self._bridge.stop()
        super().closeEvent(event)

    @property
    def bridge(self) -> HisBridge:
        """Trả về HisBridge instance để tích hợp."""
        return self._bridge


def main() -> None:
    """Entry point khi chạy standalone: python -m his_bridge.main"""
    app = QApplication(sys.argv)

    # Load config
    config_path = Path(__file__).parent / "config.yaml"
    config = HisConfig.load(config_path)

    window = HisBridgeUI(config=config)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
