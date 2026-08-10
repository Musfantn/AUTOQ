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

# ─── CSS Constants (tránh lặp inline styles) ────────────────────────────────
_CSS_NUMBER_NORMAL = (
    "font-size:100px; font-weight:bold; color: #0B5FA5; "
    "background: #f8f9fa; border: 1px solid #ddd; border-radius: 10px;"
)
_CSS_NUMBER_EMERGENCY = (
    "font-size:100px; font-weight:bold; color: #dc3545; "
    "background: #f8f9fa; border: 1px solid #ddd; border-radius: 10px;"
)
_CSS_BTN_PRIORITY_NORMAL = "background-color: #dc3545; color: white; font-weight: bold;"
_CSS_BTN_PRIORITY_CANCEL = "background-color: #333; color: white; font-weight: bold;"
_CSS_BTN_DUTY_ON = (
    "background-color: #fd7e14; color: white; min-height: 45px; "
    "font-size: 15px; font-weight: bold;"
)
_CSS_BTN_DUTY_OFF = (
    "background-color: #e74c3c; color: white; min-height: 45px; "
    "font-size: 15px; font-weight: bold;"
)


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
        self._last_priority_ts = 0.0  # Timestamp của priority_notification đã xử lý gần nhất
        self._blink_count = 0
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._do_blink)

        self.setWindowTitle("Radiology Dashboard - BVĐK Kỳ Anh")
        self.setMinimumSize(680, 710)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # === CỘT TRÁI: ĐIỀU KHIỂN GỌI SỐ (330px) ===
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        
        # Hiển thị số
        self.number = QLabel("000")
        self.number.setStyleSheet(_CSS_NUMBER_NORMAL)
        self.number.setAlignment(Qt.AlignCenter)

        # Nút bấm
        btn_next = QPushButton("TIẾP THEO")
        self.btn_priority = QPushButton("GỌI CẤP CỨU")
        btn_set = QPushButton("NHẢY ĐẾN SỐ (SET)")
        btn_mini = QPushButton("MỞ MINI PANEL")
        btn_settings = QPushButton("CẤU HÌNH")
        btn_reset = QPushButton("RESET")

        # Nút Chế độ phòng trực
        btn_oncall_setup = QPushButton("⚙ THIẾT LẬP BS TRỰC")
        self.btn_duty_mode = QPushButton("🌙 CHẾ ĐỘ PHÒNG TRỰC")

        # Style cho các nút (dùng min-height thay vì height để không cắt chữ khi zoom)
        btn_next.setStyleSheet("background-color: #28a745; color: white; min-height: 55px; font-size: 18px; font-weight: bold; border-radius: 6px;")
        self.btn_priority.setStyleSheet(_CSS_BTN_PRIORITY_NORMAL)
        self.btn_priority.setMinimumHeight(40)
        btn_set.setStyleSheet("background-color: #007bff; color: white; min-height: 38px; font-weight: bold; border-radius: 5px;")
        btn_mini.setStyleSheet("background-color: #17a2b8; color: white; min-height: 35px; border-radius: 5px;")
        btn_settings.setStyleSheet("background-color: #6c757d; color: white; min-height: 35px; border-radius: 5px;")
        btn_reset.setStyleSheet("background-color: #dc3545; color: white; min-height: 35px; font-weight: bold; border-radius: 5px;")
        btn_oncall_setup.setStyleSheet("background-color: #6c757d; color: white; min-height: 35px; font-weight: bold; border-radius: 5px;")
        self.btn_duty_mode.setStyleSheet(_CSS_BTN_DUTY_ON)

        # Kết nối sự kiện
        btn_next.clicked.connect(self.next)
        self.btn_priority.clicked.connect(self.toggle_priority)
        btn_set.clicked.connect(self.set_number)
        btn_mini.clicked.connect(self.show_mini)
        btn_settings.clicked.connect(self.show_settings)
        btn_reset.clicked.connect(self.reset)
        btn_oncall_setup.clicked.connect(self.show_oncall_setup)
        self.btn_duty_mode.clicked.connect(self.toggle_duty_mode)

        left_layout.addWidget(self.number)
        left_layout.addWidget(btn_next)
        left_layout.addWidget(self.btn_priority)
        left_layout.addWidget(btn_set)
        left_layout.addWidget(btn_mini)
        left_layout.addWidget(btn_settings)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: #ccc; margin: 3px 0;")
        left_layout.addWidget(separator)

        left_layout.addWidget(btn_oncall_setup)
        left_layout.addWidget(self.btn_duty_mode)

        left_layout.addStretch()
        left_layout.addWidget(btn_reset)

        # === CỘT PHẢI: DANH SÁCH HÀNG ĐỢI (320px) ===
        right_frame = QFrame()
        right_frame.setMinimumWidth(320)
        right_frame.setStyleSheet("background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 10px;")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(6)

        lbl_queue_header = QLabel("📋 DANH SÁCH HÀNG ĐỢI")
        lbl_queue_header.setAlignment(Qt.AlignCenter)
        lbl_queue_header.setStyleSheet("font-size: 15px; font-weight: bold; color: #0B5FA5; border: none; padding-bottom: 2px; background: transparent;")
        right_layout.addWidget(lbl_queue_header)

        # Tạo 7 card hiển thị:
        # Card 0, 1, 2: 3 Bệnh nhân đã thực hiện (Đã gọi)
        # Card 3: Bệnh nhân hiện tại (Đang gọi)
        # Card 4, 5, 6: 3 Bệnh nhân đang chờ (Tiếp theo)
        self.queue_cards = []
        for idx in range(7):
            card = QFrame()
            card.setMinimumHeight(75)
            card.setStyleSheet("background: white; border: 1px solid #e2e8f0; border-radius: 8px;")
            
            c_layout = QHBoxLayout(card)
            c_layout.setContentsMargins(8, 6, 8, 6)
            c_layout.setSpacing(8)

            stt_lbl = QLabel("")
            stt_lbl.setMinimumSize(48, 42)
            stt_lbl.setAlignment(Qt.AlignCenter)
            stt_lbl.setStyleSheet("font-size: 16px; font-weight: bold; border-radius: 6px;")

            info_box = QWidget()
            info_box.setStyleSheet("background: transparent; border: none;")
            v_box = QVBoxLayout(info_box)
            v_box.setContentsMargins(0, 0, 0, 0)
            v_box.setSpacing(2)

            top_row = QHBoxLayout()
            name_lbl = QLabel("")
            name_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #1e293b; background: transparent; border: none;")
            
            tag_lbl = QLabel("")
            tag_lbl.setStyleSheet("font-size: 10px; font-weight: bold; padding: 2px 4px; border-radius: 4px; background: transparent;")
            
            top_row.addWidget(name_lbl, 1)
            top_row.addWidget(tag_lbl)

            sub_lbl = QLabel("")
            sub_lbl.setStyleSheet("font-size: 11px; color: #64748b; background: transparent; border: none;")

            v_box.addLayout(top_row)
            v_box.addWidget(sub_lbl)

            c_layout.addWidget(stt_lbl)
            c_layout.addWidget(info_box, 1)

            right_layout.addWidget(card)
            self.queue_cards.append({
                "frame": card,
                "stt": stt_lbl,
                "name": name_lbl,
                "tag": tag_lbl,
                "sub": sub_lbl,
            })

        right_layout.addStretch()

        main_layout.addWidget(left_widget)
        main_layout.addWidget(right_frame)

        # Khởi tạo cửa sổ phụ
        self.settings_window = SettingsWindow()
        self.settings_window.config_saved.connect(self.on_config_saved)
        self.oncall_setup_window = OnCallSetupWindow()
        self.mini = MiniPanel(self)
        
        # Kết nối Custom Signal
        self.queue_updated.connect(self.on_queue_updated)

        # === FIRESTORE REALTIME WATCHER / LISTENER (Không dùng Polling 2s) ===
        self.listener_worker = None
        self.start_realtime_listener()

        # Timer kiểm tra định kỳ 30 giây (Fallback / Heartbeat) phòng khi mất kết nối mạng
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self.poll_queue_once)
        self.heartbeat_timer.start(30000)

        self.apply_config_to_tv()

    def start_realtime_listener(self):
        """Khởi động Firestore Realtime Watcher Listener cho phòng hiện tại."""
        self.stop_realtime_listener()
        room_num = self.config.get("room_number", "1").strip()
        self.listener_worker = firestore_queue.FirestoreQueueListenerWorker(room_num, self)
        self.listener_worker.queue_updated.connect(self.queue_updated.emit)
        self.listener_worker.start()
        print(f"[Dashboard] Đã kết nối Firestore Realtime Listener cho Phòng {room_num}")
        # Đọc dữ liệu ban đầu 1 lần
        self.poll_queue_once()

    def stop_realtime_listener(self):
        """Dừng Firestore Realtime Listener."""
        if hasattr(self, 'listener_worker') and self.listener_worker and self.listener_worker.isRunning():
            self.listener_worker.stop()
            self.listener_worker = None

    def poll_queue_once(self):
        """Hàm đọc 1 lần trạng thái hàng đợi từ Cloud Firestore chạy ngầm"""
        if self.is_duty_mode:
            return
        room_num = self.config.get("room_number", "1").strip()
        
        def run():
            try:
                data = firestore_queue.get_room_queue(room_num)
                if data:
                    self.queue_updated.emit(data)
            except Exception as e:
                print(f"[Dashboard] Lỗi đọc hàng đợi: {e}")

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

        # === Xử lý thông báo bệnh nhân ưu tiên ===
        prio_notif = queue_data.get("priority_notification")
        if prio_notif and not prio_notif.get("seen", True):
            ts = prio_notif.get("timestamp", 0.0)
            if ts > self._last_priority_ts:
                self._last_priority_ts = ts
                stt_prio = prio_notif.get("stt", "?")
                name_prio = prio_notif.get("ten_bn", "")
                self._flash_priority_alert(stt_prio, name_prio)
                # Đánh dấu đã xử lý trong background
                room_num = self.config.get("room_number", "1").strip()
                import threading as _t
                _t.Thread(
                    target=lambda: __import__("firestore_queue").clear_priority_notification(room_num),
                    daemon=True
                ).start()

        current_calling = queue_data.get("current_calling")
        waiting_list = queue_data.get("waiting_list", [])
        history = queue_data.get("history", [])

        # 1. Cập nhật Dashboard (Ô hiển thị số lớn bên trái)
        if current_calling:
            stt = current_calling.get("stt", "000")
            self.number.setText("CC" if stt == "CC" else stt)
            
            if stt == "CC":
                self.number.setStyleSheet(_CSS_NUMBER_EMERGENCY)
                self.btn_priority.setText("HỦY CẤP CỨU")
                self.btn_priority.setStyleSheet(_CSS_BTN_PRIORITY_CANCEL)
                self.is_emergency = True
            else:
                self.number.setStyleSheet(_CSS_NUMBER_NORMAL)
                self.btn_priority.setText("GỌI CẤP CỨU")
                self.btn_priority.setStyleSheet(_CSS_BTN_PRIORITY_NORMAL)
                self.is_emergency = False
        else:
            self.number.setText("000")
            self.number.setStyleSheet(_CSS_NUMBER_NORMAL)
            self.btn_priority.setText("GỌI CẤP CỨU")
            self.btn_priority.setStyleSheet(_CSS_BTN_PRIORITY_NORMAL)
            self.is_emergency = False

        # 2. Cập nhật Cột hàng đợi bên phải (7 dòng)
        # a) 3 Bệnh nhân đã thực hiện (Indices 0, 1, 2)
        recent_history = history[-3:] if len(history) >= 3 else history
        padded_history = [None] * (3 - len(recent_history)) + recent_history

        for i in range(3):
            card = self.queue_cards[i]
            pat = padded_history[i]
            if pat:
                stt_val = pat.get("stt", "---")
                name_val = pat.get("ten_bn", "").upper()
                tuoi_val = pat.get("tuoi", "")
                dv_val = pat.get("dich_vu", "").replace("\n", ", ").strip()
                if len(dv_val) > 20:
                    dv_val = dv_val[:18] + "..."
                sub_text = f"Tuổi: {tuoi_val} | {dv_val}" if tuoi_val else dv_val

                card["frame"].setStyleSheet("background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 8px;")
                card["stt"].setText(stt_val)
                card["stt"].setStyleSheet("background: #94a3b8; color: white; font-size: 15px; font-weight: bold; border-radius: 6px;")
                card["name"].setText(name_val)
                card["name"].setStyleSheet("font-size: 13px; font-weight: bold; color: #64748b; background: transparent;")
                card["tag"].setText("✔ ĐÃ GỌI")
                card["tag"].setStyleSheet("font-size: 10px; font-weight: bold; color: #64748b; background: #e2e8f0; border-radius: 4px; padding: 2px 4px;")
                card["sub"].setText(sub_text)
                card["sub"].setStyleSheet("font-size: 11px; color: #94a3b8; background: transparent;")
            else:
                card["frame"].setStyleSheet("background: transparent; border: 1px dashed #e2e8f0; border-radius: 8px;")
                card["stt"].setText("")
                card["stt"].setStyleSheet("background: transparent;")
                card["name"].setText("---")
                card["name"].setStyleSheet("font-size: 13px; color: #cbd5e1; background: transparent;")
                card["tag"].setText("")
                card["tag"].setStyleSheet("background: transparent;")
                card["sub"].setText("")

        # b) Bệnh nhân hiện tại đang gọi (Index 3)
        curr_card = self.queue_cards[3]
        if current_calling:
            stt_val = current_calling.get("stt", "000")
            name_val = current_calling.get("ten_bn", "").upper()
            tuoi_val = current_calling.get("tuoi", "")
            dv_val = current_calling.get("dich_vu", "").replace("\n", ", ").strip()
            if len(dv_val) > 20:
                dv_val = dv_val[:18] + "..."
            sub_text = f"Tuổi: {tuoi_val} | {dv_val}" if tuoi_val else dv_val

            if stt_val == "CC":
                curr_card["frame"].setStyleSheet("background: #fef2f2; border: 2px solid #ef4444; border-radius: 8px;")
                curr_card["stt"].setText("CC")
                curr_card["stt"].setStyleSheet("background: #dc2626; color: white; font-size: 16px; font-weight: bold; border-radius: 6px;")
                curr_card["name"].setText("CẤP CỨU")
                curr_card["name"].setStyleSheet("font-size: 13px; font-weight: bold; color: #b91c1c; background: transparent;")
                curr_card["tag"].setText("🚨 CẤP CỨU")
                curr_card["tag"].setStyleSheet("font-size: 10px; font-weight: bold; color: white; background: #dc2626; border-radius: 4px; padding: 2px 4px;")
                curr_card["sub"].setText(dv_val or "SIÊU ÂM CẤP CỨU")
                curr_card["sub"].setStyleSheet("font-size: 11px; color: #ef4444; font-weight: bold; background: transparent;")
            else:
                curr_card["frame"].setStyleSheet("background: #eff6ff; border: 2px solid #0284c7; border-radius: 8px;")
                curr_card["stt"].setText(stt_val)
                curr_card["stt"].setStyleSheet("background: #0B5FA5; color: white; font-size: 16px; font-weight: bold; border-radius: 6px;")
                curr_card["name"].setText(name_val)
                curr_card["name"].setStyleSheet("font-size: 13px; font-weight: bold; color: #0369a1; background: transparent;")
                curr_card["tag"].setText("▶ ĐANG GỌI")
                curr_card["tag"].setStyleSheet("font-size: 10px; font-weight: bold; color: white; background: #0284c7; border-radius: 4px; padding: 2px 4px;")
                curr_card["sub"].setText(sub_text)
                curr_card["sub"].setStyleSheet("font-size: 11px; color: #0284c7; font-weight: bold; background: transparent;")
        else:
            curr_card["frame"].setStyleSheet("background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px;")
            curr_card["stt"].setText("000")
            curr_card["stt"].setStyleSheet("background: #e2e8f0; color: #94a3b8; font-size: 15px; font-weight: bold; border-radius: 6px;")
            curr_card["name"].setText("--- CHỜ GỌI SỐ ---")
            curr_card["name"].setStyleSheet("font-size: 13px; font-weight: bold; color: #94a3b8; background: transparent;")
            curr_card["tag"].setText("")
            curr_card["tag"].setStyleSheet("background: transparent;")
            curr_card["sub"].setText("")

        # c) 3 Bệnh nhân đang chờ tiếp theo (Indices 4, 5, 6)
        for i in range(3):
            card = self.queue_cards[4 + i]
            pat = waiting_list[i] if i < len(waiting_list) else None
            if pat:
                stt_val = pat.get("stt", "---")
                name_val = pat.get("ten_bn", "").upper()
                tuoi_val = pat.get("tuoi", "")
                dv_val = pat.get("dich_vu", "").replace("\n", ", ").strip()
                if len(dv_val) > 20:
                    dv_val = dv_val[:18] + "..."
                sub_text = f"Tuổi: {tuoi_val} | {dv_val}" if tuoi_val else dv_val

                card["frame"].setStyleSheet("background: white; border: 1px solid #cbd5e1; border-radius: 8px;")
                card["stt"].setText(stt_val)
                card["stt"].setStyleSheet("background: #059669; color: white; font-size: 15px; font-weight: bold; border-radius: 6px;")
                card["name"].setText(name_val)
                card["name"].setStyleSheet("font-size: 13px; font-weight: bold; color: #0f172a; background: transparent;")
                card["tag"].setText("CHỜ KHÁM")
                card["tag"].setStyleSheet("font-size: 10px; font-weight: bold; color: #047857; background: #d1fae5; border-radius: 4px; padding: 2px 4px;")
                card["sub"].setText(sub_text)
                card["sub"].setStyleSheet("font-size: 11px; color: #64748b; background: transparent;")
            else:
                card["frame"].setStyleSheet("background: transparent; border: 1px dashed #e2e8f0; border-radius: 8px;")
                card["stt"].setText("")
                card["stt"].setStyleSheet("background: transparent;")
                card["name"].setText("---")
                card["name"].setStyleSheet("font-size: 13px; color: #cbd5e1; background: transparent;")
                card["tag"].setText("")
                card["tag"].setStyleSheet("background: transparent;")
                card["sub"].setText("")

        # 3. Cập nhật TV (nếu không ở chế độ trực)
        if not self.is_duty_mode:
            self.tv.update_queue_data(current_calling, waiting_list)
            
        # 4. Cập nhật Mini Panel
        if hasattr(self, 'mini') and not self.is_duty_mode:
            stt_panel = current_calling.get("stt", "000") if current_calling else "000"
            self.mini.update_number("CC" if stt_panel == "CC" else stt_panel)

    def _flash_priority_alert(self, stt: str, ten_bn: str):
        """Hiển thị popup cảnh báo và khởi động nhấp nháy cửa sổ khi có BN ưu tiên."""
        # Popup cảnh báo
        msg = QMessageBox(self)
        msg.setWindowTitle("🚨 BỆNH NHÂN ƯU TIÊN")
        msg.setIcon(QMessageBox.Warning)
        msg.setText(
            f"⚠️ Có bệnh nhân Ưu tiên / cấp cứu mới!\n"
            f"STT: <b>{stt}</b>\n"
            f"Tên: <b>{ten_bn}</b>"
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setStyleSheet("""
            QMessageBox { background-color: #450a0a; }
            QLabel { color: #fca5a5; font-size: 14px; }
            QPushButton { background-color: #dc2626; color: white; min-width: 80px; padding: 6px; }
        """)
        # Khởi động hiệu ứng nhấp nháy
        self._blink_count = 12
        self._blink_state = True
        self._blink_timer.start(250)
        msg.exec()  # Modal — block cho đến khi nhấn OK
        self._blink_timer.stop()
        # Khôi phục style gốc của window
        self.setStyleSheet("")

    def _do_blink(self):
        """Nhấp nháy nền của dashboard và mini_panel."""
        if self._blink_count <= 0:
            self._blink_timer.stop()
            self.setStyleSheet("")
            if hasattr(self, 'mini'):
                self.mini.setStyleSheet("background:#0B5FA5; color:white; border-radius:10px; border: 1px solid white;")
            return
        self._blink_count -= 1
        self._blink_state = not self._blink_state
        if self._blink_state:
            self.setStyleSheet("background-color: #7f1d1d;")
            if hasattr(self, 'mini'):
                self.mini.setStyleSheet("background:#dc2626; color:white; border-radius:10px; border: 2px solid #fca5a5;")
        else:
            self.setStyleSheet("")
            if hasattr(self, 'mini'):
                self.mini.setStyleSheet("background:#0B5FA5; color:white; border-radius:10px; border: 1px solid white;")

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
        # Khởi động lại Realtime Listener cho phòng mới
        self.start_realtime_listener()

    def apply_config_to_tv(self):
        """Đọc config và áp dụng lên TV Display (bao gồm footer text)."""
        room   = self.config.get("room", "PHÒNG KHÁM")
        bs     = self.config.get("doctor", "---")
        ktv    = self.config.get("ktv", "---")
        footer = self.config.get("footer", "")

        self.tv.update_room(room)
        self.tv.update_staff(bs, ktv)

        if footer:
            self.tv.update_footer_text(footer)

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
                self.stop_realtime_listener()
                self.tv.enter_duty_mode(doc_name, doc_phone)

                self.btn_duty_mode.setText("🔆 TẮT PHÒNG TRỰC")
                self.btn_duty_mode.setStyleSheet(_CSS_BTN_DUTY_OFF)

                if hasattr(self, 'mini'):
                    self.mini.set_duty_mode(True)
        else:
            # === TẮT chế độ trực ===
            self.is_duty_mode = False
            self.start_realtime_listener()
            self.tv.exit_duty_mode()

            self.btn_duty_mode.setText("🌙 CHẾ ĐỘ PHÒNG TRỰC")
            self.btn_duty_mode.setStyleSheet(_CSS_BTN_DUTY_ON)

            if hasattr(self, 'mini'):
                self.mini.set_duty_mode(False)

    def closeEvent(self, event):
        """Dọn dẹp tài nguyên khi đóng ứng dụng."""
        self.stop_realtime_listener()
        if hasattr(self, 'heartbeat_timer'):
            self.heartbeat_timer.stop()
        super().closeEvent(event)