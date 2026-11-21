# =============================================================================
# FILE: user_guide_dialog.py
# MÔ TẢ: Tài liệu Hướng Dẫn Sử Dụng Nhanh tích hợp trực tiếp trong phần mềm AUTOQ.
#        Chia thành 4 chuyên mục trực quan giúp Bác sĩ, KTV, Điều dưỡng và Admin
#        tra cứu nhanh mọi tính năng của hệ thống ngay tại phòng khám.
# =============================================================================

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTextBrowser
)
from PySide6.QtCore import Qt
from version import APP_VERSION


_COMMON_HTML_STYLE = """
<style>
    body {
        font-family: 'Segoe UI', Arial, sans-serif;
        color: #0f172a;
        background-color: #ffffff;
        line-height: 1.55;
        font-size: 14px;
        margin: 8px;
    }
    h2 {
        color: #0B5FA5;
        border-bottom: 2px solid #bae6fd;
        padding-bottom: 6px;
        margin-top: 6px;
        font-size: 17px;
    }
    h3 {
        color: #0369a1;
        margin-top: 14px;
        margin-bottom: 4px;
        font-size: 15px;
    }
    .box-tip {
        background-color: #f0fdf4;
        border-left: 4px solid #16a34a;
        padding: 10px 12px;
        margin: 10px 0;
        border-radius: 6px;
    }
    .box-warn {
        background-color: #fffbeb;
        border-left: 4px solid #d97706;
        padding: 10px 12px;
        margin: 10px 0;
        border-radius: 6px;
    }
    .badge {
        background-color: #e0f2fe;
        color: #0369a1;
        font-weight: bold;
        padding: 2px 6px;
        border-radius: 4px;
    }
    ul {
        margin-top: 4px;
        padding-left: 22px;
    }
    li {
        margin-bottom: 6px;
    }
</style>
"""

_TAB1_CALLING_HTML = _COMMON_HTML_STYLE + """
<h2>1. Hướng Dẫn Gọi Số Bệnh Nhân & Điều Khiển Màn Hình TV</h2>
<p>Bảng điều khiển chính giúp Bác sĩ và KTV/ĐD điều phối lượt bệnh nhân vào khám nhanh chóng với độ trễ <b>0ms</b> và tự động phát loa thông báo tiếng Việt.</p>

<h3>🔹 Các nút điều khiển gọi số chính</h3>
<ul>
    <li><b>▶ TIẾP THEO (GỌI SỐ MỚI):</b> Tăng số thứ tự lên <b>+1</b> (ví dụ từ <code>005</code> lên <code>006</code>), cập nhật ngay lên màn hình TV của phòng và phát loa: <i>"Đinh đong... Mời bệnh nhân số thứ tự 6 vào phòng..."</i>.</li>
    <li><b>🔊 GỌI LẠI SỐ HIỆN TẠI:</b> Phát loa gọi lại bệnh nhân đang hiển thị trên màn hình (tăng bộ đếm <i>Gọi lần 2, lần 3...</i>) khi bệnh nhân chưa nghe rõ.</li>
    <li><b>⏭ CHƯA VÀO (QUA LƯỢT):</b> Khi gọi nhưng bệnh nhân chưa có mặt:
        <ul>
            <li>Số hiện tại sẽ được tự động chuyển sang cột bên phải <b>"⏳ BỆNH NHÂN CHƯA VÀO PHÒNG (CHỜ GỌI LẠI)"</b>.</li>
            <li>Hệ thống lập tức gọi tiếp số kế tiếp để không làm gián đoạn phòng khám.</li>
        </ul>
    </li>
    <li><b>🎯 Gọi lại bệnh nhân vừa quay lại:</b> Khi bệnh nhân bị qua lượt quay lại phòng, chỉ cần bấm nút <b>"🔊 Gọi lại"</b> ngay cạnh số của bệnh nhân đó ở cột bên phải. Hệ thống sẽ mời bệnh nhân đó vào khám nhưng <b>vẫn giữ nguyên mốc số thứ tự cao nhất</b> (lần bấm <i>TIẾP THEO</i> kế tiếp vẫn tăng tiếp đúng thứ tự, không bị lùi số).</li>
</ul>

<h3>🔹 Các tiện ích hỗ trợ trong ca khám</h3>
<ul>
    <li><b>🔢 NHẢY ĐẾN SỐ / GỌI SỐ BẤT KỲ (SET):</b> Nhập trực tiếp một số thứ tự bất kỳ (ví dụ: <code>025</code>) để nhảy tới số đó. Các lần bấm <i>TIẾP THEO</i> sau đó sẽ đếm tiếp từ <code>026</code>.</li>
    <li><b>🚨 GỌI CẤP CỨU:</b> Chuyển màn hình TV sang trạng thái đỏ <b>"ĐANG CẤP CỨU - VUI LÒNG CHỜ"</b> để bệnh nhân bên ngoài nắm được thông tin. Bấm lại lần nữa để trở về gọi số bình thường.</li>
    <li><b>🗗 MỞ MINI PANEL:</b> Thu nhỏ phần mềm thành một thanh nổi nhỏ gọn luôn nằm trên góc màn hình (có thể kéo thả tới vị trí bất kỳ) để vừa làm việc trên phần mềm HIS/PACS vừa bấm <i>Tiếp theo / Gọi lại / Qua lượt / Chat</i>.</li>
    <li><b>🔄 RESET SỐ VỀ 000:</b> Đặt lại toàn bộ bộ đếm của phòng về <code>000</code> (Hệ thống cũng tự động Reset về <code>000</code> khi bước sang ngày mới).</li>
</ul>
"""

