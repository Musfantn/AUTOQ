from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QPoint, QTimer, QTime
from config_manager import ConfigManager


class MiniPanel(QWidget):

    def __init__(self, dashboard):
        super().__init__()
        self.dashboard = dashboard
        self.config = ConfigManager()
        self.old_pos = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowOpacity(0.9)
        self.setStyleSheet("background:#0B5FA5; color:white; border-radius:10px; border: 1px solid white;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)

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

        # Nhãn số: Gán cố định độ rộng để không bị nhảy layout khi đổi số
        self.number = QLabel("000")
        self.number.setFixedWidth(50)
        self.number.setStyleSheet("font-size:22px; font-weight:bold; color: #FFD700; border: none;")

        btn_next = QPushButton("TIẾP THEO")
        btn_dash = QPushButton("PHÓNG TO")

        btn_next.setStyleSheet("background: #28a745; border-radius: 5px; padding: 5px; border: none;")
        btn_dash.setStyleSheet("background: #6c757d; border-radius: 5px; padding: 5px; border: none;")

        # Kết nối nút NEXT về Dashboard
        btn_next.clicked.connect(self.dashboard.next)
        btn_dash.clicked.connect(self.restore)

        layout.addWidget(self.duty_indicator)
        layout.addWidget(self.number)
        layout.addWidget(btn_next)
        layout.addWidget(btn_dash)
        layout.addStretch()

        # ===== clock =====
        self.time_label = QLabel("00:00:00")
        self.time_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFD700; border: none;")
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.time_label)

        self.setFixedSize(420, 50)

        # ===== clock timer =====
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_time)
        self.clock_timer.start(1000)
        self.update_time()

    def update_time(self):
        """Cập nhật đồng hồ realtime"""
        t = QTime.currentTime()
        self.time_label.setText(t.toString("HH:mm:ss"))

    def load_last_position(self):
        """Đọc tọa độ x, y từ config và di chuyển panel tới đó"""
        last_x = int(self.config.get("mini_x", 100))
        last_y = int(self.config.get("mini_y", 100))
        self.move(last_x, last_y)

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
        # Khi thả chuột, lưu ngay vị trí mới vào database
        self.config.set("mini_x", self.x())
        self.config.set("mini_y", self.y())

    def update_number(self, n):
        """Cập nhật text và ép label vẽ lại"""
        self.number.setText(str(n))
        self.number.repaint()

    # ===== duty mode indicator =====
    def set_duty_mode(self, active):
        """Bật/tắt ký hiệu chế độ trực trên mini panel."""
        self.duty_indicator.setVisible(active)
        if active:
            self.number.setText("TRỰC")
            self.number.setFixedWidth(50)
            self.number.setStyleSheet("font-size: 16px; font-weight: 700; color: #FF9800; border: none;")
        else:
            # Khôi phục lại số hiện tại từ dashboard
            current_number = self.dashboard.number.text()
            self.number.setText(current_number)
            self.number.setFixedWidth(50)
            self.number.setStyleSheet("font-size: 22px; font-weight: bold; color: #FFD700; border: none;")
            self.number.repaint()

    def restore(self):
        self.dashboard.show()
        self.hide()