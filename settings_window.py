from PySide6.QtWidgets import *
from config_manager import ConfigManager

class SettingsWindow(QWidget):

    def __init__(self):

        super().__init__()

        self.config=ConfigManager()

        self.setWindowTitle("Cấu hình")

        layout=QFormLayout()

        self.room=QLineEdit(
            self.config.get("room","PHÒNG SIÊU ÂM 1")
        )

        self.doctor=QLineEdit(
            self.config.get("doctor","BS: ---")
        )

        self.ktv=QLineEdit(
            self.config.get("ktv","KTV: ---")
        )

        self.footer=QLineEdit(
            self.config.get(
                "footer",
                "Xin vui lòng chuẩn bị giấy tờ trước khi vào khám"
            )
        )

        btn=QPushButton("Lưu")

        btn.clicked.connect(self.save)

        layout.addRow("Phòng:",self.room)
        layout.addRow("Bác sĩ:",self.doctor)
        layout.addRow("KTV:",self.ktv)
        layout.addRow("Footer:",self.footer)

        layout.addWidget(btn)

        self.setLayout(layout)


    def save(self):

        self.config.set("room",self.room.text())
        self.config.set("doctor",self.doctor.text())
        self.config.set("ktv",self.ktv.text())
        self.config.set("footer",self.footer.text())

        QMessageBox.information(self,"OK","Đã lưu")