_TAB2_CHAT_HTML = _COMMON_HTML_STYLE + """
<h2>2. Hướng Dẫn Chat Nhanh Nội Bộ Giữa 11 Phòng & Admin</h2>
<p>Tính năng <b>💬 CHAT NỘI BỘ</b> giúp các phòng siêu âm, nội soi, thăm dò chức năng và Admin trao đổi điều phối bệnh nhân tức thì mà không cần rời phòng khám.</p>

<div class="box-tip">
    <b>🔒 Đảm bảo riêng tư y tế:</b> Mọi cửa sổ Chat và thông báo tin nhắn mới <b>chỉ hiển thị trên màn hình máy tính điều khiển của Bác sĩ/KTV</b>, tuyệt đối không bao giờ hiển thị lên màn hình TV gọi số của bệnh nhân.
</div>

<h3>🔹 Cách gửi tin nhắn & Chọn phòng nhận</h3>
<ul>
    <li>Bấm nút <b>"💬 CHAT NỘI BỘ GIỮA CÁC PHÒNG"</b> trên bảng điều khiển (hoặc nút <b>"💬 CHAT"</b> trên thanh Mini Panel).</li>
    <li>Tại mục <b>"Gửi tới:"</b> ở đầu cửa sổ:
        <ul>
            <li>Chọn <b>"📢 Toàn khoa (Tất cả 11 phòng & Admin)"</b> nếu muốn nhắn thông báo chung cho cả khoa.</li>
            <li>Hoặc chọn <b>đích danh 1 phòng cụ thể</b> (menu hiển thị kèm tên Bác sĩ đang phụ trách phòng đó, ví dụ: <i>"🎯 Phòng SA 1 — BS. Nguyễn Việt Phương"</i>).</li>
        </ul>
    </li>
    <li>Tích chọn <b>"🚨 Tin khẩn cấp"</b> nếu cần làm nổi bật tin nhắn màu đỏ khẩn cấp trên màn hình phòng nhận.</li>
</ul>

<h3>🔹 Sử dụng Menu "⚡ Mẫu tin nhắn nhanh ▾" (Gửi 1 chạm)</h3>
<ul>
    <li>Bấm nút <b>"⚡ Mẫu tin nhắn nhanh ▾"</b> nằm ngay bên trái ô nhập chữ ở đáy cửa sổ Chat để sổ danh sách câu nhắn mẫu y tế:
        <ul>
            <li><i>🔄 Phòng đang quá tải, nhờ các phòng hỗ trợ chia bớt BN!</i></li>
            <li><i>🩺 Nhờ BS hội chẩn ca khó tại phòng</i></li>
            <li><i>🚨 Có ca Cấp cứu đang chuyển sang</i></li>
            <li><i>✅ Phòng đã vãn bệnh nhân, có thể nhận thêm ca</i></li>
            <li><i>📄 Nhờ KTV / ĐD hỗ trợ in trả kết quả</i></li>
        </ul>
    </li>
    <li><b>Bấm chọn dòng nào là gửi đi ngay lập tức!</b></li>
    <li>Trong menu sổ ra cũng có dòng <b>"➕ Thêm mẫu tin nhắn nhanh mới..."</b> để mỗi phòng tự tạo thêm câu nhắn riêng và mục <b>"🗑 Xóa mẫu tin tự thêm"</b>.</li>
</ul>

<h3>🔹 Nhận tin nhắn & Trả lời nhanh</h3>
<ul>
    <li>Khi có phòng khác nhắn tới, một <b>Hộp thông báo nổi (Toast)</b> sẽ hiện ở góc dưới bên phải màn hình trong 8 giây kèm nút <b>"↩ Mở Chat & Trả lời ngay"</b>, đồng thời nút Chat trên Dashboard/MiniPanel sẽ báo đỏ số tin chưa đọc <b>(🔴)</b>.</li>
</ul>
"""

