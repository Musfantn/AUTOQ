# BÁO CÁO PHÂN TÍCH TOÀN BỘ DỰ ÁN AUTOQ (AUTOMATED QUEUE SYSTEM)
> **Đơn vị áp dụng**: Khoa Chẩn đoán Hình ảnh - Bệnh viện Đa khoa Thị xã Kỳ Anh  
> **Ngày cập nhật**: 05/08/2026  
> **Phiên bản**: v4.0 (Tích hợp HIS REST Bridge + Cloud Firestore + TaskView Sync)

---

## 1. TỔNG QUAN DỰ ÁN (PROJECT OVERVIEW)

**AUTOQ** là hệ thống phần mềm quản lý và điều phối hàng đợi thông minh dành riêng cho **Khoa Chẩn đoán Hình ảnh - Bệnh viện Đa khoa Thị xã Kỳ Anh**. Hệ thống giải quyết bài toán tiếp đón, phân luồng bệnh nhân siêu âm, tự động hóa quy trình gọi số, đồng bộ hiển thị màn hình TV lớn tại các phòng khám, và hỗ trợ chuyển đổi linh hoạt sang **Chế độ Phòng Trực** ngoài giờ.

### Các mục tiêu chính:
1. **Tiếp đón & Phân phòng tự động (Kiosk App)**: Cho phép quét mã vạch (Barcode) phiếu chỉ định hoặc tra cứu thông tin bệnh nhân từ **VNPT HIS**, sau đó phân bệnh nhân vào 5 phòng siêu âm với số thứ tự (STT) tự động tăng.
2. **Điều khiển gọi số chuyên nghiệp (Dashboard & Mini Panel)**: Nhân viên y tế tại từng phòng siêu âm điều khiển gọi số ("TIẾP THEO", "GỌI CẤP CỨU", "SET SỐ") với giao diện mượt mà, hỗ trợ Mini Panel nổi trên các phần mềm chuyên môn.
3. **Màn hình hiển thị TV (TV Display)**: Giao diện tràn màn hình (Full HD/4K) hiển thị bệnh nhân đang gọi, danh sách 5 bệnh nhân chờ tiếp theo, thông tin dịch vụ chỉ định, bác sĩ/KTV phụ trách và dòng chữ chạy thông báo (Marquee).
4. **Theo dõi Session tự động (Session Watcher)**: Chạy ngầm dưới khay hệ thống (System Tray), kết nối Chrome Debugging Port (9222) để tự động trích xuất `JSESSIONID`, `SESSIONID`, `uuid` (JWT) từ VNPT HIS và ghi vào file cấu hình `config.yaml` mà không cần người dùng nhập tay.
5. **Chế độ Phòng Trực (Duty Mode)**: Cho phép chuyển màn hình TV phòng siêu âm sang hiển thị tên & SĐT Bác sĩ trực ngoài giờ. Đồng bộ danh sách nhân sự và lịch trực từ hệ thống **TaskView** trên Cloud Firestore.

---

## 2. KIẾN TRÚC HỆ THỐNG (SYSTEM ARCHITECTURE)

