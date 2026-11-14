# =============================================================================
# AUTOQ (AUTOMATED QUEUE SYSTEM) — MASTER ARCHITECTURAL SPECIFICATION
# =============================================================================
> **Đơn vị triển khai**: Khoa Chẩn đoán Hình ảnh — Bệnh viện Đa khoa Thị xã Kỳ Anh, Hà Tĩnh  
> **Tác giả / Thiết kế hệ thống**: BS. Nguyễn Việt Phương  
> **Phiên bản hệ thống**: v5.1 (Gọi số đơn giản theo phòng + Trạm Phát Loa Trung Tâm tại Phòng Siêu Âm 2 + Loa TTS Tiếng Việt Đa Tầng Online/Offline + Hỗ trợ Gọi lại & Qua lượt + Admin Giám sát Realtime)  
> **Mục đích tài liệu**: Cung cấp toàn bộ ngữ cảnh kỹ thuật, kiến trúc mã nguồn, luồng dữ liệu, schema cơ sở dữ liệu và quy ước vận hành cho hệ thống AUTOQ.

---

## 1. TỔNG QUAN HỆ THỐNG (SYSTEM OVERVIEW & OBJECTIVES)

**AUTOQ v5.1** là hệ thống phần mềm chuyên dụng điều phối gọi số thứ tự tự động, điều phối loa phát thanh trung tâm Tiếng Việt và giám sát tải lượng bệnh nhân tại **Khoa Chẩn đoán Hình ảnh - BVĐK Thị xã Kỳ Anh**:
1. **Gọi số đơn giản trực tiếp tại từng phòng (Room-Autonomous Number Queue — 11 Phòng Khám, Nội Soi & Thăm dò Chức năng)**:
   - Hỗ trợ đầy đủ **11 phòng**: **Phòng Siêu Âm 1..5**, **Phòng Nội Soi Tai Mũi Họng (TMH)**, **Phòng Nội Soi Tiêu Hóa (NSTH)**, **Phòng Điện Tâm Đồ (ĐTĐ)**, **Phòng Điện Não Đồ (ĐNĐ)**, **Phòng Đo Lưu Huyết Não (LHN)** và **Phòng Đo Chức Năng Hô Hấp (CNHH)**.
   - Bác sĩ / KTV tại từng phòng chủ động gọi bệnh nhân bằng số thứ tự tăng dần (`TIẾP THEO`), nhảy đến số bất kỳ (`NHẢY ĐẾN SỐ (SET)`), hoặc bật chế độ `GỌI CẤP CỨU` mà không phụ thuộc vào việc quét mã vạch hay đẩy tên từ quầy Kiosk.
2. **Trạm Phát Loa Trung Tâm tại Phòng Siêu Âm 2 (`speaker_hub.py`)**:
   - Loa phát thanh sảnh chờ được cắm trực tiếp vào máy trạm của Bác sĩ tại **Phòng Siêu Âm 2** (chế độ mặc định `hub`).
   - Các máy trạm tại **10 phòng còn lại** (Siêu âm 1, 3, 4, 5, Nội soi TMH, Nội soi Tiêu hóa, Điện tâm đồ, Điện não đồ, Lưu huyết não, Chức năng hô hấp — chế độ mặc định `client`) khi bấm gọi số hoặc gọi lại sẽ đẩy tín hiệu tức thì về máy Phòng Siêu Âm 2 thông qua **Cơ chế Kép (Dual-Channel)**:
     - **Kênh 1 — LAN UDP Broadcast (Cổng `50505`)**: Truyền gói tin nội bộ `< 2ms`, giúp loa Phòng 2 phát ngay lập tức và hoạt động cả khi mất Internet.
     - **Kênh 2 — Cloud Firestore Multi-Room Listener (`autoq_queues/room_*`)**: Dự phòng xuyên VLAN/Subnet (lấy trọn bộ 11 phòng chỉ bằng 1 HTTP GET), tự động khử trùng lặp (`Deduplicator`) và chống đọc hàng loạt khi mới bật máy (`Cold-Start Suppression`).
   - **Hàng đợi Đọc Loa Đa Phòng Tuần Tự (`FIFO Multi-Room Queue`)**: Khi nhiều phòng bấm gọi cùng lúc, máy Phòng 2 tự động xếp hàng đọc lần lượt từng phòng mà không cắt ngang câu đang đọc; nếu cùng một phòng bấm liên tiếp khi đang chờ tới lượt thì tự động gộp (`Coalescing`) lấy số mới nhất của phòng đó.