_TAB3_SETTINGS_HTML = _COMMON_HTML_STYLE + """
<h2>3. Cấu Hình Phòng, Trạm Loa Trung Tâm & Chế Độ Phòng Trực</h2>

<h3>🔹 Cấu hình Phòng khám, Bác sĩ & KTV phụ máy (Nút "⚙ CẤU HÌNH PHÒNG")</h3>
<ul>
    <li><b>Chọn Phòng Khám:</b> Hỗ trợ đầy đủ <b>11 phòng chuyên môn</b>:
        <ul>
            <li>Phòng Siêu Âm 1, 2, 3, 4, 5</li>
            <li>Phòng Nội Soi Tai Mũi Họng (TMH) & Phòng Nội Soi Tiêu Hóa (NSTH)</li>
            <li>Phòng Điện Tâm Đồ (ĐTĐ), Điện Não Đồ (ĐNĐ), Đo Lưu Huyết Não (LHN), Đo Chức Năng Hô Hấp (CNHH)</li>
        </ul>
    </li>
    <li><b>Chọn Bác sĩ:</b> Chọn từ <b>Menu Dropdown</b> (tự động đồng bộ danh sách Bác sĩ từ hệ thống lịch trực Firestore). Có thể bấm nút <b>"🔄 Đồng bộ"</b> bên cạnh để tải danh sách mới nhất.</li>
    <li><b>Chọn KTV / Điều dưỡng phụ máy:</b> Chọn từ Menu Dropdown hoặc bấm nút <b>"➕ Thêm KTV"</b> để tự gõ thêm tên KTV/ĐD phụ máy mới (được lưu cố định vào máy trạm).</li>
    <li>Khi bấm <b>"LƯU CẤU HÌNH"</b>, tên Bác sĩ phụ trách phòng sẽ hiển thị lên TV và tự động đồng bộ về máy Quản trị Admin.</li>
</ul>

<h3>🔹 Cơ chế Trạm Phát Loa Trung Tâm tại Phòng Siêu Âm 2</h3>
<div class="box-warn">
    <b>📢 Lưu ý vận hành hệ thống loa:</b>
    <ul>
        <li><b>Tại máy Phòng Siêu Âm 2 (Máy cắm dây loa âm ly):</b> Chọn vai trò loa là <i>"📢 Trạm Phát Loa Trung Tâm tại P.Siêu Âm 2 (Đọc cho tất cả 11 phòng)"</i>.</li>
        <li><b>Tại 10 phòng còn lại:</b> Chọn <i>"📡 Gửi tín hiệu phát loa về Phòng Siêu Âm 2 (Tắt loa tại máy này)"</i>. Khi bất kỳ phòng nào bấm gọi số, tín hiệu sẽ truyền tức thì qua mạng LAN và Cloud về Phòng Siêu Âm 2 để xếp hàng phát loa lần lượt, không bao giờ đè tiếng nhau.</li>
    </ul>
</div>

<h3>🔹 Chế độ Phòng Trực ("🌙 CHẾ ĐỘ PHÒNG TRỰC")</h3>
<ul>
    <li>Khi hết giờ hành chính chuyển sang ca trực, bấm nút <b>"🌙 CHẾ ĐỘ PHÒNG TRỰC"</b>.</li>
    <li>Phần mềm tự động tra cứu <b>Bác sĩ trực hôm nay</b> từ bảng Lịch Trực Tháng trên Firestore và chọn sẵn trong danh sách kèm số điện thoại.</li>
    <li>Sau khi bấm <b>"✅ Xác nhận"</b>, màn hình TV sẽ chuyển sang bảng thông báo tên và số điện thoại Bác sĩ trực.</li>
</ul>
"""

