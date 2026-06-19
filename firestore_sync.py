# =============================================================================
# FILE: firestore_sync.py
# MÔ TẢ: Module đồng bộ dữ liệu nhân sự và lịch trực từ Firestore (TaskView)
#        Dùng Firestore REST API với API key – không cần firebase-admin SDK.
# =============================================================================

import urllib.request
import urllib.parse
import json
import datetime
import sys

# Đảm bảo stdout hỗ trợ UTF-8 trên Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def _log(msg: str):
    """In ra console an toàn trên mọi hệ điều hành."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('utf-8', errors='replace').decode('ascii', errors='replace'))


# ─── CẤU HÌNH FIREBASE (từ TaskView project) ──────────────────────────────────
FIREBASE_API_KEY = "AIzaSyCzwZJ_STEXN3bhEUXEDhaeLcjkx5kVvxQ"
FIREBASE_PROJECT = "tasksched"
FIRESTORE_BASE   = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT}/databases/(default)/documents"
TIMEOUT_SECONDS  = 10


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

def _firestore_get(path: str) -> dict | None:
    """GET request đến Firestore REST API. Trả về dict JSON hoặc None nếu lỗi."""
    url = f"{FIRESTORE_BASE}/{path}?key={FIREBASE_API_KEY}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        _log(f"[FirestoreSync] Loi GET '{path}': {e}")
        return None


# ─── Firestore value parsers ───────────────────────────────────────────────────

def _parse_field(fv: dict):
    """
    Chuyển đổi Firestore field value sang Python type.
    Hỗ trợ: string, integer, boolean, null, double, map, array.
    """
    if not isinstance(fv, dict):
        return None
    if "stringValue"  in fv: return fv["stringValue"]
    if "integerValue" in fv: return str(fv["integerValue"])
    if "doubleValue"  in fv: return fv["doubleValue"]
    if "booleanValue" in fv: return fv["booleanValue"]          # Python bool
    if "nullValue"    in fv: return None
    if "mapValue"     in fv:
        return {k: _parse_field(v)
                for k, v in fv["mapValue"].get("fields", {}).items()}
    if "arrayValue"   in fv:
        return [_parse_field(v)
                for v in fv["arrayValue"].get("values", [])]
    return None


def _doc_to_dict(doc: dict) -> dict:
    """Chuyển toàn bộ fields của một Firestore document thành Python dict."""
    return {k: _parse_field(v) for k, v in doc.get("fields", {}).items()}


# ─── Name matching helper ──────────────────────────────────────────────────────

def _names_match(a: str, b: str) -> bool:
    """So khớp tên gần đúng (bỏ qua hoa/thường, khoảng trắng thừa, tiền tố)."""
    import re
    def clean(s: str) -> str:
        s = re.sub(r'^(bs\.|tk\.|ktv\.)\s*', '', s.strip().lower())
        return re.sub(r'\s+', ' ', s).strip()
    ca, cb = clean(a), clean(b)
    return ca == cb or ca in cb or cb in ca


# ─── Public API ───────────────────────────────────────────────────────────────

def fetch_all_personnel() -> list[dict]:
    """
    Lấy danh sách BÁC SĨ active từ collection 'personnel'.
    CHỈ trả về nhân sự có role == 'doctor'.

    Returns:
        [{"id": str, "name": str, "phone": str, "specialty": str}, ...]
    """
    data = _firestore_get("personnel")
    if not data:
        return []

    result = []
    for doc in data.get("documents", []):
        d = _doc_to_dict(doc)

        # Chỉ lấy bác sĩ (role == 'doctor')
        if str(d.get("role", "")).lower() != "doctor":
            continue

        # Bỏ qua nhân sự không hoạt động
        is_active = d.get("isActive", True)
        if is_active is False or str(is_active).lower() == "false":
            continue

        doc_id = doc.get("name", "").split("/")[-1]
        result.append({
            "id":        doc_id,
            "name":      str(d.get("name", "")).strip(),
            "phone":     str(d.get("phone", "")).strip(),
            "specialty": str(d.get("specialty", "")).strip(),
        })

    result.sort(key=lambda x: x["name"])
    _log(f"[FirestoreSync] Dong bo {len(result)} bac si.")
    return result


def fetch_today_oncall_from_roster() -> dict | None:
    """
    Lấy bác sĩ trực hôm nay từ LỊCH TRỰC THÁNG (monthly roster).
    Đọc document 'assignments/roster_YYYY-MM', tra bảng dutySchedule theo ngày,
    ánh xạ ultrasoundEmployeeId → tên BS → SĐT từ personnel.

    Returns:
        {"name": str, "phone": str} hoặc None nếu không có dữ liệu.
    """
    today      = datetime.date.today()
    doc_id     = f"roster_{today.strftime('%Y-%m')}"
    today_str  = today.strftime("%Y-%m-%d")

    # Lấy document lịch trực tháng
    doc = _firestore_get(f"assignments/{urllib.parse.quote(doc_id)}")
    if not doc:
        _log(f"[FirestoreSync] Khong tim thay document {doc_id}")
        return None

    d = _doc_to_dict(doc)  # Parsed Python dict with nested maps/arrays

    # 1. Lấy lịch trực ngày hôm nay
    duty_schedule = d.get("dutySchedule") or {}
    today_entry   = duty_schedule.get(today_str)

    if not today_entry or not isinstance(today_entry, dict):
        _log(f"[FirestoreSync] Khong co lich truc ngay {today_str}")
        return None

    us_id = today_entry.get("ultrasoundEmployeeId", "")
    if not us_id:
        _log("[FirestoreSync] Khong co ultrasoundEmployeeId cho ngay nay")
        return None

    # 2. Tìm tên bác sĩ trong danh sách ultrasoundEmployees
    us_employees = d.get("ultrasoundEmployees") or []
    doctor_name  = ""
    for emp in us_employees:
        if isinstance(emp, dict) and emp.get("id") == us_id:
            doctor_name = emp.get("name", "").strip()
            break

    if not doctor_name:
        _log(f"[FirestoreSync] Khong tim thay ten BS cho ID '{us_id}'")
        return None

    # 3. Lấy số điện thoại từ collection personnel (khớp theo tên)
    phone = ""
    personnel = fetch_all_personnel()
    for p in personnel:
        if _names_match(p["name"], doctor_name):
            phone = p["phone"]
            break

    _log(f"[FirestoreSync] BS truc hom nay: {doctor_name} | SDT: {phone or 'chua co'}")
    return {"name": doctor_name, "phone": phone}


# ─── TEST ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== TEST: fetch_all_personnel (chi bac si) ===")
    doctors = fetch_all_personnel()
    for p in doctors:
        print(f"  {p['name']} | {p['phone']} | ID: {p['id']}")

    print("\n=== TEST: fetch_today_oncall_from_roster ===")
    oncall = fetch_today_oncall_from_roster()
    if oncall:
        print(f"  BS truc: {oncall['name']} | SDT: {oncall['phone']}")
    else:
        print("  Khong co lich truc hom nay")
