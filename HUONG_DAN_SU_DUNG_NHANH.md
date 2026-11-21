# 📖 HƯỚNG DẪN SỬ DỤNG NHANH HỆ THỐNG GỌI SỐ & ĐIỀU PHỐI AUTOQ (v7.1.0)
**Khoa Chẩn Đoán Hình Ảnh & Thăm Dò Chức Năng — BVĐK Thị Xã Kỳ Anh**

---

## 1. Gọi Số Bệnh Nhân & Điều Khiển Màn Hình TV (11 Phòng)

- **▶ TIẾP THEO (GỌI SỐ MỚI):** Tăng số thứ tự lên `+1` (ví dụ `005` ➔ `006`), cập nhật tức thì (`0ms`) lên màn hình TV của phòng và phát loa: *"Đinh đong... Mời bệnh nhân số thứ tự 6 vào phòng..."*.
- **🔊 GỌI LẠI SỐ HIỆN TẠI:** Phát loa nhắc lại số đang hiển thị trên màn hình (tăng bộ đếm *Gọi lần 2, lần 3...*).
- **⏭ CHƯA VÀO (QUA LƯỢT):** Khi gọi nhưng bệnh nhân chưa có mặt:
  - Số hiện tại được chuyển sang cột bên phải **"⏳ BỆNH NHÂN CHƯA VÀO PHÒNG (CHỜ GỌI LẠI)"**.
  - Hệ thống tự động nhảy sang gọi số kế tiếp để không làm gián đoạn phòng khám.
- **🎯 Gọi lại bệnh nhân vừa quay lại:** Bấm nút **"🔊 Gọi lại"** ngay cạnh số của bệnh nhân đó ở cột bên phải. Hệ thống sẽ mời bệnh nhân đó vào khám nhưng **vẫn giữ nguyên mốc số thứ tự cao nhất** (lần bấm *TIẾP THEO* kế tiếp vẫn tăng tiếp đúng tiến độ).
- **🔢 NHẢY ĐẾN SỐ (SET):** Nhập số thứ tự bất kỳ để bắt đầu gọi từ số đó.
- **🚨 GỌI CẤP CỨU:** Chuyển màn hình TV sang trạng thái ưu tiên cấp cứu màu đỏ.
- **🗗 MỞ MINI PANEL:** Thu nhỏ phần mềm thành thanh công cụ nổi luôn nằm trên màn hình để vừa làm việc trên HIS/PACS vừa bấm gọi số hoặc mở Chat.

---

## 2. Chat Nhanh Nội Bộ Giữa 11 Phòng Khám & Admin

> **Lưu ý riêng tư:** Cửa sổ Chat và thông báo tin nhắn mới chỉ hiển thị trên màn hình máy tính điều khiển của Bác sĩ/KTV, **tuyệt đối không hiển thị lên màn hình TV của bệnh nhân**.

- **Mở cửa sổ Chat:** Bấm nút **"💬 CHAT NỘI BỘ"** trên bảng điều khiển hoặc nút **"💬 CHAT"** trên thanh Mini Panel.
- **Chọn nơi nhận (`Gửi tới:`):**
  - Chọn **`📢 Toàn khoa (Tất cả 11 phòng & Admin)`** để nhắn thông báo chung.
  - Chọn **`🎯 Tên Phòng — Tên Bác sĩ phụ trách`** để nhắn riêng cho một phòng cụ thể.
- **Menu sổ ra `⚡ Mẫu tin nhắn nhanh ▾` (Gửi 1 chạm):**
  - Bấm nút **`⚡ Mẫu tin nhắn nhanh ▾`** ở cạnh trái ô nhập tin nhắn để mở danh sách các câu nhắn y tế thông dụng (*Quá tải nhờ chia bớt BN, Nhờ hội chẩn ca khó, Có ca cấp cứu chuyển sang, Đã vãn BN, Nhờ hỗ trợ in kết quả*).
  - Bấm chọn mẫu nào là gửi đi ngay lập tức!
  - Có thể bấm **`➕ Thêm mẫu tin nhắn nhanh mới...`** hoặc **`🗑 Xóa mẫu tin tự thêm`** ngay trong menu này.

---

## 3. Cấu Hình Phòng, Trạm Loa Trung Tâm (Phòng 2) & Chế Độ Phòng Trực

- **⚙ CẤU HÌNH PHÒNG:**
  - **Chọn Phòng Khám:** Gồm 11 phòng (*Siêu âm 1..5, Nội soi TMH, Nội soi Tiêu hóa, Điện tâm đồ, Điện não đồ, Lưu huyết não, Đo chức năng hô hấp*).
  - **Bác sĩ:** Chọn từ **Menu Dropdown** đồng bộ trực tiếp với danh sách nhân sự trên Firestore (nút **`🔄 Đồng bộ`**).
  - **KTV / ĐD:** Chọn từ Menu Dropdown hoặc bấm **`➕ Thêm KTV`** để tự gõ thêm tên KTV/ĐD phụ máy mới vào danh sách.
- **📢 Trạm Phát Loa Trung Tâm (Phòng Siêu Âm 2):**
  - Máy Phòng Siêu Âm 2 (cắm loa âm ly) để chế độ: *`📢 Trạm Phát Loa Trung Tâm tại P.Siêu Âm 2 (Đọc cho tất cả 11 phòng)`*.
  - 10 phòng còn lại để chế độ: *`📡 Gửi tín hiệu phát loa về Phòng Siêu Âm 2`*.
- **🌙 CHẾ ĐỘ PHÒNG TRỰC:** Tự động tra cứu Bác sĩ trực hôm nay từ Lịch Trực Tháng trên Firestore và hiển thị tên + số điện thoại Bác sĩ trực lên màn hình TV.

---

## 4. Trung Tâm Quản Trị Admin & Cập Nhật Tự Động (Auto-Update)

- **Admin Center (`AdminQueue.exe`):**
  - Mật khẩu mặc định: `123` (đổi mật khẩu và lưu lên Cloud Firestore qua nút **`🔑 Đổi mật khẩu`**).
  - **🔄 Đồng bộ Nhân sự & Phân phòng:** Tự động gắn Bác sĩ phụ trách vào từng phòng từ lịch phân công Firestore (hoặc chọn trực tiếp trên thẻ phòng).
  - **Thống kê & Xuất Báo cáo Excel (`.xlsx`):** Tự động thống kê giờ bắt đầu ca đầu tiên trong ngày, lọc theo lịch làm việc Mùa Đông (`16/10–15/04`) / Mùa Hè (`16/04–15/10`), và xuất file Excel `.xlsx` thay tên phòng bằng tên **Bác sĩ phụ trách phòng**.
- **Tự động Cập nhật Phần mềm (`Auto-Update`):**
  - Tự động thông báo khi có bản mới trên Server hoặc kiểm tra thủ công qua nút **`🔄 Kiểm tra cập nhật`** trong *Cấu hình phòng*.
  - Tự động tải bộ cài từ GitHub Releases CDN, kiểm tra mã `SHA-256`, cài đè ngầm và mở lại phần mềm mà **không mất cấu hình phòng đã lưu**.
