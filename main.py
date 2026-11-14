import os
import sys

# Ẩn dòng log thông báo khởi tạo backend FFmpeg của Qt Multimedia
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg*=false")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from dashboard import Dashboard
from tv_display import TVDisplay

# High DPI scaling configuration
QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)

tv = TVDisplay("PHÒNG SIÊU ÂM 1")
#tv.showFullScreen()

dashboard = Dashboard(tv)
dashboard.show()

sys.exit(app.exec())