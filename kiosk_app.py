import sys
import os
import time
import socket
import subprocess
import json
import threading
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QTextEdit,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QIcon

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import firestore_queue

# =============================================================================
# SELENIUM UTILS
# =============================================================================
def tinh_tuoi(ngay_sinh_str):
    try:
        ngay_sinh_str = ngay_sinh_str.strip()
        if not ngay_sinh_str:
            return 0
        date_part = ngay_sinh_str.split()[0]
        if "/" in date_part:
            birth_year = int(date_part.split("/")[-1])
        elif "-" in date_part:
            birth_year = int(date_part.split("-")[0])
        else:
            birth_year = int(date_part)
        current_year = datetime.now().year
        return current_year - birth_year
    except Exception:
        return 0

def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def open_chrome_debug():
    if is_port_open(9222):
        return True
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
    ]
    chrome_path = None
    for path in chrome_paths:
        if os.path.exists(path):
            chrome_path = path
            break
    if not chrome_path:
        return False
    user_data_dir = r"C:\ChromeDebug"
    os.makedirs(user_data_dir, exist_ok=True)
    try:
        subprocess.Popen([chrome_path, "--remote-debugging-port=9222", f"--user-data-dir={user_data_dir}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.5)
        return True
    except Exception:
        return False

# Thread tra cứu bằng Selenium
class LookupThread(QThread):
    success = Signal(str, str, str, str)  # ten_bn, ngay_sinh, tuoi, dich_vu_str
    error = Signal(str)

    def __init__(self, ma_bn):
        super().__init__()
        self.ma_bn = ma_bn

    def run(self):
        driver = None
        try:
            if not open_chrome_debug():
                self.error.emit("Không tìm thấy Google Chrome hoặc không thể mở cổng 9222!")
                return

            options = webdriver.ChromeOptions()
            options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
            driver = webdriver.Chrome(options=options)
            wait = WebDriverWait(driver, 5)

            search_box = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Nhập thông tin phiếu chỉ định để tìm kiếm']"))
            )
            search_box.clear()
            search_box.send_keys(self.ma_bn)
            search_box.send_keys(Keys.ENTER)

            def cho_ma_bn_khop(d):
                try:
                    rows = d.find_elements(By.XPATH, "//table[@id='grdDanhSachCDHA']//tr[contains(@class, 'jqgrow')]")
                    if not rows:
                        return False
                    cells = rows[0].find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 6:
                        return cells[5].text.strip().upper() == self.ma_bn.upper()
                    return False
                except Exception:
                    return False

            wait.until(cho_ma_bn_khop)
            row = driver.find_element(By.XPATH, "//table[@id='grdDanhSachCDHA']//tr[contains(@class, 'jqgrow')][1]")
            cells = row.find_elements(By.TAG_NAME, "td")

            ten_bn = cells[7].text.strip()
            ngay_sinh = cells[8].text.strip()
            tuoi = str(tinh_tuoi(ngay_sinh))

            try:
                row.click()
                time.sleep(0.5)
            except Exception:
                pass

            dich_vu_list = []
            dich_vu_xpath = "//table[@id='grdKetQuaChanDoan']//tr[contains(@class, 'jqgrow')]"
            try:
                wait.until(EC.presence_of_element_located((By.XPATH, dich_vu_xpath)))
                service_rows = driver.find_elements(By.XPATH, dich_vu_xpath)
                for s_row in service_rows:
                    s_cells = s_row.find_elements(By.TAG_NAME, "td")
                    if len(s_cells) >= 4:
                        s_name = s_cells[3].text.strip()
                        if s_name:
                            dich_vu_list.append(s_name)
            except Exception:
                pass

            dich_vu_str = "\n".join(dich_vu_list) if dich_vu_list else "Không tìm thấy dịch vụ chỉ định"
            self.success.emit(ten_bn, ngay_sinh, tuoi, dich_vu_str)

        except Exception as e:
            self.error.emit(f"Tra cứu thất bại (Hết thời gian chờ hoặc Mã BN không khớp)")

# =============================================================================
# PYSIDE6 GUI - KIOSK MODULE
# =============================================================================
class KioskApp(QWidget):
    # Signal để cập nhật giao diện sau khi đẩy Firestore thành công
    push_success = Signal(str, str, str)  # room_num, ten_bn, stt
    push_failed = Signal(str, str)        # room_num, error_msg
    counts_updated = Signal(dict)         # dict room_num -> count

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoQ Kiosk Tiếp đón v3.0 (Cloud Firestore)")
        self.setFixedSize(600, 720)
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
            QTextEdit {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px;
                color: #f1f5f9;
                font-size: 13px;
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
        title.setStyleSheet("color: #3b82f6; margin-bottom: 5px;")
        layout.addWidget(title)

        # 1. Search Box Group
        search_box = QHBoxLayout()
        self.entry_search = QLineEdit()
        self.entry_search.setPlaceholderText("Nhập hoặc quét Mã Bệnh Nhân (Enter)...")
        self.entry_search.setFixedHeight(45)
        self.entry_search.setFont(QFont("Segoe UI", 12))
        self.entry_search.returnPressed.connect(self.start_lookup)
        
        self.btn_search = QPushButton("Tra cứu (HIS)")
        self.btn_search.setFixedHeight(45)
        self.btn_search.setStyleSheet("background-color: #10b981;")
        self.btn_search.clicked.connect(self.start_lookup)
        
        search_box.addWidget(self.entry_search)
        search_box.addWidget(self.btn_search)
        layout.addLayout(search_box)

        # 2. Patient Info Group (Có thể nhập thủ công)
        self.group_info = QGroupBox("Thông tin Bệnh nhân (Cho phép nhập tay)")
        info_layout = QVBoxLayout(self.group_info)
        info_layout.setSpacing(10)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)

        grid_layout.addWidget(QLabel("Mã BN:"), 0, 0)
        self.edit_ma = QLineEdit()
        self.edit_ma.setFixedHeight(38)
        self.edit_ma.setFont(QFont("Segoe UI", 11))
        grid_layout.addWidget(self.edit_ma, 0, 1)

        grid_layout.addWidget(QLabel("Họ tên:"), 1, 0)
        self.edit_ten = QLineEdit()
        self.edit_ten.setFixedHeight(38)
        self.edit_ten.setFont(QFont("Segoe UI", 11))
        grid_layout.addWidget(self.edit_ten, 1, 1)

        grid_layout.addWidget(QLabel("Tuổi:"), 2, 0)
        self.edit_tuoi = QLineEdit()
        self.edit_tuoi.setFixedHeight(38)
        self.edit_tuoi.setFont(QFont("Segoe UI", 11))
        grid_layout.addWidget(self.edit_tuoi, 2, 1)
        
        info_layout.addLayout(grid_layout)

        info_layout.addWidget(QLabel("Các dịch vụ chỉ định:"))
        self.edit_dich_vu = QTextEdit()
        self.edit_dich_vu.setFixedHeight(80)
        info_layout.addWidget(self.edit_dich_vu)

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
            btn.setFixedHeight(50)
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
        self.status_log = QLabel("Hệ thống đồng bộ Firestore sẵn sàng. Chờ quét mã.")
        self.status_log.setFont(QFont("Consolas", 10))
        self.status_log.setStyleSheet("color: #94a3b8; border: 1px solid #1e293b; padding: 10px; background-color: #0f172a; border-radius: 8px;")
        self.status_log.setWordWrap(True)
        layout.addWidget(self.status_log)

        # Kết nối Signals
        self.push_success.connect(self.on_push_success)
        self.push_failed.connect(self.on_push_failed)
        self.counts_updated.connect(self.update_room_waiting_counts)

        # Auto select entry_search
        self.entry_search.setFocus()

        # Khởi chạy Polling đếm số lượng bệnh nhân chờ của các phòng
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.refresh_counts_async)
        self.poll_timer.start(10000)  # Cập nhật mỗi 10 giây
        QTimer.singleShot(500, self.refresh_counts_async)

    def log(self, text):
        now = datetime.now().strftime("%H:%M:%S")
        self.status_log.setText(f"[{now}] {text}")

    def start_lookup(self):
        ma_bn = self.entry_search.text().strip()
        if not ma_bn:
            self.log("Vui lòng nhập hoặc quét Mã bệnh nhân!")
            return
        
        self.log(f"Đang tìm kiếm Mã BN '{ma_bn}' trên VNPT HIS...")
        self.btn_search.setEnabled(False)
        self.entry_search.setEnabled(False)
        
        # Chạy thread tìm kiếm ngầm
        self.thread = LookupThread(ma_bn)
        self.thread.success.connect(self.on_lookup_success)
        self.thread.error.connect(self.on_lookup_error)
        self.thread.start()

    @Slot(str, str, str, str)
    def on_lookup_success(self, ten_bn, ngay_sinh, tuoi, dich_vu_str):
        self.btn_search.setEnabled(True)
        self.entry_search.setEnabled(True)
        
        self.edit_ma.setText(self.entry_search.text().strip())
        self.edit_ten.setText(ten_bn)
        self.edit_tuoi.setText(tuoi)
        self.edit_dich_vu.setText(dich_vu_str)
        
        self.log(f"Tìm thấy bệnh nhân: {ten_bn} (Tuổi: {tuoi})")
        self.entry_search.clear()

    @Slot(str)
    def on_lookup_error(self, err_msg):
        self.btn_search.setEnabled(True)
        self.entry_search.setEnabled(True)
        self.log(err_msg)
        
        self.edit_ma.setText(self.entry_search.text().strip())
        self.edit_ten.clear()
        self.edit_tuoi.clear()
        self.edit_dich_vu.clear()
        self.edit_ten.setFocus()

    def push_to_room(self, room_num):
        ma_bn = self.edit_ma.text().strip()
        ten_bn = self.edit_ten.text().strip()
        tuoi_str = self.edit_tuoi.text().strip()
        dich_vu = self.edit_dich_vu.toPlainText().strip()

        if not ten_bn:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng nhập tên bệnh nhân trước khi đẩy phòng!")
            return

        tuoi = 0
        try:
            if tuoi_str:
                tuoi = int(tuoi_str)
        except ValueError:
            pass

        # Vô hiệu hóa các nút đẩy phòng để tránh nhấn lặp
        for btn in self.room_buttons:
            btn.setEnabled(False)
            
        self.log(f"Đang đồng bộ bệnh nhân '{ten_bn}' lên Firestore Phòng {room_num}...")

        # Chạy thao tác ghi Firestore trong luồng riêng biệt
        def run():
            stt = firestore_queue.push_patient(room_num, ma_bn, ten_bn, tuoi, dich_vu)
            if stt:
                self.push_success.emit(room_num, ten_bn, stt)
            else:
                self.push_failed.emit(room_num, "Lỗi kết nối Firestore Cloud hoặc Security Rules.")

        threading.Thread(target=run, daemon=True).start()

    @Slot(str, str, str)
    def on_push_success(self, room_num, ten_bn, stt):
        # Kích hoạt lại các nút phòng
        for btn in self.room_buttons:
            btn.setEnabled(True)
            
        self.log(f"Đồng bộ THÀNH CÔNG! Đã đẩy BN '{ten_bn}' vào PHÒNG {room_num} - STT: {stt}")
        
        # Xóa sạch thông tin cũ để quét bệnh nhân tiếp theo
        self.edit_ma.clear()
        self.edit_ten.clear()
        self.edit_tuoi.clear()
        self.edit_dich_vu.clear()
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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    kiosk = KioskApp()
    kiosk.show()
    sys.exit(app.exec())
