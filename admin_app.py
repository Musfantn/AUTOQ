import sys
import csv
import time
import threading
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget, QFileDialog, QMessageBox,
    QProgressBar, QScrollArea, QInputDialog, QDialog, QLineEdit, QFormLayout
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont

import firestore_queue
from firestore_client import firestore_list, doc_to_dict, doc_id_from_name
from speaker_hub import (
    ALL_ROOM_IDS,
    ROOM_DEFINITIONS,
    get_room_display_name,
    get_room_short_name,
)


# =============================================================================
# LỊCH LÀM VIỆC MÙA ĐÔNG (16/10 - 15/04) & MÙA HÈ (16/04 - 15/10)
# =============================================================================

def is_winter_season(dt: datetime | None = None) -> bool:
    """Kiểm tra ngày hiện tại có thuộc lịch làm việc Mùa Đông (16/10 đến 15/04 hàng năm) hay không."""
    dt = dt or datetime.now()
    m, d = dt.month, dt.day
    if (m == 10 and d >= 16) or m in (11, 12, 1, 2, 3) or (m == 4 and d <= 15):
        return True
    return False


def get_seasonal_shift_config(dt: datetime | None = None, force_season: str = "AUTO") -> dict:
    """Trả về cấu hình khung giờ Ca Sáng / Ca Chiều / Ca Trực Đêm chính xác theo mùa:
    - Mùa Đông (16/10 - 15/04): Ca Sáng (07:00 - 11:30), Ca Chiều (13:30 - 17:00), Ca Trực Đêm (17:00 - 07:00)
    - Mùa Hè   (16/04 - 15/10): Ca Sáng (07:00 - 11:30), Ca Chiều (14:00 - 17:30), Ca Trực Đêm (17:30 - 07:00)
    """
    if force_season == "WINTER":
        winter = True
    elif force_season == "SUMMER":
        winter = False
    else:
        winter = is_winter_season(dt)

    if winter:
        return {
            "is_winter": True,
            "season_badge": "❄️ LỊCH MÙA ĐÔNG (16/10 - 15/04)",
            "morning_label": "Ca Sáng Mùa Đông (07:00 - 11:30)",
            "afternoon_label": "Ca Chiều Mùa Đông (13:30 - 17:00)",
            "night_label": "Ca Trực Đêm Mùa Đông (17:00 - 07:00)",
            "morning_start_min": 7 * 60,           # 07:00
            "morning_end_min": 11 * 60 + 30,       # 11:30
            "afternoon_start_min": 13 * 60 + 30,   # 13:30
            "afternoon_end_min": 17 * 60,          # 17:00
            "night_start_min": 17 * 60,            # 17:00
        }
    else:
        return {
            "is_winter": False,
            "season_badge": "☀️ LỊCH MÙA HÈ (16/04 - 15/10)",
            "morning_label": "Ca Sáng Mùa Hè (07:00 - 11:30)",
            "afternoon_label": "Ca Chiều Mùa Hè (14:00 - 17:30)",
            "night_label": "Ca Trực Đêm Mùa Hè (17:30 - 07:00)",
            "morning_start_min": 7 * 60,           # 07:00
            "morning_end_min": 11 * 60 + 30,       # 11:30
            "afternoon_start_min": 14 * 60,        # 14:00
            "afternoon_end_min": 17 * 60 + 30,     # 17:30
            "night_start_min": 17 * 60 + 30,       # 17:30
        }


def extract_first_case_time_str(q_data: dict) -> str:
    """Trích xuất thời gian bắt đầu làm ca bệnh đầu tiên trong ngày của phòng (HH:MM:SS)."""
    if not q_data:
        return "---"
    candidates: list[float] = []

    fc = float(q_data.get("first_call_at") or 0.0)
    if fc > 0:
        candidates.append(fc)

    for item in q_data.get("history", []) or []:
        ts = float(item.get("called_at") or item.get("timestamp") or 0.0)
        if ts > 0:
            candidates.append(ts)

    for item in q_data.get("missed_list", []) or []:
        ts = float(item.get("called_at") or item.get("timestamp") or 0.0)
        if ts > 0:
            candidates.append(ts)

    curr = q_data.get("current_calling")
    if curr and isinstance(curr, dict) and curr.get("stt"):
        ts = float(curr.get("called_at") or curr.get("timestamp") or 0.0)
        if ts > 0:
            candidates.append(ts)

    if not candidates:
        return "---"
    earliest = min(candidates)
    return datetime.fromtimestamp(earliest).strftime("%H:%M:%S")


# =============================================================================
# HỘP THOẠI ĐĂNG NHẬP & ĐỔI MẬT KHẨU ADMIN (LƯU TRÊN CLOUD FIRESTORE)
# =============================================================================

