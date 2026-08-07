# HIS Bridge — VNPT HIS RestService Integration

Module Python tích hợp trực tiếp với VNPT HIS RestService để lấy thông tin bệnh nhân cho hệ thống gọi số Khoa Chẩn đoán Hình ảnh.

**Không sử dụng**: Selenium, Playwright, OCR, HTML parsing.  
**Giao tiếp trực tiếp**: REST API (POST requests) giống trình duyệt.

## Cài đặt

```bash
cd D:\AUTOQ
pip install -r his_bridge/requirements.txt
```

## Cấu hình

### 1. Chỉnh sửa `his_bridge/config.yaml`

```yaml
his:
  base_url: "https://bvhatinh.vncare.vn/vnpthis/RestService"
  hospital_id: "42"
  department_id: "26060"
  room_id: "77846"
  database_name: "HIS_DATA_HTH_KYANH"
  session:
    jsessionid: "PASTE_TỪ_TRÌNH_DUYỆT"
    uuid_jwt: "PASTE_TỪ_TRÌNH_DUYỆT"
```

### 2. Tự động lấy Session bằng Session Watcher (Khuyên dùng)

Hệ thống có kèm một công cụ chạy ngầm để **tự động lấy Cookies & Token** mỗi khi bạn đăng nhập VNPT HIS trên Chrome:

```bash
cd D:\AUTOQ
python session_watcher.py
```

*   **Tính năng:**
    *   Tự động mở Chrome ở cổng Debug 9222.
    *   Theo dõi và tự động trích xuất `JSESSIONID`, `SESSIONID`, và `uuid` (JWT token) ngay khi bạn đăng nhập thành công.
    *   Cập nhật trực tiếp vào file `his_bridge/config.yaml` mà không làm mất comment.
    *   Hiển thị một cửa sổ thông báo (Custom HUD UI) nhắc nhở: **"Đăng nhập thành công! Vui lòng không đóng cửa sổ Chrome này để tránh lỗi."**
    *   Chạy ẩn dưới System Tray (khay hệ thống) vô cùng nhẹ nhàng.

### 3. Lấy Session Cookie thủ công (Nếu không dùng Session Watcher)

1. Mở Chrome → Đăng nhập VNPT HIS bình thường
2. Nhấn **F12** → Tab **Network**
3. Thực hiện một thao tác bất kỳ (ví dụ tìm bệnh nhân)
4. Chọn request `RestService` trong danh sách
5. Tab **Headers** → Mục **Cookie**:
   - Copy giá trị `JSESSIONID=xxx` → paste vào `config.yaml`
   - Copy giá trị `SESSIONID=xxx` → paste vào `config.yaml`
   - Copy giá trị `uuid=xxx` (nếu có) → paste vào `config.yaml`

> **Lưu ý**: Session có thể hết hạn. Khi bridge báo lỗi "Session hết hạn", lặp lại bước trên hoặc chạy `session_watcher.py` để tự động hóa.

### 3. Override bằng biến môi trường (tùy chọn)

```bash
set HIS_BASE_URL=https://bvhatinh.vncare.vn/vnpthis/RestService
set HIS_JSESSIONID=abc123
set HIS_UUID_JWT=def456
set FIREBASE_API_KEY=AIzaSy...
```

## Chạy standalone

```bash
cd D:\AUTOQ
python -m his_bridge.main
```

Giao diện sẽ mở với:
- Textbox quét barcode
- Hiển thị tên, tuổi, dịch vụ
- Trạng thái kết nối HIS / Firestore

## Tích hợp vào Kiosk App

`kiosk_app.py` đã được refactor để sử dụng HIS Bridge thay vì Selenium:

```python
from his_bridge.bridge import HisBridge
from his_bridge.config import HisConfig

config = HisConfig.load()
bridge = HisBridge(config)
bridge.patient_found.connect(self.on_patient_found)
bridge.start()

# Khi quét barcode:
bridge.lookup("BN00280291")
```

## Kiến trúc module

```
his_bridge/
├── __init__.py              # Package exports
├── config.py                # HisConfig — đọc config.yaml
├── config.yaml              # Cấu hình (KHÔNG hardcode)
├── models.py                # Pydantic models
├── vnpt_his_client.py       # Async HTTP client → HIS RestService
├── firestore_service.py     # Async Firestore publisher + local queue
├── barcode_listener.py      # Signal-based barcode receiver
├── bridge.py                # Orchestrator — kết nối tất cả
├── cache.py                 # TTL cache (tránh gọi trùng 5s)
├── logger.py                # Structured logging
├── main.py                  # Standalone UI (PySide6)
├── requirements.txt         # Dependencies
├── queue/                   # Local queue fallback (auto-created)
│   └── pending.json
├── tests/
│   ├── test_models.py
│   ├── test_cache.py
│   └── test_vnpt_client.py
└── architecture.md          # Tài liệu kiến trúc + diagrams
```

## Luồng xử lý

1. **Barcode received** → BarcodeListener validate
2. **Cache check** → Nếu trùng trong 5s → trả cache
3. **Search patient** → POST `ajaxExecuteQueryPaging` (SP: CLS02C001.SIDS)
4. **Concurrent calls** → `asyncio.gather()`:
   - `get_patient_info` (SP: NGT02K016.EV003)
   - `get_services` (SP: CLS02C001.DSKQ)
5. **Normalize** → PatientInfo model
6. **Emit signal** → Kiosk app hiển thị kết quả

## Chạy tests

```bash
cd D:\AUTOQ
python -m pytest his_bridge/tests/ -v
```

## Lưu ý quan trọng

- Bridge **chỉ tra cứu và push signal** — không tự đẩy vào room queue
- Kiosk app vẫn sử dụng `firestore_queue.push_patient()` để đẩy vào phòng
- Nếu HIS thay đổi SP hoặc tham số → chỉ cần sửa `config.yaml`
- Log ghi tại `logs/his_bridge.log` (rotation 5MB × 3 backup)
