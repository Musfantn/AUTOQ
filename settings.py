import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QCheckBox, QSlider, QLabel, QPushButton, QListView,
    QInputDialog, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QThread
from config_manager import ConfigManager
from oncall_manager import OnCallManager
from version import APP_VERSION
from updater import UpdateDialog
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


class StaffComboBox(QComboBox):
    """QComboBox chuyên dụng cho chọn Bác sĩ / KTV với menu dropdown nền đặc tương phản cao,
    đồng thời hỗ trợ phương thức .text() và .setText() tương thích ngược với QLineEdit.
    """

    def text(self) -> str:
        return self.currentText().strip()

    def setText(self, value: str) -> None:
        val = (value or "").strip() or "---"
        idx = self.findText(val, Qt.MatchFixedString)
        if idx < 0:
            self.addItem(val)
            idx = self.count() - 1
        self.setCurrentIndex(idx)

    def showPopup(self):
        popup = self.view().window()
        popup.setAttribute(Qt.WA_TranslucentBackground, False)
        super().showPopup()


class SettingsPersonnelWorker(QThread):
    """Luồng chạy ngầm lấy danh sách Bác sĩ và KTV/Thư ký từ Firestore (như Nhân sự trực)."""
    done = Signal(list, list)  # (doctor_names, ktv_names)
    error = Signal(str)

    def __init__(self, oncall_mgr: OnCallManager):
        super().__init__()
        self.oncall_mgr = oncall_mgr

    def run(self):
        try:
            from firestore_sync import fetch_doctors_and_ktvs
            data = fetch_doctors_and_ktvs()
            doctors = data.get("doctors", [])
            ktvs = data.get("ktvs", [])

            if doctors:
                self.oncall_mgr.sync_from_firestore(doctors)
                doc_names = [d["name"].strip() for d in doctors if d.get("name")]
            else:
                local_docs = self.oncall_mgr.get_all()
                doc_names = [row[1].strip() for row in local_docs if row[1]]

            ktv_names = [k["name"].strip() for k in ktvs if k.get("name")]
            self.done.emit(doc_names, ktv_names)
        except Exception as e:
            local_docs = self.oncall_mgr.get_all()
            doc_names = [row[1].strip() for row in local_docs if row[1]]
            self.error.emit(str(e))
            self.done.emit(doc_names, [])