class AdminLoginDialog(QDialog):
    """Hộp thoại yêu cầu nhập mật khẩu trước khi truy cập Admin Center."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Đăng Nhập Quản Trị Hệ Thống AUTOQ")
        self.setFixedSize(420, 260)
        self.setStyleSheet("""
            QDialog { background-color: #0f172a; color: #f1f5f9; font-family: "Segoe UI", Arial; }
            QLabel { color: #e2e8f0; font-size: 13px; }
            QLineEdit {
                background-color: #1e293b; border: 2px solid #334155; border-radius: 6px;
                padding: 8px 12px; color: #ffffff; font-size: 15px; font-weight: bold;
            }
            QLineEdit:focus { border: 2px solid #38bdf8; }
            QPushButton {
                background-color: #0284c7; color: white; font-weight: bold;
                border: none; border-radius: 6px; padding: 10px 16px; font-size: 14px;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        lbl_head = QLabel("🔐 XÁC THỰC QUẢN TRỊ VIÊN (ADMIN)")
        lbl_head.setAlignment(Qt.AlignCenter)
        lbl_head.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(lbl_head)

        lbl_desc = QLabel("Vui lòng nhập mật khẩu quản trị để truy cập trung tâm kiểm soát:")
        lbl_desc.setAlignment(Qt.AlignCenter)
        lbl_desc.setStyleSheet("font-size: 12px; color: #94a3b8;")
        layout.addWidget(lbl_desc)

        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.setPlaceholderText("Nhập mật khẩu Admin...")
        self.txt_password.returnPressed.connect(self.verify_password)
        layout.addWidget(self.txt_password)

        self.lbl_error = QLabel("")
        self.lbl_error.setAlignment(Qt.AlignCenter)
        self.lbl_error.setStyleSheet("font-size: 12px; color: #ef4444; font-weight: bold;")
        layout.addWidget(self.lbl_error)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Thoát")
        btn_cancel.setStyleSheet("background-color: #475569;")
        btn_cancel.clicked.connect(self.reject)

        self.btn_login = QPushButton("ĐĂNG NHẬP")
        self.btn_login.clicked.connect(self.verify_password)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_login, 1)
        layout.addLayout(btn_row)

        self._expected_password = firestore_queue.DEFAULT_ADMIN_PASSWORD
        threading.Thread(target=self._prefetch_cloud_password, daemon=True).start()

    def _prefetch_cloud_password(self):
        try:
            self._expected_password = firestore_queue.get_admin_password()
        except Exception:
            pass

    def verify_password(self):
        entered = self.txt_password.text().strip()
        if not entered:
            self.lbl_error.setText("⚠️ Vui lòng nhập mật khẩu!")
            return

        # Kiểm tra lại trên Firestore nếu chưa khớp cache
        if entered != self._expected_password:
            self._expected_password = firestore_queue.get_admin_password()

        if entered == self._expected_password:
            self.accept()
        else:
            self.lbl_error.setText("❌ Mật khẩu không chính xác! Vui lòng thử lại.")
            self.txt_password.selectAll()
            self.txt_password.setFocus()


class AdminChangePasswordDialog(QDialog):
    """Hộp thoại đổi mật khẩu Admin và đồng bộ lên Cloud Firestore."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Đổi Mật Khẩu Quản Trị (Lưu Cloud Firestore)")
        self.setFixedSize(440, 290)
        self.setStyleSheet("""
            QDialog { background-color: #0f172a; color: #f1f5f9; font-family: "Segoe UI", Arial; }
            QLabel { color: #e2e8f0; font-size: 13px; font-weight: bold; }
            QLineEdit {
                background-color: #1e293b; border: 1px solid #334155; border-radius: 6px;
                padding: 7px 10px; color: #ffffff; font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #38bdf8; }
            QPushButton {
                background-color: #059669; color: white; font-weight: bold;
                border: none; border-radius: 6px; padding: 9px 16px; font-size: 13px;
            }
            QPushButton:hover { background-color: #047857; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("🔑 ĐỔI MẬT KHẨU QUẢN TRỊ ADMIN")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        self.txt_old = QLineEdit()
        self.txt_old.setEchoMode(QLineEdit.Password)
        self.txt_old.setPlaceholderText("Nhập mật khẩu hiện tại")

        self.txt_new = QLineEdit()
        self.txt_new.setEchoMode(QLineEdit.Password)
        self.txt_new.setPlaceholderText("Nhập mật khẩu mới")

        self.txt_confirm = QLineEdit()
        self.txt_confirm.setEchoMode(QLineEdit.Password)
        self.txt_confirm.setPlaceholderText("Nhập lại mật khẩu mới")

        form.addRow("Mật khẩu cũ:", self.txt_old)
        form.addRow("Mật khẩu mới:", self.txt_new)
        form.addRow("Xác nhận mới:", self.txt_confirm)
        layout.addLayout(form)

        self.lbl_msg = QLabel("")
        self.lbl_msg.setAlignment(Qt.AlignCenter)
        self.lbl_msg.setStyleSheet("font-size: 12px; color: #ef4444;")
        layout.addWidget(self.lbl_msg)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.setStyleSheet("background-color: #475569;")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("💾 LƯU LÊN FIRESTORE")
        btn_save.clicked.connect(self.save_new_password)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save, 1)
        layout.addLayout(btn_row)

    def save_new_password(self):
        old_p = self.txt_old.text().strip()
        new_p = self.txt_new.text().strip()
        cnf_p = self.txt_confirm.text().strip()

        if not old_p or not new_p:
            self.lbl_msg.setText("⚠️ Vui lòng nhập đầy đủ mật khẩu hiện tại và mật khẩu mới!")
            return
        if new_p != cnf_p:
            self.lbl_msg.setText("❌ Mật khẩu xác nhận không khớp!")
            return

        current_cloud_pwd = firestore_queue.get_admin_password()
        if old_p != current_cloud_pwd:
            self.lbl_msg.setText("❌ Mật khẩu hiện tại không đúng!")
            return

        ok = firestore_queue.set_admin_password(new_p)
        if ok:
            QMessageBox.information(
                self,
                "Thành công",
                "Đã đổi mật khẩu Admin và đồng bộ lên Cloud Firestore thành công!",
            )
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Đã lưu cục bộ",
                "Đã lưu mật khẩu mới vào bộ nhớ cục bộ (hiện không kết nối được Cloud Firestore).",
            )
            self.accept()


# =============================================================================
# ADMIN & MONITORING APP - MODULE QUẢN TRỊ & KIỂM SOÁT LƯỢNG BỆNH NHÂN CÁC PHÒNG
# =============================================================================

class AdminApp(QMainWindow):
    rooms_data_updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            "AUTOQ ADMIN CENTER - KIỂM SOÁT LƯỢNG BỆNH NHÂN & BÁO CÁO (11 PHÒNG SIÊU ÂM, NỘI SOI & THĂM DÒ CHỨC NĂNG)"
        )
        self.resize(1260, 840)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0f172a;
                color: #e2e8f0;
                font-family: "Segoe UI", Arial, sans-serif;
            }
            QTabWidget::pane {
                border: 1px solid #334155;
                border-radius: 8px;
                background-color: #0f172a;
            }
            QTabBar::tab {
                background: #1e293b;
                color: #94a3b8;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #0284c7;
                color: white;
            }
            QPushButton {
                background-color: #0284c7;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QComboBox {
                background-color: #1e293b;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 6px 10px;
                color: #f8fafc;
                font-size: 13px;
                font-weight: bold;
            }
            QComboBox QAbstractItemView {
                background-color: #1e293b;
                color: #f8fafc;
                border: 2px solid #38bdf8;
                selection-background-color: #0284c7;
                selection-color: #ffffff;
                outline: 0px;
                padding: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QComboBox QAbstractItemView::item {
                background-color: #1e293b;
                color: #f8fafc;
                min-height: 30px;
                padding: 5px 10px;
            }
            QComboBox QAbstractItemView::item:hover,
            QComboBox QAbstractItemView::item:selected {
                background-color: #0284c7;
                color: #ffffff;
            }
            QTableWidget {
                background-color: #1e293b;
                border: 1px solid #334155;
                gridline-color: #334155;
                color: #f1f5f9;
                font-size: 12px;
                border-radius: 8px;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QHeaderView::section {
                background-color: #0f172a;
                color: #38bdf8;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #334155;
                padding: 6px;
            }
            QProgressBar {
                border: 1px solid #334155;
                border-radius: 5px;
                text-align: center;
                background-color: #0f172a;
                color: white;
                font-weight: bold;
                font-size: 11px;
                min-height: 18px;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 4px;
            }
        """)

        self.all_rooms_cache = {}
        self._is_polling = False

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # Header Title Bar
        header_box = QHBoxLayout()
        lbl_title = QLabel(
            "🏥 AUTOQ ADMIN - KIỂM SOÁT LƯỢNG BỆNH NHÂN (SIÊU ÂM, NỘI SOI TMH, NỘI SOI TIÊU HÓA, ĐTĐ, ĐNĐ, LHN, CNHH)"
        )
        lbl_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lbl_title.setStyleSheet("color: #38bdf8;")

        self.lbl_season_badge = QLabel("")
        self.lbl_season_badge.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #fbbf24; background: #1e293b; "
            "border: 1px solid #475569; border-radius: 6px; padding: 4px 10px;"
        )

        self.btn_change_pwd = QPushButton("🔑 Đổi mật khẩu")
        self.btn_change_pwd.setStyleSheet(
            "background-color: #334155; color: #f8fafc; font-size: 12px; padding: 6px 12px; border-radius: 6px;"
        )
        self.btn_change_pwd.clicked.connect(self.open_change_password_dialog)

        self.lbl_clock = QLabel("")
        self.lbl_clock.setFont(QFont("Consolas", 12, QFont.Bold))
        self.lbl_clock.setStyleSheet("color: #10b981;")

        header_box.addWidget(lbl_title, 1)
        header_box.addWidget(self.lbl_season_badge)
        header_box.addWidget(self.btn_change_pwd)
        header_box.addWidget(self.lbl_clock)
        main_layout.addLayout(header_box)

        # Tabs Container
        self.tabs = QTabWidget()

        self.tab_monitor = QWidget()
        self._init_monitor_tab()
        self.tabs.addTab(self.tab_monitor, "🖥 Giám Sát Lượng Bệnh Nhân Realtime (11 Phòng)")

        self.tab_report = QWidget()
        self._init_report_tab()
        self.tabs.addTab(self.tab_report, "📊 Thống Kê Sản Lượng & Xuất Báo Cáo")

        main_layout.addWidget(self.tabs)
        self.setCentralWidget(main_widget)

        self.rooms_data_updated.connect(self.on_rooms_data_updated)

        self.timer_clock = QTimer(self)
        self.timer_clock.timeout.connect(self._update_clock)
        self.timer_clock.start(1000)
        self._update_clock()

        self.timer_poll = QTimer(self)
        self.timer_poll.timeout.connect(self.poll_all_rooms_async)
        self.timer_poll.start(3000)
        QTimer.singleShot(100, self.poll_all_rooms_async)

    def _update_clock(self):
        now = datetime.now()
        now_str = now.strftime("%d/%m/%Y %H:%M:%S")
        self.lbl_clock.setText(f"⏱️ {now_str}")
        scfg = get_seasonal_shift_config(now)
        self.lbl_season_badge.setText(scfg["season_badge"])

    def open_change_password_dialog(self):
        dlg = AdminChangePasswordDialog(self)
        dlg.exec()

    # =========================================================================
    # TAB 1: GIÁM SÁT LƯỢNG BỆNH NHÂN REALTIME 5 PHÒNG SIÊU ÂM
    # =========================================================================
    def _init_monitor_tab(self):
        layout = QVBoxLayout(self.tab_monitor)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Summary Metrics Bar
        summary_box = QFrame()
        summary_box.setStyleSheet("background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 6px;")
        s_layout = QHBoxLayout(summary_box)
        s_layout.setContentsMargins(12, 8, 12, 8)
        s_layout.setSpacing(15)

        self.card_total_bn = self._create_metric_widget("📊 Tổng Lượt Gọi Toàn Khoa", "0", "#38bdf8")
        self.card_completed_bn = self._create_metric_widget("✅ Đã Hoàn Thành Khám", "0", "#10b981")
        self.card_missed_bn = self._create_metric_widget("⏳ Qua Lượt / Chưa Vào", "0", "#f59e0b")
        self.card_emergency_bn = self._create_metric_widget("🚨 Phòng Đang Cấp Cứu", "0", "#ef4444")
        self.card_avg_time = self._create_metric_widget("⏱️ Thời Gian Khám TB", "0.0 phút", "#a855f7")

        s_layout.addWidget(self.card_total_bn)
        s_layout.addWidget(self.card_completed_bn)
        s_layout.addWidget(self.card_missed_bn)
        s_layout.addWidget(self.card_emergency_bn)
        s_layout.addWidget(self.card_avg_time)
        layout.addWidget(summary_box)

        # 5 Room Cards Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        grid = QGridLayout(scroll_content)
        grid.setSpacing(14)

        self.room_cards = {}
        for idx, r_id in enumerate(ALL_ROOM_IDS):
            card = self._create_room_card_widget(r_id)
            row = idx // 3
            col = idx % 3
            grid.addWidget(card["frame"], row, col)
            self.room_cards[r_id] = card

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

    def _create_metric_widget(self, title, init_val, color_hex):
        box = QWidget()
        box.setStyleSheet("background: transparent; border: none;")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 12px; color: #94a3b8; font-weight: bold;")

        lbl_v = QLabel(init_val)
        lbl_v.setStyleSheet(f"font-size: 22px; color: {color_hex}; font-weight: bold;")

        v.addWidget(lbl_t)
        v.addWidget(lbl_v)
        box.lbl_val = lbl_v
        return box

    def _create_room_card_widget(self, room_id: str):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
            }
        """)
        f_layout = QVBoxLayout(frame)
        f_layout.setContentsMargins(14, 12, 14, 12)
        f_layout.setSpacing(8)

        # Header Row: Room Name & Status Badge
        top_row = QHBoxLayout()
        lbl_name = QLabel(get_room_display_name(room_id))
        lbl_name.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8; border: none;")

        badge_status = QLabel("☀️ HOẠT ĐỘNG")
        badge_status.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: white; background: #059669; padding: 3px 8px; border-radius: 4px; border: none;"
        )

        top_row.addWidget(lbl_name, 1)
        top_row.addWidget(badge_status)
        f_layout.addLayout(top_row)

        # Current Calling Number Box
        curr_box = QFrame()
        curr_box.setStyleSheet("background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 8px;")
        c_layout = QVBoxLayout(curr_box)
        c_layout.setContentsMargins(8, 6, 8, 6)
        c_layout.setSpacing(4)

        lbl_curr_head = QLabel("▶ SỐ THỨ TỰ ĐANG GỌI:")
        lbl_curr_head.setStyleSheet("font-size: 11px; font-weight: bold; color: #94a3b8; border: none;")

        lbl_curr_pat = QLabel("000")
        lbl_curr_pat.setAlignment(Qt.AlignCenter)
        lbl_curr_pat.setStyleSheet("font-size: 36px; font-weight: bold; color: #38bdf8; border: none;")

        lbl_curr_sub = QLabel("Trạng thái: Chờ gọi số")
        lbl_curr_sub.setAlignment(Qt.AlignCenter)
        lbl_curr_sub.setStyleSheet("font-size: 12px; color: #94a3b8; border: none;")

        c_layout.addWidget(lbl_curr_head)
        c_layout.addWidget(lbl_curr_pat)
        c_layout.addWidget(lbl_curr_sub)
        f_layout.addWidget(curr_box)

        # Load Balance Progress Bar (Tỷ trọng lượng bệnh nhân của phòng)
        load_bar = QProgressBar()
        load_bar.setRange(0, 100)
        load_bar.setValue(0)
        load_bar.setFormat("Tải lượng phòng: 0 ca (0%)")
        f_layout.addWidget(load_bar)

        # Room Stats Summary
        lbl_stats = QLabel("🔢 Số cao nhất: 000 | ✅ Đã khám: 0 | ⏳ Qua lượt: 0 | ⏱️ TB: 0.0p")
        lbl_stats.setStyleSheet("font-size: 12px; font-weight: bold; color: #cbd5e1; border: none;")
        f_layout.addWidget(lbl_stats)

        # Admin Quick Control Row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)

        btn_set_room = QPushButton("🔢 Đặt số")
        btn_set_room.setStyleSheet("background: #2563eb; padding: 5px 10px; font-size: 12px;")
        btn_set_room.clicked.connect(lambda checked=False, r=room_id: self.admin_set_room_number(r))

        btn_reset_room = QPushButton("🔄 Reset phòng")
        btn_reset_room.setStyleSheet("background: #475569; padding: 5px 10px; font-size: 12px;")
        btn_reset_room.clicked.connect(lambda checked=False, r=room_id: self.admin_reset_room(r))

        ctrl_row.addWidget(btn_set_room)
        ctrl_row.addWidget(btn_reset_room)
        f_layout.addLayout(ctrl_row)

        return {
            "frame": frame,
            "name": lbl_name,
            "badge": badge_status,
            "curr_pat": lbl_curr_pat,
            "curr_sub": lbl_curr_sub,
            "load_bar": load_bar,
            "stats": lbl_stats,
        }

    # =========================================================================
    # TAB 2: THỐNG KÊ SẢN LƯỢNG & XUẤT BÁO CÁO
    # =========================================================================
    def _init_report_tab(self):
        layout = QVBoxLayout(self.tab_report)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Filter Control Bar
        filter_box = QFrame()
        filter_box.setStyleSheet("background: #1e293b; border: 1px solid #334155; border-radius: 8px;")
        fl_layout = QHBoxLayout(filter_box)
        fl_layout.setContentsMargins(10, 8, 10, 8)
        fl_layout.setSpacing(10)

        fl_layout.addWidget(QLabel("Chọn Phòng:"))
        self.cbo_room_filter = QComboBox()
        self.cbo_room_filter.addItem("Tất cả các phòng (11 phòng)", "ALL")
        for r_id in ALL_ROOM_IDS:
            self.cbo_room_filter.addItem(ROOM_DEFINITIONS[r_id]["combo_label"], r_id)
        self.cbo_room_filter.currentIndexChanged.connect(self.apply_report_filter)
        fl_layout.addWidget(self.cbo_room_filter)

        fl_layout.addWidget(QLabel("Lịch Mùa:"))
        self.cbo_season_mode = QComboBox()
        self.cbo_season_mode.addItem("🔄 Tự động theo ngày (16/10-15/04: Đông)", "AUTO")
        self.cbo_season_mode.addItem("❄️ Lịch Mùa Đông (16/10 - 15/04)", "WINTER")
        self.cbo_season_mode.addItem("☀️ Lịch Mùa Hè (16/04 - 15/10)", "SUMMER")
        self.cbo_season_mode.currentIndexChanged.connect(self._on_season_mode_changed)
        fl_layout.addWidget(self.cbo_season_mode)

        fl_layout.addWidget(QLabel("Ca làm việc:"))
        self.cbo_shift_filter = QComboBox()
        self._populate_shift_filter_options()
        self.cbo_shift_filter.currentIndexChanged.connect(self.apply_report_filter)
        fl_layout.addWidget(self.cbo_shift_filter)

        btn_refresh = QPushButton("🔄 LÀM MỚI DỮ LIỆU")
        btn_refresh.setStyleSheet("background-color: #0284c7;")
        btn_refresh.clicked.connect(self.poll_all_rooms_async)
        fl_layout.addWidget(btn_refresh)

        btn_excel = QPushButton("📥 XUẤT EXCEL / CSV")
        btn_excel.setStyleSheet("background-color: #059669;")
        btn_excel.clicked.connect(self.export_excel_csv)
        fl_layout.addWidget(btn_excel)

        btn_print_pdf = QPushButton("📄 XUẤT BÁO CÁO TỔNG HỢP TXT")
        btn_print_pdf.setStyleSheet("background-color: #7c3aed;")
        btn_print_pdf.clicked.connect(self.export_text_summary_report)
        fl_layout.addWidget(btn_print_pdf)

        layout.addWidget(filter_box)

        # Split Layout: Detailed Calls Table (Left) + Room Load Summary Table (Right)
        split_layout = QHBoxLayout()
        split_layout.setSpacing(10)

        self.table_patients = QTableWidget()
        self.table_patients.setColumnCount(7)
        self.table_patients.setHorizontalHeaderLabels([
            "Phòng", "Số Thứ Tự (STT)", "Trạng thái", "Số lần gọi loa",
            "Thời điểm gọi", "Thời điểm hoàn thành", "Thời gian khám (phút)"
        ])
        header = self.table_patients.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)

        split_layout.addWidget(self.table_patients, 2)

        # Side Box: Thống kê lượng bệnh nhân theo từng phòng (kèm giờ bắt đầu ca đầu tiên)
        side_box = QFrame()
        side_box.setFixedWidth(495)
        side_box.setStyleSheet("background: #1e293b; border: 1px solid #334155; border-radius: 8px;")
        sd_layout = QVBoxLayout(side_box)
        sd_layout.setContentsMargins(10, 10, 10, 10)
        sd_layout.setSpacing(8)

        lbl_side_title = QLabel("📊 THỐNG KÊ LƯỢNG BN & GIỜ BẮT ĐẦU CA ĐẦU TIÊN")
        lbl_side_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        lbl_side_title.setStyleSheet("color: #38bdf8; border: none;")
        sd_layout.addWidget(lbl_side_title)

        self.table_room_summary = QTableWidget()
        self.table_room_summary.setColumnCount(6)
        self.table_room_summary.setHorizontalHeaderLabels([
            "Phòng", "Ca đầu tiên", "Số hiện tại", "Đã khám", "Qua lượt", "TB (phút)"
        ])
        self.table_room_summary.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        sd_layout.addWidget(self.table_room_summary)

        split_layout.addWidget(side_box, 1)
        layout.addLayout(split_layout, 1)

    def _populate_shift_filter_options(self):
        """Cập nhật danh sách Ca làm việc chính xác theo lịch Mùa Đông (16/10-16/04) hoặc Mùa Hè (17/04-15/10)."""
        prev_code = self.cbo_shift_filter.currentData() if hasattr(self, "cbo_shift_filter") else "ALL"
        season_mode = self.cbo_season_mode.currentData() if hasattr(self, "cbo_season_mode") else "AUTO"
        scfg = get_seasonal_shift_config(datetime.now(), force_season=season_mode or "AUTO")

        self.cbo_shift_filter.blockSignals(True)
        self.cbo_shift_filter.clear()
        self.cbo_shift_filter.addItem("Cả ngày (Tất cả ca)", "ALL")
        self.cbo_shift_filter.addItem(scfg["morning_label"], "MORNING")
        self.cbo_shift_filter.addItem(scfg["afternoon_label"], "AFTERNOON")
        self.cbo_shift_filter.addItem(scfg["night_label"], "NIGHT")

        idx = self.cbo_shift_filter.findData(prev_code)
        self.cbo_shift_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.cbo_shift_filter.blockSignals(False)

    def _on_season_mode_changed(self):
        self._populate_shift_filter_options()
        self.apply_report_filter()

    # =========================================================================
    # POLLING & ADMIN ACTIONS (HỖ TRỢ 11 PHÒNG)
    # =========================================================================
    def poll_all_rooms_async(self):
        if self._is_polling:
            return
        self._is_polling = True

        def run():
            try:
                today_str = datetime.now().strftime("%Y-%m-%d")
                data_all = {}
                try:
                    docs = firestore_list("autoq_queues", page_size=30)
                    for raw_doc in docs:
                        doc_id = doc_id_from_name(raw_doc)
                        if doc_id.startswith("room_"):
                            r_id = doc_id.replace("room_", "").strip().lower()
                            if r_id in ROOM_DEFINITIONS:
                                parsed = doc_to_dict(raw_doc)
                                if parsed.get("date") == today_str:
                                    data_all[r_id] = firestore_queue._ensure_schema(parsed, r_id)
                except Exception as e:
                    print(f"[AdminApp] Lỗi đọc danh sách phòng: {e}")

                for r_id in ALL_ROOM_IDS:
                    if r_id not in data_all:
                        data_all[r_id] = firestore_queue._new_queue(r_id, today_str)

                self.rooms_data_updated.emit(data_all)
            finally:
                self._is_polling = False

        threading.Thread(target=run, daemon=True).start()

    def admin_set_room_number(self, room_id: str):
        r_str = str(room_id).strip().lower()
        r_title = get_room_display_name(r_str)
        r_data = self.all_rooms_cache.get(r_str, {})
        cur_last = int(r_data.get("last_number", 1) or 1)
        n, ok = QInputDialog.getInt(
            self,
            f"Đặt số thứ tự — {r_title}",
            f"Nhập số thứ tự muốn gọi cho {r_title}:",
            value=max(1, cur_last),
            minValue=1,
            maxValue=999,
        )
        if ok:
            def run():
                firestore_queue.set_number(r_str, n)
                self.poll_all_rooms_async()
            threading.Thread(target=run, daemon=True).start()

    def admin_reset_room(self, room_id: str):
        r_str = str(room_id).strip().lower()
        r_title = get_room_display_name(r_str)
        ans = QMessageBox.question(
            self,
            "Xác nhận Reset Phòng",
            f"Bạn có chắc chắn muốn Reset toàn bộ số thứ tự của {r_title} về 000?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            def run():
                firestore_queue.reset_queue(r_str)
                self.poll_all_rooms_async()
            threading.Thread(target=run, daemon=True).start()

    @Slot(dict)
    def on_rooms_data_updated(self, data_all):
        self.all_rooms_cache = data_all

        total_bn_cnt = 0
        completed_bn_cnt = 0
        missed_bn_cnt = 0
        emergency_bn_cnt = 0
        total_exam_time_sec = 0
        total_exam_cases = 0

        room_loads = {}
        for r_str in ALL_ROOM_IDS:
            q_data = data_all.get(r_str, {})
            curr = q_data.get("current_calling")
            missed = q_data.get("missed_list", [])
            history = q_data.get("history", [])
            has_curr = 1 if (curr and curr.get("stt") and curr.get("stt") != "CC") else 0
            r_total = len(history) + len(missed) + has_curr
            room_loads[r_str] = r_total
            total_bn_cnt += r_total
            completed_bn_cnt += len(history)
            missed_bn_cnt += len(missed)

        for r_str in ALL_ROOM_IDS:
            q_data = data_all.get(r_str, {})
            card = self.room_cards.get(r_str)
            if not card:
                continue

            curr = q_data.get("current_calling")
            missed = q_data.get("missed_list", [])
            history = q_data.get("history", [])
            last_number = int(q_data.get("last_number", 0))

            c_missed = len(missed)
            c_history = len(history)

            r_exam_secs = [h.get("exam_duration_sec", 0) for h in history if h.get("exam_duration_sec", 0) > 0]
            if r_exam_secs:
                r_avg_min = round(sum(r_exam_secs) / len(r_exam_secs) / 60.0, 1)
                total_exam_time_sec += sum(r_exam_secs)
                total_exam_cases += len(r_exam_secs)
            else:
                r_avg_min = 0.0

            is_duty = q_data.get("is_duty_mode", False)
            if is_duty:
                duty_doc = q_data.get("duty_doctor", "")
                card["badge"].setText(f"🌙 TRỰC: {duty_doc}" if duty_doc else "🌙 PHÒNG TRỰC")
                card["badge"].setStyleSheet(
                    "font-size: 11px; font-weight: bold; color: white; background: #e74c3c; padding: 3px 8px; border-radius: 4px; border: none;"
                )
            else:
                card["badge"].setText("☀️ HOẠT ĐỘNG")
                card["badge"].setStyleSheet(
                    "font-size: 11px; font-weight: bold; color: white; background: #059669; padding: 3px 8px; border-radius: 4px; border: none;"
                )

            if curr and curr.get("stt"):
                stt = str(curr.get("stt", "000"))
                call_cnt = int(curr.get("call_count", 1))
                called_ts = curr.get("called_at") or curr.get("timestamp")
                t_str = datetime.fromtimestamp(called_ts).strftime("%H:%M:%S") if called_ts else ""

                if stt == "CC":
                    emergency_bn_cnt += 1
                    card["curr_pat"].setText("🚨 CẤP CỨU")
                    card["curr_pat"].setStyleSheet("font-size: 30px; font-weight: bold; color: #ef4444; border: none;")
                    card["curr_sub"].setText("Đang thực hiện ca cấp cứu")
                else:
                    card["curr_pat"].setText(f"SỐ {stt}")
                    card["curr_pat"].setStyleSheet("font-size: 36px; font-weight: bold; color: #38bdf8; border: none;")
                    card["curr_sub"].setText(f"Đang gọi lần {call_cnt} (Lúc {t_str})")
            else:
                card["curr_pat"].setText("000")
                card["curr_pat"].setStyleSheet("font-size: 36px; font-weight: bold; color: #64748b; border: none;")
                card["curr_sub"].setText("Chờ gọi số")

            # Cập nhật thanh tải lượng phòng & thời gian bắt đầu ca đầu tiên trong ngày
            r_load = room_loads.get(r_str, 0)
            pct = int(round((r_load / total_bn_cnt) * 100)) if total_bn_cnt > 0 else 0
            card["load_bar"].setValue(pct)
            short_lbl = get_room_short_name(r_str)
            card["load_bar"].setFormat(f"Tải lượng ({short_lbl}): {r_load} ca ({pct}%)")

            first_case_str = extract_first_case_time_str(q_data)
            card["stats"].setText(
                f"🕒 Ca đầu: {first_case_str} | 🔢 Cao nhất: {last_number:03d} | ✅ Khám: {c_history} | ⏳ Qua lượt: {c_missed} | ⏱️ TB: {r_avg_min}p"
            )

        self.card_total_bn.lbl_val.setText(str(total_bn_cnt))
        self.card_completed_bn.lbl_val.setText(str(completed_bn_cnt))
        self.card_missed_bn.lbl_val.setText(str(missed_bn_cnt))
        self.card_emergency_bn.lbl_val.setText(str(emergency_bn_cnt))

        if total_exam_cases > 0:
            overall_avg = round(total_exam_time_sec / total_exam_cases / 60.0, 1)
            self.card_avg_time.lbl_val.setText(f"{overall_avg} phút")
        else:
            self.card_avg_time.lbl_val.setText("0.0 phút")

        self.apply_report_filter()

    def apply_report_filter(self):
        selected_room_id = self.cbo_room_filter.currentData() or "ALL"
        selected_shift_code = self.cbo_shift_filter.currentData() or "ALL"
        season_mode = self.cbo_season_mode.currentData() if hasattr(self, "cbo_season_mode") else "AUTO"

        patient_rows = []
        target_rooms = ALL_ROOM_IDS if selected_room_id == "ALL" else [str(selected_room_id)]

        # Cập nhật bảng tổng hợp 11 phòng bên phải (kèm cột Ca đầu tiên)
        self.table_room_summary.setRowCount(len(ALL_ROOM_IDS))
        for idx, r_str in enumerate(ALL_ROOM_IDS):
            r_data = self.all_rooms_cache.get(r_str, {})
            curr = r_data.get("current_calling")
            curr_stt = curr.get("stt", "000") if curr else "000"
            hist = r_data.get("history", [])
            missed = r_data.get("missed_list", [])
            r_secs = [h.get("exam_duration_sec", 0) for h in hist if h.get("exam_duration_sec", 0) > 0]
            r_avg = f"{round(sum(r_secs) / len(r_secs) / 60.0, 1)}" if r_secs else "0.0"
            first_case_t = extract_first_case_time_str(r_data)

            self.table_room_summary.setItem(idx, 0, QTableWidgetItem(get_room_short_name(r_str)))
            self.table_room_summary.setItem(idx, 1, QTableWidgetItem(first_case_t))
            self.table_room_summary.setItem(idx, 2, QTableWidgetItem(str(curr_stt)))
            self.table_room_summary.setItem(idx, 3, QTableWidgetItem(str(len(hist))))
            self.table_room_summary.setItem(idx, 4, QTableWidgetItem(str(len(missed))))
            self.table_room_summary.setItem(idx, 5, QTableWidgetItem(r_avg))

        # Cập nhật bảng chi tiết các lượt gọi bên trái (lọc chính xác theo khung giờ Mùa Đông / Mùa Hè)
        for r_str in target_rooms:
            r_data = self.all_rooms_cache.get(r_str, {})
            history = r_data.get("history", [])
            missed = r_data.get("missed_list", [])
            curr = r_data.get("current_calling")

            all_pats = []
            for h in history:
                all_pats.append((h, "Đã hoàn thành"))
            if curr and curr.get("stt"):
                all_pats.append((curr, "Đang gọi khám"))
            for m in missed:
                all_pats.append((m, "Chưa vào (Qua lượt)"))

            for pat, status_str in all_pats:
                ts = pat.get("called_at") or pat.get("timestamp") or time.time()
                pat_dt = datetime.fromtimestamp(ts)
                pat_mins = pat_dt.hour * 60 + pat_dt.minute
                scfg = get_seasonal_shift_config(pat_dt, force_season=season_mode or "AUTO")

                m_start = scfg["morning_start_min"]      # 07:00
                m_end = scfg["morning_end_min"]          # 11:30
                a_start = scfg["afternoon_start_min"]    # 13:30 (Đông) / 14:00 (Hè)
                a_end = scfg["afternoon_end_min"]        # 17:00 (Đông) / 17:30 (Hè)

                if selected_shift_code == "MORNING" and not (m_start <= pat_mins <= m_end):
                    continue
                if selected_shift_code == "AFTERNOON" and not (a_start <= pat_mins <= a_end):
                    continue
                if selected_shift_code == "NIGHT" and ((m_start <= pat_mins <= m_end) or (a_start <= pat_mins <= a_end)):
                    continue

                stt = str(pat.get("stt", "---"))
                call_cnt = str(pat.get("call_count", 1))
                t_call = pat_dt.strftime("%H:%M:%S")

                comp_ts = pat.get("completed_at")
                t_comp = datetime.fromtimestamp(comp_ts).strftime("%H:%M:%S") if comp_ts else "---"

                dur_sec = int(pat.get("exam_duration_sec", 0))
                dur_min = f"{round(dur_sec / 60.0, 1)} phút" if dur_sec > 0 else "---"

                patient_rows.append({
                    "room": get_room_short_name(r_str),
                    "stt": stt,
                    "status": status_str,
                    "call_cnt": f"{call_cnt} lần",
                    "t_call": t_call,
                    "t_comp": t_comp,
                    "dur_min": dur_min,
                })

        self.table_patients.setRowCount(len(patient_rows))
        for row_idx, p in enumerate(patient_rows):
            self.table_patients.setItem(row_idx, 0, QTableWidgetItem(p["room"]))
            self.table_patients.setItem(row_idx, 1, QTableWidgetItem(p["stt"]))
            self.table_patients.setItem(row_idx, 2, QTableWidgetItem(p["status"]))
            self.table_patients.setItem(row_idx, 3, QTableWidgetItem(p["call_cnt"]))
            self.table_patients.setItem(row_idx, 4, QTableWidgetItem(p["t_call"]))
            self.table_patients.setItem(row_idx, 5, QTableWidgetItem(p["t_comp"]))
            self.table_patients.setItem(row_idx, 6, QTableWidgetItem(p["dur_min"]))

    # =========================================================================
    # EXPORT REPORTS (EXCEL/CSV & TEXT SUMMARY)
    # =========================================================================
    def export_excel_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Xuất Báo Cáo Excel/CSV",
            f"Bao_Cao_Sieu_Am_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)",
        )
        if not file_path:
            return

        try:
            scfg = get_seasonal_shift_config(datetime.now())
            with open(file_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["BÁO CÁO LƯỢNG BỆNH NHÂN VÀ THỜI GIAN THỰC HIỆN KHÁM / THĂM DÒ CHỨC NĂNG"])
                writer.writerow([f"Ngày xuất báo cáo: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} ({scfg['season_badge']})"])
                writer.writerow([f"Ca lọc báo cáo: {self.cbo_shift_filter.currentText()}"])
                writer.writerow([])
                writer.writerow(["I. TỔNG HỢP THEO PHÒNG (KÈM GIỜ BẮT ĐẦU CA BỆNH ĐẦU TIÊN TRONG NGÀY)"])
                writer.writerow(["Phòng", "Giờ bắt đầu ca đầu tiên", "Số hiện tại", "Đã khám", "Qua lượt", "TB (phút)"])
                for srow in range(self.table_room_summary.rowCount()):
                    s_data = [
                        self.table_room_summary.item(srow, scol).text() if self.table_room_summary.item(srow, scol) else ""
                        for scol in range(6)
                    ]
                    writer.writerow(s_data)
                writer.writerow([])
                writer.writerow(["II. DANH SÁCH CHI TIẾT CÁC LƯỢT GỌI"])
                writer.writerow([
                    "Phòng", "Số Thứ Tự (STT)", "Trạng thái", "Số lần gọi loa",
                    "Thời điểm gọi", "Thời điểm hoàn thành", "Thời gian khám (phút)"
                ])

                for row in range(self.table_patients.rowCount()):
                    r_data = [
                        self.table_patients.item(row, col).text() if self.table_patients.item(row, col) else ""
                        for col in range(7)
                    ]
                    writer.writerow(r_data)

            QMessageBox.information(self, "Thành công", f"Đã xuất báo cáo thành công ra file:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể xuất file: {e}")

    def export_text_summary_report(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Xuất Báo Cáo Tổng Hợp Text",
            f"Tong_Hop_Khoa_CDHA_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt)",
        )
        if not file_path:
            return

        try:
            now_dt = datetime.now()
            now_str = now_dt.strftime("%d/%m/%Y %H:%M:%S")
            scfg = get_seasonal_shift_config(now_dt)
            lines = [
                "=" * 82,
                "          BỆNH VIỆN ĐA KHOA THỊ XÃ KỲ ANH - KHOA CHẨN ĐOÁN HÌNH ẢNH",
                "      BÁO CÁO TỔNG HỢP LƯỢNG BỆNH NHÂN & THỜI GIAN BẮT ĐẦU CA ĐẦU TIÊN",
                "=" * 82,
                f"Thời gian xuất:               {now_str}",
                f"Chế độ lịch làm việc:         {scfg['season_badge']}",
                f"Ca làm việc đang chọn:        {self.cbo_shift_filter.currentText()}",
                f"Tổng số lượt gọi trong ngày:  {self.card_total_bn.lbl_val.text()}",
                f"Số ca đã hoàn thành khám:     {self.card_completed_bn.lbl_val.text()}",
                f"Số ca qua lượt / chưa vào:    {self.card_missed_bn.lbl_val.text()}",
                f"Số phòng đang cấp cứu:        {self.card_emergency_bn.lbl_val.text()}",
                f"Thời gian khám trung bình/BN: {self.card_avg_time.lbl_val.text()}",
                "-" * 82,
                "THỐNG KÊ CHI TIẾT THEO TỪNG PHÒNG (KÈM GIỜ BẮT ĐẦU CA ĐẦU TIÊN TRONG NGÀY):",
            ]

            for row in range(self.table_room_summary.rowCount()):
                r_name = self.table_room_summary.item(row, 0).text()
                r_first = self.table_room_summary.item(row, 1).text()
                r_curr = self.table_room_summary.item(row, 2).text()
                r_done = self.table_room_summary.item(row, 3).text()
                r_miss = self.table_room_summary.item(row, 4).text()
                r_avg = self.table_room_summary.item(row, 5).text()
                lines.append(
                    f"  - {r_name:<16} | Ca đầu: {r_first:<8} | Hiện tại: {r_curr:<5} | Đã khám: {r_done:<4} | Qua lượt: {r_miss:<3} | TB: {r_avg}p"
                )

            lines.append("=" * 82)

            with open(file_path, mode="w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            QMessageBox.information(self, "Thành công", f"Đã xuất báo cáo tổng hợp ra file:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể xuất file báo cáo: {e}")

    def closeEvent(self, event):
        if hasattr(self, "timer_clock"):
            self.timer_clock.stop()
        if hasattr(self, "timer_poll"):
            self.timer_poll.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    login_dlg = AdminLoginDialog()
    if login_dlg.exec() == QDialog.Accepted:
        window = AdminApp()
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)