3. **Hệ thống Đọc Loa TTS Tiếng Việt Tự Nhiên & Dự Phòng Khi Mất Mạng (`tts_service.py`)**:
   - Tự động phát nhạc hiệu *"Ding-Dong"* (`assets/dingdong.wav`) và đọc câu mời chuẩn cho từng phòng (VD: **"Mời bệnh nhân số thứ tự 24 vào phòng siêu âm 1"**, **"Mời bệnh nhân số thứ tự 12 vào phòng nội soi tai mũi họng"**, **"Mời bệnh nhân số thứ tự 8 vào phòng điện tâm đồ"**...).
   - **Kiến trúc Đa Tầng (5-Tier TTS Engine) + Pre-fetching 3 số kế tiếp**:
     - *Tầng 1 (Local Audio Cache + Pre-fetch)*: Lưu cache MP3 vĩnh viễn tại `%PROGRAMDATA%\AUTOQ\database\tts_cache` và tự động tải ngầm trước 3 số tiếp theo, giúp phát lại tức thì (0ms latency).
     - *Tầng 2 (Google Translate TTS Vietnamese)*: Giọng đọc nữ Tiếng Việt tự nhiên mặc định, phản hồi cực nhanh (~0.3s).
     - *Tầng 3 (Microsoft Edge Neural TTS - `vi-VN-HoaiMyNeural`)*: Giọng AI Neural dự phòng chất lượng cao.
     - *Tầng 4 (Offline Vietnamese Voice Pack - `assets/tts_offline/`)*: Bộ 28 file âm thanh từ vựng tiếng Việt đóng gói sẵn trong ứng dụng, tự động ghép nối số thứ tự (1..999) và tên cả 10 phòng khám để đọc giọng Tiếng Việt tự nhiên **100% không cần Internet**.
     - *Tầng 5 (Qt `QTextToSpeech` / Windows SAPI5)*: Dự phòng hệ điều hành cuối cùng.
3. **Hỗ trợ Gọi Lại & Quản lý Bệnh nhân Chưa Vào Phòng (`recall_current`, `skip_and_next`, `recall_specific`)**:
   - **Nút `🔊 GỌI LẠI`**: Phát loa đọc lại số hiện tại, tăng bộ đếm số lần gọi (`Gọi lần 2, 3...`) và kích hoạt hiệu ứng nhấp nháy đỏ-trắng trên màn hình TV để thu hút sự chú ý.
   - **Nút `⏭ CHƯA VÀO (QUA LƯỢT)`**: Khi bệnh nhân vắng mặt tạm thời, lưu số hiện tại vào danh sách **"Bệnh nhân chưa vào phòng (Chờ gọi lại)"** đồng thời tự động gọi số tiếp theo.
   - **Gọi lại 1-Click từ Danh sách Chưa vào hoặc Lịch sử vừa gọi**: Bác sĩ có thể bấm `🔊 Gọi lại` bất kỳ số cũ nào khi bệnh nhân quay lại mà vẫn **bảo toàn mốc số cao nhất (`last_number`)** của phòng để lượt `TIẾP THEO` không bị lùi số.
4. **Màn hình hiển thị TV công khai (`tv_display.py`)**: Tự động nhận diện và hiển thị Fullscreen trên màn hình phụ (TV HDMI). Cột trái hiển thị số thứ tự cực lớn (280px) có nhấp nháy khi gọi; Cột phải hiển thị 3 số chuẩn bị tiếp theo và danh sách các số qua lượt chưa vào phòng.
5. **Chế độ Phòng Trực Ngoài Giờ (`duty_mode_dialog.py`)**: Chuyển màn hình TV sang chế độ trực cấp cứu ngoài giờ, đồng bộ lịch trực bác sĩ từ hệ sinh thái **TaskView** trên Cloud Firestore.
6. **Trung tâm Quản trị & Kiểm soát Lượng Bệnh nhân (`admin_app.py`)**:
   - **Bảo mật Đăng nhập Admin (`AdminLoginDialog` & `AdminChangePasswordDialog`)**: Yêu cầu mật khẩu khi mở ứng dụng (mật khẩu mặc định: `123`), hỗ trợ đổi mật khẩu trực tiếp trong ứng dụng và đồng bộ lên Cloud Firestore (`autoq_queues/admin_auth`).
   - **Theo dõi thời gian thực 11 phòng**: Hiển thị thanh tỷ trọng tải lượng bệnh nhân giữa các phòng, **thời gian bắt đầu làm ca bệnh đầu tiên trong ngày (`Ca đầu tiên`)** của từng phòng, số ca đã khám, số ca qua lượt và thời gian thực hiện trung bình.
   - **Linh động Lịch làm việc Mùa Đông / Mùa Hè**: Tự động nhận diện **Mùa Đông (`16/10 – 15/04` hàng năm: Sáng `07:00 - 11:30`, Chiều `13:30 - 17:00`)** và **Mùa Hè (`16/04 – 15/10` hàng năm: Sáng `07:00 - 11:30`, Chiều `14:00 - 17:30`)** để áp dụng khung giờ lọc chính xác đến từng phút khi thống kê và xuất báo cáo Excel/CSV/TXT.

---

## 2. SƠ ĐỒ KIẾN TRÚC HỆ THỐNG (SYSTEM ARCHITECTURE)

