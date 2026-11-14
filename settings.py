from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QCheckBox, QSlider, QLabel, QPushButton
)
from PySide6.QtCore import Qt, Signal
from config_manager import ConfigManager
from speaker_hub import (
    SPEAKER_MODE_HUB,
    SPEAKER_MODE_CLIENT,
    SPEAKER_MODE_LOCAL,
    ROOM_DEFINITIONS,
    ALL_ROOM_IDS,
    get_room_display_name,
    get_default_speaker_mode,
)


# Tập các tên phòng mặc định để tự động điền khi người dùng đổi phòng trong combobox
_DEFAULT_ROOM_NAMES = {info["display_name"].upper() for info in ROOM_DEFINITIONS.values()}


class SettingsWindow(QWidget):
    # Signal báo cho Dashboard biết dữ liệu cấu hình đã thay đổi
    config_saved = Signal()
    test_tts_requested = Signal()

    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.setWindowTitle("Cấu hình Hệ thống Gọi số & Trạm Loa Trung Tâm - BVĐK Kỳ Anh")
        self.setMinimumSize(580, 520)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)

        form_layout = QFormLayout()
        form_layout.setSpacing(14)
        form_layout.setLabelAlignment(Qt.AlignRight)

        # Khởi tạo các ô nhập liệu
        self.room = QLineEdit()
        self.room.setPlaceholderText("Ví dụ: PHÒNG SIÊU ÂM 1, PHÒNG NỘI SOI TAI MŨI HỌNG...")

        self.room_number = QComboBox()
        for r_id in ALL_ROOM_IDS:
            r_info = ROOM_DEFINITIONS[r_id]
            self.room_number.addItem(r_info["combo_label"], r_id)
        self.room_number.currentIndexChanged.connect(self._on_room_index_changed)

        self.doctor = QLineEdit()
        self.doctor.setPlaceholderText("Tên Bác sĩ phụ trách")

        self.ktv = QLineEdit()
        self.ktv.setPlaceholderText("Tên Kỹ thuật viên / Điều dưỡng")

        self.footer = QLineEdit()
        self.footer.setPlaceholderText("Dòng chữ chạy ở đáy màn hình TV")

        # Chế độ Loa của máy trạm (Mặc định Phòng Siêu Âm 2 là Trạm Phát Loa Trung Tâm cho toàn bộ 11 phòng)
        self.cbo_speaker_mode = QComboBox()
        self.cbo_speaker_mode.addItem(
            "📢 Trạm Phát Loa Trung Tâm tại P.Siêu Âm 2 (Đọc cho tất cả 11 phòng)", SPEAKER_MODE_HUB
        )
        self.cbo_speaker_mode.addItem(
            "📡 Gửi tín hiệu phát loa về Phòng Siêu Âm 2 (Tắt loa tại máy này)", SPEAKER_MODE_CLIENT
        )
        self.cbo_speaker_mode.addItem(
            "🔊 Chỉ phát loa riêng của phòng này (Độc lập)", SPEAKER_MODE_LOCAL
        )
        self.cbo_speaker_mode.setStyleSheet("padding: 6px; font-size: 13px; font-weight: bold; color: #0B5FA5;")

        # Cấu hình Bật/Tắt & Âm lượng loa
        self.chk_tts_enabled = QCheckBox("Cho phép kích hoạt gọi loa khi bấm số / gọi lại")
        self.chk_tts_enabled.setStyleSheet("font-size: 14px; font-weight: bold; color: #0B5FA5;")

        vol_row = QHBoxLayout()
        self.slider_volume = QSlider(Qt.Horizontal)
        self.slider_volume.setRange(10, 100)
        self.slider_volume.setValue(100)
        self.lbl_volume_val = QLabel("100%")
        self.lbl_volume_val.setFixedWidth(45)
        self.lbl_volume_val.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.slider_volume.valueChanged.connect(lambda v: self.lbl_volume_val.setText(f"{v}%"))

        self.btn_test_tts = QPushButton("🔊 Nghe thử loa")
        self.btn_test_tts.setStyleSheet(
            "background-color: #0284c7; color: white; font-weight: bold; padding: 6px 12px; border-radius: 5px;"
        )
        self.btn_test_tts.clicked.connect(self.test_tts_requested.emit)

        vol_row.addWidget(self.slider_volume, 1)
        vol_row.addWidget(self.lbl_volume_val)
        vol_row.addWidget(self.btn_test_tts)

        # Style cho LineEdit & ComboBox
        input_style = "padding: 8px; font-size: 14px;"
        self.room.setStyleSheet(input_style)
        self.room_number.setStyleSheet("padding: 6px; font-size: 14px;")
        self.doctor.setStyleSheet(input_style)
        self.ktv.setStyleSheet(input_style)
        self.footer.setStyleSheet(input_style)

        label_style = "font-size: 14px; font-weight: bold;"
        l_rnum = QLabel("Chọn Phòng Khám:")
        l_rnum.setStyleSheet(label_style)
        l_room = QLabel("Tên Hiển Thị TV:")
        l_room.setStyleSheet(label_style)
        l_dr = QLabel("Bác sĩ:")
        l_dr.setStyleSheet(label_style)
        l_ktv = QLabel("KTV / ĐD:")
        l_ktv.setStyleSheet(label_style)
        l_foot = QLabel("Chữ chạy Footer:")
        l_foot.setStyleSheet(label_style)
        l_mode = QLabel("Vai trò Loa:")
        l_mode.setStyleSheet(label_style)
        l_tts = QLabel("Trạng thái Loa:")
        l_tts.setStyleSheet(label_style)
        l_vol = QLabel("Âm lượng loa:")
        l_vol.setStyleSheet(label_style)

        form_layout.addRow(l_rnum, self.room_number)
        form_layout.addRow(l_room, self.room)
        form_layout.addRow(l_dr, self.doctor)
        form_layout.addRow(l_ktv, self.ktv)
        form_layout.addRow(l_foot, self.footer)
        form_layout.addRow(l_mode, self.cbo_speaker_mode)
        form_layout.addRow(l_tts, self.chk_tts_enabled)
        form_layout.addRow(l_vol, vol_row)

        layout.addLayout(form_layout)
        layout.addStretch()

        # Nút Lưu
        self.btn_save = QPushButton("LƯU CẤU HÌNH")
        self.btn_save.setStyleSheet(
            "background-color: #28a745; color: white; font-size: 16px; font-weight: bold; padding: 12px; border-radius: 5px;"
        )
        self.btn_save.clicked.connect(self.save)
        layout.addWidget(self.btn_save)

        self.setLayout(layout)
        self.load_config_to_ui()

    def get_selected_room_id(self) -> str:
        """Lấy mã định danh chuẩn của phòng đang chọn (VD: '1'..'5', 'tmh', 'dtd', 'dnd', 'lhn', 'cnhh')."""
        data = self.room_number.currentData()
        if data:
            return str(data).strip().lower()
        return "1"

    def _on_room_index_changed(self, _index: int):
        """Tự động cập nhật tên hiển thị phòng và gợi ý vai trò Loa mặc định (Phòng 2 = Trạm Loa Trung Tâm)."""
        room_id = self.get_selected_room_id()
        cur_name = self.room.text().strip().upper()
        if not cur_name or cur_name in _DEFAULT_ROOM_NAMES or cur_name.startswith("PHÒNG "):
            self.room.setText(get_room_display_name(room_id))

        default_mode = get_default_speaker_mode(room_id)
        m_idx = self.cbo_speaker_mode.findData(default_mode)
        if m_idx >= 0:
            self.cbo_speaker_mode.setCurrentIndex(m_idx)

    def load_config_to_ui(self):
        """Đọc dữ liệu từ ConfigManager và điền vào các ô nhập liệu."""
        room_num = self.config.get("room_number", "1").strip().lower()
        self.room_number.blockSignals(True)
        idx = self.room_number.findData(room_num)
        if idx < 0:
            idx = 0
        self.room_number.setCurrentIndex(idx)
        self.room_number.blockSignals(False)

        default_title = get_room_display_name(room_num)
        self.room.setText(self.config.get("room", default_title) or default_title)
        self.doctor.setText(self.config.get("doctor", "---"))
        self.ktv.setText(self.config.get("ktv", "---"))
        self.footer.setText(self.config.get("footer", "Xin vui lòng chuẩn bị giấy tờ và lắng nghe loa gọi số trước khi vào phòng khám"))

        saved_mode = self.config.get("speaker_mode", "").strip()
        if not saved_mode:
            saved_mode = get_default_speaker_mode(room_num)
        m_idx = self.cbo_speaker_mode.findData(saved_mode)
        if m_idx >= 0:
            self.cbo_speaker_mode.setCurrentIndex(m_idx)

        tts_enabled = str(self.config.get("tts_enabled", "1")) != "0"
        self.chk_tts_enabled.setChecked(tts_enabled)

        try:
            vol = int(self.config.get("tts_volume", "100"))
        except ValueError:
            vol = 100
        self.slider_volume.setValue(max(10, min(100, vol)))

    def save(self):
        """Lưu dữ liệu từ UI vào ConfigManager và phát tín hiệu."""
        room_id = self.get_selected_room_id()
        room_title = self.room.text().strip() or get_room_display_name(room_id)
        self.config.set("room", room_title)
        self.config.set("room_number", room_id)
        self.config.set("doctor", self.doctor.text().strip())
        self.config.set("ktv", self.ktv.text().strip())
        self.config.set("footer", self.footer.text().strip())
        self.config.set("speaker_mode", self.cbo_speaker_mode.currentData())
        self.config.set("tts_enabled", "1" if self.chk_tts_enabled.isChecked() else "0")
        self.config.set("tts_volume", str(self.slider_volume.value()))

        self.config_saved.emit()
        self.close()
        self.hide()