_TAB4_ADMIN_UPDATE_HTML = _COMMON_HTML_STYLE + """
<h2>4. Trung Tâm Quản Trị Admin & Cập Nhật Tự Động (Auto-Update)</h2>

<h3>🔹 Trung tâm Quản trị & Thống kê 11 Phòng (AdminQueue.exe)</h3>
<ul>
    <li><b>Đăng nhập bảo mật:</b> Sử dụng mật khẩu quản trị (mặc định: <code>123</code>, có thể đổi mật khẩu qua nút <b>"🔑 Đổi mật khẩu"</b> và lưu đồng bộ trên Cloud Firestore).</li>
    <li><b>🔄 Đồng bộ Nhân sự & Phân phòng:</b> Tự động lấy danh sách Bác sĩ và lịch phân buồng trong ngày từ Firestore để gắn Bác sĩ vào từng phòng (Admin cũng có thể chọn/đổi Bác sĩ trực tiếp trên ô Dropdown <code>👨‍⚕️ BS:</code> của từng thẻ phòng).</li>
    <li><b>Thống kê ca đầu tiên & Lịch Mùa Đông / Mùa Hè:</b>
        <ul>
            <li>Tự động ghi nhận <b>Giờ bắt đầu gọi ca bệnh đầu tiên trong ngày</b> của mỗi phòng.</li>
            <li>Tự động nhận diện khung giờ làm việc <b>Mùa Đông (16/10 – 15/04: Sáng 07:00–11:30, Chiều 13:30–17:00)</b> và <b>Mùa Hè (16/04 – 15/10: Sáng 07:00–11:30, Chiều 14:00–17:30)</b>.</li>
        </ul>
    </li>
    <li><b>📥 XUẤT EXCEL (.XLSX):</b> Xuất báo cáo bảng tính Microsoft Excel chuẩn <code>.xlsx</code>, trong đó <b>tên phòng được thay thế bằng tên Bác sĩ phụ trách phòng</b> kèm số ca đã khám, qua lượt, giờ bắt đầu ca đầu tiên và thời gian khám trung bình.</li>
</ul>

<h3>🔹 Kiểm tra & Tự động Cập nhật Phần mềm (Auto-Update)</h3>
<ul>
    <li><b>Tự động phát hiện bản mới:</b> Mỗi khi mở phần mềm, hệ thống tự kiểm tra phiên bản mới trên Cloud Firestore & GitHub Releases. Nếu có bản mới, nút màu cam <b>"⬆️ ĐÃ CÓ BẢN CẬP NHẬT MỚI — BẤM ĐỂ CẬP NHẬT"</b> sẽ hiện ra.</li>
    <li><b>Kiểm tra thủ công:</b> Vào mục <b>"⚙ CẤU HÌNH PHÒNG"</b> (hoặc thanh tiêu đề Admin) ➔ bấm nút <b>"🔄 Kiểm tra cập nhật"</b>.</li>
    <li><b>Nâng cấp an toàn 100%:</b> Khi bấm <b>"⬆️ TẢI & CẬP NHẬT NGAY"</b>, phần mềm tự tải bộ cài mới, kiểm tra mã toàn vẹn <code>SHA-256</code>, tự đóng bản cũ, cài đè ngầm trong ~5 giây và tự mở lại bản mới (<b>giữ nguyên 100% cấu hình phòng, tên bác sĩ và KTV đã lưu</b>).</li>
</ul>
"""