```
                                  +---------------------------------------+
                                  |         VNPT HIS REST SERVICE         |
                                  |      (bvhatinh.vncare.vn/vnpthis)     |
                                  +-------------------+-------------------+
                                                      ^
                                                      | HTTP Async Request
                                                      v
+------------------------+      CDP 9222     +-------------------+
|  Google Chrome Debug   | <===============> |  session_watcher  |
| (Đăng nhập VNPT HIS)   |                   | (System Tray App) |
+------------------------+                   +---------+---------+
                                                       |
                                                       | Ghi Cookies & Token
                                                       v
                                             +-------------------+
                                             | his_bridge/       |
                                             |   config.yaml     |
                                             +---------+---------+
                                                       |
                                                       v
+------------------------+   Quét Barcode    +-------------------+      REST API       +-------------------+
| Barcode Scanner (HID)  | ================> |    HIS Bridge     | ==================> | Cloud Firestore   |
+------------------------+                   | (his_bridge/...)  |                     | (Firebase)        |
                                             +---------+---------+                     +---------+---------+
                                                       |                                         ^
                                                       v Push Signal                             |
                                             +-------------------+                               |
                                             |     Kiosk App     | ------------------------------+
                                             |   (kiosk_app.py)  |   push_patient()
                                             +-------------------+
                                                                                                 |
                                                                                                 | Poll / Sync
                                                                                                 v
+------------------------+   Local Config    +-------------------+   Realtime Listener   +-------------------+
|  SQLite (config.db)    | <===============> |    Dashboard      | <=================> | autoq_queues/     |
| - Config key-value     |                   |  (dashboard.py)   |  (on_snapshot ms)   |   room_1 .. 5     |
| - Bảng oncall_doctors  |                   +----+---------+----+                     +---------+---------+
+------------------------+                        |         |                                    |
                                                  |         | Cập nhật Data                      |
                                   Mở Mini Panel  |         v                                    v
                                                  |   +-----------+                    +-------------------+
                                                  +-> | MiniPanel |                    |    TV Display     |
                                                      +-----------+                    |  (tv_display.py)  |
                                                                                       +-------------------+
```

---

## 3. CẤU TRÚC CHI TIẾT CÁC THƯ MỤC VÀ FILE (FILE BREAKDOWN)

### 3.1. Thư mục Gốc (`d:\AUTOQ`)

