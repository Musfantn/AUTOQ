# HIS Bridge — Kiến trúc Module

## Tổng quan

HIS Bridge là module trung gian giữa Kiosk App và VNPT HIS RestService.
Thay thế hoàn toàn Selenium bằng giao tiếp REST API trực tiếp.

```mermaid
graph TB
    subgraph "Kiosk App (PySide6)"
        SCAN["Barcode Scanner<br/>USB HID + Enter"]
        KIOSK_UI["KioskApp UI<br/>Hiển thị BN + Nút phòng"]
    end

    subgraph "HIS Bridge Module"
        BL["BarcodeListener<br/>Validate + Signal"]
        CACHE["TTLCache<br/>5s dedup"]
        BRIDGE["HisBridge<br/>Orchestrator"]
        CLIENT["VNPTHisClient<br/>httpx.AsyncClient"]
        FS_PUB["FirestorePublisher<br/>Retry + Local Queue"]
        LOG["Logger<br/>his_bridge.log"]
    end

    subgraph "Session Watcher Service"
        SW["session_watcher.py<br/>Tray App + CDP websocket"]
        CFG["config.yaml<br/>YAML config file"]
    end

    subgraph "External Services"
        HIS["VNPT HIS RestService<br/>bvhatinh.vncare.vn"]
        FIRESTORE["Cloud Firestore<br/>autoq_queues/*"]
        CHROME["Google Chrome<br/>Debugging Port 9222"]
    end

    SCAN --> BL
    BL --> BRIDGE
    BRIDGE --> CACHE
    BRIDGE --> CLIENT
    CLIENT --> HIS
    BRIDGE --> FS_PUB
    FS_PUB --> FIRESTORE
    BRIDGE --> LOG
    BRIDGE -.->|patient_found signal| KIOSK_UI
    KIOSK_UI -->|push_patient()| FIRESTORE
    
    CHROME -->|CDP read session/cookies| SW
    SW -->|Auto update credentials| CFG
    CFG -->|Read config| BRIDGE
```

## Sequence Diagram — Luồng tra cứu bệnh nhân

```mermaid
sequenceDiagram
    participant Scanner as Barcode Scanner
    participant Kiosk as KioskApp
    participant Listener as BarcodeListener
    participant Bridge as HisBridge
    participant Cache as TTLCache
    participant Worker as _BridgeWorker
    participant Client as VNPTHisClient
    participant HIS as VNPT HIS RestService
    participant Models as PatientInfo

    Scanner->>Kiosk: Quét barcode "BN00280291" + Enter
    Kiosk->>Listener: receive("BN00280291")
    Listener->>Listener: validate(regex)
    Listener->>Bridge: barcode_received signal

    Bridge->>Worker: submit_barcode("BN00280291")

    Worker->>Cache: get("BN00280291")
    Cache-->>Worker: None (cache miss)

    Note over Worker,HIS: Bước 2: Search Patient
    Worker->>Client: search_patient("BN00280291")
    Client->>HIS: POST ajaxExecuteQueryPaging<br/>SP: CLS02C001.SIDS
    HIS-->>Client: {MAUBENHPHAMID: "15757827", ...}
    Client-->>Worker: search_result

    Note over Worker,HIS: Bước 3 & 4: Concurrent Calls
    par asyncio.gather()
        Worker->>Client: get_patient_info("15757827")
        Client->>HIS: POST ajaxCALL_SP_O<br/>SP: NGT02K016.EV003
        HIS-->>Client: {TENBENHNHAN, TUOI, DIACHI, ...}
    and
        Worker->>Client: get_services(params)
        Client->>HIS: POST ajaxCALL_SP_O<br/>SP: CLS02C001.DSKQ
        HIS-->>Client: [{MADICHVU, TENDICHVU, ...}]
    end

    Worker->>Models: normalize → PatientInfo
    Worker->>Cache: set("BN00280291", patient)
    Worker->>Kiosk: patient_found signal(PatientInfo)

    Kiosk->>Kiosk: Hiển thị tên, tuổi, dịch vụ
    Note over Kiosk: Người tiếp đón bấm nút phòng
    Kiosk->>HIS: firestore_queue.push_patient()
```

## Sequence Diagram — Cache Hit (quét trùng trong 5 giây)

```mermaid
sequenceDiagram
    participant Scanner as Barcode Scanner
    participant Bridge as HisBridge
    participant Cache as TTLCache
    participant Kiosk as KioskApp

    Scanner->>Bridge: "BN00280291" (lần 2 trong 5s)
    Bridge->>Cache: get("BN00280291")
    Cache-->>Bridge: PatientInfo (cache hit)
    Bridge->>Kiosk: patient_found signal
    Note over Bridge: KHÔNG gọi HIS — tiết kiệm thời gian
```