```
+------------------------+   Local SQLite    +---------------------------+   Realtime Listener / REST   +-----------------------+
|  SQLite (config.db)    | <===============> |         Dashboard         | <==========================> |    Cloud Firestore    |
| - config (key-value)   |   (config_mgr)    |      (dashboard.py)       |   + Local JSON Queue Cache   | (autoq_queues/room_*) |
| - oncall_doctors       |                   +-----+-------+-------+-----+                              +-----------+-----------+
+------------------------+                         |       |       |                                                |
                                    Mở Mini Panel  |       |       | Phát âm thanh gọi số                           | Polling 3s
                                                   v       |       v                                                v
                                             +-----------+ | +--------------+                           +-----------------------+
                                             | MiniPanel | | |  TTSService  |                           |      Admin Center     |
                                             +-----------+ | |(tts_service) |                           |    (admin_app.py)     |
                                                           | +--------------+                           +-----------------------+
                                                           |  - Tầng 1: Cache MP3
                                                           |  - Tầng 2: Google TTS (vi)
                                                           |  - Tầng 3: Edge Neural TTS
                                                           |  - Tầng 4: Offline Voice Pack (assets/tts_offline)
                                                           v
                                             +---------------------------+
                                             |        TV Display         |
                                             |      (tv_display.py)      |
                                             +---------------------------+
```

---

## 3. BẢN ĐỒ THƯ MỤC VÀ VAI TRÒ TỪNG MODULE (CODEBASE MAP)

```
D:\AUTOQ/
├── admin_app.py            # [GUI] Trung tâm Quản trị, Kiểm soát lượng bệnh nhân 5 phòng & Báo cáo
├── autostart.py            # [Util] Quản lý tự khởi động cùng Windows (Registry Run key)
├── config_manager.py       # [Data] Quản lý cấu hình Key-Value lưu trong SQLite local (config.db)
├── dashboard.py            # [GUI] Bàn điều khiển gọi số, gọi lại, qua lượt & loa TTS của Bác sĩ
├── duty_mode_dialog.py     # [GUI] Hộp thoại kích hoạt Chế độ trực ngoài giờ & chọn BS trực
├── firestore_client.py     # [Cloud] HTTP Client giao tiếp Cloud Firestore REST API & Data mappers
├── firestore_queue.py      # [Cloud+Offline] Nghiệp vụ gọi số tự động, gọi lại, qua lượt & Offline Cache
├── firestore_sync.py       # [Cloud] Đồng bộ nhân sự & lịch trực từ TaskView Firestore
├── main.py                 # [Entry] Điểm khởi động ứng dụng gọi số phòng khám (Dashboard + TV)
├── mini_panel.py           # [GUI] Bảng điều khiển thu nhỏ nổi (Tiếp theo, Gọi lại, Chưa vào, Phóng to)
├── oncall_manager.py       # [Data] Quản lý danh sách bác sĩ trực lưu SQLite local & Sync TaskView
├── oncall_setup_window.py  # [GUI] Cửa sổ thiết lập danh sách bác sĩ trực
├── settings.py             # [GUI] Cửa sổ cấu hình phòng khám, BS, KTV, Chế độ Loa (Hub/Client/Local) & Âm lượng
├── setup_aio.iss           # [Build] Script Inno Setup tạo bộ cài All-In-One Setup v5.1 EXE
├── speaker_hub.py          # [Hub] Điều phối Loa Trung Tâm tại Phòng 2 (UDP LAN Broadcast 50505 + Firestore Multi-Room)
├── tts_service.py          # [Audio] Hệ thống đọc loa TTS Tiếng Việt Đa Tầng + Hàng đợi FIFO Đa Phòng + Offline Backup
├── tv_display.py           # [GUI] Màn hình TV lớn hiển thị số đang gọi, số chuẩn bị & số qua lượt
├── assets/                 # Thư mục tài nguyên
│   ├── logo.png            # Logo bệnh viện
│   ├── dingdong.wav        # Nhạc hiệu chuông báo Ding-Dong WAV chuẩn trước khi phát giọng đọc
│   └── tts_offline/        # Bộ 23 file MP3 từ vựng Tiếng Việt phục vụ đọc loa khi mất mạng
└── database/               # Thư mục lưu database SQLite cục bộ (config.db) & tts_cache/
```

---

## 4. CẤU TRÚC DỮ LIỆU HÀNG ĐỢI TRÊN FIRESTORE (`autoq_queues/room_{1..5}`)

```json
{
  "room": "1",
  "date": "2026-11-09",
  "last_number": 24,
  "is_duty_mode": false,
  "duty_doctor": "",
  "duty_phone": "",
  "current_calling": {
    "stt": "024",
    "timestamp": 1787580000.0,
    "called_at": 1787580120.0,
    "recalled_at": 1787580150.0,
    "call_count": 2,
    "is_recall": true
  },
  "missed_list": [
    {
      "stt": "021",
      "timestamp": 1787579500.0,
      "called_at": 1787579500.0,
      "skipped_at": 1787579620.0,
      "call_count": 2
    }
  ],
  "history": [
    {
      "stt": "023",
      "timestamp": 1787579800.0,
      "called_at": 1787579800.0,
      "completed_at": 1787580120.0,
      "exam_duration_sec": 320,
      "call_count": 1
    }
  ]
}
```