| Tên File / Thư mục | Kích thước | Vai trò & Chức năng |
|---|---|---|
| `main.py` | 273 B | Entry point khởi chạy ứng dụng chính (khởi tạo `QApplication`, `TVDisplay`, `Dashboard`). |
| `kiosk_app.py` | 19.1 KB | Ứng dụng Kiosk Tiếp đón v4.0. Quét/nhập Mã BN, tra cứu HIS Bridge, phân tích dịch vụ và đẩy bệnh nhân vào các phòng. Tích hợp **System Health Monitor Bar** tự động kiểm tra, khởi tạo và phục hồi ngầm các app phụ trợ (Chrome Debug 9222, Session Watcher, HIS Bridge). |
| `dashboard.py` | 11.4 KB | Cửa sổ điều khiển trung tâm cho Bác sĩ/KTV tại phòng siêu âm. Xử lý các thao tác: Tiếp theo, Gọi cấp cứu, Đặt số (Set), Bật/Tắt chế độ trực. Tích hợp **Firestore Realtime Watcher** (`on_snapshot`) và **Cột hàng đợi bên phải** (3 BN đã thực hiện + 1 BN đang gọi + 3 BN đang chờ). |
| `tv_display.py` | 24.2 KB | Giao diện màn hình TV lớn hiển thị công khai. Tự động phát hiện màn hình phụ (Secondary Screen), hiển thị STT lớn, tên BN, tuổi/năm sinh, dịch vụ, 5 bệnh nhân chờ tiếp theo, chữ chạy Footer và Màn hình trực. |
| `mini_panel.py` | 4.6 KB | Bảng điều khiển thu nhỏ đè lên các phần mềm chuyên môn (PACS, HIS). Cho phép kéo thả trên màn hình, hiển thị đồng hồ realtime, bấm "TIẾP THEO" nhanh. |
| `admin_app.py` | 18.5 KB | Module Quản trị & Báo cáo Realtime (Admin Center). Giám sát Realtime 5 phòng siêu âm (BN đang khám, danh sách chờ, số ca hoàn thành, chế độ trực), tính thời gian khám trung bình/BN, lập báo cáo cuối buổi/cuối ngày, phân tích cơ cấu dịch vụ chỉ định và hỗ trợ xuất file Excel/CSV & Báo cáo Text PDF. |
| `session_watcher.py` | 13.8 KB | Service chạy ngầm dưới khay hệ thống (System Tray). Tự động kết nối WebSocket CDP cổng 9222 của Chrome, bóc tách `JSESSIONID`, `SESSIONID`, `uuid` và ghi vào `his_bridge/config.yaml`. Hiển thị thông báo GlassmorphicHUD. |
| `his_lookup.py` | 5.7 KB | Module tra cứu bệnh nhân dự phòng qua Selenium WebDriver (kết nối Chrome Debug 9222). |
| `config_manager.py` | 1.9 KB | Quản lý cấu hình Key-Value lưu trong cơ sở dữ liệu SQLite local (`database/config.db`). Tự động xác định đường dẫn `%APPDATA%/AUTOQ/database/` khi đóng gói EXE. |
| `settings.py` | 4.2 KB | Cửa sổ cấu hình giao diện (Tên phòng, Số phòng 1-5, Tên Bác sĩ, KTV, Dòng chữ chạy Footer). |
| `oncall_manager.py` | 6.7 KB | Quản lý bảng `oncall_doctors` trong SQLite local. Hỗ trợ CRUD bác sĩ trực và đồng bộ danh sách bác sĩ từ Firestore TaskView. |
| `oncall_setup_window.py` | 11.0 KB | Cửa sổ GUI quản lý danh sách Bác sĩ trực, hỗ trợ nút bấm đồng bộ bất đồng bộ (`SyncWorker`) từ TaskView Firestore. |
| `duty_mode_dialog.py` | 12.2 KB | Popup chọn bác sĩ trực khi kích hoạt Chế độ Phòng Trực. Tự động lấy lịch trực hôm nay từ document `assignments/roster_YYYY-MM` trên Firestore. |
| `firestore_client.py` | 7.5 KB | Module dùng chung cho mọi giao tiếp Firestore REST API HTTP. Chuyển đổi dữ liệu 2 chiều giữa Python types và Firestore JSON (`py_to_firestore`, `doc_to_dict`), xử lý chuẩn hóa tên (`clean_name`, `names_match`) và trích xuất năm sinh (`extract_birth_year`). |
| `firestore_queue.py` | 4.8 KB | API thao tác hàng đợi gọi số phòng siêu âm trên Firestore: `get_room_queue`, `push_patient`, `next_patient`, `toggle_emergency`, `set_number`, `reset_queue`. Tích hợp `FirestoreQueueListenerWorker` (`on_snapshot`) và hỗ trợ tra cứu bệnh nhân chính xác khi Nhảy đến số (SET). |
| `firestore_sync.py` | 4.7 KB | Module đồng bộ dữ liệu nhân sự (`fetch_all_personnel` từ collection `personnel`) và lịch trực tháng (`fetch_today_oncall_from_roster` từ `assignments/roster_YYYY-MM`). |
| `autostart.py` | 377 B | Hàm thêm ứng dụng vào Windows Startup Registry (`Software\Microsoft\Windows\CurrentVersion\Run`). |
| `seed_data.py` | 12.4 KB | Script CLI quản lý data mẫu cho testing (`--dump`, `--reset`, `--seed-only`). |
| `seed_data_firestore.json` | 82.6 KB | File dữ liệu JSON mẫu của Firestore (personnel, rooms, assignments, queues). |

### 3.2. Package Tích hợp REST HIS (`his_bridge/`)

| Tên File | Chức năng chi tiết |
|---|---|
| `his_bridge/__init__.py` | Package export chính cho `HisBridge`, `HisConfig`, `PatientInfo`, `VNPTHisClient`. |
| `his_bridge/bridge.py` | Controller điều phối (Orchestrator). Kết nối `BarcodeListener`, `TTLCache`, `_BridgeWorker`, `VNPTHisClient` và phát tín hiệu PySide6 (`patient_found`, `bridge_error`, `his_connected`). |
| `his_bridge/vnpt_his_client.py` | Async HTTP Client sử dụng `httpx` gọi trực tiếp vào VNPT HIS RestService qua các Stored Procedures (`CLS02C001.SIDS`, `NGT02K016.EV003`, `CLS02C001.DSKQ`). |
| `his_bridge/barcode_listener.py` | Tiếp nhận và validate mã vạch Barcode từ cổng quét USB HID qua Regex. |
| `his_bridge/cache.py` | TTL Cache thread-safe loại bỏ các thao tác quét trùng lặp trong thời gian 5 giây. |
| `his_bridge/firestore_service.py` | Async Publisher hỗ trợ đẩy kết quả trực tiếp lên Firestore với cơ chế Retry và lưu Queue cục bộ (`queue/pending.json`) khi mất mạng. |
| `his_bridge/config.py` | Parser đọc cấu hình từ `his_bridge/config.yaml` và các biến môi trường `HIS_*`. |
| `his_bridge/config.yaml` | File chứa cấu hình kết nối HIS (URL, Hospital ID, Dept ID, Room ID, Cookies & Tokens). |
| `his_bridge/models.py` | Định nghĩa các Pydantic data models: `PatientInfo`, `ServiceInfo`, `HisIdentifiers`. |
| `his_bridge/logger.py` | Hệ thống ghi log chuyên dụng (`logs/his_bridge.log`) với cơ chế xoay file (Rotation 5MB). |
| `his_bridge/main.py` | Giao diện Standalone UI bằng PySide6 để kiểm thử riêng module HIS Bridge. |

