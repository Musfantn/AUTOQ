from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QStackedWidget, QApplication
)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QPixmap, QGuiApplication
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
import os
import sys

# Link logo dự phòng online
ONLINE_LOGO_URL = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR-WQz3PjdjFwRym5KeITVAmlgNgpiA0ae5rg&s"


def resource_path(path):
    """Hỗ trợ lấy đường dẫn file khi đóng gói ứng dụng (Inno Setup {app}/assets hoặc PyInstaller _MEIPASS)."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        ext_path = os.path.join(exe_dir, path)
        if os.path.exists(ext_path):
            return ext_path
    if hasattr(sys, "_MEIPASS"):
        mei_path = os.path.join(sys._MEIPASS, path)
        if os.path.exists(mei_path):
            return mei_path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, path)


class TVDisplay(QWidget):
    def __init__(self, room_name="PHÒNG SIÊU ÂM 1"):
        super().__init__()
        self.setWindowTitle("Hệ thống Gọi số - BVĐK Thị xã Kỳ Anh")
        self.setStyleSheet("background: white;")

        self._flash_count = 0
        self._flash_state = False
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._do_flash_number)

        # --- CẤU HÌNH GIAO DIỆN CHÍNH ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 1. HEADER (Chứa Logo và Tên BV) - DÙNG CHUNG ---
        header = QFrame()
        header.setMinimumHeight(120)
        header.setStyleSheet("background: #0B5FA5; color: white; border: none;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(25, 8, 25, 8)
        header_layout.setSpacing(18)

        logo_container = QWidget()
        logo_container_layout = QVBoxLayout(logo_container)
        logo_container_layout.setContentsMargins(0, 0, 0, 0)
        logo_container_layout.setAlignment(Qt.AlignCenter)

        self.logo = QLabel()
        self.logo.setMinimumSize(100, 100)
        self.logo.setAlignment(Qt.AlignCenter)
        self.load_logo()

        logo_container_layout.addWidget(self.logo)
        header_layout.addWidget(logo_container)

        title_container = QVBoxLayout()
        title_container.setSpacing(4)
        title_container.setAlignment(Qt.AlignVCenter)

        hospital = QLabel("BỆNH VIỆN ĐA KHOA THỊ XÃ KỲ ANH")
        hospital.setStyleSheet("font-size: 36px; font-weight: bold; font-family: 'Arial';")

        dept = QLabel("KHOA CHẨN ĐOÁN HÌNH ẢNH")
        dept.setStyleSheet("font-size: 30px; font-weight: bold; color: #E0E0E0; font-family: 'Arial';")

        title_container.addWidget(hospital)
        title_container.addWidget(dept)

        header_layout.addLayout(title_container)
        header_layout.addStretch()

        # --- 2. STACKED WIDGET (Chứa 2 chế độ hiển thị) ---
        self.stacked = QStackedWidget()

        # ===== PAGE 0: Màn hình gọi số theo STT =====
        normal_page = QWidget()
        normal_page.setStyleSheet("background: #f1f5f9;")
        normal_layout = QVBoxLayout(normal_page)
        normal_layout.setContentsMargins(0, 0, 0, 0)
        normal_layout.setSpacing(0)

        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(16, 14, 16, 14)
        body_layout.setSpacing(16)

        # --- CỘT TRÁI (Số thứ tự đang gọi - Chiếm 72% diện tích màn hình) ---
        self.left_frame = QFrame()
        self.left_frame.setStyleSheet("background: white; border-radius: 20px; border: 3px solid #cbd5e1;")
        left_layout = QVBoxLayout(self.left_frame)
        left_layout.setContentsMargins(24, 18, 24, 18)
        left_layout.setSpacing(8)
        left_layout.setAlignment(Qt.AlignCenter)

        self.room_label = QLabel(room_name.upper())
        self.room_label.setAlignment(Qt.AlignCenter)
        self.room_label.setStyleSheet(
            "font-size: 72px; color: #0B5FA5; font-weight: 900; font-family: 'Arial Black', 'Arial'; border: none; background: transparent;"
        )

        self.lbl_invite = QLabel("XIN MỜI BỆNH NHÂN SỐ THỨ TỰ")
        self.lbl_invite.setAlignment(Qt.AlignCenter)
        self.lbl_invite.setStyleSheet(
            "font-size: 36px; color: #334155; font-weight: bold; border: none; background: transparent;"
        )

        self.number_style_active = (
            "font-size: 380px; color: #dc2626; font-weight: 900; font-family: 'Arial Black', 'Segoe UI Black', 'Arial'; "
            "background: #fff5f5; border: 4px solid #fecaca; border-radius: 24px; padding: 0px 20px;"
        )
        self.number_style_flash = (
            "font-size: 380px; color: #ffffff; font-weight: 900; font-family: 'Arial Black', 'Segoe UI Black', 'Arial'; "
            "background: #dc2626; border: 4px solid #b91c1c; border-radius: 24px; padding: 0px 20px;"
        )
        self.number_style_idle = (
            "font-size: 380px; color: #94a3b8; font-weight: 900; font-family: 'Arial Black', 'Segoe UI Black', 'Arial'; "
            "background: #f8fafc; border: 3px dashed #cbd5e1; border-radius: 24px; padding: 0px 20px;"
        )
        self.number_style_emergency = (
            "font-size: 290px; color: #dc2626; font-weight: 900; font-family: 'Arial Black', 'Segoe UI Black', 'Arial'; "
            "background: #fff5f5; border: 4px solid #dc2626; border-radius: 24px; padding: 0px 20px;"
        )

        self.number = QLabel("000")
        self.number.setAlignment(Qt.AlignCenter)
        self.number.setMinimumHeight(390)
        self.number.setStyleSheet(self.number_style_idle)

        self.lbl_status = QLabel("--- CHỜ GỌI SỐ ---")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet(
            "font-size: 40px; color: #0284c7; font-weight: bold; border: none; margin-top: 4px; background: transparent;"
        )

        self.lbl_sub_note = QLabel("Vui lòng chuẩn bị phiếu chỉ định khi vào phòng")
        self.lbl_sub_note.setAlignment(Qt.AlignCenter)
        self.lbl_sub_note.setStyleSheet(
            "font-size: 26px; color: #64748b; font-weight: normal; border: none; background: transparent;"
        )

        left_layout.addWidget(self.room_label)
        left_layout.addWidget(self.lbl_invite)
        left_layout.addWidget(self.number, 1)  # Cho phép ô số thứ tự giãn tối đa chiếm trọn diện tích chính
        left_layout.addWidget(self.lbl_status)
        left_layout.addWidget(self.lbl_sub_note)

        # --- CỘT PHẢI (Số chuẩn bị tiếp theo & Số qua lượt chờ gọi lại - Chiếm 28%) ---
        right_frame = QFrame()
        right_frame.setStyleSheet("background: white; border-radius: 20px; border: 1px solid #cbd5e1;")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(18, 18, 18, 18)
        right_layout.setSpacing(12)
        right_layout.setAlignment(Qt.AlignTop)

        # Phần 1: Các số chuẩn bị tiếp theo
        upcoming_title = QLabel("SỐ TIẾP THEO (CHUẨN BỊ)")
        upcoming_title.setAlignment(Qt.AlignCenter)
        upcoming_title.setStyleSheet(
            "font-size: 30px; color: #0B5FA5; font-weight: bold; border: none; padding-bottom: 4px; background: transparent;"
        )
        right_layout.addWidget(upcoming_title)

        self.upcoming_cards = []
        for i in range(3):
            card_frame = QFrame()
            card_frame.setMinimumHeight(78)
            card_frame.setStyleSheet("background: #f8fafc; border-radius: 10px; border: 1px solid #cbd5e1;")
            c_layout = QHBoxLayout(card_frame)
            c_layout.setContentsMargins(16, 8, 16, 8)
            c_layout.setSpacing(16)

            badge = QLabel("---")
            badge.setMinimumSize(95, 54)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                "background-color: #0B5FA5; color: white; font-size: 30px; font-weight: bold; border-radius: 8px; border: none;"
            )

            desc = QLabel("Vui lòng chuẩn bị")
            desc.setStyleSheet("font-size: 24px; color: #334155; font-weight: bold; border: none; background: transparent;")

            c_layout.addWidget(badge)
            c_layout.addWidget(desc, 1)
            right_layout.addWidget(card_frame)
            self.upcoming_cards.append({"frame": card_frame, "badge": badge, "desc": desc})

        # Đường kẻ phân cách
        sep_right = QFrame()
        sep_right.setFrameShape(QFrame.HLine)
        sep_right.setStyleSheet("background: #e2e8f0; min-height: 2px; margin: 6px 0;")
        right_layout.addWidget(sep_right)

        # Phần 2: Danh sách số qua lượt / chưa vào phòng
        self.missed_title = QLabel("SỐ QUA LƯỢT / CHƯA VÀO")
        self.missed_title.setAlignment(Qt.AlignCenter)
        self.missed_title.setStyleSheet(
            "font-size: 28px; color: #d97706; font-weight: bold; border: none; padding-bottom: 2px; background: transparent;"
        )
        right_layout.addWidget(self.missed_title)

        self.missed_cards = []
        for i in range(2):
            card_frame = QFrame()
            card_frame.setMinimumHeight(74)
            card_frame.setStyleSheet("background: #fffbeb; border-radius: 10px; border: 1px solid #fcd34d;")
            c_layout = QHBoxLayout(card_frame)
            c_layout.setContentsMargins(16, 8, 16, 8)
            c_layout.setSpacing(16)

            badge = QLabel("")
            badge.setMinimumSize(95, 50)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                "background-color: #d97706; color: white; font-size: 28px; font-weight: bold; border-radius: 8px; border: none;"
            )

            desc = QLabel("")
            desc.setStyleSheet("font-size: 21px; color: #92400e; font-weight: bold; border: none; background: transparent;")

            c_layout.addWidget(badge)
            c_layout.addWidget(desc, 1)
            right_layout.addWidget(card_frame)
            self.missed_cards.append({"frame": card_frame, "badge": badge, "desc": desc})

        right_layout.addStretch(1)

        body_layout.addWidget(self.left_frame, 72)
        body_layout.addWidget(right_frame, 28)

        # Footer bình thường
        normal_footer = QWidget()
        normal_footer.setMinimumHeight(110)
        normal_footer.setStyleSheet("background: #0B5FA5; border-top: 3px solid #084B83;")

        nf_layout = QVBoxLayout(normal_footer)
        nf_layout.setContentsMargins(0, 5, 0, 5)
        nf_layout.setSpacing(0)

        self.staff = QLabel("BS: --- | KTV: ---")
        self.staff.setAlignment(Qt.AlignCenter)
        self.staff.setStyleSheet("font-size: 32px; font-weight: bold; color: #FFD700; font-family: 'Arial';")

        self.marquee_base_text = " Xin vui lòng chuẩn bị giấy tờ và lắng nghe loa gọi số thứ tự trước khi vào phòng khám. "
        self.marquee_label = QLabel(self.marquee_base_text)
        self.marquee_label.setAlignment(Qt.AlignCenter)
        self.marquee_label.setStyleSheet("font-size: 28px; color: white; font-weight: normal; font-family: 'Arial';")

        nf_layout.addWidget(self.staff)
        nf_layout.addWidget(self.marquee_label)

        normal_layout.addWidget(body_widget, 1)
        normal_layout.addWidget(normal_footer)

        # ===== PAGE 1: Màn hình trực ngoài giờ =====
        duty_page = QWidget()
        duty_page.setStyleSheet("background: #f0f4f8;")
        duty_layout = QVBoxLayout(duty_page)
        duty_layout.setContentsMargins(0, 0, 0, 0)
        duty_layout.setSpacing(0)

        duty_body = QWidget()
        duty_body.setStyleSheet("background: #f0f4f8;")
        duty_body_layout = QVBoxLayout(duty_body)
        duty_body_layout.setContentsMargins(60, 60, 60, 40)
        duty_body_layout.setSpacing(20)
        duty_body_layout.setAlignment(Qt.AlignCenter)

        duty_room_title = QLabel("PHÒNG SIÊU ÂM CẤP CỨU")
        duty_room_title.setAlignment(Qt.AlignCenter)
        duty_room_title.setStyleSheet(
            "font-size: 90px; font-weight: bold; color: #c0392b; font-family: 'Arial'; padding: 10px;"
        )

        duty_room_en = QLabel("Emergency Ultrasound Room")
        duty_room_en.setAlignment(Qt.AlignCenter)
        duty_room_en.setStyleSheet(
            "font-size: 48px; font-weight: normal; color: #7f8c8d; font-family: 'Arial'; font-style: italic; margin-bottom: 40px;"
        )

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background: #bdc3c7; min-height: 3px; margin: 10px 100px;")

        duty_doctor_header = QLabel("👨‍⚕️  BÁC SĨ TRỰC")
        duty_doctor_header.setAlignment(Qt.AlignCenter)
        duty_doctor_header.setStyleSheet(
            "font-size: 50px; font-weight: bold; color: #0B5FA5; font-family: 'Arial'; margin-top: 30px;"
        )

        self.duty_doctor_name = QLabel("---")
        self.duty_doctor_name.setAlignment(Qt.AlignCenter)
        self.duty_doctor_name.setStyleSheet(
            "font-size: 120px; font-weight: bold; color: #2c3e50; font-family: 'Arial'; padding: 10px;"
        )

        duty_phone_header = QLabel("📞  SỐ ĐIỆN THOẠI")
        duty_phone_header.setAlignment(Qt.AlignCenter)
        duty_phone_header.setStyleSheet(
            "font-size: 50px; font-weight: bold; color: #0B5FA5; font-family: 'Arial'; margin-top: 20px;"
        )

        self.duty_phone = QLabel("---")
        self.duty_phone.setAlignment(Qt.AlignCenter)
        self.duty_phone.setStyleSheet(
            "font-size: 120px; font-weight: bold; color: #e74c3c; font-family: 'Arial'; padding: 10px;"
        )

        duty_body_layout.addWidget(duty_room_title)
        duty_body_layout.addWidget(duty_room_en)
        duty_body_layout.addWidget(separator)
        duty_body_layout.addWidget(duty_doctor_header)
        duty_body_layout.addWidget(self.duty_doctor_name)
        duty_body_layout.addWidget(duty_phone_header)
        duty_body_layout.addWidget(self.duty_phone)
        duty_body_layout.addStretch()

        duty_footer = QWidget()
        duty_footer.setMinimumHeight(70)
        duty_footer.setStyleSheet("background: #0B5FA5; border-top: 3px solid #084B83;")

        df_layout = QVBoxLayout(duty_footer)
        df_layout.setContentsMargins(0, 5, 0, 5)
        df_layout.setAlignment(Qt.AlignCenter)

        self.duty_marquee_base_text = "     ★  Bệnh nhân siêu âm: Vui lòng bấm chuông tại phòng trực hoặc liên hệ số điện thoại bác sĩ trực  ★     "
        self.duty_marquee_label = QLabel(self.duty_marquee_base_text)
        self.duty_marquee_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.duty_marquee_label.setStyleSheet(
            "font-size: 32px; font-weight: bold; color: #FFD700; font-family: 'Arial';"
        )

        df_layout.addWidget(self.duty_marquee_label)

        duty_layout.addWidget(duty_body, 1)
        duty_layout.addWidget(duty_footer)

        self.stacked.addWidget(normal_page)   # index 0
        self.stacked.addWidget(duty_page)     # index 1

        main_layout.addWidget(header)
        main_layout.addWidget(self.stacked, 1)

        QTimer.singleShot(100, self.move_to_secondary_screen)

        self.marquee_timer = QTimer(self)
        self.marquee_timer.timeout.connect(self.scroll_text)
        self.marquee_timer.start(150)

    def load_logo(self):
        local_path = resource_path("assets/logo.png")
        if os.path.exists(local_path):
            self.set_logo_pixmap(QPixmap(local_path))
        else:
            self.logo.setText("Loading...")
            self.download_online_logo()

    def download_online_logo(self):
        self.manager = QNetworkAccessManager()
        self.manager.finished.connect(self.on_logo_downloaded)
        self.manager.get(QNetworkRequest(QUrl(ONLINE_LOGO_URL)))

    def on_logo_downloaded(self, reply):
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                self.set_logo_pixmap(pixmap)
                return
        self.logo.setText("BV KY ANH")
        self.logo.setStyleSheet("font-size: 20px; color: white; font-weight: bold; border: 2px solid white; border-radius: 58px;")

    def set_logo_pixmap(self, pixmap):
        self.logo.setPixmap(pixmap.scaled(115, 115, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def scroll_text(self):
        current_text = self.marquee_label.text()
        if current_text:
            self.marquee_label.setText(current_text[1:] + current_text[0])

        duty_text = self.duty_marquee_label.text()
        if duty_text:
            self.duty_marquee_label.setText(duty_text[1:] + duty_text[0])

    # ─── HIỆU ỨNG NHẤP NHÁY SỐ KHI GỌI HOẶC GỌI LẠI ─────────────────────────

    def flash_calling_number(self):
        """Nhấp nháy số thứ tự trên màn hình TV để thu hút sự chú ý của bệnh nhân."""
        self._flash_count = 8
        self._flash_state = False
        self._flash_timer.start(250)

    def _do_flash_number(self):
        if self._flash_count <= 0:
            self._flash_timer.stop()
            self.number.setStyleSheet(self.number_style_active)
            self.left_frame.setStyleSheet("background: white; border-radius: 20px; border: 3px solid #cbd5e1;")
            return

        self._flash_count -= 1
        self._flash_state = not self._flash_state
        if self._flash_state:
            self.number.setStyleSheet(self.number_style_flash)
            self.left_frame.setStyleSheet("background: #fef2f2; border-radius: 20px; border: 4px solid #dc2626;")
        else:
            self.number.setStyleSheet(self.number_style_active)
            self.left_frame.setStyleSheet("background: white; border-radius: 20px; border: 3px solid #cbd5e1;")

    # ─── CẬP NHẬT DỮ LIỆU GỌI SỐ LÊN TV ─────────────────────────────────────

    def update_queue_data(self, current_calling, missed_list=None, last_number: int = 0):
        """Cập nhật số đang gọi, các số chuẩn bị tiếp theo và số qua lượt."""
        missed_list = missed_list or []

        # 1. Cập nhật Cột trái (Số đang gọi)
        if current_calling and current_calling.get("stt"):
            stt = str(current_calling.get("stt", "000"))
            call_count = int(current_calling.get("call_count", 1))
            is_recall = bool(current_calling.get("is_recall", False))

            if stt == "CC":
                self._flash_timer.stop()
                self.number.setStyleSheet(self.number_style_emergency)
                self.number.setText("CC")
                self.lbl_status.setText("🚨 ĐANG THỰC HIỆN CA CẤP CỨU")
                self.lbl_status.setStyleSheet(
                    "font-size: 40px; color: #dc2626; font-weight: bold; border: none; margin-top: 4px; background: transparent;"
                )
                self.lbl_sub_note.setText("Xin quý bệnh nhân vui lòng chờ trong giây lát")
            else:
                self.number.setStyleSheet(self.number_style_active)
                self.number.setText(stt)
                if is_recall or call_count > 1:
                    self.lbl_status.setText(f"🔊 MỜI BỆNH NHÂN VÀO PHÒNG (GỌI LẦN {call_count})")
                    self.lbl_status.setStyleSheet(
                        "font-size: 40px; color: #d97706; font-weight: bold; border: none; margin-top: 4px; background: transparent;"
                    )
                else:
                    self.lbl_status.setText("MỜI BỆNH NHÂN VÀO PHÒNG KHÁM")
                    self.lbl_status.setStyleSheet(
                        "font-size: 40px; color: #0284c7; font-weight: bold; border: none; margin-top: 4px; background: transparent;"
                    )
                self.lbl_sub_note.setText("Vui lòng chuẩn bị phiếu chỉ định khi vào phòng")
        else:
            self._flash_timer.stop()
            self.number.setStyleSheet(self.number_style_idle)
            self.number.setText("000")
            self.lbl_status.setText("--- CHỜ GỌI SỐ ---")
            self.lbl_status.setStyleSheet(
                "font-size: 40px; color: #64748b; font-weight: bold; border: none; margin-top: 4px; background: transparent;"
            )
            self.lbl_sub_note.setText("Quý bệnh nhân vui lòng theo dõi số thứ tự trên màn hình")

        # 2. Cập nhật Cột phải - Phần trên: 3 Số chuẩn bị tiếp theo
        base_num = int(last_number or 0)
        for i in range(3):
            card = self.upcoming_cards[i]
            if base_num > 0:
                next_n = base_num + i + 1
                card["badge"].setText(f"{next_n:03d}")
                card["badge"].setStyleSheet(
                    "background-color: #0B5FA5; color: white; font-size: 30px; font-weight: bold; border-radius: 8px; border: none;"
                )
                card["desc"].setText("Chuẩn bị vào khám" if i == 0 else "Đang chờ đến lượt")
                card["frame"].setStyleSheet("background: #f8fafc; border-radius: 10px; border: 1px solid #cbd5e1;")
            else:
                card["badge"].setText("---")
                card["badge"].setStyleSheet(
                    "background-color: #cbd5e1; color: white; font-size: 28px; font-weight: bold; border-radius: 8px; border: none;"
                )
                card["desc"].setText("Chờ phát số")
                card["frame"].setStyleSheet("background: #f8fafc; border-radius: 10px; border: 1px dashed #cbd5e1;")

        # 3. Cập nhật Cột phải - Phần dưới: Số qua lượt / chưa vào phòng
        for i in range(2):
            card = self.missed_cards[i]
            if i < len(missed_list):
                m_item = missed_list[i]
                m_stt = str(m_item.get("stt", "---"))
                card["badge"].setText(m_stt)
                card["badge"].setStyleSheet(
                    "background-color: #d97706; color: white; font-size: 28px; font-weight: bold; border-radius: 8px; border: none;"
                )
                card["desc"].setText("Chưa vào phòng - Báo NVYT")
                card["frame"].setStyleSheet("background: #fffbeb; border-radius: 10px; border: 2px solid #f59e0b;")
            else:
                card["badge"].setText("")
                card["badge"].setStyleSheet("background: transparent; border: none;")
                card["desc"].setText("Không có số qua lượt" if i == 0 and not missed_list else "")
                card["desc"].setStyleSheet("font-size: 20px; color: #94a3b8; border: none; background: transparent;")
                card["frame"].setStyleSheet("background: transparent; border: 1px dashed #e2e8f0; border-radius: 10px;")

    def update_room(self, name):
        title = (name or "").strip().upper()
        self.room_label.setText(title)
        if len(title) <= 16:
            fsize = 72
        elif len(title) <= 23:
            fsize = 56
        else:
            fsize = 46
        self.room_label.setStyleSheet(
            f"font-size: {fsize}px; color: #0B5FA5; font-weight: 900; font-family: 'Arial Black', 'Arial'; border: none; background: transparent;"
        )

    def update_staff(self, bs, ktv):
        self.staff.setText(f"BS: {bs.upper()} | KTV: {ktv.upper()}")

    def update_footer_text(self, text):
        self.marquee_label.setText(text + "        ")

    # --- CHẾ ĐỘ PHÒNG TRỰC ---
    def enter_duty_mode(self, doctor_name, phone):
        self.duty_doctor_name.setText(doctor_name.upper())
        self.duty_phone.setText(phone)
        self.stacked.setCurrentIndex(1)

    def exit_duty_mode(self):
        self.stacked.setCurrentIndex(0)

    def is_in_duty_mode(self):
        return self.stacked.currentIndex() == 1

    def move_to_secondary_screen(self):
        screens = QGuiApplication.screens()
        if len(screens) > 1:
            secondary_screen = screens[1]
            screen_geometry = secondary_screen.geometry()
            self.move(screen_geometry.left(), screen_geometry.top())
            self.resize(screen_geometry.width(), screen_geometry.height())
            self.showFullScreen()
            print("TV Display moved to secondary screen (Fullscreen).")
        else:
            self.showMaximized()
            print("Secondary screen not found. Showing Maximized on primary.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TVDisplay("PHÒNG SIÊU ÂM 1")
    window.show()
    sys.exit(app.exec())
