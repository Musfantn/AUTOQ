from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QInputDialog, QDialog, QScrollArea, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, Signal, QTimer
from datetime import datetime
import threading
import firestore_queue
from mini_panel import MiniPanel
from settings import SettingsWindow
from config_manager import ConfigManager
from oncall_manager import OnCallManager
from oncall_setup_window import OnCallSetupWindow
from duty_mode_dialog import DutyModeDialog
from tts_service import TTSService
from chat_service import ChatService
from chat_window import ChatWindow, ChatToastPopup
from version import APP_VERSION
from updater import UpdateCheckWorker, UpdateDialog
from speaker_hub import (
    CentralSpeakerHub,
    broadcast_speaker_event,
    get_default_speaker_mode,
    get_room_display_name,
    get_room_short_name,
    SPEAKER_MODE_HUB,
    SPEAKER_MODE_CLIENT,
    SPEAKER_MODE_LOCAL,
)

# ─── CSS Constants ──────────────────────────────────────────────────────────
_CSS_NUMBER_NORMAL = (
    "font-size: 92px; font-weight: bold; color: #0B5FA5; "
    "background: #f8f9fa; border: 2px solid #cbd5e1; border-radius: 12px;"
)
_CSS_NUMBER_EMERGENCY = (
    "font-size: 92px; font-weight: bold; color: #dc3545; "
    "background: #fef2f2; border: 2px solid #ef4444; border-radius: 12px;"
)
_CSS_BTN_PRIORITY_NORMAL = (
    "background-color: #dc3545; color: white; font-weight: bold; min-height: 38px; border-radius: 6px;"
)
_CSS_BTN_PRIORITY_CANCEL = (
    "background-color: #334155; color: white; font-weight: bold; min-height: 38px; border-radius: 6px;"
)
_CSS_BTN_DUTY_ON = (
    "background-color: #fd7e14; color: white; min-height: 42px; "
    "font-size: 14px; font-weight: bold; border-radius: 6px;"
)
_CSS_BTN_DUTY_OFF = (
    "background-color: #e74c3c; color: white; min-height: 42px; "
    "font-size: 14px; font-weight: bold; border-radius: 6px;"
)