---

## 4. LUỒNG DỮ LIỆU CHÍNH (DATA FLOW & WORKFLOWS)

### Luồng 1: Tiếp đón & Phân phòng bệnh nhân (Kiosk App)
1. Bệnh nhân mang phiếu chỉ định đến bàn tiếp đón. Nhân viên quét mã vạch phiếu chỉ định bằng đầu quét Barcode (USB HID).
2. `KioskApp` nhận chuỗi mã vạch (ví dụ: `BN00280291`) và gửi lệnh tra cứu tới `HisBridge`.
3. `HisBridge` kiểm tra `TTLCache` (nếu trùng trong 5s thì trả về ngay). Nếu chưa có:
   - Gọi `VNPTHisClient.search_patient()` -> Gửi POST request tới VNPT HIS RestService (`CLS02C001.SIDS`) lấy `MAUBENHPHAMID`.
   - Chạy song song (`asyncio.gather`):
     - `get_patient_info()` -> Gửi POST (`NGT02K016.EV003`) lấy tên, tuổi, địa chỉ.
     - `get_services()` -> Gửi POST (`CLS02C001.DSKQ`) lấy danh sách các dịch vụ chỉ định.
4. `HisBridge` chuẩn hóa dữ liệu thành `PatientInfo` và phát signal `patient_found` về GUI `KioskApp`.
5. Nhân viên kiểm tra danh sách dịch vụ trên màn hình, tích chọn các dịch vụ cần thiết và bấm nút chọn phòng (**PHÒNG SIÊU ÂM 1 -> 5**).
6. `KioskApp` khởi tạo luồng ngầm gọi `firestore_queue.push_patient(room_num, ...)`.
7. Dữ liệu bệnh nhân được ghi vào document `autoq_queues/room_X` trên Cloud Firestore với STT tự động tăng (ví dụ `004`).

### Luồng 2: Gọi số & Đồng bộ màn hình TV Display (Realtime Stream)
1. Bác sĩ tại phòng siêu âm bấm nút **"TIẾP THEO"**, **"GỌI CẤP CỨU"** hoặc **"NHẢY ĐẾN SỐ (SET)"** trên `Dashboard` / `MiniPanel`.
2. Khi bấm **"NHẢY ĐẾN SỐ (SET)"**, `firestore_queue.set_number(room_num, num)` tự động đọc lại Firestore, tra cứu số thứ tự trên tất cả các phòng để lấy chính xác Hồ sơ bệnh nhân (Họ tên, Tuổi, Năm sinh, Dịch vụ chỉ định) thay vì nhãn tạm.
3. `Dashboard` không cần chạy Timer polling 2s. Luồng ngầm `FirestoreQueueListenerWorker` (`on_snapshot` gRPC stream) lắng nghe trực tiếp document `autoq_queues/room_X` trên Cloud Firestore.
4. Ngay khi dữ liệu Firestore thay đổi, `on_snapshot` callback phát signal `queue_updated` về UI thread trong vài miligiây (ms).
5. `TVDisplay` nhận dữ liệu mới và cập nhật tức thì:
   - Cột trái: Hiển thị STT màu đỏ lớn (260px), Họ tên bệnh nhân (IN HOA), Tuổi/Năm sinh, Danh sách dịch vụ chỉ định.
   - Cột phải: Cập nhật danh sách 5 bệnh nhân chờ tiếp theo vào các card tương ứng.

