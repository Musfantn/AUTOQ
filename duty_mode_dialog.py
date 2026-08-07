# =============================================================================
# FILE: duty_mode_dialog.py
# MÔ TẢ: Dialog chọn bác sĩ trực.
#        - Tự động lấy BS trực hôm nay từ lịch trực tháng (Firestore).
#        - Dropdown hiển thị toàn bộ BS, pre-select BS trực hôm nay.
#        - Một nút "Xác nhận" duy nhất.
# =============================================================================

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QProgressBar, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal
from firestore_client import names_match


# ─── Worker thread fetch dữ liệu bất đồng bộ ─────────────────────────────────

class FetchWorker(QThread):
    """Fetch dữ liệu Firestore trong thread riêng để không block UI."""
    # today_doc: {"name": str, "phone": str} hoặc None
    # doctors:   [(id, name, phone), ...]  từ local DB
    done  = Signal(object, list)
    error = Signal(str)

    def __init__(self, oncall_mgr):
        super().__init__()
        self.oncall_mgr = oncall_mgr

    def run(self):
        try:
            from firestore_sync import fetch_today_oncall_from_roster
            today_doc = fetch_today_oncall_from_roster()
            doctors   = self.oncall_mgr.get_all()   # [(id, name, phone), ...]
            self.done.emit(today_doc, doctors)
        except Exception as e:
            doctors = self.oncall_mgr.get_all()
            self.error.emit(str(e))
            # Vẫn emit doctors để có fallback
            self.done.emit(None, doctors)


# ─── Dialog ───────────────────────────────────────────────────────────────────

