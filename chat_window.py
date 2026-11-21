# =============================================================================
# FILE: chat_window.py
# MÔ TẢ: Giao diện Cửa sổ Chat Nhanh Nội Bộ (ChatWindow) và Hộp Thông Báo Nổi
#        Góc Màn Hình (ChatToastPopup) cho hệ thống AUTOQ (11 Phòng + Admin).
#        Tuyệt đối chỉ hiển thị trên máy trạm điều khiển, KHÔNG hiện lên TV bệnh nhân.
# =============================================================================

import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QCheckBox, QScrollArea, QFrame,
    QListView, QInputDialog, QApplication, QMenu
)
from PySide6.QtCore import Qt, QTimer, Signal, QPoint

from config_manager import ConfigManager
from speaker_hub import ALL_ROOM_IDS, ROOM_DEFINITIONS
from chat_service import (
    ChatService,
    DEFAULT_QUICK_TEMPLATES,
    get_room_or_admin_short_name,
)


def _setup_opaque_combo(combo: QComboBox, border_color: str = "#0B5FA5") -> None:
    """Đảm bảo menu dropdown có nền trắng đặc 100%, không bị trong suốt trên Windows 11."""
    lv = QListView(combo)
    lv.setStyleSheet(f"""
        QListView {{
            background-color: #ffffff;
            color: #0f172a;
            border: 2px solid {border_color};
            selection-background-color: {border_color};
            selection-color: #ffffff;
            outline: 0px;
            padding: 4px;
            font-size: 13px;
            font-weight: bold;
        }}
        QListView::item {{
            background-color: #ffffff;
            color: #0f172a;
            min-height: 32px;
            padding: 5px 10px;
        }}
        QListView::item:hover,
        QListView::item:selected {{
            background-color: {border_color};
            color: #ffffff;
        }}
    """)
    combo.setView(lv)
    popup = combo.view().window()
    popup.setStyleSheet("background-color: #ffffff; color: #0f172a;")
    popup.setAttribute(Qt.WA_TranslucentBackground, False)


# =============================================================================
# HỘP THÔNG BÁO NỔI GÓC DƯỚI MÀN HÌNH MÁY TÍNH (NON-BLOCKING TOAST)
# =============================================================================