### Luồng 3: Tự động trích xuất Cookies/Tokens VNPT HIS (`session_watcher.py`)
1. Nhân viên mở Chrome và đăng nhập vào VNPT HIS bình thường.
2. `session_watcher.py` (chạy 5 giây/lần) kết nối tới `http://127.0.0.1:9222/json` qua CDP Websocket.
3. Tìm tab có URL chứa `bvhatinh.vncare.vn`.
4. Thực thi lệnh CDP:
   - `Network.getCookies` -> Trích xuất `JSESSIONID` và `SESSIONID`.
   - `Runtime.evaluate` -> Chạy đoạn script JS quét LocalStorage/SessionStorage lấy chuỗi JWT token (`uuid`).
5. Nếu phát hiện Session thay đổi, tự động cập nhật lại các giá trị này vào file `his_bridge/config.yaml` và hiển thị cửa sổ thông báo nổi (Glassmorphic Notification HUD) nhắc nhở giữ trình duyệt Chrome mở.

### Luồng 4: Bật/Tắt Chế độ Phòng Trực (Duty Mode)
1. Khi đến giờ trực, Bác sĩ bấm nút **"🌙 CHẾ ĐỘ PHÒNG TRỰC"** trên `Dashboard`.
2. `DutyModeDialog` mở ra và chạy worker thread `FetchWorker`:
   - Truy vấn document `assignments/roster_YYYY-MM` trên Firestore để xác định Bác sĩ trực hôm nay theo lịch tháng của TaskView.
   - Đọc danh sách Bác sĩ từ SQLite local (`oncall_doctors`).
   - Tự động chọn (pre-select) Bác sĩ trực hôm nay trong ComboBox và hiển thị SĐT.
3. Bác sĩ bấm **"Xác nhận"**. `Dashboard` tạm ngắt Realtime Listener và gọi `tv.enter_duty_mode(doc_name, doc_phone)`.
4. Màn hình TV Display chuyển sang Page 1 (`StackedWidget` index 1): Hiển thị tiêu đề **"PHÒNG SIÊU ÂM CẤP CỨU"**, Tên Bác sĩ trực (chữ lớn 120px), Số điện thoại liên hệ (120px màu đỏ) và dòng chữ chạy Footer hướng dẫn bệnh nhân cấp cứu bấm chuông/liên hệ SĐT.

---

## 5. CÔNG NGHỆ VÀ THƯ VIỆN SỬ DỤNG (TECH STACK)

- **Ngôn ngữ chính**: Python 3.10+
- **Giao diện người dùng (GUI)**: `PySide6` (Qt cho Python) với các thành phần chính `QMainWindow`, `QWidget`, `QStackedWidget`, `QGraphicsDropShadowEffect`, `QTimer`, `QThread`, `Signal/Slot`.
- **Giao tiếp REST API & Cloud**:
  - `google-cloud-firestore` (`on_snapshot` gRPC Realtime Stream): Lắng nghe sự thay đổi dữ liệu Firestore theo thời gian thực (độ trễ ms).
  - `httpx` & `urllib.request`: Thực hiện HTTP POST/GET tới VNPT HIS RestService và Cloud Firestore REST API.
  - `websocket-client`: Kết nối Chrome DevTools Protocol (CDP) cổng 9222.
- **Cơ sở dữ liệu**:
  - **Cloud Firestore**: Lưu trữ trạng thái hàng đợi theo thời gian thực (`autoq_queues/room_1..5`), thông tin nhân sự (`personnel`), danh sách phòng (`rooms`) và lịch trực tháng (`assignments`).
  - **SQLite 3 (Local)**: Lưu cấu hình phần mềm (`config.db` -> bảng `config`) và danh sách bác sĩ trực cục bộ (`config.db` -> bảng `oncall_doctors`).