class SettingsWindow(QWidget):
    # Signal báo cho Dashboard biết dữ liệu cấu hình đã thay đổi
    config_saved = Signal()
    test_tts_requested = Signal()

    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.oncall_mgr = OnCallManager()
        self._sync_worker = None

        self.setWindowTitle("Cấu hình Hệ thống Gọi số & Trạm Loa Trung Tâm - BVĐK Kỳ Anh")
        self.setMinimumSize(640, 560)
        self.setStyleSheet("""
            QWidget {
                background-color: #f8fafc;
                color: #0f172a;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                background-color: transparent;
                color: #0f172a;
            }
            QLineEdit {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #94a3b8;
                border-radius: 6px;
                padding: 8px 10px;
                font-size: 14px;
                font-weight: 600;
            }
            QLineEdit:focus {
                border: 2px solid #0B5FA5;
            }
            QComboBox {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #94a3b8;
                border-radius: 6px;
                padding: 7px 12px;
                font-size: 14px;
                font-weight: bold;
            }
            QComboBox:hover, QComboBox:focus {
                border: 2px solid #0B5FA5;
                background-color: #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #0f172a;
                border: 2px solid #0B5FA5;
                selection-background-color: #0B5FA5;
                selection-color: #ffffff;
                outline: 0px;
                padding: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QComboBox QAbstractItemView::item {
                background-color: #ffffff;
                color: #0f172a;
                min-height: 34px;
                padding: 6px 12px;
            }
            QComboBox QAbstractItemView::item:hover,
            QComboBox QAbstractItemView::item:selected {
                background-color: #0B5FA5;
                color: #ffffff;
            }
            QCheckBox {
                background-color: transparent;
                color: #0B5FA5;
                font-size: 14px;
                font-weight: bold;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)

        form_layout = QFormLayout()
        form_layout.setSpacing(14)
        form_layout.setLabelAlignment(Qt.AlignRight)

        # 1. Chọn phòng & Tên hiển thị TV
        self.room = QLineEdit()
        self.room.setPlaceholderText("Ví dụ: PHÒNG SIÊU ÂM 1, PHÒNG NỘI SOI TAI MŨI HỌNG...")

        self.room_number = QComboBox()
        for r_id in ALL_ROOM_IDS:
            r_info = ROOM_DEFINITIONS[r_id]
            self.room_number.addItem(r_info["combo_label"], r_id)
        self.room_number.currentIndexChanged.connect(self._on_room_index_changed)

        # 2. Ô chọn Bác sĩ: Menu Dropdown lấy danh sách từ Firestore (như Nhân sự trực)
        doctor_row = QHBoxLayout()
        doctor_row.setSpacing(8)
        self.doctor = StaffComboBox()

        self.btn_sync_staff = QPushButton("🔄 Đồng bộ")
        self.btn_sync_staff.setToolTip("Tải danh sách Bác sĩ & Nhân sự mới nhất từ Firestore")
        self.btn_sync_staff.setStyleSheet(
            "QPushButton { background-color: #0284c7; color: white; font-size: 13px; "
            "font-weight: bold; padding: 7px 12px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background-color: #0369a1; }"
            "QPushButton:disabled { background-color: #94a3b8; color: #f1f5f9; }"
        )
        self.btn_sync_staff.clicked.connect(lambda: self.sync_personnel_from_firestore(silent=False))

        doctor_row.addWidget(self.doctor, 1)
        doctor_row.addWidget(self.btn_sync_staff)

        # 3. Ô chọn KTV / Điều dưỡng phụ máy: Menu Dropdown + Nút Thêm / Xóa nhân sự KTV
        ktv_row = QHBoxLayout()
        ktv_row.setSpacing(8)
        self.ktv = StaffComboBox()

        self.btn_add_ktv = QPushButton("➕ Thêm KTV")
        self.btn_add_ktv.setToolTip("Tự viết thêm tên KTV / Điều dưỡng phụ máy mới vào danh sách chọn")
        self.btn_add_ktv.setStyleSheet(
            "QPushButton { background-color: #16a34a; color: white; font-size: 13px; "
            "font-weight: bold; padding: 7px 12px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background-color: #15803d; }"
        )
        self.btn_add_ktv.clicked.connect(self.prompt_add_custom_ktv)

        self.btn_del_ktv = QPushButton("🗑")
        self.btn_del_ktv.setToolTip("Xóa KTV đang chọn khỏi danh sách tự thêm")
        self.btn_del_ktv.setFixedWidth(36)
        self.btn_del_ktv.setStyleSheet(
            "QPushButton { background-color: #e2e8f0; color: #dc2626; font-size: 14px; "
            "font-weight: bold; padding: 7px 6px; border-radius: 6px; border: 1px solid #cbd5e1; }"
            "QPushButton:hover { background-color: #fecaca; }"
        )
        self.btn_del_ktv.clicked.connect(self.remove_selected_custom_ktv)

        ktv_row.addWidget(self.ktv, 1)
        ktv_row.addWidget(self.btn_add_ktv)
        ktv_row.addWidget(self.btn_del_ktv)

        # 4. Dòng chữ chạy Footer
        self.footer = QLineEdit()
        self.footer.setPlaceholderText("Dòng chữ chạy ở đáy màn hình TV")

        # 5. Chế độ Loa của máy trạm (Mặc định Phòng Siêu Âm 2 là Trạm Phát Loa Trung Tâm cho toàn bộ 11 phòng)
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

        # 6. Cấu hình Bật/Tắt & Âm lượng loa
        self.chk_tts_enabled = QCheckBox("Cho phép kích hoạt gọi loa khi bấm số / gọi lại")

        vol_row = QHBoxLayout()
        self.slider_volume = QSlider(Qt.Horizontal)
        self.slider_volume.setRange(10, 100)
        self.slider_volume.setValue(100)
        self.lbl_volume_val = QLabel("100%")
        self.lbl_volume_val.setFixedWidth(45)
        self.lbl_volume_val.setStyleSheet("font-size: 13px; font-weight: bold; color: #0f172a;")
        self.slider_volume.valueChanged.connect(lambda v: self.lbl_volume_val.setText(f"{v}%"))

        self.btn_test_tts = QPushButton("🔊 Nghe thử loa")
        self.btn_test_tts.setStyleSheet(
            "background-color: #0284c7; color: white; font-weight: bold; padding: 6px 12px; border-radius: 5px;"
        )
        self.btn_test_tts.clicked.connect(self.test_tts_requested.emit)

        vol_row.addWidget(self.slider_volume, 1)
        vol_row.addWidget(self.lbl_volume_val)
        vol_row.addWidget(self.btn_test_tts)

        # 7. Phiên bản & Kiểm tra cập nhật phần mềm tự động
        update_row = QHBoxLayout()
        update_row.setSpacing(10)
        self.lbl_version_info = QLabel(f"Phiên bản hiện tại: v{APP_VERSION}")
        self.lbl_version_info.setStyleSheet("font-size: 13px; font-weight: bold; color: #0369a1;")

        self.btn_check_update = QPushButton("🔄 Kiểm tra cập nhật")
        self.btn_check_update.setToolTip("Kiểm tra và tự động tải phiên bản mới nhất từ GitHub Releases & Firestore")
        self.btn_check_update.setStyleSheet(
            "QPushButton { background-color: #0f766e; color: white; font-size: 13px; "
            "font-weight: bold; padding: 7px 14px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background-color: #115e59; }"
        )
        self.btn_check_update.clicked.connect(self.open_update_dialog)

        update_row.addWidget(self.lbl_version_info)
        update_row.addStretch()
        update_row.addWidget(self.btn_check_update)

        label_style = "font-size: 14px; font-weight: bold; color: #0f172a;"
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
        l_upd = QLabel("Cập nhật App:")
        l_upd.setStyleSheet(label_style)

        form_layout.addRow(l_rnum, self.room_number)
        form_layout.addRow(l_room, self.room)
        form_layout.addRow(l_dr, doctor_row)
        form_layout.addRow(l_ktv, ktv_row)
        form_layout.addRow(l_foot, self.footer)
        form_layout.addRow(l_mode, self.cbo_speaker_mode)
        form_layout.addRow(l_tts, self.chk_tts_enabled)
        form_layout.addRow(l_vol, vol_row)
        form_layout.addRow(l_upd, update_row)

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
        # Thiết lập popup nền đặc 100% sau khi đã gắn layout & nạp dữ liệu
        for cbo in (self.room_number, self.doctor, self.ktv, self.cbo_speaker_mode):
            self._setup_opaque_combobox(cbo)

    @staticmethod
    def _setup_opaque_combobox(combo: QComboBox):
        """Đảm bảo menu xổ xuống (dropdown popup) của QComboBox có nền trắng đặc 100%,
        không bị trong suốt trên Windows 11 và có độ tương phản cao rõ nét.
        """
        list_view = QListView(combo)
        list_view.setStyleSheet("""
            QListView {
                background-color: #ffffff;
                color: #0f172a;
                border: 2px solid #0B5FA5;
                selection-background-color: #0B5FA5;
                selection-color: #ffffff;
                outline: 0px;
                padding: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QListView::item {
                background-color: #ffffff;
                color: #0f172a;
                min-height: 34px;
                padding: 6px 12px;
            }
            QListView::item:hover,
            QListView::item:selected {
                background-color: #0B5FA5;
                color: #ffffff;
            }
        """)
        combo.setView(list_view)
        popup = combo.view().window()
        popup.setStyleSheet("background-color: #ffffff; color: #0f172a;")
        popup.setAttribute(Qt.WA_TranslucentBackground, False)

    # ─── Quản lý danh sách Bác sĩ & KTV (Firestore + Tự thêm) ────────────────

    def _get_custom_ktv_list(self) -> list[str]:
        """Đọc danh sách KTV phụ máy do người dùng tự thêm từ SQLite ConfigManager."""
        raw = self.config.get("custom_ktv_list", "[]")
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                return [str(x).strip() for x in items if str(x).strip()]
        except Exception:
            pass
        return []

    def _save_custom_ktv_list(self, ktv_list: list[str]) -> None:
        """Lưu danh sách KTV phụ máy tự thêm vào SQLite ConfigManager."""
        cleaned = []
        seen = set()
        for item in ktv_list:
            s = str(item).strip()
            if s and s != "---" and s.lower() not in seen:
                seen.add(s.lower())
                cleaned.append(s)
        self.config.set("custom_ktv_list", json.dumps(cleaned, ensure_ascii=False))

    def _get_cached_firestore_ktvs(self) -> list[str]:
        """Đọc danh sách KTV/Thư ký đã đồng bộ từ Firestore được cache trong ConfigManager."""
        raw = self.config.get("firestore_ktv_cache", "[]")
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                return [str(x).strip() for x in items if str(x).strip()]
        except Exception:
            pass
        return []

    def _save_cached_firestore_ktvs(self, ktv_list: list[str]) -> None:
        cleaned = [str(x).strip() for x in ktv_list if str(x).strip()]
        self.config.set("firestore_ktv_cache", json.dumps(cleaned, ensure_ascii=False))

    def _populate_doctor_dropdown(self, doctor_names: list[str] | None = None, selected_name: str | None = None):
        """Điền danh sách Bác sĩ vào dropdown self.doctor và giữ nguyên lựa chọn hiện tại."""
        current_sel = selected_name if selected_name is not None else self.doctor.text()
        if doctor_names is None:
            local_docs = self.oncall_mgr.get_all()
            doctor_names = [row[1].strip() for row in local_docs if row[1]]

        self.doctor.blockSignals(True)
        self.doctor.clear()
        self.doctor.addItem("---")

        seen = {"---"}
        for name in doctor_names:
            n = name.strip()
            if n and n.lower() not in seen:
                seen.add(n.lower())
                self.doctor.addItem(n)

        self.doctor.setText(current_sel or "---")
        self.doctor.blockSignals(False)
        self.doctor.view().window().setAttribute(Qt.WA_TranslucentBackground, False)

    def _populate_ktv_dropdown(self, firestore_ktvs: list[str] | None = None, selected_name: str | None = None):
        """Điền danh sách KTV / Điều dưỡng (Firestore + Tự thêm) vào dropdown self.ktv."""
        current_sel = selected_name if selected_name is not None else self.ktv.text()
        if firestore_ktvs is None:
            firestore_ktvs = self._get_cached_firestore_ktvs()
        custom_ktvs = self._get_custom_ktv_list()

        self.ktv.blockSignals(True)
        self.ktv.clear()
        self.ktv.addItem("---")

        seen = {"---"}
        for name in list(custom_ktvs) + list(firestore_ktvs):
            n = name.strip()
            if n and n.lower() not in seen:
                seen.add(n.lower())
                self.ktv.addItem(n)

        self.ktv.setText(current_sel or "---")
        self.ktv.blockSignals(False)
        self.ktv.view().window().setAttribute(Qt.WA_TranslucentBackground, False)

    def add_custom_ktv_name(self, new_name: str) -> bool:
        """Thêm một KTV phụ máy mới vào danh sách lưu trữ và chọn ngay trên dropdown."""
        name = (new_name or "").strip()
        if not name or name == "---":
            return False

        custom_list = self._get_custom_ktv_list()
        if not any(x.lower() == name.lower() for x in custom_list):
            custom_list.append(name)
            self._save_custom_ktv_list(custom_list)

        self._populate_ktv_dropdown(selected_name=name)
        return True

    def prompt_add_custom_ktv(self):
        """Mở hộp thoại để người dùng tự viết thêm tên KTV / Điều dưỡng phụ máy."""
        text, ok = QInputDialog.getText(
            self,
            "Thêm KTV / Điều dưỡng phụ máy",
            "Nhập họ và tên KTV / Điều dưỡng phụ máy mới:",
            QLineEdit.Normal,
            "",
        )
        if ok and text.strip():
            added_name = text.strip()
            self.add_custom_ktv_name(added_name)

    def remove_selected_custom_ktv(self):
        """Xóa KTV đang chọn khỏi danh sách KTV tự thêm."""
        current = self.ktv.text()
        if not current or current == "---":
            return

        custom_list = self._get_custom_ktv_list()
        new_list = [x for x in custom_list if x.lower() != current.lower()]
        if len(new_list) == len(custom_list):
            QMessageBox.information(
                self,
                "Thông báo",
                f"Nhân sự '{current}' thuộc danh sách đồng bộ từ Firestore hoặc mặc định.",
            )
            return

        self._save_custom_ktv_list(new_list)
        self._populate_ktv_dropdown(selected_name="---")

    def sync_personnel_from_firestore(self, silent: bool = True):
        """Tải danh sách Bác sĩ và KTV từ Firestore trong background thread."""
        if self._sync_worker is not None and self._sync_worker.isRunning():
            return

        self._silent_sync = silent
        self.btn_sync_staff.setEnabled(False)
        self.btn_sync_staff.setText("⏳ Đang tải...")

        self._sync_worker = SettingsPersonnelWorker(self.oncall_mgr)
        self._sync_worker.done.connect(self._on_personnel_sync_done)
        self._sync_worker.error.connect(self._on_personnel_sync_error)
        self._sync_worker.start()

    def _on_personnel_sync_done(self, doc_names: list[str], ktv_names: list[str]):
        self.btn_sync_staff.setEnabled(True)
        self.btn_sync_staff.setText("🔄 Đồng bộ")

        if doc_names:
            self._populate_doctor_dropdown(doctor_names=doc_names)
        if ktv_names:
            self._save_cached_firestore_ktvs(ktv_names)
            self._populate_ktv_dropdown(firestore_ktvs=ktv_names)

        if not getattr(self, "_silent_sync", True):
            QMessageBox.information(
                self,
                "Đồng bộ hoàn tất",
                f"Đã cập nhật {len(doc_names)} Bác sĩ và {len(ktv_names)} Nhân sự hỗ trợ từ Firestore!",
            )

    def _on_personnel_sync_error(self, err_msg: str):
        self.btn_sync_staff.setEnabled(True)
        self.btn_sync_staff.setText("🔄 Đồng bộ")
        if not getattr(self, "_silent_sync", True):
            QMessageBox.warning(
                self,
                "Lỗi đồng bộ Firestore",
                f"Không thể tải danh sách nhân sự từ Firestore:\n{err_msg}\n\n"
                "Hệ thống vẫn sử dụng danh sách đã lưu trên máy.",
            )

    # ─── Xử lý Phòng & Lưu cấu hình ──────────────────────────────────────────

    def get_selected_room_id(self) -> str:
        """Lấy mã định danh chuẩn của phòng đang chọn (VD: '1'..'5', 'tmh', 'nsth', 'dtd', 'dnd', 'lhn', 'cnhh')."""
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
        """Đọc dữ liệu từ ConfigManager và điền vào các ô nhập liệu / dropdown."""
        room_num = self.config.get("room_number", "1").strip().lower()
        self.room_number.blockSignals(True)
        idx = self.room_number.findData(room_num)
        if idx < 0:
            idx = 0
        self.room_number.setCurrentIndex(idx)
        self.room_number.blockSignals(False)

        default_title = get_room_display_name(room_num)
        self.room.setText(self.config.get("room", default_title) or default_title)

        saved_doc = self.config.get("doctor", "---")
        saved_ktv = self.config.get("ktv", "---")

        # Nạp danh sách từ bộ nhớ local trước (0ms)
        self._populate_doctor_dropdown(selected_name=saved_doc)
        self._populate_ktv_dropdown(selected_name=saved_ktv)

        self.footer.setText(
            self.config.get(
                "footer",
                "Xin vui lòng chuẩn bị giấy tờ và lắng nghe loa gọi số trước khi vào phòng khám",
            )
        )

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
        self.config.set("doctor", self.doctor.text())
        self.config.set("ktv", self.ktv.text())
        self.config.set("footer", self.footer.text().strip())
        self.config.set("speaker_mode", self.cbo_speaker_mode.currentData())
        self.config.set("tts_enabled", "1" if self.chk_tts_enabled.isChecked() else "0")
        self.config.set("tts_volume", str(self.slider_volume.value()))

        self.config_saved.emit()
        self.close()
        self.hide()

    def open_update_dialog(self):
        dlg = UpdateDialog(parent=self)
        dlg.exec()

    def showEvent(self, event):
        """Mỗi khi mở cửa sổ Settings, tự động đồng bộ ngầm danh sách Bác sĩ & KTV từ Firestore."""
        super().showEvent(event)
        self.sync_personnel_from_firestore(silent=True)

    def closeEvent(self, event):
        if self._sync_worker is not None and self._sync_worker.isRunning():
            self._sync_worker.wait(1500)
        super().closeEvent(event)
