from PySide6.QtWidgets import *
from PySide6.QtCore import *
from config_manager import ConfigManager # Import để lưu vị trí

class MiniPanel(QWidget):

    def __init__(self, dashboard):
        super().__init__()
        self.dashboard = dashboard
        self.config = ConfigManager() # Để lưu vị trí
        self.old_pos = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowOpacity(0.9)
        self.setStyleSheet("background:#0B5FA5; color:white; border-radius:10px; border: 1px solid white;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)

        # Nhãn số: Gán cố định độ rộng để không bị nhảy layout khi đổi số
        self.number = QLabel("000")
        self.number.setFixedWidth(50) 
        self.number.setStyleSheet("font-size:22px; font-weight:bold; color: #FFD700;") # Màu vàng cho dễ nhìn

        btn_next = QPushButton("TIẾP THEO")
        btn_dash = QPushButton("PHÓNG TO")
        
        btn_next.setStyleSheet("background: #28a745; border-radius: 5px; padding: 5px;")
        btn_dash.setStyleSheet("background: #6c757d; border-radius: 5px; padding: 5px;")

        # Kết nối nút NEXT về Dashboard
        btn_next.clicked.connect(self.dashboard.next)
        btn_dash.clicked.connect(self.restore)

        layout.addWidget(self.number)
        layout.addWidget(btn_next)
        layout.addWidget(btn_dash)

        self.setFixedSize(220, 50)

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
        self.number.repaint() # Ép giao diện cập nhật ngay lập tức

    def restore(self):
        self.dashboard.show()
        self.hide()