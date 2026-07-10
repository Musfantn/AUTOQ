import urllib.request
import json
import time
from datetime import datetime

# =============================================================================
# CẤU HÌNH FIRESTORE (Dùng chung với TaskView)
# =============================================================================
FIREBASE_API_KEY = "AIzaSyCzwZJ_STEXN3bhEUXEDhaeLcjkx5kVvxQ"
FIREBASE_PROJECT = "tasksched"
FIRESTORE_BASE = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT}/databases/(default)/documents"
TIMEOUT_SECONDS = 8

# Helper: Chuyển đổi dữ liệu Python sang định dạng Field Value của Firestore JSON
def _py_to_firestore(val):
    if val is None:
        return {"nullValue": None}
    if isinstance(val, bool):
        return {"booleanValue": val}
    if isinstance(val, int):
        return {"integerValue": str(val)}
    if isinstance(val, float):
        return {"doubleValue": val}
    if isinstance(val, str):
        return {"stringValue": val}
    if isinstance(val, list):
        return {"arrayValue": {"values": [_py_to_firestore(v) for v in val]}}
    if isinstance(val, dict):
        return {"mapValue": {"fields": {k: _py_to_firestore(v) for k, v in val.items()}}}
    return {"stringValue": str(val)}

# Helper: Chuyển đổi định dạng Field Value của Firestore JSON về kiểu dữ liệu Python
def _parse_field(fv: dict):
    if not isinstance(fv, dict):
        return None
    if "stringValue"  in fv: return fv["stringValue"]
    if "integerValue" in fv: return int(fv["integerValue"])
    if "doubleValue"  in fv: return fv["doubleValue"]
    if "booleanValue" in fv: return fv["booleanValue"]
    if "nullValue"    in fv: return None
    if "mapValue"     in fv:
        return {k: _parse_field(v)
                for k, v in fv["mapValue"].get("fields", {}).items()}
    if "arrayValue"   in fv:
        return [_parse_field(v)
                for v in fv["arrayValue"].get("values", [])]
    return None

def _doc_to_dict(doc: dict) -> dict:
    return {k: _parse_field(v) for k, v in doc.get("fields", {}).items()}

def _firestore_get(path: str) -> dict | None:
    url = f"{FIRESTORE_BASE}/{path}?key={FIREBASE_API_KEY}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return _doc_to_dict(json.loads(resp.read().decode("utf-8")))
    except Exception as e:
        # Nếu tài liệu không tồn tại hoặc lỗi, trả về None
        return None

def _firestore_set(path: str, data: dict) -> bool:
    url = f"{FIRESTORE_BASE}/{path}?key={FIREBASE_API_KEY}"
    body = json.dumps({"fields": {k: _py_to_firestore(v) for k, v in data.items()}}).encode("utf-8")
    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="PATCH"
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return resp.status in (200, 201)
    except Exception as e:
        print(f"[FirestoreQueue] Lỗi ghi '{path}': {e}")
        return False

# =============================================================================
# CÁC API THAO TÁC HÀNG ĐỢI GỌI SỐ (CLOUD FIRESTORE)
# =============================================================================

def get_room_queue(room_num) -> dict:
    """Lấy thông tin hàng đợi của phòng siêu âm chỉ định. Tự động kiểm tra và reset khi qua ngày mới."""
    path = f"autoq_queues/room_{room_num}"
    data = _firestore_get(path)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Nếu tài liệu chưa tồn tại hoặc thuộc về ngày cũ, ta reset số thứ tự
    if not data or data.get("date") != today_str:
        data = {
            "room": str(room_num),
            "current_calling": None,
            "waiting_list": [],
            "last_number": 0,
            "date": today_str
        }
        _firestore_set(path, data)
        
    return data

def save_room_queue(room_num, queue_data) -> bool:
    """Lưu toàn bộ hàng đợi của phòng lên Firestore."""
    path = f"autoq_queues/room_{room_num}"
    return _firestore_set(path, queue_data)

def push_patient(room_num, ma_bn, ten_bn, tuoi, ngay_sinh, dich_vu) -> str | None:
    """Đẩy bệnh nhân mới vào phòng khám chỉ định, tự động gán số thứ tự tiếp theo."""
    queue_data = get_room_queue(room_num)
    queue_data["last_number"] += 1
    stt_str = f"{queue_data['last_number']:03d}"
    
    patient = {
        "stt": stt_str,
        "ma_bn": ma_bn,
        "ten_bn": ten_bn,
        "tuoi": tuoi,
        "ngay_sinh": ngay_sinh,
        "dich_vu": dich_vu,
        "timestamp": time.time()
    }
    queue_data["waiting_list"].append(patient)
    if save_room_queue(room_num, queue_data):
        return stt_str
    return None

def next_patient(room_num) -> dict:
    """Gọi bệnh nhân tiếp theo trong hàng đợi."""
    queue_data = get_room_queue(room_num)
    if queue_data["waiting_list"]:
        next_pat = queue_data["waiting_list"].pop(0)
        queue_data["current_calling"] = next_pat
    else:
        queue_data["current_calling"] = None
    save_room_queue(room_num, queue_data)
    return queue_data

def toggle_emergency(room_num) -> dict:
    """Kích hoạt hoặc hủy trạng thái CẤP CỨU."""
    queue_data = get_room_queue(room_num)
    curr = queue_data.get("current_calling")
    if curr and curr.get("stt") == "CC":
        queue_data["current_calling"] = None
    else:
        queue_data["current_calling"] = {
            "stt": "CC",
            "ma_bn": "",
            "ten_bn": "CẤP CỨU",
            "tuoi": "",
            "dich_vu": "SIÊU ÂM CẤP CỨU",
            "timestamp": time.time()
        }
    save_room_queue(room_num, queue_data)
    return queue_data

def set_number(room_num, num) -> dict:
    """Đặt hàng đợi gọi trực tiếp đến số thứ tự mong muốn."""
    queue_data = get_room_queue(room_num)
    queue_data["last_number"] = max(queue_data["last_number"], num)
    stt_str = f"{num:03d}"
    
    # Tìm trong hàng chờ xem bệnh nhân số này có sẵn chưa
    found_idx = -1
    for idx, pat in enumerate(queue_data["waiting_list"]):
        if pat.get("stt") == stt_str:
            found_idx = idx
            break
            
    if found_idx != -1:
        queue_data["current_calling"] = queue_data["waiting_list"].pop(found_idx)
    else:
        # Nếu không có sẵn, tạo bản ghi ảo tạm thời
        queue_data["current_calling"] = {
            "stt": stt_str,
            "ma_bn": "BN_SET",
            "ten_bn": "Bệnh nhân đặt số",
            "tuoi": "",
            "dich_vu": "",
            "timestamp": time.time()
        }
    save_room_queue(room_num, queue_data)
    return queue_data

def reset_queue(room_num) -> dict:
    """Reset toàn bộ dữ liệu hàng đợi của phòng chỉ định."""
    queue_data = {
        "room": str(room_num),
        "current_calling": None,
        "waiting_list": [],
        "last_number": 0,
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    save_room_queue(room_num, queue_data)
    return queue_data
