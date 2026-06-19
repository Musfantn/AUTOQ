import sys
from PySide6.QtWidgets import QApplication
from dashboard import Dashboard
from tv_display import TVDisplay

app = QApplication(sys.argv)

tv = TVDisplay("PHÒNG SIÊU ÂM 1")
#tv.showFullScreen()

dashboard = Dashboard(tv)
dashboard.show()

sys.exit(app.exec())