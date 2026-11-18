from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, QPoint, QTimer, QTime
from config_manager import ConfigManager


class MiniPanel(QWidget):

    def __init__(self, dashboard):
        super().__init__()
        self.dashboard = dashboard
        self.config = ConfigManager()
        self.old_pos = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowOpacity(0.92)
        self.setStyleSheet("background:#0B5FA5; color:white; border-radius:10px; border: 1px solid white;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(6)

        # ===== duty indicator =====
        self.duty_indicator = QLabel("🌙 TRỰC")
        self.duty_indicator.setStyleSheet("""
            font-size: 13px;
            font-weight: 700;
            color: #1e1e1e;
            background: #FFD54F;
            border-radius: 5px;
            border: none;
            padding: 3px 6px;
        """)
        self.duty_indicator.setVisible(False)

        # Nhãn số hiện tại: cố định độ rộng để không nhảy layout
        self.number = QLabel("000")
        self.number.setFixedWidth(56)
        self.number.setAlignment(Qt.AlignCenter)
        self.number.setStyleSheet("font-size:22px; font-weight:bold; color: #FFD700; border: none;")

        self.btn_next = QPushButton("▶ TIẾP THEO")
        self.btn_recall = QPushButton("🔊 GỌI LẠI")
        self.btn_skip = QPushButton("⏭ CHƯA VÀO")
        self.btn_chat = QPushButton("💬 CHAT")
        self.btn_dash = QPushButton("PHÓNG TO")

        self.btn_next.setStyleSheet(
            "QPushButton { background: #28a745; color: white; font-weight: bold; border-radius: 5px; padding: 6px 10px; border: none; }"
            "QPushButton:hover { background: #218838; }"
        )
        self.btn_recall.setStyleSheet(
            "QPushButton { background: #f59e0b; color: white; font-weight: bold; border-radius: 5px; padding: 6px 10px; border: none; }"
            "QPushButton:hover { background: #d97706; }"
        )
        self.btn_skip.setStyleSheet(
            "QPushButton { background: #0284c7; color: white; font-weight: bold; border-radius: 5px; padding: 6px 8px; border: none; }"
            "QPushButton:hover { background: #0369a1; }"
        )
        self.btn_skip.setToolTip("Bệnh nhân chưa vào phòng: Lưu vào danh sách chờ gọi lại và gọi số tiếp theo")
        self.btn_chat.setStyleSheet(
            "QPushButton { background: #7c3aed; color: white; font-weight: bold; border-radius: 5px; padding: 6px 8px; border: none; }"
            "QPushButton:hover { background: #6d28d9; }"
        )
        self.btn_chat.setToolTip("Mở cửa sổ Chat Nhanh Nội Bộ giữa các phòng")
        self.btn_dash.setStyleSheet(
            "QPushButton { background: #6c757d; color: white; font-weight: bold; border-radius: 5px; padding: 6px 8px; border: none; }"
            "QPushButton:hover { background: #5a6268; }"
        )

        # Kết nối các nút điều khiển về Dashboard
        self.btn_next.clicked.connect(self.dashboard.next)
        self.btn_recall.clicked.connect(self.dashboard.recall_current)
        self.btn_skip.clicked.connect(self.dashboard.skip_and_next)
        self.btn_chat.clicked.connect(self.dashboard.show_chat_window)
        self.btn_dash.clicked.connect(self.restore)

        layout.addWidget(self.duty_indicator)
        layout.addWidget(self.number)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_recall)
        layout.addWidget(self.btn_skip)
        layout.addWidget(self.btn_chat)
        layout.addWidget(self.btn_dash)
        layout.addStretch()

        # ===== clock =====
        self.time_label = QLabel("00:00:00")
        self.time_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #FFD700; border: none;")
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.time_label)

        self.setFixedSize(640, 52)
        self.load_last_position()

        # ===== clock timer =====
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_time)
        self.clock_timer.start(1000)
        self.update_time()

    def update_time(self):
        """Cập nhật đồng hồ realtime."""
        t = QTime.currentTime()
        self.time_label.setText(t.toString("HH:mm:ss"))

    def load_last_position(self):
        """Đọc tọa độ x, y từ config và di chuyển panel tới đó."""
        try:
            last_x = int(self.config.get("mini_x", 100))
            last_y = int(self.config.get("mini_y", 100))
            self.move(last_x, last_y)
        except Exception:
            pass

    # --- LOGIC CHO PHÉP KÉO CHUỘT ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            delta = QPoint(event.globalPosition().toPoint() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None
        self.config.set("mini_x", self.x())
        self.config.set("mini_y", self.y())

    def update_number(self, n):
        """Cập nhật số hiện tại trên MiniPanel."""
        self.number.setText(str(n))
        self.number.repaint()

    # ===== duty mode indicator =====
    def set_duty_mode(self, active: bool):
        """Bật/tắt ký hiệu chế độ trực trên mini panel."""
        self.duty_indicator.setVisible(active)
        self.btn_next.setEnabled(not active)
        self.btn_recall.setEnabled(not active)
        self.btn_skip.setEnabled(not active)
        if active:
            self.number.setText("TRỰC")
            self.number.setStyleSheet("font-size: 16px; font-weight: 700; color: #FF9800; border: none;")
        else:
            current_number = self.dashboard.number.text()
            self.number.setText(current_number)
            self.number.setStyleSheet("font-size: 22px; font-weight: bold; color: #FFD700; border: none;")
            self.number.repaint()

    def update_chat_badge(self, unread_count: int):
        """Cập nhật badge tin nhắn chưa đọc trên nút Chat của MiniPanel."""
        if unread_count > 0:
            self.btn_chat.setText(f"💬 ({unread_count})")
            self.btn_chat.setStyleSheet(
                "QPushButton { background: #dc2626; color: white; font-weight: bold; border-radius: 5px; padding: 6px 8px; border: 1px solid #fef08a; }"
                "QPushButton:hover { background: #b91c1c; }"
            )
        else:
            self.btn_chat.setText("💬 CHAT")
            self.btn_chat.setStyleSheet(
                "QPushButton { background: #7c3aed; color: white; font-weight: bold; border-radius: 5px; padding: 6px 8px; border: none; }"
                "QPushButton:hover { background: #6d28d9; }"
            )

    def restore(self):
        self.dashboard.show()
        self.hide()
