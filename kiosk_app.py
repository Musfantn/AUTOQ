import sys
import os
import json
import threading
import socket
import subprocess
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QTextEdit,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QMessageBox, QFrame,
    QListWidget, QListWidgetItem, QDialog, QScrollArea
)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QIcon

from his_bridge.bridge import HisBridge
from his_bridge.config import HisConfig
from his_bridge.models import PatientInfo

import firestore_queue


# =============================================================================
# WORKER THREAD FETCH DANH SÁCH BỆNH NHÂN BẤT ĐỒNG BỘ
# =============================================================================
class QueueFetchWorker(QThread):
    """Worker thread fetching queue data for all rooms in background."""
    data_loaded = Signal(dict)

    def run(self):
        result = {}
        for r in range(1, 6):
            room_str = str(r)
            try:
                data = firestore_queue.get_room_queue(room_str)
                result[room_str] = data or {}
            except Exception:
                result[room_str] = {}
        self.data_loaded.emit(result)


# =============================================================================
# CỬA SỔ HIỂN THỊ DANH SÁCH BỆNH NHÂN TIẾP NHẬN THEO PHÒNG
# =============================================================================
class PatientQueueDialog(QDialog):
    """Cửa sổ hiển thị danh sách bệnh nhân đã được tiếp nhận chia theo từng cột của 5 phòng."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DANH SÁCH BỆNH NHÂN ĐÃ TIẾP NHẬN THEO PHÒNG")
        self.resize(1180, 720)
        self.setMinimumSize(950, 600)
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #e2e8f0;
                font-family: "Segoe UI", Arial, sans-serif;
            }
            QLabel {
                color: #e2e8f0;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #1e293b;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #475569;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #64748b;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QPushButton {
                background-color: #0284c7;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:pressed {
                background-color: #075985;
            }
        """)

        self.room_colors = {
            "1": {"bg": "#0284c7", "header": "#0369a1", "border": "#38bdf8"},
            "2": {"bg": "#059669", "header": "#047857", "border": "#34d399"},
            "3": {"bg": "#7c3aed", "header": "#6d28d9", "border": "#a78bfa"},
            "4": {"bg": "#db2777", "header": "#be185d", "border": "#f472b6"},
            "5": {"bg": "#d97706", "header": "#b45309", "border": "#fbbf24"},
        }

        self._build_ui()

        # Timer auto-refresh mỗi 5s
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.fetch_data_async)
        self.timer.start(5000)

        # Nạp dữ liệu lần đầu
        self.fetch_data_async()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Top Bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        title_lbl = QLabel("📋 DANH SÁCH BỆNH NHÂN TIẾP NHẬN THEO PHÒNG")
        title_lbl.setFont(QFont("Segoe UI", 15, QFont.Bold))
        title_lbl.setStyleSheet("color: #38bdf8;")

        self.lbl_total_count = QLabel("Tổng cộng: 0 BN")
        self.lbl_total_count.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.lbl_total_count.setStyleSheet(
            "color: #10b981; background: #064e3b; padding: 4px 12px; border-radius: 6px;"
        )

        self.lbl_status = QLabel("⏳ Đang cập nhật...")
        self.lbl_status.setFont(QFont("Segoe UI", 10))
        self.lbl_status.setStyleSheet("color: #94a3b8;")

        btn_refresh = QPushButton("🔄 Làm mới")
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.clicked.connect(self.fetch_data_async)

        top_bar.addWidget(title_lbl)
        top_bar.addWidget(self.lbl_total_count)
        top_bar.addStretch()
        top_bar.addWidget(self.lbl_status)
        top_bar.addWidget(btn_refresh)

        main_layout.addLayout(top_bar)

        # Container cho 5 cột phòng
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(10)

        self.column_widgets = {}
        self.column_scroll_layouts = {}
        self.column_count_labels = {}

        for r in range(1, 6):
            room_str = str(r)
            color_info = self.room_colors[room_str]

            # Container phòng
            col_frame = QFrame()
            col_frame.setStyleSheet("""
                QFrame {
                    background-color: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 10px;
                }
            """)
            col_vlayout = QVBoxLayout(col_frame)
            col_vlayout.setContentsMargins(8, 8, 8, 8)
            col_vlayout.setSpacing(8)

            # Room Header Badge
            header_frame = QFrame()
            header_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {color_info['bg']};
                    border-radius: 6px;
                    padding: 6px;
                }}
            """)
            header_layout = QHBoxLayout(header_frame)
            header_layout.setContentsMargins(8, 4, 8, 4)

            lbl_room_title = QLabel(f"PHÒNG SIÊU ÂM {r}")
            lbl_room_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
            lbl_room_title.setStyleSheet("color: white;")

            lbl_count = QLabel("0 BN")
            lbl_count.setFont(QFont("Segoe UI", 10, QFont.Bold))
            lbl_count.setStyleSheet(
                "color: white; background: rgba(0,0,0,0.3); padding: 2px 8px; border-radius: 4px;"
            )
            self.column_count_labels[room_str] = lbl_count

            header_layout.addWidget(lbl_room_title)
            header_layout.addStretch()
            header_layout.addWidget(lbl_count)

            col_vlayout.addWidget(header_frame)

            # Scroll Area cho danh sách bệnh nhân
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll_content = QWidget()
            scroll_layout = QVBoxLayout(scroll_content)
            scroll_layout.setContentsMargins(4, 4, 4, 4)
            scroll_layout.setSpacing(6)
            scroll_layout.addStretch()
            scroll.setWidget(scroll_content)

            col_vlayout.addWidget(scroll)

            self.column_scroll_layouts[room_str] = scroll_layout
            self.column_widgets[room_str] = col_frame

            columns_layout.addWidget(col_frame, 1)

        main_layout.addLayout(columns_layout, 1)

    def fetch_data_async(self):
        self.lbl_status.setText("⏳ Đang tải dữ liệu...")
        self.worker = QueueFetchWorker()
        self.worker.data_loaded.connect(self.on_data_loaded)
        self.worker.start()

    @Slot(dict)
    def on_data_loaded(self, rooms_data):
        now_str = datetime.now().strftime("%H:%M:%S")
        self.lbl_status.setText(f"Cập nhật lúc {now_str}")

        total_patients = 0

        for r in range(1, 6):
            room_str = str(r)
            data = rooms_data.get(room_str, {})
            scroll_layout = self.column_scroll_layouts[room_str]

            # Clear old items in layout
            while scroll_layout.count() > 0:
                item = scroll_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            current_calling = data.get("current_calling")
            waiting_list = data.get("waiting_list", [])

            room_total = (1 if current_calling else 0) + len(waiting_list)
            total_patients += room_total

            self.column_count_labels[room_str].setText(f"{room_total} BN")

            # 1. Hiển thị Bệnh nhân Đang khám (nếu có)
            if current_calling:
                calling_card = QFrame()
                calling_card.setStyleSheet("""
                    QFrame {
                        background-color: #064e3b;
                        border: 2px solid #10b981;
                        border-radius: 8px;
                    }
                """)
                cc_layout = QVBoxLayout(calling_card)
                cc_layout.setContentsMargins(8, 8, 8, 8)
                cc_layout.setSpacing(4)

                stt = current_calling.get("stt", "---")
                name = current_calling.get("ten_bn", "Chưa rõ")
                ma_bn = current_calling.get("ma_bn", "")
                dich_vu = current_calling.get("dich_vu", "")

                header_row = QHBoxLayout()
                badge_status = QLabel("🟢 ĐANG KHÁM")
                badge_status.setFont(QFont("Segoe UI", 9, QFont.Bold))
                badge_status.setStyleSheet("color: #34d399;")

                stt_lbl = QLabel(f"STT {stt}")
                stt_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
                stt_lbl.setStyleSheet("color: #fbbf24;")

                header_row.addWidget(badge_status)
                header_row.addStretch()
                header_row.addWidget(stt_lbl)
                cc_layout.addLayout(header_row)

                name_lbl = QLabel(name.upper())
                name_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
                name_lbl.setStyleSheet("color: white;")
                name_lbl.setWordWrap(True)
                cc_layout.addWidget(name_lbl)

                if ma_bn:
                    code_lbl = QLabel(f"Mã BN: {ma_bn}")
                    code_lbl.setFont(QFont("Segoe UI", 9))
                    code_lbl.setStyleSheet("color: #94a3b8;")
                    cc_layout.addWidget(code_lbl)

                if dich_vu:
                    dv_clean = dich_vu.replace('\n', ', ')
                    dv_lbl = QLabel(f"DV: {dv_clean}")
                    dv_lbl.setFont(QFont("Segoe UI", 9))
                    dv_lbl.setStyleSheet("color: #cbd5e1;")
                    dv_lbl.setWordWrap(True)
                    cc_layout.addWidget(dv_lbl)

                scroll_layout.addWidget(calling_card)

            # 2. Hiển thị danh sách Đang chờ
            if waiting_list:
                lbl_waiting_title = QLabel(f"⏳ HÀNG CHỜ ({len(waiting_list)})")
                lbl_waiting_title.setFont(QFont("Segoe UI", 9, QFont.Bold))
                lbl_waiting_title.setStyleSheet("color: #94a3b8; margin-top: 6px; margin-bottom: 2px;")
                scroll_layout.addWidget(lbl_waiting_title)

                for idx, pat in enumerate(waiting_list, 1):
                    pat_card = QFrame()
                    pat_card.setStyleSheet("""
                        QFrame {
                            background-color: #0f172a;
                            border: 1px solid #334155;
                            border-radius: 6px;
                        }
                        QFrame:hover {
                            border-color: #38bdf8;
                            background-color: #1e293b;
                        }
                    """)
                    pat_layout = QVBoxLayout(pat_card)
                    pat_layout.setContentsMargins(8, 8, 8, 8)
                    pat_layout.setSpacing(4)

                    stt = pat.get("stt", f"{idx:03d}")
                    name = pat.get("ten_bn", "Bệnh nhân")
                    ma_bn = pat.get("ma_bn", "")
                    tuoi = pat.get("tuoi", "")
                    dich_vu = pat.get("dich_vu", "")

                    top_row = QHBoxLayout()
                    top_row.setSpacing(6)

                    stt_badge = QLabel(f"#{stt}")
                    stt_badge.setFont(QFont("Segoe UI", 10, QFont.Bold))
                    stt_badge.setStyleSheet(
                        "color: #38bdf8; background: #0284c7; padding: 2px 6px; border-radius: 4px;"
                    )

                    name_lbl = QLabel(name)
                    name_lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
                    name_lbl.setStyleSheet("color: #f8fafc;")
                    name_lbl.setWordWrap(True)

                    top_row.addWidget(stt_badge)
                    top_row.addWidget(name_lbl, 1)
                    pat_layout.addLayout(top_row)

                    sub_info = []
                    if ma_bn:
                        sub_info.append(f"Mã: {ma_bn}")
                    if tuoi:
                        sub_info.append(f"Tuổi: {tuoi}")

                    if sub_info:
                        sub_lbl = QLabel(" | ".join(sub_info))
                        sub_lbl.setFont(QFont("Segoe UI", 9))
                        sub_lbl.setStyleSheet("color: #94a3b8;")
                        pat_layout.addWidget(sub_lbl)

                    if dich_vu:
                        dv_clean = dich_vu.replace('\n', ', ')
                        dv_lbl = QLabel(f"DV: {dv_clean}")
                        dv_lbl.setFont(QFont("Segoe UI", 8))
                        dv_lbl.setStyleSheet("color: #64748b;")
                        dv_lbl.setWordWrap(True)
                        pat_layout.addWidget(dv_lbl)

                    scroll_layout.addWidget(pat_card)
            elif not current_calling:
                empty_lbl = QLabel("Chưa có bệnh nhân")
                empty_lbl.setAlignment(Qt.AlignCenter)
                empty_lbl.setFont(QFont("Segoe UI", 10))
                empty_lbl.setStyleSheet("color: #64748b; padding: 20px 0;")
                scroll_layout.addWidget(empty_lbl)

            scroll_layout.addStretch()

        self.lbl_total_count.setText(f"Tổng cộng: {total_patients} BN")

    def closeEvent(self, event):
        if hasattr(self, 'timer') and self.timer:
            self.timer.stop()
        super().closeEvent(event)


# =============================================================================
# PYSIDE6 GUI - KIOSK MODULE
# =============================================================================
class DeletableListWidget(QListWidget):
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in self.selectedItems():
                self.takeItem(self.row(item))
        else:
            super().keyPressEvent(event)

class KioskApp(QWidget):
    # Signal để cập nhật giao diện sau khi đẩy Firestore thành công
    push_success = Signal(str, str, str, list)  # room_num, ten_bn, stt, pushed_services
    push_failed = Signal(str, str)        # room_num, error_msg
    counts_updated = Signal(dict)         # dict room_num -> count

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoQ Kiosk Tiếp đón v4.0 (HIS Bridge + Firestore)")
        self.setMinimumSize(600, 720)
        self.setStyleSheet("""
            QWidget {
                background-color: #121824;
                color: #e2e8f0;
                font-family: "Segoe UI", Arial, sans-serif;
            }
            QLabel {
                font-size: 14px;
                font-weight: 500;
            }
            QLineEdit {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px 12px;
                color: #f1f5f9;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #3b82f6;
            }
            QTextEdit, QListWidget {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px;
                color: #f1f5f9;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 4px;
                border-bottom: 1px solid #1e293b;
            }
            QListWidget::item:hover {
                background-color: #334155;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #3b82f6;
                color: white;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #3b82f6;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:pressed {
                background-color: #1d4ed8;
            }
            QGroupBox {
                border: 1px solid #334155;
                border-radius: 12px;
                margin-top: 15px;
                padding-top: 15px;
                font-weight: bold;
                font-size: 15px;
                color: #3b82f6;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)

        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header Title
        title = QLabel("AUTOQ KIOSK TIẾP ĐÓN")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #3b82f6; margin-bottom: 2px;")
        layout.addWidget(title)

        # === SYSTEM HEALTH MONITOR BAR (Thanh trạng thái các app phụ trợ) ===
        health_bar = QFrame()
        health_bar.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 4px;
            }
            QLabel {
                font-size: 11px;
                font-weight: bold;
            }
        """)
        h_layout = QHBoxLayout(health_bar)
        h_layout.setContentsMargins(8, 4, 8, 4)
        h_layout.setSpacing(6)

        self.badge_chrome = QLabel("🌐 Chrome 9222: ⏳ Check...")
        self.badge_watcher = QLabel("👁 Watcher: ⏳ Check...")
        self.badge_his = QLabel("🏥 HIS Rest: ⏳ Check...")
        self.badge_firestore = QLabel("☁ Firestore: 🟢 OK")

        badge_style_init = "color: #f59e0b; background: #78350f; padding: 3px 6px; border-radius: 4px;"
        self.badge_chrome.setStyleSheet(badge_style_init)
        self.badge_watcher.setStyleSheet(badge_style_init)
        self.badge_his.setStyleSheet(badge_style_init)
        self.badge_firestore.setStyleSheet("color: #10b981; background: #064e3b; padding: 3px 6px; border-radius: 4px;")

        h_layout.addWidget(self.badge_chrome)
        h_layout.addWidget(self.badge_watcher)
        h_layout.addWidget(self.badge_his)
        h_layout.addWidget(self.badge_firestore)
        layout.addWidget(health_bar)

        # 1. Search Box Group
        search_box = QHBoxLayout()
        self.entry_search = QLineEdit()
        self.entry_search.setPlaceholderText("Nhập hoặc quét Mã Bệnh Nhân (Enter)...")
        self.entry_search.setMinimumHeight(45)
        self.entry_search.setFont(QFont("Segoe UI", 12))
        self.entry_search.returnPressed.connect(self.start_lookup)
        
        self.btn_search = QPushButton("Tra cứu (HIS)")
        self.btn_search.setMinimumHeight(45)
        self.btn_search.setStyleSheet("background-color: #10b981;")
        self.btn_search.clicked.connect(self.start_lookup)
        
        search_box.addWidget(self.entry_search)
        search_box.addWidget(self.btn_search)
        layout.addLayout(search_box)

        # 2. Patient Info Group (Có thể nhập thủ công)
        self.group_info = QGroupBox("Thông tin Bệnh nhân (Cho phép nhập tay)")
        info_layout = QVBoxLayout(self.group_info)
        info_layout.setContentsMargins(12, 20, 12, 12)
        info_layout.setSpacing(8)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(8)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        # Cột 0 (label) cố định chiều rộng vừa đủ, cột 1 (input) co giãn tự do
        grid_layout.setColumnStretch(0, 0)
        grid_layout.setColumnStretch(1, 1)

        lbl_ma = QLabel("Mã BN:")
        lbl_ma.setMinimumWidth(70)
        lbl_ma.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid_layout.addWidget(lbl_ma, 0, 0)
        self.edit_ma = QLineEdit()
        self.edit_ma.setMinimumHeight(38)
        self.edit_ma.setFont(QFont("Segoe UI", 11))
        grid_layout.addWidget(self.edit_ma, 0, 1)

        lbl_ten = QLabel("Họ tên:")
        lbl_ten.setMinimumWidth(70)
        lbl_ten.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid_layout.addWidget(lbl_ten, 1, 0)
        self.edit_ten = QLineEdit()
        self.edit_ten.setMinimumHeight(38)
        self.edit_ten.setFont(QFont("Segoe UI", 11))
        grid_layout.addWidget(self.edit_ten, 1, 1)

        lbl_tuoi = QLabel("Tuổi:")
        lbl_tuoi.setMinimumWidth(70)
        lbl_tuoi.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid_layout.addWidget(lbl_tuoi, 2, 0)
        self.edit_tuoi = QLineEdit()
        self.edit_tuoi.setMinimumHeight(38)
        self.edit_tuoi.setFont(QFont("Segoe UI", 11))
        grid_layout.addWidget(self.edit_tuoi, 2, 1)
        
        info_layout.addLayout(grid_layout)

        lbl_dv = QLabel("Các dịch vụ chỉ định (Tích chọn để phân phòng riêng):")
        lbl_dv.setWordWrap(True)
        info_layout.addWidget(lbl_dv)
        self.edit_dich_vu = DeletableListWidget()
        self.edit_dich_vu.setMinimumHeight(100)
        info_layout.addWidget(self.edit_dich_vu)

        # Khung thêm dịch vụ thủ công
        add_service_layout = QHBoxLayout()
        self.edit_new_service = QLineEdit()
        self.edit_new_service.setPlaceholderText("Nhập thêm dịch vụ thủ công...")
        self.edit_new_service.setMinimumHeight(30)
        self.edit_new_service.setFont(QFont("Segoe UI", 9))
        self.edit_new_service.returnPressed.connect(self.add_manual_service)

        self.btn_add_service = QPushButton("+")
        self.btn_add_service.setFixedWidth(40)
        self.btn_add_service.setMinimumHeight(30)
        self.btn_add_service.setStyleSheet("background-color: #3b82f6; font-size: 14px; padding: 0;")
        self.btn_add_service.clicked.connect(self.add_manual_service)

        add_service_layout.addWidget(self.edit_new_service)
        add_service_layout.addWidget(self.btn_add_service)
        info_layout.addLayout(add_service_layout)

        layout.addWidget(self.group_info)

        # 3. Destination Rooms Group (5 buttons)
        group_rooms = QGroupBox("Đẩy bệnh nhân vào phòng siêu âm")
        rooms_layout = QGridLayout(group_rooms)
        rooms_layout.setContentsMargins(15, 20, 15, 15)
        rooms_layout.setSpacing(12)

        # Màu sắc premium cho từng phòng
        room_colors = {
            "1": "background-color: #0284c7; color: white;",
            "2": "background-color: #059669; color: white;",
            "3": "background-color: #7c3aed; color: white;",
            "4": "background-color: #db2777; color: white;",
            "5": "background-color: #d97706; color: white;",
        }

        self.room_buttons = []
        for i in range(1, 6):
            btn = QPushButton(f"PHÒNG SIÊU ÂM {i}")
            btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
            btn.setMinimumHeight(50)
            btn.setStyleSheet(room_colors[str(i)])
            btn.clicked.connect(lambda checked=False, r=str(i): self.push_to_room(r))
            self.room_buttons.append(btn)

        rooms_layout.addWidget(self.room_buttons[0], 0, 0)
        rooms_layout.addWidget(self.room_buttons[1], 0, 1)
        rooms_layout.addWidget(self.room_buttons[2], 1, 0)
        rooms_layout.addWidget(self.room_buttons[3], 1, 1)
        rooms_layout.addWidget(self.room_buttons[4], 2, 0, 1, 2)

        layout.addWidget(group_rooms)

        # 4. Status Bar and logs
        self.status_log = QLabel("He thong dong bo Firestore san sang. Cho quet ma.")
        self.status_log.setFont(QFont("Consolas", 10))
        self.status_log.setStyleSheet(
            "color: #94a3b8; border: 1px solid #1e293b; padding: 8px 10px;"
            "background-color: #0f172a; border-radius: 8px;"
        )
        self.status_log.setWordWrap(True)
        self.status_log.setMinimumHeight(48)
        self.status_log.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.status_log)

        # 5. Nút Xem Danh sách bệnh nhân đã tiếp nhận theo phòng (phía dưới cùng)
        self.btn_patient_list = QPushButton("📋 DANH SÁCH BỆNH NHÂN ĐÃ TIẾP NHẬN (THEO PHÒNG)")
        self.btn_patient_list.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.btn_patient_list.setMinimumHeight(48)
        self.btn_patient_list.setCursor(Qt.PointingHandCursor)
        self.btn_patient_list.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: 1px solid #38bdf8;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #0369a1;
                border-color: #7dd3fc;
            }
            QPushButton:pressed {
                background-color: #075985;
            }
        """)
        self.btn_patient_list.clicked.connect(self.open_patient_list)
        layout.addWidget(self.btn_patient_list)

        # Kết nối Signals
        self.push_success.connect(self.on_push_success)
        self.push_failed.connect(self.on_push_failed)
        self.counts_updated.connect(self.update_room_waiting_counts)

        # Khởi tạo HIS Bridge — thay thế Selenium (tự động ưu tiên ProgramData)
        try:
            his_config = HisConfig.load()
        except Exception:
            his_config = HisConfig.load(None)  # Defaults

        self._bridge = HisBridge(config=his_config, parent=self)
        self._bridge.patient_found.connect(self._on_bridge_patient_found)
        self._bridge.bridge_error.connect(self._on_bridge_error)
        self._bridge.his_connected.connect(self._on_his_status)
        self._bridge.processing.connect(self._on_bridge_processing)
        self._bridge.start()

        # Lưu trạng thái PatientInfo hiện tại
        self._current_patient: PatientInfo | None = None

        # Auto select entry_search
        self.entry_search.setFocus()

        # Khởi chạy Polling đếm số lượng bệnh nhân chờ của các phòng
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.refresh_counts_async)
        self.poll_timer.start(10000)  # Cập nhật mỗi 10 giây
        QTimer.singleShot(500, self.refresh_counts_async)

        # Trạng thái HIS connection
        self._his_connected = False

        # Khởi chạy Timer tự động kiểm tra và phục hồi các App phụ trợ (Chrome Debug, Session Watcher, HIS Bridge)
        self.health_timer = QTimer(self)
        self.health_timer.timeout.connect(self.check_and_heal_subservices)
        self.health_timer.start(10000)  # Kiểm tra mỗi 10 giây
        QTimer.singleShot(1000, self.check_and_heal_subservices)

    def log(self, text):
        now = datetime.now().strftime("%H:%M:%S")
        self.status_log.setText(f"[{now}] {text}")

    def check_and_heal_subservices(self):
        """Kiểm tra và tự động khởi động/tự phục hồi các app phụ trợ (Chrome Debug 9222, Session Watcher, HIS Bridge)."""
        from his_lookup import is_port_open, open_chrome_debug

        # 1. Kiểm tra & Khởi động Chrome Debugging Port 9222
        if is_port_open(9222):
            self.badge_chrome.setText("🌐 Chrome 9222: 🟢 OK")
            self.badge_chrome.setStyleSheet("color: #10b981; background: #064e3b; padding: 3px 6px; border-radius: 4px;")
        else:
            self.badge_chrome.setText("🌐 Chrome 9222: 🟡 Khởi động...")
            self.badge_chrome.setStyleSheet("color: #f59e0b; background: #78350f; padding: 3px 6px; border-radius: 4px;")
            self.log("⚠️ Phát hiện Chrome Debug 9222 chưa mở -> Tự động khởi động Chrome...")
            def launch_chrome():
                if open_chrome_debug():
                    self.log("🟢 Đã mở Chrome Remote Debugging (Port 9222) thành công.")
                else:
                    self.log("🔴 Không thể khởi động Chrome Remote Debugging.")
            threading.Thread(target=launch_chrome, daemon=True).start()

        # 2. Kiểm tra & Khởi động Session Watcher (session_watcher.py)
        if self._is_session_watcher_running():
            self.badge_watcher.setText("👁 Watcher: 🟢 OK")
            self.badge_watcher.setStyleSheet("color: #10b981; background: #064e3b; padding: 3px 6px; border-radius: 4px;")
        else:
            self.badge_watcher.setText("👁 Watcher: 🟡 Khởi động...")
            self.badge_watcher.setStyleSheet("color: #f59e0b; background: #78350f; padding: 3px 6px; border-radius: 4px;")
            self.log("⚠️ Phát hiện Session Watcher chưa chạy -> Tự động kích hoạt session_watcher.py...")
            self._launch_session_watcher()

        # 3. Trạng thái HIS Bridge RestService
        if self._his_connected:
            self.badge_his.setText("🏥 HIS Rest: 🟢 OK")
            self.badge_his.setStyleSheet("color: #10b981; background: #064e3b; padding: 3px 6px; border-radius: 4px;")
        else:
            self.badge_his.setText("🏥 HIS Rest: 🟡 Chờ Session")
            self.badge_his.setStyleSheet("color: #f59e0b; background: #78350f; padding: 3px 6px; border-radius: 4px;")

    def _is_session_watcher_running(self) -> bool:
        """Kiểm tra xem process session_watcher có đang chạy hay không."""
        try:
            import psutil
            for proc in psutil.process_iter(['name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline') or []
                    cmdline_str = " ".join([str(a) for a in cmdline]).lower()
                    if 'session_watcher' in cmdline_str or '--session-watcher' in cmdline_str:
                        return True
                except Exception:
                    continue
        except Exception:
            try:
                output = subprocess.check_output('wmic process get commandline', shell=True, text=True, errors='ignore')
                output_lower = output.lower()
                if 'session_watcher' in output_lower or '--session-watcher' in output_lower:
                    return True
            except Exception:
                pass
        return False

    def _launch_session_watcher(self):
        """Kích hoạt session_watcher ngầm trong background process (hỗ trợ cả Dev Mode lẫn PyInstaller EXE Mode)."""
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            if getattr(sys, 'frozen', False):
                # Trong môi trường đóng gói PyInstaller EXE: khởi chạy file EXE chính kèm cờ --session-watcher
                subprocess.Popen([sys.executable, "--session-watcher"], creationflags=creationflags)
                self.log("🟢 Đã kích hoạt Session Watcher ngầm (môi trường EXE) thành công.")
                return True
            else:
                # Trong môi trường Dev (chạy file .py)
                script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_watcher.py")
                if os.path.exists(script_path):
                    subprocess.Popen([sys.executable, script_path], creationflags=creationflags)
                    self.log("🟢 Đã kích hoạt Session Watcher ngầm (môi trường Dev) thành công.")
                    return True
                else:
                    self.log(f"🔴 Không tìm thấy file script: {script_path}")
        except Exception as e:
            self.log(f"🔴 Lỗi kích hoạt Session Watcher: {e}")
        return False

    def start_lookup(self):
        """Tra cứu bệnh nhân qua HIS Bridge (REST API, không Selenium)."""
        ma_bn = self.entry_search.text().strip()
        if not ma_bn:
            self.log("Vui lòng nhập hoặc quét Mã bệnh nhân!")
            return

        self.log(f"Đang tìm kiếm Mã BN '{ma_bn}' trên VNPT HIS (REST API)...")
        self.btn_search.setEnabled(False)
        self.entry_search.setEnabled(False)

        # Gọi HIS Bridge — async, không block UI
        self._bridge.lookup(ma_bn)

    @Slot(object)
    def _on_bridge_patient_found(self, patient: PatientInfo):
        """Callback khi HIS Bridge tìm thấy bệnh nhân."""
        self.btn_search.setEnabled(True)
        self.entry_search.setEnabled(True)

        # Lưu PatientInfo hiện tại
        self._current_patient = patient

        self.edit_ma.setText(patient.patient_code)
        self.edit_ten.setText(patient.patient_name)
        self.edit_tuoi.setText(str(patient.age) if patient.age else "")
        self.patient_ngay_sinh = ""

        # Cập nhật danh sách dịch vụ
        self.edit_dich_vu.clear()
        service_names = patient.service_names()
        if service_names:
            for s in service_names:
                item = QListWidgetItem(s)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self.edit_dich_vu.addItem(item)
        else:
            item = QListWidgetItem("Không tìm thấy dịch vụ chỉ định")
            self.edit_dich_vu.addItem(item)

        self.log(
            f"Tìm thấy: {patient.patient_name} "
            f"(Tuổi: {patient.age}, {len(patient.services)} dịch vụ)"
        )
        self.entry_search.clear()

    @Slot(str)
    def _on_bridge_error(self, err_msg: str):
        """Callback khi HIS Bridge gặp lỗi."""
        self.btn_search.setEnabled(True)
        self.entry_search.setEnabled(True)
        self.log(f"HIS Bridge: {err_msg}")

        # Cho phép nhập thủ công
        self.edit_ma.setText(self.entry_search.text().strip())
        self.edit_ten.clear()
        self.edit_tuoi.clear()
        self.edit_dich_vu.clear()
        self.patient_ngay_sinh = ""
        self._current_patient = None
        self.edit_ten.setFocus()

    @Slot(bool)
    def _on_his_status(self, connected: bool):
        """Cập nhật trạng thái kết nối HIS trên status bar và System Health Bar."""
        self._his_connected = connected
        if connected:
            self.log("🟢 Đã kết nối VNPT HIS RestService")
            self.badge_his.setText("🏥 HIS Rest: 🟢 OK")
            self.badge_his.setStyleSheet("color: #10b981; background: #064e3b; padding: 3px 6px; border-radius: 4px;")
        else:
            self.log("🔴 Mất kết nối VNPT HIS — kiểm tra mạng hoặc session")
            self.badge_his.setText("🏥 HIS Rest: 🟡 Chờ Session")
            self.badge_his.setStyleSheet("color: #f59e0b; background: #78350f; padding: 3px 6px; border-radius: 4px;")

    @Slot(bool)
    def _on_bridge_processing(self, is_processing: bool):
        """Vô hiệu hóa input khi bridge đang xử lý."""
        self.btn_search.setEnabled(not is_processing)
        self.entry_search.setEnabled(not is_processing)

    def add_manual_service(self):
        text = self.edit_new_service.text().strip()
        if text:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.edit_dich_vu.addItem(item)
            self.edit_new_service.clear()

    def push_to_room(self, room_num):
        ma_bn = self.edit_ma.text().strip()
        ten_bn = self.edit_ten.text().strip()
        tuoi_str = self.edit_tuoi.text().strip()

        # Lấy danh sách dịch vụ được tích chọn hoặc tất cả nếu không tích chọn
        checked_services = []
        all_services = []
        for i in range(self.edit_dich_vu.count()):
            item = self.edit_dich_vu.item(i)
            all_services.append(item.text())
            if item.checkState() == Qt.Checked:
                checked_services.append(item.text())

        if checked_services:
            services_to_push = checked_services
        else:
            services_to_push = all_services

        if not services_to_push:
            QMessageBox.warning(self, "Cảnh báo", "Không có dịch vụ chỉ định nào để đẩy!")
            return

        dich_vu = "\n".join(services_to_push)

        if not ten_bn:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng nhập tên bệnh nhân trước khi đẩy phòng!")
            return

        tuoi = 0
        try:
            if tuoi_str:
                tuoi = int(tuoi_str)
        except ValueError:
            pass

        # Lấy ngay_sinh
        ngay_sinh = getattr(self, "patient_ngay_sinh", "")
        if not ngay_sinh and tuoi_str:
            try:
                # Ước lượng năm sinh từ tuổi
                year = datetime.now().year - int(tuoi_str)
                ngay_sinh = str(year)
            except ValueError:
                pass

        # Vô hiệu hóa các nút đẩy phòng để tránh nhấn lặp
        for btn in self.room_buttons:
            btn.setEnabled(False)
            
        self.log(f"Đang đồng bộ bệnh nhân '{ten_bn}' lên Firestore Phòng {room_num}...")

        # Chạy thao tác ghi Firestore trong luồng riêng biệt
        def run():
            stt = firestore_queue.push_patient(room_num, ma_bn, ten_bn, tuoi, ngay_sinh, dich_vu)
            if stt:
                self.push_success.emit(room_num, ten_bn, stt, services_to_push)
            else:
                self.push_failed.emit(room_num, "Lỗi kết nối Firestore Cloud hoặc Security Rules.")

        threading.Thread(target=run, daemon=True).start()

    @Slot(str, str, str, list)
    def on_push_success(self, room_num, ten_bn, stt, pushed_services):
        # Kích hoạt lại các nút phòng
        for btn in self.room_buttons:
            btn.setEnabled(True)
            
        self.log(f"Đồng bộ THÀNH CÔNG! Đã đẩy BN '{ten_bn}' vào PHÒNG {room_num} - STT: {stt}")
        
        # Xóa các dịch vụ đã đẩy thành công khỏi danh sách hiển thị
        for s in pushed_services:
            for i in range(self.edit_dich_vu.count()):
                item = self.edit_dich_vu.item(i)
                if item and item.text() == s:
                    self.edit_dich_vu.takeItem(i)
                    break

        # Nếu không còn dịch vụ nào, xóa sạch thông tin cũ để quét bệnh nhân tiếp theo
        if self.edit_dich_vu.count() == 0:
            self.edit_ma.clear()
            self.edit_ten.clear()
            self.edit_tuoi.clear()
            self.edit_dich_vu.clear()
            self.patient_ngay_sinh = ""
            self.entry_search.clear()
            self.entry_search.setFocus()
        else:
            # Nếu vẫn còn dịch vụ chưa đẩy, giữ lại thông tin bệnh nhân và chỉ làm sạch ô tìm kiếm
            self.entry_search.clear()
            self.entry_search.setFocus()

        # Cập nhật ngay số lượng chờ trên các nút phòng
        self.refresh_counts_async()

    def refresh_counts_async(self):
        def run():
            counts = {}
            for i in range(1, 6):
                try:
                    q = firestore_queue.get_room_queue(str(i))
                    if q and "waiting_list" in q:
                        counts[str(i)] = len(q["waiting_list"])
                    else:
                        counts[str(i)] = 0
                except Exception:
                    counts[str(i)] = 0
            self.counts_updated.emit(counts)

        threading.Thread(target=run, daemon=True).start()

    @Slot(dict)
    def update_room_waiting_counts(self, counts):
        for i in range(1, 6):
            btn = self.room_buttons[i - 1]
            cnt = counts.get(str(i), 0)
            btn.setText(f"PHÒNG SIÊU ÂM {i} (còn {cnt} BN)")

    @Slot(str, str)
    def on_push_failed(self, room_num, error_msg):
        # Kích hoạt lại các nút phòng
        for btn in self.room_buttons:
            btn.setEnabled(True)
            
        self.log(f"Đồng bộ THẤT BẠI: {error_msg}")
        QMessageBox.critical(self, "Lỗi đồng bộ", f"Không thể lưu lên cơ sở dữ liệu Cloud của Phòng {room_num}.\nChi tiết: {error_msg}")

    def open_patient_list(self):
        """Mở cửa sổ hiển thị danh sách bệnh nhân tiếp nhận theo 5 phòng."""
        dlg = PatientQueueDialog(parent=self)
        dlg.exec()

    def closeEvent(self, event):
        """Dừng HIS Bridge worker khi đóng cửa sổ."""
        if hasattr(self, "_bridge"):
            self._bridge.stop()
        super().closeEvent(event)

if __name__ == "__main__":
    if "--session-watcher" in sys.argv:
        import session_watcher
        session_watcher.main()
    else:
        # High DPI scaling configuration
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        app = QApplication(sys.argv)
        kiosk = KioskApp()
        kiosk.show()
        sys.exit(app.exec())