- **Mô hình hóa Dữ liệu & Clean Code**: `pydantic`, `pyyaml`, `typing`.
- **Đóng gói & Phân phối**:
  - `PyInstaller`: Đóng gói ứng dụng thành các file thực thi `.exe` standalone trong `dist/`:
    - `dist/RadiologyQueue.exe` (91.5 MB - App Dashboard & TV Display)
    - `dist/KioskQueue.exe` (99.6 MB - App Kiosk Tiếp đón)
    - `dist/AdminQueue.exe` (61.8 MB - App Quản trị & Báo cáo Realtime)
  - `Session Watcher (`session_watcher.py`)`: Tự động kết nối CDP Chrome 9222 trích xuất Session. Tích hợp cờ `--session-watcher` cho phép `KioskQueue.exe` tự kích hoạt Session Watcher ngầm trong môi trường đóng gói PyInstaller EXE mà không phụ thuộc vào Python interpreter ngoài.
  - `Inno Setup 7`: Tạo bộ cài đặt All-In-One tất cả trong một (`setup_aio.iss` -> `installer/AUTOQ_AllInOne_Setup_v4.0.exe` 248 MB). Hỗ trợ chọn kiểu cài đặt phân quyền vai trò (Cài đầy đủ, Máy Kiosk tiếp đón, Máy phòng siêu âm, Máy Quản trị) và tự động cấp quyền người dùng lưu cơ sở dữ liệu/cấu hình tại `%PROGRAMDATA%\AUTOQ\` để triệt tiêu hoàn toàn lỗi Access Denied trên Windows.
  - `Debian Packaging (.deb)`: Tạo gói cài đặt gốc cho môi trường Linux Ubuntu 26.04 / 24.04 LTS (`package_deb.py` -> `installer/autoq-admin_4.0-1_amd64.deb` ~79.8 KB). Tích hợp cấu hình `DEBIAN/control`, script tự động đăng ký ứng dụng `usr/bin/autoq-admin` và cài đặt Shortcut Desktop `usr/share/applications/autoq-admin.desktop`.

---

## 6. ĐÁNH GIÁ ĐIỂM MẠNH & HƯỚNG TỐI ƯU HÓA

### Điểm mạnh:
1. **Kiến trúc REST API trực tiếp**: Việc thay thế Selenium bằng `his_bridge` gọi thẳng vào REST API của VNPT HIS giúp tốc độ tra cứu giảm từ 4-5 giây xuống dưới **0.5 giây**, loại bỏ hoàn toàn các lỗi giật lag hay phụ thuộc vào giao diện web.
2. **Tự động hóa lấy Session thông minh**: Module `session_watcher.py` giải quyết triệt để vấn đề hết hạn Cookie/Token của VNPT HIS mà không phiền người dùng phải F12 copy/paste thủ công.
3. **Đồng bộ Realtime Watcher (gRPC Streaming)**: Thay thế hoàn toàn cơ chế Polling 2s ở Dashboard bằng `doc_ref.on_snapshot()` của `google-cloud-firestore`. Cập nhật dữ liệu hàng đợi xuống màn hình TV tức thì trong vài miligiây (ms) và giảm 100% chi phí đọc API định kỳ.
4. **Hiển thị thông tin chuẩn xác khi Nhảy đến số (SET)**: Hàm `set_number` tự động đọc lại dữ liệu mới nhất từ Firestore và tìm đúng thông tin bệnh nhân (Tên, Tuổi, Năm sinh, Dịch vụ chỉ định) từ danh sách chờ của tất cả các phòng để hiển thị lên màn hình TV.
5. **Tích hợp sâu hệ sinh thái TaskView**: Tự động liên kết danh sách nhân sự và lịch trực từ TaskView Firestore, giúp đơn giản hóa quy trình chuyển chế độ phòng trực ngoài giờ.
6. **Khả năng hoạt động ngoại tuyến (Offline Resiliency)**: Cơ chế Retry và Local Pending Queue (`queue/pending.json`) giúp lưu lại các lượt ghi khi mất mạng và tự động đồng bộ lại khi có kết nối.