class Dashboard(QWidget):
    # Signal truyền dữ liệu nhận được từ thread chạy ngầm về UI thread an toàn
    queue_updated = Signal(dict, bool)  # (queue_data, should_announce_tts)

    def __init__(self, tv):
        super().__init__()
        self.tv = tv
        self.config = ConfigManager()
        self.oncall_mgr = OnCallManager()
        self.tts = TTSService(self)
        self.speaker_hub = CentralSpeakerHub(self.tts, self)

        # Biến trạng thái
        self.is_emergency = False
        self.is_duty_mode = False
        self.latest_queue_data = None
        self.speaker_mode = SPEAKER_MODE_CLIENT
        self._cmd_lock = threading.Lock()

        self.setWindowTitle(f"Bảng Điều Khiển Gọi Số Phòng Khám - BVĐK Kỳ Anh (v{APP_VERSION})")
        self.setMinimumSize(860, 750)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # =====================================================================
        # CỘT TRÁI: ĐIỀU KHIỂN GỌI SỐ & TRẠM LOA TRUNG TÂM (350px)
        # =====================================================================
        left_widget = QWidget()
        left_widget.setMinimumWidth(345)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.lbl_room_header = QLabel("PHÒNG SIÊU ÂM 1")
        self.lbl_room_header.setAlignment(Qt.AlignCenter)
        self.lbl_room_header.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #0B5FA5; padding: 2px;"
        )

        # Thanh hiển thị trạng thái Trạm Phát Loa Trung Tâm / Kết nối Loa
        self.lbl_hub_banner = QLabel("")
        self.lbl_hub_banner.setAlignment(Qt.AlignCenter)
        self.lbl_hub_banner.setWordWrap(True)
        self.lbl_hub_banner.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #0f766e; background: #ccfbf1; "
            "border: 1px solid #5eead4; border-radius: 6px; padding: 5px;"
        )

        # Nút thông báo có bản cập nhật mới (Chỉ tự động hiện ra khi phát hiện phiên bản mới trên Server)
        self.btn_update_banner = QPushButton("⬆️ ĐÃ CÓ BẢN CẬP NHẬT MỚI — BẤM ĐỂ CẬP NHẬT")
        self.btn_update_banner.setVisible(False)
        self.btn_update_banner.setStyleSheet(
            "QPushButton { background-color: #ea580c; color: white; font-size: 13px; "
            "font-weight: bold; padding: 7px 10px; border-radius: 6px; border: 1px solid #fed7aa; }"
            "QPushButton:hover { background-color: #c2410c; }"
        )
        self.btn_update_banner.clicked.connect(self.open_update_dialog)

        # Hiển thị số thứ tự hiện tại
        self.number = QLabel("000")
        self.number.setStyleSheet(_CSS_NUMBER_NORMAL)
        self.number.setAlignment(Qt.AlignCenter)

        # Nhãn phụ hiển thị số lần gọi & tiến độ
        self.lbl_call_meta = QLabel("Trạng thái: Chờ gọi số | Đã khám: 0 ca")
        self.lbl_call_meta.setAlignment(Qt.AlignCenter)
        self.lbl_call_meta.setStyleSheet("font-size: 13px; font-weight: bold; color: #475569;")

        # 1. Nút GỌI SỐ TIẾP THEO
        self.btn_next = QPushButton("▶  TIẾP THEO (GỌI SỐ MỚI)")
        self.btn_next.setStyleSheet(
            "QPushButton { background-color: #16a34a; color: white; min-height: 58px; "
            "font-size: 18px; font-weight: bold; border-radius: 8px; }"
            "QPushButton:hover { background-color: #15803d; }"
            "QPushButton:pressed { background-color: #166534; }"
        )

        # 2. Cụm nút GỌI LẠI & CHƯA VÀO PHÒNG (QUA LƯỢT)
        recall_row = QHBoxLayout()
        recall_row.setSpacing(8)

        self.btn_recall = QPushButton("🔊 GỌI LẠI SỐ NÀY")
        self.btn_recall.setToolTip("Đọc loa gọi lại bệnh nhân số hiện tại (khi BN chưa nghe thấy)")
        self.btn_recall.setStyleSheet(
            "QPushButton { background-color: #f59e0b; color: white; min-height: 46px; "
            "font-size: 14px; font-weight: bold; border-radius: 6px; }"
            "QPushButton:hover { background-color: #d97706; }"
        )

        self.btn_skip = QPushButton("⏭ CHƯA VÀO (QUA LƯỢT)")
        self.btn_skip.setToolTip("Lưu số này vào danh sách 'Chưa vào phòng' để gọi lại sau và tự động gọi số kế tiếp")
        self.btn_skip.setStyleSheet(
            "QPushButton { background-color: #0284c7; color: white; min-height: 46px; "
            "font-size: 14px; font-weight: bold; border-radius: 6px; }"
            "QPushButton:hover { background-color: #0369a1; }"
        )

        recall_row.addWidget(self.btn_recall, 1)
        recall_row.addWidget(self.btn_skip, 1)

        # 3. Các nút chức năng khác
        btn_set = QPushButton("🔢 NHẢY ĐẾN SỐ / GỌI SỐ BẤT KỲ (SET)")
        btn_set.setStyleSheet(
            "background-color: #2563eb; color: white; min-height: 38px; font-weight: bold; border-radius: 6px;"
        )

        self.btn_priority = QPushButton("🚨 GỌI CẤP CỨU")
        self.btn_priority.setStyleSheet(_CSS_BTN_PRIORITY_NORMAL)

        # Nút Bật/Tắt loa nhanh & Mở Mini Panel
        util_row = QHBoxLayout()
        util_row.setSpacing(8)

        self.btn_toggle_tts = QPushButton("🔊 LOA: ĐANG BẬT")
        self.btn_toggle_tts.setStyleSheet(
            "background-color: #0d9488; color: white; min-height: 36px; font-weight: bold; border-radius: 6px;"
        )

        btn_mini = QPushButton("🗗 MỞ MINI PANEL")
        btn_mini.setStyleSheet(
            "background-color: #0891b2; color: white; min-height: 36px; font-weight: bold; border-radius: 6px;"
        )
        util_row.addWidget(self.btn_toggle_tts, 1)
        util_row.addWidget(btn_mini, 1)

        btn_settings = QPushButton("⚙ CẤU HÌNH PHÒNG")
        btn_settings.setStyleSheet(
            "background-color: #64748b; color: white; min-height: 35px; font-weight: bold; border-radius: 6px;"
        )

        self.btn_chat = QPushButton("💬 CHAT NỘI BỘ GIỮA CÁC PHÒNG")
        self.btn_chat.setStyleSheet(
            "background-color: #7c3aed; color: white; min-height: 36px; font-weight: bold; border-radius: 6px;"
        )

        btn_oncall_setup = QPushButton("👨‍⚕️ THIẾT LẬP DANH SÁCH BS TRỰC")
        btn_oncall_setup.setStyleSheet(
            "background-color: #64748b; color: white; min-height: 35px; font-weight: bold; border-radius: 6px;"
        )

        self.btn_duty_mode = QPushButton("🌙 CHẾ ĐỘ PHÒNG TRỰC")
        self.btn_duty_mode.setStyleSheet(_CSS_BTN_DUTY_ON)

        btn_reset = QPushButton("🔄 RESET SỐ VỀ 000")
        btn_reset.setStyleSheet(
            "background-color: #dc3545; color: white; min-height: 35px; font-weight: bold; border-radius: 6px;"
        )

        # Kết nối sự kiện
        self.btn_next.clicked.connect(self.next)
        self.btn_recall.clicked.connect(self.recall_current)
        self.btn_skip.clicked.connect(self.skip_and_next)
        btn_set.clicked.connect(self.set_number)
        self.btn_priority.clicked.connect(self.toggle_priority)
        self.btn_toggle_tts.clicked.connect(self.toggle_tts_mute)
        btn_mini.clicked.connect(self.show_mini)
        btn_settings.clicked.connect(self.show_settings)
        self.btn_chat.clicked.connect(self.show_chat_window)
        btn_oncall_setup.clicked.connect(self.show_oncall_setup)
        self.btn_duty_mode.clicked.connect(self.toggle_duty_mode)
        btn_reset.clicked.connect(self.reset)

        left_layout.addWidget(self.lbl_room_header)
        left_layout.addWidget(self.lbl_hub_banner)
        left_layout.addWidget(self.btn_update_banner)
        left_layout.addWidget(self.number)
        left_layout.addWidget(self.lbl_call_meta)
        left_layout.addWidget(self.btn_next)
        left_layout.addLayout(recall_row)
        left_layout.addWidget(btn_set)
        left_layout.addWidget(self.btn_priority)
        left_layout.addLayout(util_row)
        left_layout.addWidget(self.btn_chat)
        left_layout.addWidget(btn_settings)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: #cbd5e1; margin: 4px 0;")
        left_layout.addWidget(separator)

        left_layout.addWidget(btn_oncall_setup)
        left_layout.addWidget(self.btn_duty_mode)
        left_layout.addStretch()
        left_layout.addWidget(btn_reset)

        # =====================================================================
        # CỘT PHẢI: DANH SÁCH CHƯA VÀO PHÒNG & LỊCH SỬ GỌI LẠI NHANH (455px+)
        # =====================================================================
        right_frame = QFrame()
        right_frame.setMinimumWidth(455)
        right_frame.setStyleSheet("background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 10px;")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)

        # --- PHẦN 1: BỆNH NHÂN CHƯA VÀO PHÒNG / QUA LƯỢT ---
        lbl_missed_header = QLabel("⏳ BỆNH NHÂN CHƯA VÀO PHÒNG (CHỜ GỌI LẠI)")
        lbl_missed_header.setAlignment(Qt.AlignCenter)
        lbl_missed_header.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #b45309; background: #fef3c7; "
            "border: 1px solid #fcd34d; border-radius: 6px; padding: 6px;"
        )
        right_layout.addWidget(lbl_missed_header)

        self.missed_scroll = QScrollArea()
        self.missed_scroll.setWidgetResizable(True)
        self.missed_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.missed_container = QWidget()
        self.missed_container.setStyleSheet("background: transparent; border: none;")
        self.missed_list_layout = QVBoxLayout(self.missed_container)
        self.missed_list_layout.setContentsMargins(0, 0, 0, 0)
        self.missed_list_layout.setSpacing(6)
        self.missed_list_layout.setAlignment(Qt.AlignTop)
        self.missed_scroll.setWidget(self.missed_container)
        right_layout.addWidget(self.missed_scroll, 1)

        # --- PHẦN 2: LỊCH SỬ CÁC SỐ VỪA GỌI GẦN ĐÂY ---
        lbl_history_header = QLabel("🕘 CÁC SỐ VỪA GỌI GẦN ĐÂY (BẤM ĐỂ GỌI LẠI)")
        lbl_history_header.setAlignment(Qt.AlignCenter)
        lbl_history_header.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #0B5FA5; background: #e0f2fe; "
            "border: 1px solid #bae6fd; border-radius: 6px; padding: 6px;"
        )
        right_layout.addWidget(lbl_history_header)

        self.history_container = QWidget()
        self.history_container.setStyleSheet("background: transparent; border: none;")
        self.history_list_layout = QVBoxLayout(self.history_container)
        self.history_list_layout.setContentsMargins(0, 0, 0, 0)
        self.history_list_layout.setSpacing(6)
        self.history_list_layout.setAlignment(Qt.AlignTop)
        right_layout.addWidget(self.history_container, 1)

        main_layout.addWidget(left_widget, 4)
        main_layout.addWidget(right_frame, 5)

        # Khởi tạo cửa sổ phụ
        self.settings_window = SettingsWindow()
        self.settings_window.config_saved.connect(self.on_config_saved)
        self.settings_window.test_tts_requested.connect(self.test_tts_voice)
        self.oncall_setup_window = OnCallSetupWindow()
        self.mini = MiniPanel(self)

        # Khởi tạo Dịch vụ & Cửa sổ Chat Nhanh Nội Bộ (Hybrid LAN UDP + Firestore)
        init_room = self.config.get("room_number", "1").strip().lower()
        init_doc = self.config.get("doctor", "---").strip()
        self.chat_service = ChatService(local_room_id=init_room, local_doctor_name=init_doc, parent=self)
        self.chat_window = ChatWindow(self.chat_service)
        self.chat_toast = ChatToastPopup()
        self.chat_toast.reply_requested.connect(self.open_chat_reply_to)
        self.chat_service.unread_count_changed.connect(self._on_chat_unread_changed)
        self.chat_service.message_received.connect(self._on_chat_message_received)
        self.chat_service.start()

        # Kết nối Custom Signals
        self.queue_updated.connect(self.on_queue_updated)
        self.tts.announcement_started.connect(self._on_tts_announcement_started)

        # Khởi tạo cấu hình TV & Trạm Loa Trung Tâm
        self.apply_config_to_tv()

        # Khởi động Firestore Realtime Listener cho phòng hiện tại
        self.listener_worker = None
        self.start_realtime_listener()

        # Timer kiểm tra định kỳ 30 giây (Fallback / Heartbeat)
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self.poll_queue_once)
        self.heartbeat_timer.start(30000)

        # Tự động kiểm tra bản cập nhật mới sau khi mở app 4 giây (không chặn UI)
        self._latest_update_meta = None
        self._update_check_worker = None
        QTimer.singleShot(4000, self._check_update_silently)

    # ─── REALTIME LISTENER & CLOUD COMMANDS ──────────────────────────────────

    def start_realtime_listener(self):
        """Khởi động Firestore Realtime Watcher Listener cho phòng hiện tại."""
        self.stop_realtime_listener()
        room_num = self.config.get("room_number", "1").strip()
        self.listener_worker = firestore_queue.FirestoreQueueListenerWorker(room_num, self)
        self.listener_worker.queue_updated.connect(lambda data: self.queue_updated.emit(data, False))
        self.listener_worker.start()
        self.poll_queue_once()

    def stop_realtime_listener(self):
        if hasattr(self, "listener_worker") and self.listener_worker and self.listener_worker.isRunning():
            self.listener_worker.stop()
            self.listener_worker = None

    def poll_queue_once(self):
        if self.is_duty_mode:
            return
        room_num = self.config.get("room_number", "1").strip()

        def run():
            try:
                data = firestore_queue.get_room_queue(room_num)
                if data:
                    self.queue_updated.emit(data, False)
            except Exception as e:
                print(f"[Dashboard] Lỗi đọc hàng đợi: {e}")

        threading.Thread(target=run, daemon=True).start()

    def send_api_command(self, action: str, payload: dict | None = None, announce_tts: bool = False):
        """Thực thi lệnh gọi số trên Firestore ở thread ngầm (tuần tự hóa qua _cmd_lock) và cập nhật giao diện."""
        room_num = self.config.get("room_number", "1").strip().lower()

        def run():
            with self._cmd_lock:
                try:
                    data = None
                    if action == "next":
                        data = firestore_queue.next_patient(room_num)
                    elif action == "recall_current":
                        data = firestore_queue.recall_current_patient(room_num)
                    elif action == "skip_and_next":
                        data = firestore_queue.skip_current_and_next(room_num)
                    elif action == "recall_specific":
                        target_stt = payload.get("stt", 1) if payload else 1
                        data = firestore_queue.recall_specific_number(room_num, target_stt)
                    elif action == "remove_missed":
                        target_stt = str(payload.get("stt", "")).strip() if payload else ""
                        q = firestore_queue.get_room_queue(room_num)
                        q["missed_list"] = [
                            m for m in q.get("missed_list", [])
                            if str(m.get("stt", "")).strip() != target_stt
                        ]
                        firestore_queue.save_room_queue(room_num, q)
                        data = q
                    elif action == "emergency":
                        data = firestore_queue.toggle_emergency(room_num)
                    elif action == "set":
                        num = payload.get("number", 1) if payload else 1
                        data = firestore_queue.set_number(room_num, num)
                    elif action == "reset":
                        data = firestore_queue.reset_queue(room_num)

                    if data:
                        self.queue_updated.emit(data, announce_tts)
                except Exception as e:
                    print(f"[Dashboard] Lỗi thực hiện lệnh '{action}': {e}")

        threading.Thread(target=run, daemon=True).start()

    # ─── CẬP NHẬT UI & PHÁT LOA TTS ──────────────────────────────────────────

    def on_queue_updated(self, queue_data: dict, should_announce_tts: bool = False):
        """Cập nhật trạng thái gọi số lên Dashboard, MiniPanel và TV Display."""
        self.latest_queue_data = queue_data

        current_calling = queue_data.get("current_calling")
        missed_list = queue_data.get("missed_list", [])
        history = queue_data.get("history", [])
        last_number = int(queue_data.get("last_number", 0))

        # 1. Cập nhật ô số lớn bên trái
        if current_calling and current_calling.get("stt"):
            stt = str(current_calling.get("stt", "000"))
            call_count = int(current_calling.get("call_count", 1))
            is_recall = bool(current_calling.get("is_recall", False))

            if stt == "CC":
                self.number.setText("CC")
                self.number.setStyleSheet(_CSS_NUMBER_EMERGENCY)
                self.btn_priority.setText("HỦY CẤP CỨU")
                self.btn_priority.setStyleSheet(_CSS_BTN_PRIORITY_CANCEL)
                self.is_emergency = True
                self.lbl_call_meta.setText(f"🚨 ĐANG CẤP CỨU | Đã khám: {len(history)} ca")
            else:
                self.number.setText(stt)
                self.number.setStyleSheet(_CSS_NUMBER_NORMAL)
                self.btn_priority.setText("🚨 GỌI CẤP CỨU")
                self.btn_priority.setStyleSheet(_CSS_BTN_PRIORITY_NORMAL)
                self.is_emergency = False

                status_tag = f"🔊 Đang gọi lại (Lần {call_count})" if (is_recall or call_count > 1) else "Đang gọi (Lần 1)"
                self.lbl_call_meta.setText(
                    f"{status_tag} | Số cao nhất: {last_number:03d} | Đã khám: {len(history)} ca"
                )

            if should_announce_tts and stt != "CC" and not self.is_duty_mode:
                self._announce_number_tts(stt)
                self.tv.flash_calling_number()
        else:
            self.number.setText("000")
            self.number.setStyleSheet(_CSS_NUMBER_NORMAL)
            self.btn_priority.setText("🚨 GỌI CẤP CỨU")
            self.btn_priority.setStyleSheet(_CSS_BTN_PRIORITY_NORMAL)
            self.is_emergency = False
            self.lbl_call_meta.setText(f"Trạng thái: Chờ gọi số | Đã khám: {len(history)} ca")

        # 2. Cập nhật Danh sách Bệnh nhân Chưa vào phòng (Missed List)
        self._rebuild_missed_list_ui(missed_list)

        # 3. Cập nhật Lịch sử 5 số vừa gọi gần nhất (History Quick Recall)
        self._rebuild_history_list_ui(history)

        # 4. Cập nhật TV Display
        if not self.is_duty_mode:
            self.tv.update_queue_data(current_calling, missed_list, last_number)

        # 5. Cập nhật Mini Panel
        if hasattr(self, "mini") and not self.is_duty_mode:
            stt_panel = current_calling.get("stt", "000") if current_calling else "000"
            self.mini.update_number("CC" if stt_panel == "CC" else stt_panel)

        # 6. Nếu máy này đang phát loa (Hub hoặc Local), tải trước âm thanh 3 số tiếp theo
        if self.speaker_mode in (SPEAKER_MODE_HUB, SPEAKER_MODE_LOCAL):
            room_num = self.config.get("room_number", "1").strip().lower()
            room_name = self.config.get("room", get_room_display_name(room_num)).strip()
            self.tts.prefetch_upcoming(last_number, room_name, room_num)

    def _on_tts_announcement_started(self, room_number: str, stt_str: str, sentence: str):
        """Hiển thị thông báo trực quan trên Trạm Phát Loa Trung Tâm (Phòng 2) khi loa đang đọc."""
        if self.speaker_mode == SPEAKER_MODE_HUB:
            short_room = get_room_short_name(room_number)
            self.lbl_hub_banner.setText(
                f"📢 TRẠM LOA TRUNG TÂM (11 PHÒNG)\n🔊 Đang đọc: {short_room} — Số {stt_str}"
            )

    def _rebuild_missed_list_ui(self, missed_list: list):
        """Vẽ lại danh sách các số chưa vào phòng kèm nút Gọi lại."""
        while self.missed_list_layout.count():
            item = self.missed_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not missed_list:
            empty_lbl = QLabel("Không có bệnh nhân qua lượt / chưa vào phòng.")
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet(
                "color: #94a3b8; font-size: 13px; padding: 18px; border: 1px dashed #cbd5e1; border-radius: 8px;"
            )
            self.missed_list_layout.addWidget(empty_lbl)
            return

        for m in missed_list[:8]:
            stt_str = str(m.get("stt", "---"))
            call_cnt = int(m.get("call_count", 1))
            skipped_ts = m.get("skipped_at") or m.get("called_at")
            time_str = datetime.fromtimestamp(skipped_ts).strftime("%H:%M") if skipped_ts else ""

            row_card = QFrame()
            row_card.setStyleSheet("background: #fffbeb; border: 1px solid #f59e0b; border-radius: 8px;")
            r_layout = QHBoxLayout(row_card)
            r_layout.setContentsMargins(10, 6, 10, 6)
            r_layout.setSpacing(8)

            badge = QLabel(f"SỐ {stt_str}")
            badge.setMinimumSize(72, 34)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                "background: #d97706; color: white; font-size: 15px; font-weight: bold; border-radius: 6px; border: none;"
            )

            info_lbl = QLabel(f"Đã gọi {call_cnt} lần" + (f" ({time_str})" if time_str else ""))
            info_lbl.setStyleSheet(
                "font-size: 12px; color: #92400e; font-weight: bold; border: none; background: transparent;"
            )

            btn_recall_item = QPushButton("🔊 Gọi lại")
            btn_recall_item.setCursor(Qt.PointingHandCursor)
            btn_recall_item.setStyleSheet(
                "QPushButton { background: #16a34a; color: white; font-size: 12px; font-weight: bold; padding: 6px 10px; border-radius: 5px; border: none; }"
                "QPushButton:hover { background: #15803d; }"
            )
            btn_recall_item.clicked.connect(lambda checked=False, s=stt_str: self.recall_specific(s))

            btn_del_item = QPushButton("✖")
            btn_del_item.setFixedWidth(28)
            btn_del_item.setToolTip("Xóa khỏi danh sách chờ gọi lại")
            btn_del_item.setStyleSheet(
                "QPushButton { background: #e2e8f0; color: #475569; font-weight: bold; padding: 5px; border-radius: 5px; border: none; }"
                "QPushButton:hover { background: #cbd5e1; color: #dc2626; }"
            )
            btn_del_item.clicked.connect(lambda checked=False, s=stt_str: self.remove_missed(s))

            r_layout.addWidget(badge)
            r_layout.addWidget(info_lbl, 1)
            r_layout.addWidget(btn_recall_item)
            r_layout.addWidget(btn_del_item)

            self.missed_list_layout.addWidget(row_card)

    def _rebuild_history_list_ui(self, history: list):
        """Vẽ danh sách 5 số vừa gọi gần nhất để bác sĩ có thể gọi lại chỉ với 1 click."""
        while self.history_list_layout.count():
            item = self.history_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        recent = list(reversed(history[-5:])) if history else []
        if not recent:
            empty_lbl = QLabel("Chưa có lịch sử số đã gọi trong ngày.")
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet(
                "color: #94a3b8; font-size: 13px; padding: 18px; border: 1px dashed #cbd5e1; border-radius: 8px;"
            )
            self.history_list_layout.addWidget(empty_lbl)
            return

        for h in recent:
            stt_str = str(h.get("stt", "---"))
            called_ts = h.get("called_at") or h.get("timestamp")
            time_str = datetime.fromtimestamp(called_ts).strftime("%H:%M:%S") if called_ts else ""
            dur_sec = int(h.get("exam_duration_sec", 0))
            dur_str = f"{round(dur_sec / 60.0, 1)}p" if dur_sec > 0 else ""

            row_card = QFrame()
            row_card.setStyleSheet("background: white; border: 1px solid #e2e8f0; border-radius: 8px;")
            r_layout = QHBoxLayout(row_card)
            r_layout.setContentsMargins(10, 5, 10, 5)
            r_layout.setSpacing(8)

            badge = QLabel(f"SỐ {stt_str}")
            badge.setMinimumSize(72, 32)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                "background: #64748b; color: white; font-size: 14px; font-weight: bold; border-radius: 6px; border: none;"
            )

            meta_text = f"Gọi lúc: {time_str}" + (f" | Khám: {dur_str}" if dur_str else "")
            info_lbl = QLabel(meta_text)
            info_lbl.setStyleSheet("font-size: 12px; color: #475569; border: none; background: transparent;")

            btn_recall_hist = QPushButton("🔊 Gọi lại")
            btn_recall_hist.setCursor(Qt.PointingHandCursor)
            btn_recall_hist.setStyleSheet(
                "QPushButton { background: #0284c7; color: white; font-size: 12px; font-weight: bold; padding: 5px 10px; border-radius: 5px; border: none; }"
                "QPushButton:hover { background: #0369a1; }"
            )
            btn_recall_hist.clicked.connect(lambda checked=False, s=stt_str: self.recall_specific(s))

            r_layout.addWidget(badge)
            r_layout.addWidget(info_lbl, 1)
            r_layout.addWidget(btn_recall_hist)

            self.history_list_layout.addWidget(row_card)

    # ─── CÁC HÀNH ĐỘNG ĐIỀU KHIỂN CỦA BÁC SĨ & ĐIỀU PHỐI LOA ─────────────────

    def _announce_number_tts(self, stt: str):
        """Điều phối đọc loa theo vai trò máy trạm:
        - Nếu là Trạm Phát Loa Trung Tâm (Phòng 2 - 'hub'): Đọc loa trực tiếp qua Hub FIFO Queue.
        - Nếu là Máy Trạm Phòng Khám Phụ (Phòng 1, 3, 4, 5 - 'client'): Phát gói tin LAN UDP Broadcast
          về Máy Phòng 2 (< 2ms) kết hợp đồng bộ Cloud Firestore, không phát loa tại máy phụ.
        - Nếu là Chế độ Độc lập ('local'): Phát loa trực tiếp tại máy này.
        """
        if not self.tts.enabled:
            return

        room_num = self.config.get("room_number", "1").strip().lower()
        room_name = self.config.get("room", get_room_display_name(room_num)).strip()

        if self.speaker_mode == SPEAKER_MODE_HUB:
            # Đánh dấu vào bộ khử trùng lặp của Hub và xếp hàng đọc loa ngay lập tức
            self.speaker_hub.trigger_announcement(room_num, room_name, stt, cooldown_sec=0.5)
        elif self.speaker_mode == SPEAKER_MODE_CLIENT:
            # Gửi tín hiệu LAN UDP Broadcast tức thì về Máy Phòng Siêu Âm 2
            broadcast_speaker_event(room_num, room_name, stt)
            self.lbl_hub_banner.setText(
                f"📡 Đã gửi lệnh gọi Số {stt} ({room_name}) về Trạm Loa Phòng Siêu Âm 2"
            )
        else:
            # Chế độ phát loa độc lập tại phòng hiện tại
            self.tts.announce_patient(stt=stt, room_name=room_name, room_number=room_num)

    def _apply_optimistic_call(self, next_stt: str, new_last_num: int, is_recall: bool = False, call_count: int = 1):
        """Cập nhật tức thì (Optimistic UI Update - 0ms) trên Dashboard, MiniPanel, TV Display
        và bộ nhớ đệm local trước khi chờ phản hồi HTTP từ Cloud Firestore.
        Đảm bảo bác sĩ bấm liên tiếp nhiều lần vẫn nhảy số mượt mà, không bao giờ trùng số.
        """
        if self.latest_queue_data is None:
            room_num = self.config.get("room_number", "1").strip().lower()
            self.latest_queue_data = firestore_queue._new_queue(room_num)

        curr_obj = {
            "stt": next_stt,
            "call_count": call_count,
            "is_recall": is_recall,
        }
        self.latest_queue_data["last_number"] = new_last_num
        self.latest_queue_data["current_calling"] = curr_obj

        self.number.setText(next_stt)
        self.number.setStyleSheet(_CSS_NUMBER_NORMAL)
        if hasattr(self, "mini"):
            self.mini.update_number(next_stt)

        missed_list = self.latest_queue_data.get("missed_list", [])
        self.tv.update_queue_data(curr_obj, missed_list, new_last_num)
        self.tv.flash_calling_number()
        self._announce_number_tts(next_stt)

    def next(self):
        """Gọi bệnh nhân số thứ tự tiếp theo và kích hoạt loa NGAY LẬP TỨC (0ms delay)."""
        if self.is_duty_mode:
            return
        last_num = int(self.latest_queue_data.get("last_number", 0)) if self.latest_queue_data else 0
        new_num = last_num + 1
        next_stt = f"{new_num:03d}"
        self._apply_optimistic_call(next_stt, new_num, is_recall=False, call_count=1)
        self.send_api_command("next", announce_tts=False)

    def recall_current(self):
        """Gọi lại bệnh nhân đang hiển thị hiện tại (phát loa tức thì 0ms)."""
        if self.is_duty_mode:
            return
        curr = self.latest_queue_data.get("current_calling") if self.latest_queue_data else None
        if not curr or not curr.get("stt") or curr.get("stt") == "CC":
            QMessageBox.information(self, "Thông báo", "Hiện chưa có số thứ tự nào đang gọi để gọi lại.")
            return
        stt_curr = str(curr.get("stt"))
        call_cnt = int(curr.get("call_count", 1)) + 1
        last_num = int(self.latest_queue_data.get("last_number", 0))
        self._apply_optimistic_call(stt_curr, last_num, is_recall=True, call_count=call_cnt)
        self.send_api_command("recall_current", announce_tts=False)

    def skip_and_next(self):
        """Đưa số hiện tại vào danh sách 'Chưa vào phòng' và gọi luôn số tiếp theo (0ms delay)."""
        if self.is_duty_mode:
            return
        last_num = int(self.latest_queue_data.get("last_number", 0)) if self.latest_queue_data else 0
        new_num = last_num + 1
        next_stt = f"{new_num:03d}"
        self._apply_optimistic_call(next_stt, new_num, is_recall=False, call_count=1)
        self.send_api_command("skip_and_next", announce_tts=False)

    def recall_specific(self, stt_str: str):
        """Gọi lại một số cụ thể từ danh sách Chưa vào phòng hoặc Lịch sử vừa gọi (0ms delay)."""
        if self.is_duty_mode:
            return
        try:
            target_num = int(str(stt_str).strip())
        except ValueError:
            target_num = 1
        stt_fmt = f"{target_num:03d}"
        last_num = max(int(self.latest_queue_data.get("last_number", 0)) if self.latest_queue_data else 0, target_num)
        self._apply_optimistic_call(stt_fmt, last_num, is_recall=True, call_count=2)
        self.send_api_command("recall_specific", {"stt": stt_fmt}, announce_tts=False)

    def remove_missed(self, stt_str: str):
        """Xóa một số khỏi danh sách chờ gọi lại."""
        self.send_api_command("remove_missed", {"stt": stt_str}, announce_tts=False)

    def toggle_priority(self):
        """Bật/Tắt trạng thái Cấp cứu."""
        if self.is_duty_mode:
            return
        self.send_api_command("emergency", announce_tts=False)

    def set_number(self):
        """Nhảy trực tiếp đến số thứ tự mong muốn và kích hoạt loa."""
        if self.is_duty_mode:
            return
        current_val = 1
        if self.latest_queue_data and self.latest_queue_data.get("last_number"):
            current_val = int(self.latest_queue_data.get("last_number"))

        n, ok = QInputDialog.getInt(
            self,
            "Nhảy đến số thứ tự",
            "Nhập số thứ tự bệnh nhân cần gọi:",
            value=max(1, current_val),
            minValue=1,
            maxValue=999,
        )
        if ok:
            stt_target = f"{n:03d}"
            self._apply_optimistic_call(stt_target, n, is_recall=False, call_count=1)
            self.send_api_command("set", {"number": n}, announce_tts=False)

    def toggle_tts_mute(self):
        """Bật/Tắt nhanh loa TTS ngay trên Dashboard."""
        new_state = not self.tts.enabled
        self.tts.set_enabled(new_state)
        self.config.set("tts_enabled", "1" if new_state else "0")
        self._update_tts_button_ui()

    def _update_tts_button_ui(self):
        if self.tts.enabled:
            if self.speaker_mode == SPEAKER_MODE_CLIENT:
                self.btn_toggle_tts.setText("📡 GỌI LOA P.2: BẬT")
            else:
                self.btn_toggle_tts.setText("🔊 LOA: ĐANG BẬT")
            self.btn_toggle_tts.setStyleSheet(
                "background-color: #0d9488; color: white; min-height: 36px; font-weight: bold; border-radius: 6px;"
            )
        else:
            self.btn_toggle_tts.setText("🔇 LOA: ĐÃ TẮT")
            self.btn_toggle_tts.setStyleSheet(
                "background-color: #64748b; color: white; min-height: 36px; font-weight: bold; border-radius: 6px;"
            )

    def test_tts_voice(self):
        """Phát thử câu gọi loa mẫu khi người dùng bấm 'Nghe thử loa' trong Cấu hình."""
        room_num = self.settings_window.get_selected_room_id()
        room_name = self.settings_window.room.text().strip() or get_room_display_name(room_num)
        selected_mode = self.settings_window.cbo_speaker_mode.currentData()
        self.tts.set_enabled(True)
        self.tts.set_volume(self.settings_window.slider_volume.value())

        if selected_mode == SPEAKER_MODE_CLIENT:
            broadcast_speaker_event(room_num, room_name, "024")
            QMessageBox.information(
                self.settings_window,
                "Đã gửi tín hiệu thử loa",
                f"Đã gửi tín hiệu gọi thử 'Số 24 - {room_name}' về Trạm Phát Loa Trung Tâm (Phòng Siêu Âm 2).",
            )
        else:
            self.tts.announce_patient(stt=24, room_name=room_name, room_number=room_num)

    def show_mini(self):
        self.hide()
        self.mini.show()

    def reset(self):
        ans = QMessageBox.question(
            self,
            "Xác nhận Reset",
            "Bạn có chắc chắn muốn đặt lại (Reset) số thứ tự của phòng về 000?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            self.send_api_command("reset", announce_tts=False)

    def show_settings(self):
        self.settings_window.load_config_to_ui()
        self.settings_window.show()
        self.settings_window.raise_()

    def on_config_saved(self):
        self.apply_config_to_tv()
        self.start_realtime_listener()
        room_num = self.config.get("room_number", "1").strip().lower()
        bs = self.config.get("doctor", "---").strip()
        ktv = self.config.get("ktv", "---").strip()
        threading.Thread(
            target=lambda: firestore_queue.set_room_staff(room_num, bs, ktv),
            daemon=True,
        ).start()

    def apply_config_to_tv(self):
        """Đọc config và áp dụng lên TV Display + TTS Service + CentralSpeakerHub."""
        room_num = self.config.get("room_number", "1").strip().lower()
        default_room_title = get_room_display_name(room_num)
        room = self.config.get("room", default_room_title) or default_room_title
        bs = self.config.get("doctor", "---")
        ktv = self.config.get("ktv", "---")
        footer = self.config.get("footer", "")

        saved_mode = self.config.get("speaker_mode", "").strip()
        if not saved_mode:
            saved_mode = get_default_speaker_mode(room_num)
        self.speaker_mode = saved_mode

        self.lbl_room_header.setText(f"{room.upper()} (Mã phòng: {room_num.upper()})")
        self.tv.update_room(room)
        self.tv.update_staff(bs, ktv)
        if hasattr(self, "chat_service"):
            self.chat_service.set_identity(room_num, bs)
        if footer:
            self.tv.update_footer_text(footer)

        tts_enabled = str(self.config.get("tts_enabled", "1")) != "0"
        try:
            tts_vol = int(self.config.get("tts_volume", "100"))
        except ValueError:
            tts_vol = 100
        self.tts.set_enabled(tts_enabled)
        self.tts.set_volume(tts_vol)
        self._update_tts_button_ui()

        # Quản lý khởi động / dừng CentralSpeakerHub theo chế độ loa
        self.speaker_hub.set_local_room(room_num)
        if self.speaker_mode == SPEAKER_MODE_HUB:
            self.speaker_hub.start_hub()
            self.lbl_hub_banner.setText(
                "📢 TRẠM LOA TRUNG TÂM: Đang nối loa & nhận lệnh gọi số của 11 phòng (Siêu âm, TMH, NSTH, ĐTĐ, ĐNĐ, LHN, CNHH)"
            )
            self.lbl_hub_banner.setStyleSheet(
                "font-size: 12px; font-weight: bold; color: #0f766e; background: #ccfbf1; "
                "border: 1px solid #5eead4; border-radius: 6px; padding: 5px;"
            )
        elif self.speaker_mode == SPEAKER_MODE_CLIENT:
            self.speaker_hub.stop_hub()
            self.lbl_hub_banner.setText(
                "📡 CHẾ ĐỘ PHÒNG KHÁM PHỤ: Tự động gửi lệnh phát loa về Máy Phòng Siêu Âm 2"
            )
            self.lbl_hub_banner.setStyleSheet(
                "font-size: 12px; font-weight: bold; color: #0369a1; background: #e0f2fe; "
                "border: 1px solid #7dd3fc; border-radius: 6px; padding: 5px;"
            )
        else:
            self.speaker_hub.stop_hub()
            self.lbl_hub_banner.setText(
                "🔊 CHẾ ĐỘ LOA ĐỘC LẬP: Chỉ phát loa cho riêng phòng khám này"
            )
            self.lbl_hub_banner.setStyleSheet(
                "font-size: 12px; font-weight: bold; color: #475569; background: #f1f5f9; "
                "border: 1px solid #cbd5e1; border-radius: 6px; padding: 5px;"
            )

    # ─── CHAT NHANH NỘI BỘ GIỮA CÁC PHÒNG ───────────────────────────────────

    def show_chat_window(self):
        self.chat_window.show()
        self.chat_window.raise_()
        self.chat_window.activateWindow()

    def open_chat_reply_to(self, target_room_id: str):
        self.show_chat_window()
        self.chat_window.select_target_room(target_room_id)

    def _on_chat_unread_changed(self, unread_count: int):
        if unread_count > 0:
            self.btn_chat.setText(f"💬 CHAT NỘI BỘ ({unread_count} TIN MỚI 🔴)")
            self.btn_chat.setStyleSheet(
                "background-color: #dc2626; color: white; min-height: 36px; font-weight: bold; border-radius: 6px;"
            )
        else:
            self.btn_chat.setText("💬 CHAT NỘI BỘ GIỮA CÁC PHÒNG")
            self.btn_chat.setStyleSheet(
                "background-color: #7c3aed; color: white; min-height: 36px; font-weight: bold; border-radius: 6px;"
            )
        if hasattr(self, "mini"):
            self.mini.update_chat_badge(unread_count)

    def _on_chat_message_received(self, msg: dict, is_incoming: bool):
        if is_incoming and not self.chat_window.isVisible():
            self.chat_toast.show_message_toast(msg)
            if self.config.get("chat_sound_enabled", "1") != "0":
                try:
                    QApplication.beep()
                except Exception:
                    pass

    # ─── TỰ ĐỘNG KIỂM TRA & CẬP NHẬT PHẦN MỀM ────────────────────────────────

    def _check_update_silently(self):
        if not self.isVisible() and not (hasattr(self, "mini") and self.mini.isVisible()):
            return
        if self._update_check_worker and self._update_check_worker.isRunning():
            return
        self._update_check_worker = UpdateCheckWorker()
        self._update_check_worker.checked.connect(self._on_silent_update_checked)
        self._update_check_worker.start()

    def _on_silent_update_checked(self, meta: dict, has_new: bool):
        self._latest_update_meta = meta
        if has_new:
            ver = meta.get("latest_version", "")
            self.btn_update_banner.setText(f"⬆️ ĐÃ CÓ BẢN CẬP NHẬT MỚI (v{ver}) — BẤM ĐỂ CẬP NHẬT")
            self.btn_update_banner.setVisible(True)
            if meta.get("is_mandatory") and self.isVisible():
                self.open_update_dialog()

    def open_update_dialog(self):
        dlg = UpdateDialog(initial_meta=self._latest_update_meta, parent=self)
        dlg.exec()

    # ─── CHẾ ĐỘ PHÒNG TRỰC ──────────────────────────────────────────────────

    def show_oncall_setup(self):
        self.oncall_setup_window.refresh_table()
        self.oncall_setup_window.show()
        self.oncall_setup_window.raise_()

    def toggle_duty_mode(self):
        room_num = self.config.get("room_number", "1").strip()
        if not self.is_duty_mode:
            dialog = DutyModeDialog(self.oncall_mgr, parent=self)
            if dialog.exec() == QDialog.Accepted and dialog.selected_name:
                doc_name = dialog.selected_name
                doc_phone = dialog.selected_phone or ""

                self.is_duty_mode = True
                self.stop_realtime_listener()
                self.tv.enter_duty_mode(doc_name, doc_phone)

                self.btn_duty_mode.setText("🔆 TẮT PHÒNG TRỰC")
                self.btn_duty_mode.setStyleSheet(_CSS_BTN_DUTY_OFF)

                if hasattr(self, "mini"):
                    self.mini.set_duty_mode(True)

                threading.Thread(
                    target=lambda: firestore_queue.set_duty_mode(room_num, True, doc_name, doc_phone),
                    daemon=True,
                ).start()
        else:
            self.is_duty_mode = False
            self.start_realtime_listener()
            self.tv.exit_duty_mode()

            self.btn_duty_mode.setText("🌙 CHẾ ĐỘ PHÒNG TRỰC")
            self.btn_duty_mode.setStyleSheet(_CSS_BTN_DUTY_ON)

            if hasattr(self, "mini"):
                self.mini.set_duty_mode(False)

            threading.Thread(
                target=lambda: firestore_queue.set_duty_mode(room_num, False),
                daemon=True,
            ).start()

    def closeEvent(self, event):
        self.stop_realtime_listener()
        self.speaker_hub.stop_hub()
        if hasattr(self, "chat_service"):
            self.chat_service.stop()
        if hasattr(self, "_update_check_worker") and self._update_check_worker and self._update_check_worker.isRunning():
            self._update_check_worker.wait(1000)
        if hasattr(self, "heartbeat_timer"):
            self.heartbeat_timer.stop()
        for child_win in ("mini", "settings_window", "oncall_setup_window", "chat_window", "chat_toast", "tv"):
            w = getattr(self, child_win, None)
            if w is not None:
                try:
                    w.close()
                except Exception:
                    pass
        super().closeEvent(event)
