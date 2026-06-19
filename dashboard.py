from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, Signal, QTimer
import threading
import firestore_queue
from mini_panel import MiniPanel
from settings import SettingsWindow
from config_manager import ConfigManager
from oncall_manager import OnCallManager
from oncall_setup_window import OnCallSetupWindow
from duty_mode_dialog import DutyModeDialog

class Dashboard(QWidget):
    # Signal để truyền dữ liệu nhận được từ thread chạy ngầm về UI thread an toàn
    queue_updated = Signal(dict)

    def __init__(self, tv):
        super().__init__()
        self.tv = tv
        self.config = ConfigManager()
        self.oncall_mgr = OnCallManager()
        
        # Biến trạng thái
        self.is_emergency = False
        self.is_duty_mode = False
        self.last_number = "000"
        self.latest_queue_data = None

        self.setWindowTitle("Radiology Dashboard - BVĐK Kỳ Anh")
        self.setFixedSize(350, 700)

        layout = QVBoxLayout(self)
        
        # Hiển thị số
        self.number = QLabel("000")
        self.number.setStyleSheet("font-size:100px; font-weight:bold; color: #0B5FA5; background: #f8f9fa; border: 1px solid #ddd; border-radius: 10px;")
        self.number.setAlignment(Qt.AlignCenter)

        # Nút bấm
        btn_next = QPushButton("TIẾP THEO")
        self.btn_priority = QPushButton("GỌI CẤP CỨU")
        btn_set = QPushButton("NHẢY ĐẾN SỐ (SET)")
        btn_mini = QPushButton("MỞ MINI PANEL")
        btn_settings = QPushButton("CẤU HÌNH")
        btn_reset = QPushButton("RESET")

        # === NÚT MỚI: Chế độ phòng trực ===
        btn_oncall_setup = QPushButton("⚙ THIẾT LẬP BS TRỰC")
        self.btn_duty_mode = QPushButton("🌙 CHẾ ĐỘ PHÒNG TRỰC")

        # Style cho các nút
        btn_next.setStyleSheet("background-color: #28a745; color: white; height: 60px; font-size: 18px; font-weight: bold;")
        self.btn_priority.setStyleSheet("background-color: #dc3545; color: white; height: 40px; font-weight: bold;")
        btn_mini.setStyleSheet("background-color: #17a2b8; color: white; height: 35px;")
        
        btn_oncall_setup.setStyleSheet("""
            background-color: #6c757d; color: white; height: 35px; font-weight: bold;
        """)
        self.btn_duty_mode.setStyleSheet("""
            background-color: #fd7e14; color: white; height: 45px; font-size: 15px; font-weight: bold;
        """)

        # Kết nối sự kiện
        btn_next.clicked.connect(self.next)
        self.btn_priority.clicked.connect(self.toggle_priority)
        btn_set.clicked.connect(self.set_number)
        btn_mini.clicked.connect(self.show_mini)
        btn_settings.clicked.connect(self.show_settings)
        btn_reset.clicked.connect(self.reset)
        btn_oncall_setup.clicked.connect(self.show_oncall_setup)
        self.btn_duty_mode.clicked.connect(self.toggle_duty_mode)

        layout.addWidget(self.number)
        layout.addWidget(btn_next)
        layout.addWidget(self.btn_priority)
        layout.addWidget(btn_set)
        layout.addWidget(btn_mini)
        layout.addWidget(btn_settings)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: #ccc; margin: 5px 0;")
        layout.addWidget(separator)

        layout.addWidget(btn_oncall_setup)
        layout.addWidget(self.btn_duty_mode)

        layout.addStretch()
        layout.addWidget(btn_reset)

        # Khởi tạo cửa sổ phụ
        self.settings_window = SettingsWindow()
        self.settings_window.config_saved.connect(self.on_config_saved)
        self.oncall_setup_window = OnCallSetupWindow()
        self.mini = MiniPanel(self) # Khởi tạo MiniPanel
        
        # Kết nối Custom Signal
        self.queue_updated.connect(self.on_queue_updated)

        # === TIMER ĐỒNG BỘ API (POLLING) ===
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_queue)
        self.poll_timer.start(2000) # Poll mỗi 2 giây
        
        self.apply_config_to_tv()

    def poll_queue(self):
        """Hàm poll trạng thái hàng đợi từ Cloud Firestore chạy ngầm (không khóa GUI)"""
        room_num = self.config.get("room_number", "1").strip()
        
        def run():
            try:
                data = firestore_queue.get_room_queue(room_num)
                if data:
                    self.queue_updated.emit(data)
            except Exception as e:
                pass

        threading.Thread(target=run, daemon=True).start()

    def send_api_command(self, action, payload=None):
        """Gửi lệnh thay đổi trạng thái hàng đợi lên Cloud Firestore chạy ngầm"""
        room_num = self.config.get("room_number", "1").strip()
        
        def run():
            try:
                data = None
                if action == "next":
                    data = firestore_queue.next_patient(room_num)
                elif action == "emergency":
                    data = firestore_queue.toggle_emergency(room_num)
                elif action == "set":
                    num = payload.get("number", 1) if payload else 1
                    data = firestore_queue.set_number(room_num, num)
                elif action == "reset":
                    data = firestore_queue.reset_queue(room_num)
                
                if data:
                    self.queue_updated.emit(data)
            except Exception as e:
                print(f"[Dashboard] Lỗi thực hiện lệnh '{action}' trên Cloud: {e}")

        threading.Thread(target=run, daemon=True).start()

    def on_queue_updated(self, queue_data):
        """Cập nhật dữ liệu hàng đợi từ Server lên UI Dashboard và TV"""
        self.latest_queue_data = queue_data
        current_calling = queue_data.get("current_calling")
        waiting_list = queue_data.get("waiting_list", [])

        # 1. Cập nhật Dashboard
        if current_calling:
            stt = current_calling.get("stt", "000")
            display_text = "CC" if stt == "CC" else stt
            self.number.setText(display_text)
            
            # Đổi màu hiển thị số nếu là cấp cứu
            if stt == "CC":
                self.number.setStyleSheet("font-size:100px; font-weight:bold; color: #dc3545; background: #f8f9fa; border: 1px solid #ddd; border-radius: 10px;")
                self.btn_priority.setText("HỦY CẤP CỨU")
                self.btn_priority.setStyleSheet("background-color: #333; color: white; font-weight: bold;")
                self.is_emergency = True
            else:
                self.number.setStyleSheet("font-size:100px; font-weight:bold; color: #0B5FA5; background: #f8f9fa; border: 1px solid #ddd; border-radius: 10px;")
                self.btn_priority.setText("GỌI CẤP CỨU")
                self.btn_priority.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold;")
                self.is_emergency = False
        else:
            self.number.setText("000")
            self.number.setStyleSheet("font-size:100px; font-weight:bold; color: #0B5FA5; background: #f8f9fa; border: 1px solid #ddd; border-radius: 10px;")
            self.btn_priority.setText("GỌI CẤP CỨU")
            self.btn_priority.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold;")
            self.is_emergency = False

        # 2. Cập nhật TV (nếu không ở chế độ trực)
        if not self.is_duty_mode:
            self.tv.update_queue_data(current_calling, waiting_list)
            
        # 3. Cập nhật Mini Panel
        if hasattr(self, 'mini') and not self.is_duty_mode:
            stt_panel = current_calling.get("stt", "000") if current_calling else "000"
            self.mini.update_number("CC" if stt_panel == "CC" else stt_panel)

    def next(self):
        """Hàm gọi số tiếp theo"""
        if self.is_duty_mode:
            return
        self.send_api_command("next")

    def toggle_priority(self):
        """Logic Cấp cứu"""
        if self.is_duty_mode:
            return
        self.send_api_command("emergency")

    def set_number(self):
        """Đặt số nhảy trực tiếp"""
        if self.is_duty_mode:
            return

        current_val = 1
        if self.latest_queue_data and self.latest_queue_data.get("last_number"):
            current_val = self.latest_queue_data.get("last_number")
            
        n, ok = QInputDialog.getInt(self, "Đặt số", "Nhập số thứ tự cần gọi:", 
                                     value=current_val, 
                                     minValue=1, 
                                     maxValue=999)
        if ok:
            self.send_api_command("set", {"number": n})

    def show_mini(self):
        self.hide()
        self.mini.show()

    def reset(self):
        self.send_api_command("reset")

    def show_settings(self):
        self.settings_window.load_config_to_ui()
        self.settings_window.show()

    def on_config_saved(self):
        self.apply_config_to_tv()
        # Poll lại ngay khi cấu hình thay đổi (có thể đổi số phòng hoặc IP)
        self.poll_queue()

    def apply_config_to_tv(self):
        room = self.config.get("room", "PHÒNG KHÁM")
        bs = self.config.get("doctor", "---")
        ktv = self.config.get("ktv", "---")
        self.tv.update_room(room)
        self.tv.update_staff(bs, ktv)

    # ===== CHẾ ĐỘ PHÒNG TRỰC =====

    def show_oncall_setup(self):
        """Mở cửa sổ thiết lập danh sách BS trực."""
        self.oncall_setup_window.refresh_table()
        self.oncall_setup_window.show()
        self.oncall_setup_window.raise_()

    def toggle_duty_mode(self):
        """Bật/tắt chế độ phòng trực."""
        if not self.is_duty_mode:
            # === BẬT chế độ trực ===
            dialog = DutyModeDialog(self.oncall_mgr, parent=self)
            if dialog.exec() == QDialog.Accepted and dialog.selected_name:
                doc_name  = dialog.selected_name
                doc_phone = dialog.selected_phone or ""

                self.is_duty_mode = True
                
                # Tạm dừng polling hàng đợi để giữ giao diện trực
                self.poll_timer.stop()

                # Cập nhật màn hình TV
                self.tv.enter_duty_mode(doc_name, doc_phone)

                # Cập nhật nút Dashboard
                self.btn_duty_mode.setText("🔆 TẮT PHÒNG TRỰC")
                self.btn_duty_mode.setStyleSheet(
                    "background-color: #e74c3c; color: white; height: 45px;"
                    " font-size: 15px; font-weight: bold;"
                )

                # Cập nhật Mini Panel
                if hasattr(self, 'mini'):
                    self.mini.set_duty_mode(True)

        else:
            # === TẮT chế độ trực ===
            self.is_duty_mode = False
            
            # Khởi động lại polling hàng đợi
            self.poll_timer.start()
            self.poll_queue()

            self.tv.exit_duty_mode()

            # Cập nhật nút
            self.btn_duty_mode.setText("🌙 CHẾ ĐỘ PHÒNG TRỰC")
            self.btn_duty_mode.setStyleSheet("""
                background-color: #fd7e14; color: white; height: 45px; font-size: 15px; font-weight: bold;
            """)

            # Cập nhật Mini Panel
            if hasattr(self, 'mini'):
                self.mini.set_duty_mode(False)