class UserGuideDialog(QDialog):
    """Hộp thoại Hướng Dẫn Sử Dụng Nhanh tích hợp trong ứng dụng AUTOQ."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"📖 Hướng Dẫn Sử Dụng Nhanh Hệ Thống AUTOQ (v{APP_VERSION})")
        self.setMinimumSize(780, 620)
        self.setStyleSheet("""
            QDialog {
                background-color: #f8fafc;
                color: #0f172a;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QTabWidget::pane {
                border: 1.5px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background: #e2e8f0;
                color: #334155;
                font-size: 13px;
                font-weight: bold;
                padding: 9px 14px;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #0B5FA5;
                color: #ffffff;
            }
            QTextBrowser {
                border: none;
                background-color: #ffffff;
                color: #0f172a;
                padding: 6px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # Header
        header_row = QHBoxLayout()
        lbl_title = QLabel(
            f"📖 CẨM NANG HƯỚNG DẪN SỬ DỤNG NHANH — AUTOQ v{APP_VERSION}"
        )
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0B5FA5;")
        header_row.addWidget(lbl_title, 1)
        root.addLayout(header_row)

        # Tabs
        self.tabs = QTabWidget()

        self.tab_calling = self._create_browser_tab(_TAB1_CALLING_HTML)
        self.tab_chat = self._create_browser_tab(_TAB2_CHAT_HTML)
        self.tab_settings = self._create_browser_tab(_TAB3_SETTINGS_HTML)
        self.tab_admin = self._create_browser_tab(_TAB4_ADMIN_UPDATE_HTML)

        self.tabs.addTab(self.tab_calling, "🔊 1. Gọi Số & TV")
        self.tabs.addTab(self.tab_chat, "💬 2. Chat Nội Bộ 11 Phòng")
        self.tabs.addTab(self.tab_settings, "⚙ 3. Cấu Hình, Loa & Phòng Trực")
        self.tabs.addTab(self.tab_admin, "📊 4. Quản Trị Admin & Cập Nhật")

        root.addWidget(self.tabs, 1)

        # Footer
        footer_row = QHBoxLayout()
        lbl_foot = QLabel("Khoa Chẩn Đoán Hình Ảnh & Thăm Dò Chức Năng — BVĐK Thị Xã Kỳ Anh")
        lbl_foot.setStyleSheet("font-size: 12px; color: #64748b; font-weight: 600;")

        btn_close = QPushButton("Đóng hướng dẫn")
        btn_close.setStyleSheet(
            "QPushButton { background-color: #0B5FA5; color: white; font-size: 13px; "
            "font-weight: bold; padding: 8px 20px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background-color: #0369a1; }"
        )
        btn_close.clicked.connect(self.accept)

        footer_row.addWidget(lbl_foot, 1)
        footer_row.addWidget(btn_close)
        root.addLayout(footer_row)

    @staticmethod
    def _create_browser_tab(html_content: str) -> QTextBrowser:
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(html_content)
        return browser
