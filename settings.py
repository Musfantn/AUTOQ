from PySide6.QtWidgets import *
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal # Import Signal
from config_manager import ConfigManager

class SettingsWindow(QWidget):
    # Tạo một signal tùy chỉnh để báo cho Dashboard biết dữ liệu đã thay đổi
    config_saved = Signal()

    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.setWindowTitle("Cấu hình Hệ thống - BVĐK Kỳ Anh")
        self.setFixedSize(450, 380) # Giảm chiều cao do loại bỏ IP Kiosk

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignRight)

        # Khởi tạo các LineEdit & ComboBox mới
        self.room = QLineEdit()
        self.room.setPlaceholderText("Ví dụ: PHÒNG SIÊU ÂM 1")
        
        self.room_number = QComboBox()
        self.room_number.addItems(["1", "2", "3", "4", "5"])

        self.doctor = QLineEdit()
        self.doctor.setPlaceholderText("Tên Bác sĩ trực")
        
        self.ktv = QLineEdit()
        self.ktv.setPlaceholderText("Tên Kỹ thuật viên")
        
        self.footer = QLineEdit()
        self.footer.setPlaceholderText("Dòng chữ chạy ở đáy màn hình")

        # Style cho LineEdit & ComboBox
        input_style = "padding: 8px; font-size: 14px;"
        self.room.setStyleSheet(input_style)
        self.room_number.setStyleSheet("padding: 6px; font-size: 14px;")
        self.doctor.setStyleSheet(input_style)
        self.ktv.setStyleSheet(input_style)
        self.footer.setStyleSheet(input_style)

        # Thêm vào Form
        label_style = "font-size: 14px; font-weight: bold;"
        l_room = QLabel("Tên Phòng:")
        l_room.setStyleSheet(label_style)
        l_rnum = QLabel("Số phòng (1-5):")
        l_rnum.setStyleSheet(label_style)
        l_dr = QLabel("Bác sĩ:")
        l_dr.setStyleSheet(label_style)
        l_ktv = QLabel("KTV:")
        l_ktv.setStyleSheet(label_style)
        l_foot = QLabel("Chữ chạy Footer:")
        l_foot.setStyleSheet(label_style)

        form_layout.addRow(l_room, self.room)
        form_layout.addRow(l_rnum, self.room_number)
        form_layout.addRow(l_dr, self.doctor)
        form_layout.addRow(l_ktv, self.ktv)
        form_layout.addRow(l_foot, self.footer)

        layout.addLayout(form_layout)
        layout.addStretch()

        # Nút Lưu
        self.btn_save = QPushButton("LƯU CẤU HÌNH")
        self.btn_save.setStyleSheet("background-color: #28a745; color: white; font-size: 16px; font-weight: bold; padding: 12px; border-radius: 5px;")
        self.btn_save.clicked.connect(self.save)
        layout.addWidget(self.btn_save)

        self.setLayout(layout)
        
        # Load dữ liệu lần đầu
        self.load_config_to_ui()

    def load_config_to_ui(self):
        """Đọc dữ liệu từ ConfigManager và điền vào các ô nhập liệu"""
        self.room.setText(self.config.get("room", "PHÒNG SIÊU ÂM 1"))
        
        room_num = self.config.get("room_number", "1")
        idx = self.room_number.findText(room_num)
        if idx >= 0:
            self.room_number.setCurrentIndex(idx)
            
        self.doctor.setText(self.config.get("doctor", "BS: ---"))
        self.ktv.setText(self.config.get("ktv", "KTV: ---"))
        self.footer.setText(self.config.get("footer", "Xin vui lòng chuẩn bị giấy tờ trước khi vào khám"))

    def save(self):
        """Lưu dữ liệu từ UI vào ConfigManager và phát tín hiệu"""
        self.config.set("room", self.room.text().strip())
        self.config.set("room_number", self.room_number.currentText())
        self.config.set("doctor", self.doctor.text().strip())
        self.config.set("ktv", self.ktv.text().strip())
        self.config.set("footer", self.footer.text().strip())

        # Phát signal để Dashboard biết và cập nhật TV
        self.config_saved.emit()
        self.close()

        self.hide() # Ẩn cửa sổ sau khi lưu