## Sequence Diagram — Lỗi mạng + Retry

```mermaid
sequenceDiagram
    participant Client as VNPTHisClient
    participant HIS as VNPT HIS
    participant Publisher as FirestorePublisher
    participant Queue as pending.json
    participant FS as Firestore

    Client->>HIS: POST (lần 1)
    HIS--xClient: Timeout

    Client->>HIS: POST (lần 2, delay 1s)
    HIS--xClient: Timeout

    Client->>HIS: POST (lần 3, delay 2s)
    HIS-->>Client: 200 OK

    Note over Publisher,FS: Publish kết quả
    Publisher->>FS: firestore_set()
    FS--xPublisher: Connection Error

    Publisher->>FS: Retry (lần 2)
    FS--xPublisher: Connection Error

    Publisher->>FS: Retry (lần 3)
    FS--xPublisher: Connection Error

    Publisher->>Queue: Ghi vào pending.json

    Note over Publisher: 30 giây sau...
    Publisher->>Queue: Đọc pending entries
    Publisher->>FS: firestore_set()
    FS-->>Publisher: 200 OK
    Publisher->>Queue: Xóa entry đã sync
```

## Class Diagram

```mermaid
classDiagram
    class HisBridge {
        -HisConfig _config
        -BarcodeListener _barcode_listener
        -_BridgeWorker _worker
        +patient_found Signal
        +bridge_error Signal
        +his_connected Signal
        +start()
        +stop()
        +lookup(barcode: str)
    }

    class _BridgeWorker {
        -HisConfig _config
        -asyncio.Queue _barcode_queue
        +patient_found Signal
        +bridge_error Signal
        +processing Signal
        +run()
        +submit_barcode(barcode: str)
        -_process_barcode()
        -_main_loop()
    }

    class VNPTHisClient {
        -HisConfig _config
        -httpx.AsyncClient _client
        +search_patient(barcode) dict
        +get_patient_info(id) dict
        +get_services(params) list
        +fetch_full_patient(barcode) PatientInfo
        +build_service_params(id) str
        -_post_with_retry(body) dict
        -_parse_response(text) dict
        -_normalize_patient() PatientInfo
    }

    class BarcodeListener {
        -re.Pattern _pattern
        +barcode_received Signal
        +barcode_invalid Signal
        +receive(raw_input: str) bool
        +set_pattern(pattern: str)
    }

    class FirestorePublisher {
        -HisConfig _config
        -asyncio.Task _sync_task
        +publish(patient: PatientInfo) bool
        +sync_pending_queue() int
        +start_auto_sync()
        +stop_auto_sync()
        +pending_count int
        -_save_to_pending_queue()
        -_auto_sync_loop()
    }

    class TTLCache~T~ {
        -int ttl_seconds
        -dict _store
        -Lock _lock
        +get(key) T?
        +set(key, value)
        +has(key) bool
        +invalidate(key)
        +clear()
        +cleanup() int
    }

    class HisConfig {
        +HisServerConfig his
        +NetworkConfig network
        +CacheConfig cache
        +FirestoreConfig firestore
        +LoggingConfig logging
        +load(path)$ HisConfig
    }

    class PatientInfo {
        +str patient_code
        +str patient_name
        +int age
        +str gender
        +str address
        +HisIdentifiers his
        +list~ServiceInfo~ services
        +to_firestore_dict() dict
        +service_names() list
    }

    class ServiceInfo {
        +str code
        +str name
        +str note
        +str status
    }

    class HisIdentifiers {
        +str benh_nhan_id
        +str tiep_nhan_id
        +str kham_benh_id
        +str mau_benh_pham_id
        +str ho_so_benh_an_id
    }

    HisBridge o-- _BridgeWorker
    HisBridge o-- BarcodeListener
    _BridgeWorker --> VNPTHisClient
    _BridgeWorker --> FirestorePublisher
    _BridgeWorker --> TTLCache
    VNPTHisClient --> PatientInfo
    VNPTHisClient --> HisConfig
    PatientInfo *-- HisIdentifiers
    PatientInfo *-- ServiceInfo
    FirestorePublisher --> PatientInfo
```

## Nguyên tắc thiết kế

| Nguyên tắc | Áp dụng |
|---|---|
| **Single Responsibility** | Mỗi module chỉ làm 1 việc: client gọi API, publisher push Firestore, cache quản lý TTL |
| **Open/Closed** | Thêm stored procedure mới chỉ cần sửa `config.yaml` — không sửa code |
| **Dependency Inversion** | HisBridge phụ thuộc vào HisConfig interface — không hardcode URL/SP |
| **Don't Repeat Yourself** | `_post_with_retry()` dùng chung cho tất cả API calls |
| **Fail Gracefully** | Mất mạng → retry → local queue → auto-sync khi phục hồi |
