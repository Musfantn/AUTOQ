from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
import os
import sys
from firestore_client import extract_birth_year

# Link logo dự phòng online (bạn có thể thay đổi link này sau)
ONLINE_LOGO_URL = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR-WQz3PjdjFwRym5KeITVAmlgNgpiA0ae5rg&s"

def resource_path(path):
    """Hỗ trợ lấy đường dẫn file khi đóng gói ứng dụng (PyInstaller)"""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, path)
    return os.path.join(os.path.abspath("."), path)

class TVDisplay(QWidget):
    def __init__(self, room_name="---"):
        super().__init__()
        self.setWindowTitle("Hệ thống Gọi số - BVĐK Thị xã Kỳ Anh")
        self.setStyleSheet("background: white;")
        
        # --- CẤU HÌNH GIAO DIỆN CHÍNH ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 1. HEADER (Chứa Logo và Tên BV) - DÙNG CHUNG ---
        header = QFrame()
        header.setMinimumHeight(150) # Tối thiểu chiều cao header
        header.setStyleSheet("background: #0B5FA5; color: white; border: none;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(30, 10, 30, 10)
        header_layout.setSpacing(20)

        # Container cho Logo để đảm bảo căn giữa dọc
        logo_container = QWidget()
        logo_container_layout = QVBoxLayout(logo_container)
        logo_container_layout.setContentsMargins(0, 0, 0, 0)
        logo_container_layout.setAlignment(Qt.AlignCenter)

        self.logo = QLabel()
        self.logo.setMinimumSize(120, 120)
        self.logo.setAlignment(Qt.AlignCenter)
        self.load_logo() # Gọi hàm load logo phức hợp
        
        logo_container_layout.addWidget(self.logo)
        header_layout.addWidget(logo_container)

        # Cụm chữ Header (Tên BV và Khoa)
        title_container = QVBoxLayout()
        title_container.setSpacing(5)
        title_container.setAlignment(Qt.AlignVCenter)

        hospital = QLabel("BỆNH VIỆN ĐA KHOA THỊ XÃ KỲ ANH")
        hospital.setStyleSheet("font-size: 38px; font-weight: bold; font-family: 'Arial';")
        
        dept = QLabel("KHOA CHẨN ĐOÁN HÌNH ẢNH")
        dept.setStyleSheet("font-size: 34px; font-weight: bold; color: #E0E0E0; font-family: 'Arial';")
        
        title_container.addWidget(hospital)
        title_container.addWidget(dept)
        
        header_layout.addLayout(title_container)
        header_layout.addStretch() # Đẩy khoảng trắng về bên phải để header cân đối

        # --- 2. STACKED WIDGET (Chứa 2 chế độ hiển thị) ---
        self.stacked = QStackedWidget()

        # ===== PAGE 0: Màn hình gọi số bình thường =====
        normal_page = QWidget()
        normal_page.setStyleSheet("background: #f1f5f9;")
        normal_layout = QVBoxLayout(normal_page)
        normal_layout.setContentsMargins(0, 0, 0, 0)
        normal_layout.setSpacing(0)

        # Body chia 2 cột bằng QHBoxLayout
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(25, 25, 25, 25)
        body_layout.setSpacing(25)

        # --- CỘT TRÁI (Bệnh nhân đang gọi - Chiếm 55%) ---
        left_frame = QFrame()
        left_frame.setStyleSheet("background: white; border-radius: 15px; border: 1px solid #cbd5e1;")
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(30, 35, 30, 35)
        left_layout.setSpacing(15)
        left_layout.setAlignment(Qt.AlignTop)

        self.room_label = QLabel(room_name.upper())
        self.room_label.setAlignment(Qt.AlignCenter)
        self.room_label.setStyleSheet("font-size: 65px; color: #0B5FA5; font-weight: bold; font-family: 'Arial'; border: none; background: transparent;")

        msg = QLabel("XIN MỜI BỆNH NHÂN SỐ")
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("font-size: 40px; color: #334155; font-weight: 500; border: none; margin-top: 10px; background: transparent;")

        self.number = QLabel("000")
        self.number.setAlignment(Qt.AlignCenter)
        self.number.setStyleSheet("font-size: 260px; color: #dc2626; font-weight: bold; font-family: 'Arial'; line-height: 1; border: none; background: transparent;")

        # Họ tên và tuổi bệnh nhân
        self.lbl_patient_name = QLabel("--- CHỜ GỌI SỐ ---")
        self.lbl_patient_name.setAlignment(Qt.AlignCenter)
        self.lbl_patient_name.setStyleSheet("font-size: 50px; color: #0f172a; font-weight: bold; border: none; margin-top: 15px; background: transparent;")
        
        self.lbl_patient_info = QLabel("")
        self.lbl_patient_info.setAlignment(Qt.AlignCenter)
        self.lbl_patient_info.setStyleSheet("font-size: 32px; color: #475569; font-weight: normal; border: none; background: transparent;")

        self.lbl_services = QLabel("")
        self.lbl_services.setAlignment(Qt.AlignCenter)
        self.lbl_services.setStyleSheet("font-size: 36px; color: #0284c7; font-weight: bold; border: none; margin-top: 15px; background: transparent;")
        self.lbl_services.setWordWrap(True)

        left_layout.addWidget(self.room_label)
        left_layout.addWidget(msg)
        left_layout.addWidget(self.number)
        left_layout.addWidget(self.lbl_patient_name)
        left_layout.addWidget(self.lbl_patient_info)
        left_layout.addWidget(self.lbl_services)
        left_layout.addStretch()

        # --- CỘT PHẢI (Danh sách chờ tiếp theo - Chiếm 45%) ---
        right_frame = QFrame()
        right_frame.setStyleSheet("background: white; border-radius: 15px; border: 1px solid #cbd5e1;")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(12)
        right_layout.setAlignment(Qt.AlignTop)

        right_title = QLabel("DANH SÁCH CHỜ TIẾP THEO")
        right_title.setAlignment(Qt.AlignCenter)
        right_title.setStyleSheet("font-size: 34px; color: #0B5FA5; font-weight: bold; border: none; padding-bottom: 5px; background: transparent;")
        right_layout.addWidget(right_title)

        # Tạo 5 thẻ chờ
        self.waiting_cards = []
        for i in range(5):
            card_frame = QFrame()
            card_frame.setMinimumHeight(82)
            card_frame.setStyleSheet("background: transparent; border: none;")
            
            card_layout = QHBoxLayout(card_frame)
            card_layout.setContentsMargins(15, 8, 15, 8)
            card_layout.setSpacing(15)

            # Badge hiển thị STT
            stt_badge = QLabel("")
            stt_badge.setMinimumSize(70, 48)
            stt_badge.setAlignment(Qt.AlignCenter)
            stt_badge.setStyleSheet("""
                background-color: transparent;
                color: white;
                font-size: 26px;
                font-weight: bold;
                border-radius: 8px;
                border: none;
            """)

            # Khu vực thông tin bệnh nhân
            info_container = QWidget()
            info_container.setStyleSheet("background: transparent; border: none;")
            info_vlayout = QVBoxLayout(info_container)
            info_vlayout.setContentsMargins(0, 0, 0, 0)
            info_vlayout.setSpacing(2)
            info_vlayout.setAlignment(Qt.AlignVCenter)

            name_lbl = QLabel("")
            name_lbl.setStyleSheet("font-size: 23px; color: #1e293b; font-weight: bold; background: transparent; border: none;")
            
            info_lbl = QLabel("")
            info_lbl.setStyleSheet("font-size: 16px; color: #64748b; background: transparent; border: none;")

            info_vlayout.addWidget(name_lbl)
            info_vlayout.addWidget(info_lbl)

            card_layout.addWidget(stt_badge)
            card_layout.addWidget(info_container, 1)

            right_layout.addWidget(card_frame)
            
            self.waiting_cards.append({
                "frame": card_frame,
                "stt_lbl": stt_badge,
                "name_lbl": name_lbl,
                "info_lbl": info_lbl
            })

        body_layout.addWidget(left_frame, 55)
        body_layout.addWidget(right_frame, 45)

        # Footer bình thường
        normal_footer = QWidget()
        normal_footer.setMinimumHeight(140)
        normal_footer.setStyleSheet("background: #0B5FA5; border-top: 3px solid #084B83;")
        
        nf_layout = QVBoxLayout(normal_footer)
        nf_layout.setContentsMargins(0, 5, 0, 5)
        nf_layout.setSpacing(0)

        self.staff = QLabel("BS: --- | KTV: ---")
        self.staff.setAlignment(Qt.AlignCenter)
        self.staff.setStyleSheet("font-size: 32px; font-weight: bold; color: #FFD700; font-family: 'Arial';")

        self.marquee_base_text = " Xin vui lòng chuẩn bị giấy tờ trước khi vào khám. "
        self.marquee_label = QLabel(self.marquee_base_text)
        self.marquee_label.setAlignment(Qt.AlignCenter)
        self.marquee_label.setStyleSheet("font-size: 28px; color: white; font-weight: normal; font-family: 'Arial';")

        nf_layout.addWidget(self.staff)
        nf_layout.addWidget(self.marquee_label)

        normal_layout.addWidget(body_widget, 1)
        normal_layout.addWidget(normal_footer)

        # ===== PAGE 1: Màn hình trực =====
        duty_page = QWidget()
        duty_page.setStyleSheet("background: #f0f4f8;")
        duty_layout = QVBoxLayout(duty_page)
        duty_layout.setContentsMargins(0, 0, 0, 0)
        duty_layout.setSpacing(0)

        # Body trực
        duty_body = QWidget()
        duty_body.setStyleSheet("background: #f0f4f8;")
        duty_body_layout = QVBoxLayout(duty_body)
        duty_body_layout.setContentsMargins(60, 60, 60, 40)
        duty_body_layout.setSpacing(20)
        duty_body_layout.setAlignment(Qt.AlignCenter)

        # Tên phòng trực
        duty_room_title = QLabel("PHÒNG SIÊU ÂM CẤP CỨU")
        duty_room_title.setAlignment(Qt.AlignCenter)
        duty_room_title.setStyleSheet("""
            font-size: 90px;
            font-weight: bold;
            color: #c0392b;
            font-family: 'Arial';
            padding: 10px;
        """)

        duty_room_en = QLabel("Emergency Ultrasound Room")
        duty_room_en.setAlignment(Qt.AlignCenter)
        duty_room_en.setStyleSheet("""
            font-size: 48px;
            font-weight: normal;
            color: #7f8c8d;
            font-family: 'Arial';
            font-style: italic;
            margin-bottom: 40px;
        """)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background: #bdc3c7; min-height: 3px; margin: 10px 100px;")

        # Icon + label Bác sĩ trực
        duty_doctor_header = QLabel("👨‍⚕️  BÁC SĨ TRỰC")
        duty_doctor_header.setAlignment(Qt.AlignCenter)
        duty_doctor_header.setStyleSheet("""
            font-size: 50px;
            font-weight: bold;
            color: #0B5FA5;
            font-family: 'Arial';
            margin-top: 30px;
        """)

        self.duty_doctor_name = QLabel("---")
        self.duty_doctor_name.setAlignment(Qt.AlignCenter)
        self.duty_doctor_name.setStyleSheet("""
            font-size: 120px;
            font-weight: bold;
            color: #2c3e50;
            font-family: 'Arial';
            padding: 10px;
        """)

        # SĐT
        duty_phone_header = QLabel("📞  SỐ ĐIỆN THOẠI")
        duty_phone_header.setAlignment(Qt.AlignCenter)
        duty_phone_header.setStyleSheet("""
            font-size: 50px;
            font-weight: bold;
            color: #0B5FA5;
            font-family: 'Arial';
            margin-top: 20px;
        """)

        self.duty_phone = QLabel("---")
        self.duty_phone.setAlignment(Qt.AlignCenter)
        self.duty_phone.setStyleSheet("""
            font-size: 120px;
            font-weight: bold;
            color: #e74c3c;
            font-family: 'Arial';
            padding: 10px;
        """)

        duty_body_layout.addWidget(duty_room_title)
        duty_body_layout.addWidget(duty_room_en)
        duty_body_layout.addWidget(separator)
        duty_body_layout.addWidget(duty_doctor_header)
        duty_body_layout.addWidget(self.duty_doctor_name)
        duty_body_layout.addWidget(duty_phone_header)
        duty_body_layout.addWidget(self.duty_phone)
        duty_body_layout.addStretch()

        # Footer trực (chữ chạy)
        duty_footer = QWidget()
        duty_footer.setMinimumHeight(70)
        duty_footer.setStyleSheet("background: #0B5FA5; border-top: 3px solid #084B83;")

        df_layout = QVBoxLayout(duty_footer)
        df_layout.setContentsMargins(0, 5, 0, 5)
        df_layout.setAlignment(Qt.AlignCenter)

        self.duty_marquee_base_text = "     ★  Bệnh nhân siêu âm: Vui lòng bấm chuông tại phòng trực hoặc liên hệ số điện thoại bác sĩ trực  ★     "
        self.duty_marquee_label = QLabel(self.duty_marquee_base_text)
        self.duty_marquee_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.duty_marquee_label.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
            color: #FFD700;
            font-family: 'Arial';
        """)

        df_layout.addWidget(self.duty_marquee_label)

        duty_layout.addWidget(duty_body, 1)
        duty_layout.addWidget(duty_footer)

        # ===== Thêm 2 page vào stacked widget =====
        self.stacked.addWidget(normal_page)   # index 0
        self.stacked.addWidget(duty_page)     # index 1

        # Tổng hợp các phần vào layout chính
        main_layout.addWidget(header)
        main_layout.addWidget(self.stacked, 1) # Stacked chiếm diện tích còn lại

        # --- TỰ ĐỘNG SANG MÀN HÌNH PHỤ (TV) ---
        #self.move_to_secondary_screen()
        QTimer.singleShot(100, self.move_to_secondary_screen)

        # --- KHỞI TẠO TIMER CHO CHỮ CHẠY ---
        self.marquee_timer = QTimer(self)
        self.marquee_timer.timeout.connect(self.scroll_text)
        self.marquee_timer.start(150) # Tốc độ chạy (ms)

    def load_logo(self):
        """Hàm load logo: Ưu tiên file cục bộ, dự phòng online"""
        local_path = resource_path("assets/logo.png")
        if os.path.exists(local_path):
            self.set_logo_pixmap(QPixmap(local_path))
            print("Loaded local logo.")
        else:
            print(f"Local logo not found at {local_path}. Trying online...")
            self.logo.setText("Loading...")
            self.download_online_logo()

    def download_online_logo(self):
        """Tải logo từ internet"""
        self.manager = QNetworkAccessManager()
        self.manager.finished.connect(self.on_logo_downloaded)
        self.manager.get(QNetworkRequest(QUrl(ONLINE_LOGO_URL)))

    def on_logo_downloaded(self, reply):
        """Xử lý dữ liệu ảnh tải về"""
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                self.set_logo_pixmap(pixmap)
                print("Loaded online logo successfully.")
                return
        
        # Nếu cả cục bộ và online đều lỗi
        print("Failed to load logo (local & online).")
        self.logo.setText("BV KY ANH")
        self.logo.setStyleSheet("font-size: 20px; color: white; font-weight: bold; border: 2px solid white; border-radius: 60px;")

    def set_logo_pixmap(self, pixmap):
        """Scale ảnh và đặt vào QLabel"""
        self.logo.setPixmap(pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def scroll_text(self):
        """Logic dịch chuyển ký tự để tạo hiệu ứng chạy chữ"""
        # Scroll marquee bình thường
        current_text = self.marquee_label.text()
        if current_text:
            new_text = current_text[1:] + current_text[0]
            self.marquee_label.setText(new_text)

        # Scroll marquee trực
        duty_text = self.duty_marquee_label.text()
        if duty_text:
            new_duty = duty_text[1:] + duty_text[0]
            self.duty_marquee_label.setText(new_duty)

    # --- CÁC HÀM CẬP NHẬT DỮ LIỆU TỪ EXTERNAL ---
    def update_number(self, n):
        # Nếu là cấp cứu
        if n == "CẤP CỨU" or n == "CC":
            self.number.setStyleSheet("font-size: 180px; color: #dc2626; font-weight: bold; font-family: 'Arial'; border: none; background: transparent;")
            self.number.setText("CC")
            self.lbl_patient_name.setText("CẤP CỨU")
            self.lbl_patient_info.setText("")
            self.lbl_services.setText("SIÊU ÂM CẤP CỨU")
        else:
            self.number.setStyleSheet("font-size: 260px; color: #dc2626; font-weight: bold; font-family: 'Arial'; border: none; background: transparent;")
            self.number.setText(str(n))
            self.lbl_patient_name.setText("---")
            self.lbl_patient_info.setText("")
            self.lbl_services.setText("")

    def update_queue_data(self, current_calling, waiting_list):
        """Cập nhật dữ liệu hàng đợi chi tiết và hiển thị lên TV"""
        # 1. Cập nhật bệnh nhân đang gọi (Cột trái)
        if current_calling:
            stt = current_calling.get("stt", "000")
            ten_bn = current_calling.get("ten_bn", "")
            tuoi = current_calling.get("tuoi", "")
            ma_bn = current_calling.get("ma_bn", "")
            dich_vu = current_calling.get("dich_vu", "")
            ngay_sinh = current_calling.get("ngay_sinh", "")
            
            if stt == "CC":
                self.number.setStyleSheet("font-size: 180px; color: #dc2626; font-weight: bold; font-family: 'Arial'; border: none; background: transparent;")
                self.number.setText("CC")
                self.lbl_patient_name.setText("CẤP CỨU")
                self.lbl_patient_info.setText("")
                self.lbl_services.setText("SIÊU ÂM CẤP CỨU")
            else:
                self.number.setStyleSheet("font-size: 260px; color: #dc2626; font-weight: bold; font-family: 'Arial'; border: none; background: transparent;")
                self.number.setText(stt)
                self.lbl_patient_name.setText(ten_bn.upper())
                
                # Trích xuất năm sinh và hiển thị
                nam_sinh = extract_birth_year(ngay_sinh)
                self.lbl_patient_info.setText(self._format_age_info(tuoi, nam_sinh))
                
                # Hiển thị các dịch vụ chỉ định (mỗi dịch vụ 1 dòng)
                if dich_vu:
                    services_list = [s.strip() for s in dich_vu.split("\n") if s.strip()]
                    self.lbl_services.setText("\n".join(services_list))
                else:
                    self.lbl_services.setText("")
        else:
            self.number.setStyleSheet("font-size: 260px; color: #94a3b8; font-weight: bold; font-family: 'Arial'; border: none; background: transparent;")
            self.number.setText("000")
            self.lbl_patient_name.setText("--- CHỜ GỌI SỐ ---")
            self.lbl_patient_info.setText("")
            self.lbl_services.setText("")

        # 2. Cập nhật danh sách chờ (Cột phải)
        for i in range(5):
            card = self.waiting_cards[i]
            if i < len(waiting_list):
                pat = waiting_list[i]
                is_priority = pat.get("is_priority", False)
                pat_stt = pat.get("stt", "---")
                pat_name = pat.get("ten_bn", "").upper()
                if is_priority:
                    pat_name = f"🚨 {pat_name} (Ưu tiên)"

                card["stt_lbl"].setText(pat_stt)
                if is_priority:
                    card["stt_lbl"].setStyleSheet("""
                        background-color: #dc2626;
                        color: white;
                        font-size: 26px;
                        font-weight: bold;
                        border-radius: 8px;
                        border: none;
                    """)
                    card["name_lbl"].setText(pat_name)
                    card["name_lbl"].setStyleSheet(
                        "font-size: 23px; color: #ef4444; font-weight: bold; background: transparent; border: none;"
                    )
                    card["frame"].setStyleSheet(
                        "background: #450a0a; border-radius: 10px; border: 2px solid #dc2626;"
                    )
                else:
                    card["stt_lbl"].setStyleSheet("""
                        background-color: #0B5FA5;
                        color: white;
                        font-size: 26px;
                        font-weight: bold;
                        border-radius: 8px;
                        border: none;
                    """)
                    card["name_lbl"].setText(pat_name)
                    card["name_lbl"].setStyleSheet(
                        "font-size: 23px; color: #1e293b; font-weight: bold; background: transparent; border: none;"
                    )
                    card["frame"].setStyleSheet(
                        "background: #f1f5f9; border-radius: 10px; border: 1px solid #cbd5e1;"
                    )

                tuoi = pat.get("tuoi", "")
                nam_sinh = extract_birth_year(pat.get("ngay_sinh", ""))
                age_ns_str = self._format_age_info(tuoi, nam_sinh, short=True)

                dich_vu = pat.get("dich_vu", "").replace("\n", ", ").strip()
                if len(dich_vu) > 40:
                    dich_vu = dich_vu[:37] + "..."
                card["info_lbl"].setText(f"{age_ns_str}   |   {dich_vu}" if age_ns_str else dich_vu)
            else:
                card["stt_lbl"].setText("")
                card["stt_lbl"].setStyleSheet("background-color: transparent; border: none;")
                card["name_lbl"].setText("")
                card["info_lbl"].setText("")
                card["frame"].setStyleSheet("background: transparent; border: none;")

    # ─── HELPER METHODS ──────────────────────────────────────────────────────

    @staticmethod
    def _format_age_info(tuoi, nam_sinh, short: bool = False) -> str:
        """Tạo chuỗi hiển thị tuổi + năm sinh."""
        if tuoi and nam_sinh:
            return f"Tuổi: {tuoi} ({nam_sinh})"
        if tuoi:
            return f"Tuổi: {tuoi}"
        if nam_sinh:
            return f"NS: {nam_sinh}" if short else f"Năm sinh: {nam_sinh}"
        return ""

    def update_room(self, name):
        self.room_label.setText(name.upper())

    def update_staff(self, bs, ktv):
        self.staff.setText(f"BS: {bs.upper()} | KTV: {ktv.upper()}")

    def update_footer_text(self, text):
        # Reset lại text nền để timer chạy
        self.marquee_label.setText(text + "        ")

    # --- CHẾ ĐỘ PHÒNG TRỰC ---
    def enter_duty_mode(self, doctor_name, phone):
        """Chuyển sang màn hình trực, hiển thị tên BS và SĐT."""
        self.duty_doctor_name.setText(doctor_name.upper())
        self.duty_phone.setText(phone)
        self.stacked.setCurrentIndex(1)

    def exit_duty_mode(self):
        """Quay về màn hình gọi số bình thường."""
        self.stacked.setCurrentIndex(0)

    def is_in_duty_mode(self):
        """Kiểm tra có đang ở chế độ trực không."""
        return self.stacked.currentIndex() == 1

    def move_to_secondary_screen(self):
        """Hàm tự động phát hiện và nhảy sang màn hình thứ 2 (TV)"""
        screens = QGuiApplication.screens()
        if len(screens) > 1:
            # Lấy thông tin màn hình thứ 2 (thường là TV cắm ngoài)
            secondary_screen = screens[1] # Lưu ý: Nếu có nhiều hơn 2   màn hình, có thể cần logic phức tạp hơn để xác định màn hình TV
            screen_geometry = secondary_screen.geometry()
            
            # Di chuyển cửa sổ đến tọa độ góc trên bên trái của màn hình 2
            self.move(screen_geometry.left(), screen_geometry.top())
            #  Thiết lập kích thước bằng đúng màn hình phụ
            self.resize(screen_geometry.width(), screen_geometry.height())
            # Hiển thị Fullscreen
            self.showFullScreen()
            print("TV Display moved to secondary screen (Fullscreen).")
        else:
            # Nếu chỉ có 1 màn hình, hiển thị phóng to tối đa
            self.showMaximized()
            print("Secondary screen not found. Showing Maximized on primary.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Demo với tên phòng mặc định
    window = TVDisplay("PHÒNG SIÊU ÂM TỔNG QUÁT 01")
    window.show()
    sys.exit(app.exec())