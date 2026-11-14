from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont
from oncall_manager import OnCallManager


# ─── Worker thread để sync Firestore bất đồng bộ ─────────────────────────────

class SyncWorker(QThread):
    """Đồng bộ nhân sự Firestore trong thread riêng để không block UI."""
    done  = Signal(dict)   # {"added": int, "updated": int, "total": int}
    error = Signal(str)

    def __init__(self, manager: OnCallManager):
        super().__init__()
        self.manager = manager

    def run(self):
        try:
            from firestore_sync import fetch_all_personnel
            personnel = fetch_all_personnel()
            result    = self.manager.sync_from_firestore(personnel)
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ─── Cửa sổ thiết lập BS trực ─────────────────────────────────────────────────

class OnCallSetupWindow(QWidget):
    """Cửa sổ thiết lập danh sách bác sĩ trực và số điện thoại."""

    def __init__(self):
        super().__init__()
        self.manager = OnCallManager()

        self.setWindowTitle("Thiết lập Bác sĩ Trực")
        self.setMinimumSize(600, 560)
        self.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                color: #0f172a;
                font-family: 'Segoe UI', Arial;
                font-size: 14px;
            }
            QLineEdit {
                color: #0f172a;
                font-weight: 600;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ===== TITLE =====
        title = QLabel("DANH SÁCH BÁC SĨ TRỰC")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0B5FA5; padding: 5px;")
        layout.addWidget(title)

        # ===== NÚT ĐỒNG BỘ FIRESTORE =====
        sync_frame = QFrame()
        sync_frame.setStyleSheet("""
            QFrame {
                background: #e8f4fd;
                border: 1px solid #90caf9;
                border-radius: 8px;
                padding: 2px;
            }
        """)
        sync_layout = QHBoxLayout(sync_frame)
        sync_layout.setContentsMargins(12, 8, 12, 8)
        sync_layout.setSpacing(10)

        sync_info = QLabel("🔗 Đồng bộ nhân sự từ app lịch trực TaskView (Firestore):")
        sync_info.setStyleSheet("color: #1565c0; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        sync_layout.addWidget(sync_info, 1)

        self.btn_sync = QPushButton("🔄 Đồng bộ Firestore")
        self.btn_sync.setMinimumHeight(35)
        self.btn_sync.setStyleSheet("""
            QPushButton {
                background-color: #1976d2;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 6px;
                border: none;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #1565c0; }
            QPushButton:disabled { background-color: #90caf9; color: #e3f2fd; }
        """)
        self.btn_sync.clicked.connect(self.sync_from_firestore)
        sync_layout.addWidget(self.btn_sync)

        layout.addWidget(sync_frame)

        # ===== STATUS LABEL (sync result) =====
        self.sync_status = QLabel("")
        self.sync_status.setAlignment(Qt.AlignCenter)
        self.sync_status.setStyleSheet("font-size: 12px; color: #555; padding: 2px;")
        self.sync_status.setVisible(False)
        layout.addWidget(self.sync_status)

        # ===== TABLE =====
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["STT", "Tên Bác sĩ / Nhân sự", "Số điện thoại", ""])
        self.table.horizontalHeader().setStyleSheet("font-weight: bold;")
        self.table.setColumnWidth(0, 45)
        self.table.setColumnWidth(1, 240)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(3, 80)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #ddd;
                border-radius: 5px;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item { padding: 6px; }
            QHeaderView::section {
                background: #f0f0f0;
                padding: 8px;
                border: 1px solid #ddd;
            }
        """)
        layout.addWidget(self.table)

        # ===== FORM THÊM MỚI =====
        form_frame = QFrame()
        form_frame.setStyleSheet("""
            QFrame {
                background: #f8f9fa;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        form_layout = QHBoxLayout(form_frame)
        form_layout.setSpacing(10)

        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Tên Bác sĩ...")
        self.input_name.setStyleSheet("padding: 8px; border: 1px solid #ccc; border-radius: 5px; background: white;")

        self.input_phone = QLineEdit()
        self.input_phone.setPlaceholderText("Số điện thoại...")
        self.input_phone.setStyleSheet("padding: 8px; border: 1px solid #ccc; border-radius: 5px; background: white;")

        btn_add = QPushButton("➕ THÊM")
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover { background-color: #218838; }
        """)
        btn_add.clicked.connect(self.add_doctor)

        form_layout.addWidget(self.input_name, 2)
        form_layout.addWidget(self.input_phone, 2)
        form_layout.addWidget(btn_add, 1)

        layout.addWidget(form_frame)

        # Load dữ liệu ban đầu
        self.refresh_table()

    # ─── Table ────────────────────────────────────────────────────────────────

    def refresh_table(self):
        """Tải lại danh sách từ database và hiển thị lên bảng."""
        doctors = self.manager.get_all()
        self.table.setRowCount(len(doctors))

        for row, (doc_id, name, phone) in enumerate(doctors):
            stt_item = QTableWidgetItem(str(row + 1))
            stt_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, stt_item)

            self.table.setItem(row, 1, QTableWidgetItem(name))
            self.table.setItem(row, 2, QTableWidgetItem(phone))

            btn_del = QPushButton("🗑 Xóa")
            btn_del.setStyleSheet("""
                QPushButton {
                    background-color: #dc3545;
                    color: white;
                    font-weight: bold;
                    padding: 4px 10px;
                    border-radius: 4px;
                    border: none;
                    font-size: 12px;
                }
                QPushButton:hover { background-color: #c82333; }
            """)
            btn_del.clicked.connect(lambda checked, did=doc_id: self.delete_doctor(did))
            self.table.setCellWidget(row, 3, btn_del)

    # ─── Add / Delete ─────────────────────────────────────────────────────────

    def add_doctor(self):
        """Thêm BS trực mới vào database."""
        name  = self.input_name.text().strip()
        phone = self.input_phone.text().strip()

        if not name or not phone:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập đầy đủ Tên và Số điện thoại.")
            return

        self.manager.add(name, phone)
        self.input_name.clear()
        self.input_phone.clear()
        self.refresh_table()

    def delete_doctor(self, doc_id: int):
        """Xóa BS trực sau khi xác nhận."""
        reply = QMessageBox.question(
            self, "Xác nhận xóa",
            "Bạn có chắc muốn xóa bác sĩ này khỏi danh sách trực?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.manager.delete(doc_id)
            self.refresh_table()

    # ─── Đồng bộ Firestore ────────────────────────────────────────────────────

    def sync_from_firestore(self):
        """Bắt đầu đồng bộ nhân sự từ Firestore trong background thread."""
        self.btn_sync.setEnabled(False)
        self.btn_sync.setText("⏳ Đang đồng bộ…")
        self.sync_status.setText("Đang kết nối Firestore…")
        self.sync_status.setStyleSheet("font-size: 12px; color: #1976d2;")
        self.sync_status.setVisible(True)

        self._sync_worker = SyncWorker(self.manager)
        self._sync_worker.done.connect(self._on_sync_done)
        self._sync_worker.error.connect(self._on_sync_error)
        self._sync_worker.start()

    def _on_sync_done(self, result: dict):
        """Callback khi sync thành công."""
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("🔄 Đồng bộ Firestore")

        added   = result.get("added", 0)
        updated = result.get("updated", 0)
        total   = result.get("total", 0)

        msg = f"✅ Đồng bộ thành công!  +{added} mới  |  ~{updated} cập nhật  |  Tổng: {total} nhân sự"
        self.sync_status.setText(msg)
        self.sync_status.setStyleSheet(
            "font-size: 12px; color: #2e7d32; background: #e8f5e9; "
            "border-radius: 4px; padding: 4px 8px;"
        )
        self.refresh_table()

    def _on_sync_error(self, msg: str):
        """Callback khi sync thất bại."""
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("🔄 Đồng bộ Firestore")
        self.sync_status.setText(f"❌ Lỗi kết nối: {msg}")
        self.sync_status.setStyleSheet(
            "font-size: 12px; color: #c62828; background: #ffebee; "
            "border-radius: 4px; padding: 4px 8px;"
        )
        QMessageBox.warning(
            self, "Lỗi đồng bộ",
            f"Không thể kết nối đến Firestore:\n{msg}\n\n"
            "Vui lòng kiểm tra kết nối mạng và thử lại."
        )
