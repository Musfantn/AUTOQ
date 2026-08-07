import sys
import os
import csv
import json
import time
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget, QFileDialog, QMessageBox,
    QProgressBar, QScrollArea
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QColor, QIcon

import firestore_queue
from firestore_client import firestore_get_parsed


# =============================================================================
# ADMIN & MONITORING APP - MODULE QUẢN TRỊ & BÁO CÁO REALTIME
# =============================================================================

class AdminApp(QMainWindow):
    rooms_data_updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AUTOQ ADMIN CENTER - QUẢN TRỊ & BÁO CÁO THỜI GIAN THỰC")
        self.resize(1180, 800)

        # Apply Modern Dark Theme
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
            QGroupBox {
                border: 1px solid #334155;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 14px;
                font-weight: bold;
                font-size: 14px;
                color: #38bdf8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 5px;
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
            QPushButton:pressed {
                background-color: #075985;
            }
            QComboBox {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 10px;
                color: #f1f5f9;
                font-size: 13px;
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
        """)

        self.all_rooms_cache = {}

        # Main Widget & Layout
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # Header Title Bar
        header_box = QHBoxLayout()
        lbl_title = QLabel("🏥 AUTOQ ULTRASOUND ADMIN & REPORTING CENTER")
        lbl_title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        lbl_title.setStyleSheet("color: #38bdf8;")
        
        self.lbl_clock = QLabel("")
        self.lbl_clock.setFont(QFont("Consolas", 12, QFont.Bold))
        self.lbl_clock.setStyleSheet("color: #10b981;")

        header_box.addWidget(lbl_title, 1)
        header_box.addWidget(self.lbl_clock)
        main_layout.addLayout(header_box)

        # Tabs Container
        self.tabs = QTabWidget()
        
        # Tab 1: Real-time Monitoring
        self.tab_monitor = QWidget()
        self._init_monitor_tab()
        self.tabs.addTab(self.tab_monitor, "🖥 Realtime Monitoring (5 Phòng Siêu Âm)")

        # Tab 2: Reports & Metrics
        self.tab_report = QWidget()
        self._init_report_tab()
        self.tabs.addTab(self.tab_report, "📊 Báo Cáo Cuối Buổi / Cuối Ngày")

        main_layout.addWidget(self.tabs)
        self.setCentralWidget(main_widget)

        # Signal connections
        self.rooms_data_updated.connect(self.on_rooms_data_updated)

        # Timers
        self.timer_clock = QTimer(self)
        self.timer_clock.timeout.connect(self._update_clock)
        self.timer_clock.start(1000)
        self._update_clock()

        self.timer_poll = QTimer(self)
        self.timer_poll.timeout.connect(self.poll_all_rooms_async)
        self.timer_poll.start(3000)  # Polling 3s realtime
        QTimer.singleShot(100, self.poll_all_rooms_async)

    def _update_clock(self):
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.lbl_clock.setText(f"⏱️ {now_str}")

    # =========================================================================
    # TAB 1: MONITORING REALTIME 5 PHÒNG SIÊU ÂM
    # =========================================================================
    def _init_monitor_tab(self):
        layout = QVBoxLayout(self.tab_monitor)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Summary Metrics Bar
        summary_box = QFrame()
        summary_box.setStyleSheet("background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 6px;")
        s_layout = QHBoxLayout(summary_box)
        s_layout.setContentsMargins(10, 8, 10, 8)
        s_layout.setSpacing(15)

        self.card_total_bn = self._create_metric_widget("📊 Tổng BN Trong Ngày", "0", "#38bdf8")
        self.card_completed_bn = self._create_metric_widget("✅ Đã Hoàn Thành", "0", "#10b981")
        self.card_waiting_bn = self._create_metric_widget("⏳ Đang Chờ Khám", "0", "#f59e0b")
        self.card_emergency_bn = self._create_metric_widget("🚨 Ca Cấp Cứu", "0", "#ef4444")
        self.card_avg_time = self._create_metric_widget("⏱️ Thời Gian Khám TB", "0 phút", "#a855f7")

        s_layout.addWidget(self.card_total_bn)
        s_layout.addWidget(self.card_completed_bn)
        s_layout.addWidget(self.card_waiting_bn)
        s_layout.addWidget(self.card_emergency_bn)
        s_layout.addWidget(self.card_avg_time)
        layout.addWidget(summary_box)

        # 5 Room Cards Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        scroll_content = QWidget()
        grid = QGridLayout(scroll_content)
        grid.setSpacing(12)

        self.room_cards = {}
        for r in range(1, 6):
            card = self._create_room_card_widget(r)
            row = (r - 1) // 3
            col = (r - 1) % 3
            grid.addWidget(card["frame"], row, col)
            self.room_cards[str(r)] = card

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

    def _create_metric_widget(self, title, init_val, color_hex):
        box = QWidget()
        box.setStyleSheet("background: transparent; border: none;")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: bold;")
        
        lbl_v = QLabel(init_val)
        lbl_v.setStyleSheet(f"font-size: 20px; color: {color_hex}; font-weight: bold;")
        
        v.addWidget(lbl_t)
        v.addWidget(lbl_v)
        box.lbl_val = lbl_v
        return box

    def _create_room_card_widget(self, room_num):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 10px;
            }
        """)
        f_layout = QVBoxLayout(frame)
        f_layout.setContentsMargins(12, 10, 12, 10)
        f_layout.setSpacing(6)

        # Header Row: Room Name & Status Badge
        top_row = QHBoxLayout()
        lbl_name = QLabel(f"PHÒNG SIÊU ÂM {room_num}")
        lbl_name.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8; border: none;")
        
        badge_status = QLabel("☀️ NORMAL")
        badge_status.setStyleSheet("font-size: 10px; font-weight: bold; color: white; background: #059669; padding: 2px 6px; border-radius: 4px; border: none;")

        top_row.addWidget(lbl_name, 1)
        top_row.addWidget(badge_status)
        f_layout.addLayout(top_row)

        # Current Calling Box
        curr_box = QFrame()
        curr_box.setStyleSheet("background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 6px;")
        c_layout = QVBoxLayout(curr_box)
        c_layout.setContentsMargins(8, 6, 8, 6)
        c_layout.setSpacing(3)

        lbl_curr_head = QLabel("▶ ĐANG KHÁM HIỆN TẠI:")
        lbl_curr_head.setStyleSheet("font-size: 11px; font-weight: bold; color: #94a3b8; border: none;")
        
        lbl_curr_pat = QLabel("--- CHỜ GỌI SỐ ---")
        lbl_curr_pat.setStyleSheet("font-size: 13px; font-weight: bold; color: #f1f5f9; border: none;")
        
        lbl_curr_sub = QLabel("Dịch vụ: ---")
        lbl_curr_sub.setStyleSheet("font-size: 11px; color: #64748b; border: none;")

        c_layout.addWidget(lbl_curr_head)
        c_layout.addWidget(lbl_curr_pat)
        c_layout.addWidget(lbl_curr_sub)
        f_layout.addWidget(curr_box)

        # Room Stats Summary
        lbl_stats = QLabel("⏳ Đang chờ: 0 | ✅ Đã khám: 0 | ⏱️ TB: 0 phút")
        lbl_stats.setStyleSheet("font-size: 11px; font-weight: bold; color: #cbd5e1; border: none;")
        f_layout.addWidget(lbl_stats)

        return {
            "frame": frame,
            "name": lbl_name,
            "badge": badge_status,
            "curr_pat": lbl_curr_pat,
            "curr_sub": lbl_curr_sub,
            "stats": lbl_stats
        }

    # =========================================================================
    # TAB 2: BÁO CÁO CUỐI BUỔI / CUỐI NGÀY
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
        self.cbo_room_filter.addItems(["Tất cả các phòng", "Phòng 1", "Phòng 2", "Phòng 3", "Phòng 4", "Phòng 5"])
        self.cbo_room_filter.currentIndexChanged.connect(self.apply_report_filter)
        fl_layout.addWidget(self.cbo_room_filter)

        fl_layout.addWidget(QLabel("Ca làm việc:"))
        self.cbo_shift_filter = QComboBox()
        self.cbo_shift_filter.addItems(["Cả ngày (Tất cả ca)", "Ca Sáng (07:00 - 11:30)", "Ca Chiều (13:30 - 17:00)", "Ca Trực Đêm (17:00 - 07:00)"])
        self.cbo_shift_filter.currentIndexChanged.connect(self.apply_report_filter)
        fl_layout.addWidget(self.cbo_shift_filter)

        btn_refresh = QPushButton("🔄 LÀM MỚI BÁO CÁO")
        btn_refresh.setStyleSheet("background-color: #0284c7;")
        btn_refresh.clicked.connect(self.poll_all_rooms_async)
        fl_layout.addWidget(btn_refresh)

        btn_excel = QPushButton("📥 XUẤT EXCEL / CSV")
        btn_excel.setStyleSheet("background-color: #059669;")
        btn_excel.clicked.connect(self.export_excel_csv)
        fl_layout.addWidget(btn_excel)

        btn_print_pdf = QPushButton("📄 IN / XUẤT BÁO CÁO TXT")
        btn_print_pdf.setStyleSheet("background-color: #7c3aed;")
        btn_print_pdf.clicked.connect(self.export_text_summary_report)
        fl_layout.addWidget(btn_print_pdf)

        layout.addWidget(filter_box)

        # Table & Summary Breakdown Split Layout
        split_layout = QHBoxLayout()
        split_layout.setSpacing(10)

        # Table: Detailed Patients List
        self.table_patients = QTableWidget()
        self.table_patients.setColumnCount(9)
        self.table_patients.setHorizontalHeaderLabels([
            "Phòng", "STT", "Mã BN", "Họ và Tên", "Tuổi", "Dịch vụ chỉ định", "Thời gian tiếp đón", "Thời gian gọi", "Thời gian khám (phút)"
        ])
        header = self.table_patients.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Stretch)

        split_layout.addWidget(self.table_patients, 2)

        # Side Box: Service Breakdown Statistics
        side_box = QFrame()
        side_box.setFixedWidth(330)
        side_box.setStyleSheet("background: #1e293b; border: 1px solid #334155; border-radius: 8px;")
        sd_layout = QVBoxLayout(side_box)
        sd_layout.setContentsMargins(10, 10, 10, 10)
        sd_layout.setSpacing(8)

        lbl_side_title = QLabel("📊 THỐNG KÊ CƠ CẤU DỊCH VỤ")
        lbl_side_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        lbl_side_title.setStyleSheet("color: #38bdf8; border: none;")
        sd_layout.addWidget(lbl_side_title)

        self.table_services = QTableWidget()
        self.table_services.setColumnCount(2)
        self.table_services.setHorizontalHeaderLabels(["Tên Dịch vụ", "Số lượt"])
        self.table_services.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        sd_layout.addWidget(self.table_services)

        split_layout.addWidget(side_box)
        layout.addLayout(split_layout, 1)

    # =========================================================================
    # REALTIME DATA POLLING & SIGNAL HANDLING
    # =========================================================================
    def poll_all_rooms_async(self):
        def run():
            data_all = {}
            for r in range(1, 6):
                try:
                    q = firestore_queue.get_room_queue(str(r))
                    if q:
                        data_all[str(r)] = q
                except Exception as e:
                    print(f"[AdminApp] Lỗi đọc Phòng {r}: {e}")
            self.rooms_data_updated.emit(data_all)

        threading.Thread(target=run, daemon=True).start()

    @Slot(dict)
    def on_rooms_data_updated(self, data_all):
        self.all_rooms_cache = data_all
        
        # 1. Update Tab 1 Monitoring Cards
        total_bn_cnt = 0
        completed_bn_cnt = 0
        waiting_bn_cnt = 0
        emergency_bn_cnt = 0
        total_exam_time_sec = 0
        total_exam_cases = 0

        for r in range(1, 6):
            r_str = str(r)
            q_data = data_all.get(r_str, {})
            card = self.room_cards.get(r_str)
            if not card:
                continue

            curr = q_data.get("current_calling")
            waiting = q_data.get("waiting_list", [])
            history = q_data.get("history", [])

            c_waiting = len(waiting)
            c_history = len(history)

            total_bn_cnt += (c_waiting + c_history + (1 if curr else 0))
            completed_bn_cnt += c_history
            waiting_bn_cnt += c_waiting

            # Calc room avg exam duration
            r_exam_secs = [h.get("exam_duration_sec", 0) for h in history if "exam_duration_sec" in h]
            if r_exam_secs:
                r_avg_min = round(sum(r_exam_secs) / len(r_exam_secs) / 60.0, 1)
                total_exam_time_sec += sum(r_exam_secs)
                total_exam_cases += len(r_exam_secs)
            else:
                r_avg_min = 0.0

            # Duty mode badge
            is_duty = q_data.get("is_duty_mode", False)
            if is_duty:
                card["badge"].setText("🌙 PHÒNG TRỰC")
                card["badge"].setStyleSheet("font-size: 10px; font-weight: bold; color: white; background: #e74c3c; padding: 2px 6px; border-radius: 4px; border: none;")
            else:
                card["badge"].setText("☀️ NORMAL")
                card["badge"].setStyleSheet("font-size: 10px; font-weight: bold; color: white; background: #059669; padding: 2px 6px; border-radius: 4px; border: none;")

            # Current Patient Info
            if curr:
                stt = curr.get("stt", "000")
                name = curr.get("ten_bn", "").upper()
                tuoi = curr.get("tuoi", "")
                dv = curr.get("dich_vu", "").replace("\n", ", ").strip()
                if stt == "CC":
                    emergency_bn_cnt += 1
                    card["curr_pat"].setText("🚨 CẤP CỨU")
                    card["curr_pat"].setStyleSheet("font-size: 14px; font-weight: bold; color: #ef4444; border: none;")
                    card["curr_sub"].setText(dv or "SIÊU ÂM CẤP CỨU")
                else:
                    card["curr_pat"].setText(f"[{stt}] {name} ({tuoi}t)")
                    card["curr_pat"].setStyleSheet("font-size: 13px; font-weight: bold; color: #38bdf8; border: none;")
                    card["curr_sub"].setText(f"DV: {dv[:30]}..." if len(dv) > 30 else f"DV: {dv}")
            else:
                card["curr_pat"].setText("--- CHỜ GỌI SỐ ---")
                card["curr_pat"].setStyleSheet("font-size: 13px; font-weight: bold; color: #64748b; border: none;")
                card["curr_sub"].setText("Dịch vụ: ---")

            card["stats"].setText(f"⏳ Chờ: {c_waiting} | ✅ Khám: {c_history} | ⏱️ TB: {r_avg_min} phút")

        # Update System Top Metrics Bar
        self.card_total_bn.lbl_val.setText(str(total_bn_cnt))
        self.card_completed_bn.lbl_val.setText(str(completed_bn_cnt))
        self.card_waiting_bn.lbl_val.setText(str(waiting_bn_cnt))
        self.card_emergency_bn.lbl_val.setText(str(emergency_bn_cnt))
        
        if total_exam_cases > 0:
            overall_avg = round(total_exam_time_sec / total_exam_cases / 60.0, 1)
            self.card_avg_time.lbl_val.setText(f"{overall_avg} phút")
        else:
            self.card_avg_time.lbl_val.setText("0.0 phút")

        # 2. Update Tab 2 Reports Table
        self.apply_report_filter()

    def apply_report_filter(self):
        selected_room = self.cbo_room_filter.currentText()
        selected_shift = self.cbo_shift_filter.currentText()

        # Collect all patients across requested rooms
        patient_rows = []
        service_counts = {}

        target_rooms = range(1, 6) if selected_room == "Tất cả các phòng" else [int(selected_room.replace("Phòng ", ""))]

        for r in target_rooms:
            r_data = self.all_rooms_cache.get(str(r), {})
            history = r_data.get("history", [])
            waiting = r_data.get("waiting_list", [])
            curr = r_data.get("current_calling")

            all_pats = []
            for h in history:
                all_pats.append((h, "Đã hoàn thành"))
            if curr:
                all_pats.append((curr, "Đang khám"))
            for w in waiting:
                all_pats.append((w, "Đang chờ"))

            for pat, status_str in all_pats:
                # Filter shift time if needed
                ts = pat.get("timestamp") or time.time()
                pat_dt = datetime.fromtimestamp(ts)
                pat_hour = pat_dt.hour

                if "Ca Sáng" in selected_shift and not (7 <= pat_hour < 12):
                    continue
                if "Ca Chiều" in selected_shift and not (12 <= pat_hour < 17):
                    continue
                if "Ca Trực Đêm" in selected_shift and (7 <= pat_hour < 17):
                    continue

                stt = pat.get("stt", "---")
                ma = pat.get("ma_bn", "---")
                name = pat.get("ten_bn", "").upper()
                tuoi = str(pat.get("tuoi", ""))
                dv = pat.get("dich_vu", "").replace("\n", ", ").strip()
                
                t_recept = pat_dt.strftime("%H:%M:%S")
                
                called_ts = pat.get("called_at")
                t_call = datetime.fromtimestamp(called_ts).strftime("%H:%M:%S") if called_ts else "---"

                dur_sec = pat.get("exam_duration_sec", 0)
                dur_min = f"{round(dur_sec / 60.0, 1)} phút" if dur_sec > 0 else "---"

                patient_rows.append({
                    "room": f"Phòng {r}",
                    "stt": stt,
                    "ma": ma,
                    "name": name,
                    "tuoi": tuoi,
                    "dv": dv,
                    "t_recept": t_recept,
                    "t_call": t_call,
                    "dur_min": dur_min,
                    "status": status_str
                })

                # Tích lũy cơ cấu dịch vụ
                if dv:
                    for s_name in dv.split(", "):
                        s_name = s_name.strip()
                        if s_name:
                            service_counts[s_name] = service_counts.get(s_name, 0) + 1

        # Populate Patients Table
        self.table_patients.setRowCount(len(patient_rows))
        for row_idx, p in enumerate(patient_rows):
            self.table_patients.setItem(row_idx, 0, QTableWidgetItem(p["room"]))
            self.table_patients.setItem(row_idx, 1, QTableWidgetItem(p["stt"]))
            self.table_patients.setItem(row_idx, 2, QTableWidgetItem(p["ma"]))
            self.table_patients.setItem(row_idx, 3, QTableWidgetItem(p["name"]))
            self.table_patients.setItem(row_idx, 4, QTableWidgetItem(p["tuoi"]))
            self.table_patients.setItem(row_idx, 5, QTableWidgetItem(p["dv"]))
            self.table_patients.setItem(row_idx, 6, QTableWidgetItem(p["t_recept"]))
            self.table_patients.setItem(row_idx, 7, QTableWidgetItem(p["t_call"]))
            self.table_patients.setItem(row_idx, 8, QTableWidgetItem(p["dur_min"]))

        # Populate Service Breakdown Table
        sorted_services = sorted(service_counts.items(), key=lambda x: x[1], reverse=True)
        self.table_services.setRowCount(len(sorted_services))
        for s_idx, (s_name, count) in enumerate(sorted_services):
            self.table_services.setItem(s_idx, 0, QTableWidgetItem(s_name))
            self.table_services.setItem(s_idx, 1, QTableWidgetItem(str(count)))

    # =========================================================================
    # EXPORT REPORTS (EXCEL/CSV & TEXT SUMMARY)
    # =========================================================================
    def export_excel_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Xuất Báo Cáo Excel/CSV",
            f"Bao_Cao_Sieu_Am_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            with open(file_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["BÁO CÁO CHI TIẾT SỐ LƯỢNG VÀ THỜI GIAN THỰC HIỆN BỆNH NHÂN SIÊU ÂM"])
                writer.writerow([f"Ngày xuất báo cáo: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"])
                writer.writerow([])
                writer.writerow(["Phòng", "STT", "Mã BN", "Họ và Tên", "Tuổi", "Dịch vụ chỉ định", "Thời gian tiếp đón", "Thời gian gọi", "Thời gian khám (phút)"])

                for row in range(self.table_patients.rowCount()):
                    r_data = [self.table_patients.item(row, col).text() if self.table_patients.item(row, col) else "" for col in range(9)]
                    writer.writerow(r_data)

            QMessageBox.information(self, "Thành công", f"Đã xuất báo cáo thành công ra file:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể xuất file: {e}")

    def export_text_summary_report(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Xuất Báo Cáo Tổng Hợp Text",
            f"Tong_Hop_Sieu_Am_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt)"
        )
        if not file_path:
            return

        try:
            now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            lines = [
                "=" * 70,
                "     BỆNH VIỆN ĐA KHOA THỊ XÃ KỲ ANH - KHOA CHẨN ĐOÁN HÌNH ẢNH",
                "         BÁO CÁO TỔNG HỢP HOẠT ĐỘNG SIÊU ÂM TRONG NGÀY",
                "=" * 70,
                f"Thời gian xuất: {now_str}",
                f"Tổng số bệnh nhân trong ngày: {self.card_total_bn.lbl_val.text()}",
                f"Số ca đã hoàn thành khám:    {self.card_completed_bn.lbl_val.text()}",
                f"Số ca đang chờ khám:         {self.card_waiting_bn.lbl_val.text()}",
                f"Số ca gọi cấp cứu:           {self.card_emergency_bn.lbl_val.text()}",
                f"Thời gian khám trung bình/BN: {self.card_avg_time.lbl_val.text()}",
                "-" * 70,
                "THỐNG KÊ CƠ CẤU DỊCH VỤ THỰC HIỆN NHIỀU NHẤT:",
            ]

            for row in range(self.table_services.rowCount()):
                s_name = self.table_services.item(row, 0).text() if self.table_services.item(row, 0) else ""
                s_count = self.table_services.item(row, 1).text() if self.table_services.item(row, 1) else ""
                lines.append(f"  - {s_name:<45}: {s_count} lượt")

            lines.append("=" * 70)

            with open(file_path, mode="w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            QMessageBox.information(self, "Thành công", f"Đã xuất báo cáo tổng hợp ra file:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể xuất file báo cáo: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AdminApp()
    window.show()
    sys.exit(app.exec())