class ChatToastPopup(QWidget):
    """Popup nổi góc dưới bên phải màn hình máy điều khiển khi có tin nhắn mới.
    Không chiếm quyền bàn phím/chuột (WindowDoesNotAcceptFocus) và tự ẩn sau 8 giây.
    """
    reply_requested = Signal(str)  # sender_room_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sender_room = "ALL"

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setFixedWidth(380)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame()
        self.card.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 2px solid #0284c7;
                border-radius: 12px;
            }
            QLabel {
                border: none;
                background: transparent;
                color: #f8fafc;
            }
        """)
        c_layout = QVBoxLayout(self.card)
        c_layout.setContentsMargins(14, 12, 14, 12)
        c_layout.setSpacing(6)

        top_row = QHBoxLayout()
        self.lbl_header = QLabel("💬 TIN NHẮN NỘI BỘ MỚI")
        self.lbl_header.setStyleSheet("font-size: 13px; font-weight: bold; color: #38bdf8;")

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(24, 24)
        btn_close.setStyleSheet(
            "QPushButton { background: #1e293b; color: #94a3b8; border-radius: 6px; font-weight: bold; border: none; }"
            "QPushButton:hover { background: #dc2626; color: white; }"
        )
        btn_close.clicked.connect(self.hide)

        top_row.addWidget(self.lbl_header, 1)
        top_row.addWidget(btn_close)
        c_layout.addLayout(top_row)

        self.lbl_meta = QLabel("")
        self.lbl_meta.setStyleSheet("font-size: 12px; font-weight: bold; color: #fbbf24;")
        c_layout.addWidget(self.lbl_meta)

        self.lbl_content = QLabel("")
        self.lbl_content.setWordWrap(True)
        self.lbl_content.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #ffffff; "
            "background: #1e293b; border-radius: 8px; padding: 8px 10px;"
        )
        c_layout.addWidget(self.lbl_content)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_reply = QPushButton("↩ Mở Chat & Trả lời ngay")
        self.btn_reply.setStyleSheet(
            "QPushButton { background: #0284c7; color: white; font-size: 12px; "
            "font-weight: bold; padding: 6px 12px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background: #0369a1; }"
        )
        self.btn_reply.clicked.connect(self._on_reply_clicked)
        btn_row.addWidget(self.btn_reply)
        c_layout.addLayout(btn_row)

        root.addWidget(self.card)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_message_toast(self, msg: dict):
        self._sender_room = str(msg.get("sender_room", "ALL")).strip().lower()
        sender_name = msg.get("sender_room_name") or get_room_or_admin_short_name(self._sender_room)
        sender_doc = (msg.get("sender_doctor") or "").strip()
        target_r = str(msg.get("target_room", "ALL")).strip().upper()
        is_urgent = bool(msg.get("is_urgent"))
        time_str = msg.get("time_str") or ""

        if is_urgent:
            self.card.setStyleSheet("""
                QFrame {
                    background-color: #450a0a;
                    border: 2px solid #ef4444;
                    border-radius: 12px;
                }
                QLabel { border: none; background: transparent; color: #f8fafc; }
            """)
            self.lbl_header.setText(f"🚨 TIN KHẨN CẤP ({time_str})")
            self.lbl_header.setStyleSheet("font-size: 13px; font-weight: bold; color: #fca5a5;")
        else:
            self.card.setStyleSheet("""
                QFrame {
                    background-color: #0f172a;
                    border: 2px solid #0284c7;
                    border-radius: 12px;
                }
                QLabel { border: none; background: transparent; color: #f8fafc; }
            """)
            scope_txt = "📢 Toàn khoa" if target_r == "ALL" else "🎯 Gửi riêng phòng bạn"
            self.lbl_header.setText(f"💬 TIN NHẮN NỘI BỘ · {scope_txt} ({time_str})")
            self.lbl_header.setStyleSheet("font-size: 12px; font-weight: bold; color: #38bdf8;")

        doc_suffix = f" ({sender_doc})" if sender_doc else ""
        self.lbl_meta.setText(f"Từ: {sender_name}{doc_suffix}")
        self.lbl_content.setText(str(msg.get("content", "")))

        self.adjustSize()
        self._position_bottom_right()
        self.show()
        self.raise_()
        self._hide_timer.start(8000)

    def _position_bottom_right(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        avail = screen.availableGeometry()
        x = avail.right() - self.width() - 20
        y = avail.bottom() - self.height() - 20
        self.move(max(10, x), max(10, y))

    def _on_reply_clicked(self):
        self._hide_timer.stop()
        self.hide()
        self.reply_requested.emit(self._sender_room)


# =============================================================================
# CỬA SỔ CHAT NHANH NỘI BỘ GIỮA 11 PHÒNG KHÁM & ADMIN
# =============================================================================

class ChatWindow(QWidget):
    """Cửa sổ Chat Nhanh Nội Bộ hỗ trợ:
    - Chọn nơi nhận: Toàn khoa hoặc gửi riêng từng phòng (kèm tên Bác sĩ đang phụ trách)
    - Nút bấm gửi ngay 1 chạm (Quick Clinical Templates) + Tự thêm mẫu câu nhanh
    - Lịch sử hội thoại trong ngày rõ nét, có nút '↩ Trả lời riêng' trên từng tin nhắn
    """

    def __init__(self, chat_service: ChatService, parent=None):
        super().__init__(parent)
        self.chat_service = chat_service
        self.config = ConfigManager()

        self.setWindowTitle("💬 Chat Nhanh Nội Bộ Khoa CĐHA & Thăm Dò Chức Năng (11 Phòng)")
        self.setMinimumSize(650, 620)
        self.setStyleSheet("""
            QWidget {
                background-color: #f8fafc;
                color: #0f172a;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                background: transparent;
                color: #0f172a;
            }
            QLineEdit {
                background-color: #ffffff;
                color: #0f172a;
                border: 2px solid #94a3b8;
                border-radius: 8px;
                padding: 9px 12px;
                font-size: 14px;
                font-weight: 600;
            }
            QLineEdit:focus {
                border: 2px solid #0B5FA5;
            }
            QComboBox {
                background-color: #ffffff;
                color: #0f172a;
                border: 2px solid #0B5FA5;
                border-radius: 7px;
                padding: 6px 10px;
                font-size: 13px;
                font-weight: bold;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # ── 1. HEADER: ĐỊNH DANH PHÒNG & CHỌN NƠI NHẬN ──
        header_frame = QFrame()
        header_frame.setStyleSheet(
            "QFrame { background: #e0f2fe; border: 1px solid #7dd3fc; border-radius: 10px; }"
        )
        h_layout = QVBoxLayout(header_frame)
        h_layout.setContentsMargins(12, 10, 12, 10)
        h_layout.setSpacing(8)

        top_info_row = QHBoxLayout()
        self.lbl_identity = QLabel("🏥 Phòng của bạn: ---")
        self.lbl_identity.setStyleSheet("font-size: 14px; font-weight: bold; color: #0369a1; border: none;")

        self.chk_sound = QCheckBox("🔔 Âm báo khi có tin mới")
        self.chk_sound.setChecked(self.config.get("chat_sound_enabled", "1") != "0")
        self.chk_sound.setStyleSheet("font-size: 12px; font-weight: bold; color: #0f172a;")
        self.chk_sound.toggled.connect(
            lambda checked: self.config.set("chat_sound_enabled", "1" if checked else "0")
        )

        top_info_row.addWidget(self.lbl_identity, 1)
        top_info_row.addWidget(self.chk_sound)
        h_layout.addLayout(top_info_row)

        target_row = QHBoxLayout()
        target_row.setSpacing(8)
        lbl_to = QLabel("Gửi tới:")
        lbl_to.setStyleSheet("font-size: 13px; font-weight: bold; color: #0f172a; border: none;")

        self.cbo_target = QComboBox()
        self._populate_target_combo({})

        self.chk_urgent = QCheckBox("🚨 Tin khẩn cấp")
        self.chk_urgent.setStyleSheet("font-size: 13px; font-weight: bold; color: #dc2626;")

        target_row.addWidget(lbl_to)
        target_row.addWidget(self.cbo_target, 1)
        target_row.addWidget(self.chk_urgent)
        h_layout.addLayout(target_row)

        root.addWidget(header_frame)

        # ── 2. KHUNG LỊCH SỬ TIN NHẮN TRONG NGÀY (ƯU TIÊN DIỆN TÍCH TỐI ĐA) ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: #ffffff; border: 1.5px solid #cbd5e1; border-radius: 10px; }"
        )
        self.msg_container = QWidget()
        self.msg_container.setStyleSheet("background: #ffffff; border: none;")
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setContentsMargins(12, 12, 12, 12)
        self.msg_layout.setSpacing(8)
        self.msg_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.msg_container)
        root.addWidget(self.scroll_area, 1)

        # ── 3. THANH NHẬP TIN NHẮN & NÚT SỔ MENU MẪU TIN NHẮN NHANH ──
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.btn_quick_menu = QPushButton("⚡ Mẫu tin nhắn nhanh ▾")
        self.btn_quick_menu.setToolTip("Bấm để mở danh sách mẫu tin nhắn nhanh (Gửi 1 chạm hoặc thêm/xóa mẫu câu)")
        self.btn_quick_menu.setStyleSheet(
            "QPushButton { background: #0284c7; color: white; font-size: 13px; "
            "font-weight: bold; padding: 10px 14px; border-radius: 8px; border: none; }"
            "QPushButton:hover { background-color: #0369a1; }"
        )
        self.btn_quick_menu.clicked.connect(self._show_quick_templates_menu)

        self.txt_input = QLineEdit()
        self.txt_input.setPlaceholderText("Nhập nội dung tin nhắn trao đổi giữa các phòng (Nhấn Enter để gửi)...")
        self.txt_input.returnPressed.connect(self._send_text_input)

        self.btn_send = QPushButton("📤 GỬI TIN")
        self.btn_send.setStyleSheet(
            "QPushButton { background: #16a34a; color: white; font-size: 14px; "
            "font-weight: bold; padding: 10px 18px; border-radius: 8px; border: none; }"
            "QPushButton:hover { background: #15803d; }"
        )
        self.btn_send.clicked.connect(self._send_text_input)

        input_row.addWidget(self.btn_quick_menu)
        input_row.addWidget(self.txt_input, 1)
        input_row.addWidget(self.btn_send)
        root.addLayout(input_row)

        _setup_opaque_combo(self.cbo_target)
        self.refresh_identity_banner()

        # Kết nối tín hiệu từ ChatService
        self.chat_service.message_received.connect(self._on_message_received)
        self.chat_service.history_loaded.connect(self._on_history_loaded)
        self.chat_service.room_doctors_updated.connect(self._populate_target_combo)

        self._on_history_loaded(self.chat_service.get_visible_messages())

    # ─── CẬP NHẬT ĐỊNH DANH & DANH SÁCH PHÒNG NHẬN ───────────────────────────

    def refresh_identity_banner(self):
        r_name = get_room_or_admin_short_name(self.chat_service.local_room_id)
        doc_name = self.chat_service.local_doctor_name
        doc_part = f" — 👨‍⚕️ {doc_name}" if doc_name else ""
        self.lbl_identity.setText(f"🏥 Đang gửi từ: {r_name}{doc_part}")
        self._populate_target_combo(self.chat_service.get_room_doctors_map())

    def _populate_target_combo(self, room_doctors: dict[str, str]):
        prev_target = self.cbo_target.currentData() or "ALL"
        self.cbo_target.blockSignals(True)
        self.cbo_target.clear()

        self.cbo_target.addItem("📢 Toàn khoa (Tất cả 11 phòng & Admin)", "ALL")
        for r_id in ALL_ROOM_IDS:
            if r_id == self.chat_service.local_room_id:
                continue
            r_short = ROOM_DEFINITIONS[r_id]["short_name"]
            doc = (room_doctors.get(r_id) or "").strip()
            lbl = f"🎯 {r_short} — {doc}" if doc else f"🎯 {r_short}"
            self.cbo_target.addItem(lbl, r_id)

        if self.chat_service.local_room_id != "admin":
            self.cbo_target.addItem("🎯 Trung tâm Admin", "admin")

        idx = self.cbo_target.findData(prev_target)
        self.cbo_target.setCurrentIndex(idx if idx >= 0 else 0)
        self.cbo_target.blockSignals(False)
        self.cbo_target.view().window().setAttribute(Qt.WA_TranslucentBackground, False)

    def select_target_room(self, target_room_id: str):
        r = str(target_room_id or "ALL").strip()
        if r.upper() == "ALL":
            r = "ALL"
        else:
            r = r.lower()
        idx = self.cbo_target.findData(r)
        if idx >= 0:
            self.cbo_target.setCurrentIndex(idx)
        self.txt_input.setFocus()

    # ─── MENU SỔ RA CHO TIN NHẮN MẪU 1 CHẠM ──────────────────────────────────

    def _get_custom_templates(self) -> list[str]:
        raw = self.config.get("custom_chat_templates", "[]")
        try:
            arr = json.loads(raw)
            if isinstance(arr, list):
                return [str(x).strip() for x in arr if str(x).strip()]
        except Exception:
            pass
        return []

    def _save_custom_templates(self, templates: list[str]) -> None:
        self.config.set("custom_chat_templates", json.dumps(templates, ensure_ascii=False))

    def _build_quick_templates_menu(self) -> QMenu:
        """Khởi tạo QMenu nền đặc tương phản cao chứa toàn bộ tin nhắn mẫu nhanh."""
        menu_style = """
            QMenu {
                background-color: #ffffff;
                color: #0f172a;
                border: 2px solid #0B5FA5;
                border-radius: 8px;
                padding: 6px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
                font-weight: bold;
            }
            QMenu::item {
                background-color: #ffffff;
                color: #0f172a;
                padding: 8px 16px;
                border-radius: 5px;
                margin: 2px 0px;
            }
            QMenu::item:selected {
                background-color: #0B5FA5;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: #cbd5e1;
                margin: 6px 4px;
            }
        """
        menu = QMenu(self)
        menu.setStyleSheet(menu_style)
        menu.setAttribute(Qt.WA_TranslucentBackground, False)

        custom_tpls = self._get_custom_templates()
        all_tpls = list(DEFAULT_QUICK_TEMPLATES) + list(custom_tpls)

        for tpl_text in all_tpls:
            act = menu.addAction(tpl_text)
            act.triggered.connect(lambda checked=False, txt=tpl_text: self._send_quick_template(txt))

        menu.addSeparator()

        act_add = menu.addAction("➕ Thêm mẫu tin nhắn nhanh mới...")
        act_add.triggered.connect(self._prompt_add_template)

        if custom_tpls:
            del_menu = QMenu("🗑 Xóa mẫu tin tự thêm", menu)
            del_menu.setStyleSheet(menu_style)
            del_menu.setAttribute(Qt.WA_TranslucentBackground, False)
            for c_txt in custom_tpls:
                del_act = del_menu.addAction(f"✕  {c_txt}")
                del_act.triggered.connect(lambda checked=False, txt=c_txt: self._remove_custom_template(txt))
            menu.addMenu(del_menu)

        return menu

    def _show_quick_templates_menu(self):
        """Hiển thị menu mẫu tin nhắn nhanh sổ ra ngay tại nút '⚡ Mẫu tin nhắn nhanh ▾'."""
        menu = self._build_quick_templates_menu()
        menu_hint = menu.sizeHint()
        btn_global = self.btn_quick_menu.mapToGlobal(QPoint(0, 0))
        # Ưu tiên sổ lên phía trên nút nếu nút nằm ở đáy cửa sổ
        popup_y = btn_global.y() - menu_hint.height() - 4
        if popup_y < 20:
            popup_y = btn_global.y() + self.btn_quick_menu.height() + 4
        menu.exec(QPoint(btn_global.x(), popup_y))

    def _prompt_add_template(self):
        text, ok = QInputDialog.getText(
            self,
            "Thêm mẫu tin nhắn nhanh 1 chạm",
            "Nhập nội dung câu nhắn mẫu thường dùng:",
            QLineEdit.Normal,
            "",
        )
        if ok and text.strip():
            custom = self._get_custom_templates()
            new_t = text.strip()
            if new_t not in custom:
                custom.append(new_t)
                self._save_custom_templates(custom)

    def _remove_custom_template(self, tpl_text: str):
        custom = [t for t in self._get_custom_templates() if t != tpl_text]
        self._save_custom_templates(custom)

    def _send_quick_template(self, tpl_text: str):
        target_r = self.cbo_target.currentData() or "ALL"
        urgent = self.chk_urgent.isChecked() or ("🚨" in tpl_text)
        self.chat_service.send_message(tpl_text, target_room=target_r, is_urgent=urgent)
        self.chk_urgent.setChecked(False)

    def _send_text_input(self):
        text = self.txt_input.text().strip()
        if not text:
            return
        target_r = self.cbo_target.currentData() or "ALL"
        urgent = self.chk_urgent.isChecked()
        self.chat_service.send_message(text, target_room=target_r, is_urgent=urgent)
        self.txt_input.clear()
        self.chk_urgent.setChecked(False)

    # ─── HIỂN THỊ DANH SÁCH TIN NHẮN ─────────────────────────────────────────

    def _clear_message_widgets(self):
        while self.msg_layout.count():
            item = self.msg_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _on_history_loaded(self, messages: list[dict]):
        self._clear_message_widgets()
        if not messages:
            empty_lbl = QLabel("Chưa có tin nhắn trao đổi nào trong ngày hôm nay.")
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet("font-size: 13px; color: #94a3b8; padding: 25px;")
            self.msg_layout.addWidget(empty_lbl)
            return

        for m in messages:
            self._append_message_bubble(m)
        self._scroll_to_bottom()

    def _on_message_received(self, msg: dict, _is_incoming: bool):
        # Xóa dòng 'Chưa có tin nhắn' nếu là tin đầu tiên
        if self.msg_layout.count() == 1:
            first_w = self.msg_layout.itemAt(0).widget()
            if isinstance(first_w, QLabel):
                first_w.deleteLater()
        self._append_message_bubble(msg)
        self._scroll_to_bottom()

    def _append_message_bubble(self, msg: dict):
        sender_r = str(msg.get("sender_room", "")).strip().lower()
        sender_name = msg.get("sender_room_name") or get_room_or_admin_short_name(sender_r)
        sender_doc = (msg.get("sender_doctor") or "").strip()
        target_r = str(msg.get("target_room", "ALL")).strip().lower()
        target_name = msg.get("target_room_name") or get_room_or_admin_short_name(target_r)
        is_mine = (sender_r == self.chat_service.local_room_id)
        is_urgent = bool(msg.get("is_urgent"))
        time_str = msg.get("time_str") or ""

        bubble = QFrame()
        if is_urgent:
            bg = "#fef2f2"
            border = "#ef4444"
            head_color = "#b91c1c"
        elif is_mine:
            bg = "#eff6ff"
            border = "#93c5fd"
            head_color = "#1d4ed8"
        elif target_r == self.chat_service.local_room_id:
            bg = "#f0fdf4"
            border = "#4ade80"
            head_color = "#15803d"
        else:
            bg = "#f8fafc"
            border = "#cbd5e1"
            head_color = "#334155"

        bubble.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border: 1.5px solid {border}; border-radius: 10px; }}"
            "QLabel { border: none; background: transparent; }"
        )
        b_layout = QVBoxLayout(bubble)
        b_layout.setContentsMargins(12, 8, 12, 8)
        b_layout.setSpacing(4)

        top_row = QHBoxLayout()
        doc_str = f" ({sender_doc})" if sender_doc else ""
        target_badge = "📢 Toàn khoa" if target_r == "all" else f"🎯 Tới: {target_name}"
        urgent_tag = "🚨 [KHẨN CẤP] " if is_urgent else ""

        lbl_meta = QLabel(f"{urgent_tag}{sender_name}{doc_str}  ➔  {target_badge}   ·   🕒 {time_str}")
        lbl_meta.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {head_color};")
        top_row.addWidget(lbl_meta, 1)

        if not is_mine and sender_r:
            btn_reply_one = QPushButton(f"↩ Nhắn riêng {sender_name}")
            btn_reply_one.setStyleSheet(
                "QPushButton { background: #e2e8f0; color: #0f172a; font-size: 11px; "
                "font-weight: bold; padding: 2px 8px; border-radius: 4px; border: none; }"
                "QPushButton:hover { background: #0284c7; color: white; }"
            )
            btn_reply_one.clicked.connect(lambda checked=False, sr=sender_r: self.select_target_room(sr))
            top_row.addWidget(btn_reply_one)

        b_layout.addLayout(top_row)

        lbl_text = QLabel(str(msg.get("content", "")))
        lbl_text.setWordWrap(True)
        lbl_text.setStyleSheet("font-size: 14px; font-weight: 600; color: #0f172a; padding-top: 2px;")
        b_layout.addWidget(lbl_text)

        self.msg_layout.addWidget(bubble)

    def _scroll_to_bottom(self):
        QTimer.singleShot(
            40,
            lambda: self.scroll_area.verticalScrollBar().setValue(
                self.scroll_area.verticalScrollBar().maximum()
            ),
        )

    # ─── VÒNG ĐỜI CỬA SỔ ─────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_identity_banner()
        self.chat_service.set_chat_window_open(True)
        self._scroll_to_bottom()

    def hideEvent(self, event):
        self.chat_service.set_chat_window_open(False)
        super().hideEvent(event)

    def closeEvent(self, event):
        self.chat_service.set_chat_window_open(False)
        super().closeEvent(event)