class DutyModeDialog(QDialog):
    """
    Popup chọn bác sĩ trực:
      - Hiển thị thông tin BS trực hôm nay theo lịch tháng.
      - Dropdown liệt kê toàn bộ BS, pre-select BS hôm nay.
      - Một nút Xác nhận duy nhất.

    Sau khi accept(): .selected_name và .selected_phone được set.
    """

    def __init__(self, oncall_manager, parent=None):
        super().__init__(parent)
        self.oncall_mgr     = oncall_manager
        self.selected_name  = None
        self.selected_phone = None
        self._doctors       = []   # [(id, name, phone), ...]
        self._fetch_done    = False

        self.setWindowTitle("Chế độ Phòng Trực")
        self.setMinimumWidth(480)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background: #f0f4f8;
                font-family: 'Segoe UI', Arial;
            }
            QLabel { border: none; background: transparent; }
        """)

        self._build_ui()
        self._start_fetch()

    # ─── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # ── TITLE ──
        title = QLabel("🌙  CHẾ ĐỘ PHÒNG TRỰC")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #0B5FA5; padding: 6px;"
        )
        root.addWidget(title)

        # ── LOADING ──
        self.loading_frame = QFrame()
        self.loading_frame.setStyleSheet("background: transparent;")
        lf = QVBoxLayout(self.loading_frame)
        lf.setSpacing(6)

        lbl = QLabel("⏳  Đang tải lịch trực từ Firestore…")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font-size: 13px; color: #555;")

        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setFixedHeight(5)
        bar.setStyleSheet("""
            QProgressBar { border:none; background:#dce3ec; border-radius:3px; }
            QProgressBar::chunk { background:#0B5FA5; border-radius:3px; }
        """)
        lf.addWidget(lbl)
        lf.addWidget(bar)
        root.addWidget(self.loading_frame)

        # ── CARD xanh lá ──
        self.card = QFrame()
        self.card.setStyleSheet("""
            QFrame {
                background: #e8f5e9;
                border: 2px solid #43a047;
                border-radius: 12px;
            }
        """)
        self.card.setVisible(False)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)

        # Header
        card_header = QLabel("✅  BÁC SĨ TRỰC HÔM NAY (theo lịch tháng)")
        card_header.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #2e7d32; background: transparent;"
        )
        card_layout.addWidget(card_header)

        # Tên BS hôm nay
        self.today_info = QLabel("---")
        self.today_info.setStyleSheet(
            "font-size: 17px; font-weight: bold; color: #1b5e20; "
            "background: white; border: 1px solid #a5d6a7; border-radius: 8px; padding: 8px 12px;"
        )
        card_layout.addWidget(self.today_info)

        # ── Separator nhỏ ──
        sep_lbl = QLabel("Chọn bác sĩ trực:")
        sep_lbl.setStyleSheet(
            "font-size: 13px; color: #444; font-weight: bold; margin-top: 4px; background: transparent;"
        )
        card_layout.addWidget(sep_lbl)

        # Dropdown chọn BS
        self.combo = QComboBox()
        self.combo.setStyleSheet("""
            QComboBox {
                font-size: 15px;
                font-weight: bold;
                padding: 7px 12px;
                border: 1px solid #a5d6a7;
                border-radius: 7px;
                background: white;
                color: #1b5e20;
            }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox QAbstractItemView {
                font-size: 14px;
                selection-background-color: #43a047;
                selection-color: white;
            }
        """)
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        card_layout.addWidget(self.combo)

        # SĐT preview
        self.phone_preview = QLabel("📞  ---")
        self.phone_preview.setStyleSheet(
            "font-size: 14px; color: #388e3c; font-weight: bold; background: transparent;"
        )
        card_layout.addWidget(self.phone_preview)

        root.addWidget(self.card)

        # ── Thông báo không có lịch trực ──
        self.no_data_label = QLabel(
            "ℹ️  Không tìm thấy lịch trực hôm nay.\n"
            "Vui lòng chọn bác sĩ từ danh sách."
        )
        self.no_data_label.setAlignment(Qt.AlignCenter)
        self.no_data_label.setWordWrap(True)
        self.no_data_label.setStyleSheet("font-size: 13px; color: #888; padding: 4px;")
        self.no_data_label.setVisible(False)
        root.addWidget(self.no_data_label)

        # ── Lỗi kết nối ──
        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            "font-size: 12px; color: #c62828; background: #ffebee; "
            "border-radius: 6px; padding: 6px 10px;"
        )
        self.error_label.setVisible(False)
        root.addWidget(self.error_label)

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_confirm = QPushButton("✅  Xác nhận")
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background: #43a047; color: white;
                font-size: 15px; font-weight: bold;
                padding: 10px 20px; border-radius: 8px; border: none;
            }
            QPushButton:hover { background: #388e3c; }
            QPushButton:disabled { background: #a5d6a7; color: #e8f5e9; }
        """)
        self.btn_confirm.clicked.connect(self._confirm)

        btn_cancel = QPushButton("✖  Hủy")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: #9e9e9e; color: white;
                font-size: 14px; padding: 10px 20px;
                border-radius: 8px; border: none;
            }
            QPushButton:hover { background: #757575; }
        """)
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(self.btn_confirm, 2)
        btn_row.addWidget(btn_cancel, 1)
        root.addLayout(btn_row)

        self.adjustSize()

    # ─── Fetch ────────────────────────────────────────────────────────────────

    def _start_fetch(self):
        self._worker = FetchWorker(self.oncall_mgr)
        self._worker.done.connect(self._on_fetch_done)
        self._worker.start()

    def _on_fetch_done(self, today_doc, doctors):
        """Callback khi dữ liệu đã sẵn sàng."""
        if not self.isVisible():
            return   # Dialog đã đóng

        self.loading_frame.setVisible(False)
        self._doctors     = list(doctors)   # [(id, name, phone), ...]
        self._fetch_done  = True

        # Điền combo box
        self.combo.blockSignals(True)
        self.combo.clear()
        for (did, name, phone) in self._doctors:
            label = f"{name}   📞 {phone}" if phone else name
            self.combo.addItem(label)
        self.combo.blockSignals(False)

        # Pre-select BS trực hôm nay
        default_idx = 0
        if today_doc and today_doc.get("name"):
            for i, (did, name, phone) in enumerate(self._doctors):
                if names_match(name, today_doc["name"]):
                    default_idx = i
                    break

        if self._doctors:
            self.combo.setCurrentIndex(default_idx)
            self._on_combo_changed(default_idx)

            # Hiển thị thông tin BS hôm nay
            if today_doc and today_doc.get("name"):
                phone_str = today_doc.get("phone") or "---"
                self.today_info.setText(
                    f"👨‍⚕️  {today_doc['name']}    📞  {phone_str}"
                )
            else:
                self.today_info.setText("Không có lịch trực hôm nay")
                self.no_data_label.setVisible(True)

            self.card.setVisible(True)
            self.btn_confirm.setEnabled(True)
        else:
            self.no_data_label.setText(
                "⚠️  Chưa có danh sách bác sĩ.\n"
                "Vui lòng đồng bộ từ Firestore trong mục Thiết lập BS Trực."
            )
            self.no_data_label.setVisible(True)

        self.adjustSize()

    # ─── Sự kiện ──────────────────────────────────────────────────────────────

    def _on_combo_changed(self, idx: int):
        """Cập nhật preview SĐT khi đổi lựa chọn combo."""
        if not self._doctors or idx < 0 or idx >= len(self._doctors):
            return
        (did, name, phone) = self._doctors[idx]
        self.phone_preview.setText(f"📞  {phone or '---'}")

    def _confirm(self):
        """Lấy BS đang được chọn trong combo và đóng dialog."""
        if not self._fetch_done or not self._doctors:
            QMessageBox.information(self, "Đang tải", "Vui lòng chờ tải xong dữ liệu…")
            return

        idx = self.combo.currentIndex()
        if idx < 0 or idx >= len(self._doctors):
            return

        (did, name, phone) = self._doctors[idx]
        self.selected_name  = name
        self.selected_phone = phone or ""
        self.accept()
