# =============================================================================
# FILE: firestore_sync.py
# MÔ TẢ: Module đồng bộ dữ liệu nhân sự và lịch trực từ Firestore (TaskView).
#        Mọi HTTP/parse logic đã chuyển sang firestore_client.py.
# =============================================================================

import datetime
import urllib.parse

from firestore_client import (
    firestore_get, firestore_list,
    doc_to_dict, doc_id_from_name,
    names_match, _log,
)


# ─── Public API ───────────────────────────────────────────────────────────────

def fetch_all_personnel() -> list[dict]:
    """Lấy danh sách BÁC SĨ active từ collection 'personnel'.
    CHỈ trả về nhân sự có role == 'doctor'.

    Returns:
        [{"id": str, "name": str, "phone": str, "specialty": str}, ...]
    """
    docs = firestore_list("personnel")
    if not docs:
        return []

    result = []
    for doc in docs:
        d = doc_to_dict(doc)

        # Chỉ lấy bác sĩ (role == 'doctor')
        if str(d.get("role", "")).lower() != "doctor":
            continue

        # Bỏ qua nhân sự không hoạt động
        is_active = d.get("isActive", True)
        if is_active is False or str(is_active).lower() == "false":
            continue

        doc_id = doc_id_from_name(doc)
        result.append({
            "id":        doc_id,
            "name":      str(d.get("name", "")).strip(),
            "phone":     str(d.get("phone", "")).strip(),
            "specialty": str(d.get("specialty", "")).strip(),
        })

    result.sort(key=lambda x: x["name"])
    _log(f"[FirestoreSync] Đồng bộ {len(result)} bác sĩ.")
    return result


def fetch_doctors_and_ktvs() -> dict:
    """Lấy đồng thời danh sách Bác sĩ (role=='doctor') và Thư ký/KTV (role in ('secretary','ktv','xray','nurse'))
    đang active từ collection 'personnel' của Firestore trong 1 lần gọi duy nhất.

    Returns:
        {
            "doctors": [{"id": str, "name": str, "phone": str, "specialty": str}, ...],
            "ktvs":    [{"id": str, "name": str, "phone": str, "role": str}, ...]
        }
    """
    docs = firestore_list("personnel")
    if not docs:
        return {"doctors": [], "ktvs": []}

    doctors = []
    ktvs = []
    for doc in docs:
        d = doc_to_dict(doc)
        is_active = d.get("isActive", True)
        if is_active is False or str(is_active).lower() == "false":
            continue

        role = str(d.get("role", "")).strip().lower()
        name = str(d.get("name", "")).strip()
        if not name:
            continue

        doc_id = doc_id_from_name(doc)
        phone = str(d.get("phone", "")).strip()

        if role == "doctor":
            doctors.append({
                "id":        doc_id,
                "name":      name,
                "phone":     phone,
                "specialty": str(d.get("specialty", "")).strip(),
            })
        elif role in ("secretary", "ktv", "xray", "nurse"):
            ktvs.append({
                "id":    doc_id,
                "name":  name,
                "phone": phone,
                "role":  role,
            })

    doctors.sort(key=lambda x: x["name"])
    ktvs.sort(key=lambda x: x["name"])
    _log(f"[FirestoreSync] Tải nhân sự Settings: {len(doctors)} BS, {len(ktvs)} KTV/TK.")
    return {"doctors": doctors, "ktvs": ktvs}


# Ánh xạ mã phòng trên TaskView ('room-01'..'room-05') sang mã phòng của AUTOQ ('1'..'5')
_TASKVIEW_ROOM_MAP = {
    "room-01": "1",
    "room-02": "2",
    "room-03": "3",
    "room-04": "4",
    "room-05": "5",
}


def fetch_today_room_assignments(date_str: str | None = None) -> dict[str, str]:
    """Lấy danh sách phân công Bác sĩ theo từng phòng trong ngày hôm nay từ Firestore (TaskView).
    Đọc collection 'assignments' với điều kiện date == today_str và personnelRole == 'doctor'.

    Returns:
        dict ánh xạ mã phòng AUTOQ ('1'..'5', ...) -> Tên Bác sĩ phụ trách (VD: {'1': 'BS. Nguyễn Văn An'})
    """
    target_date = date_str or datetime.date.today().strftime("%Y-%m-%d")
    docs = firestore_list("assignments", page_size=300)
    if not docs:
        return {}

    room_to_doctors: dict[str, list[str]] = {}
    for raw_doc in docs:
        d = doc_to_dict(raw_doc)
        if str(d.get("personnelRole", "")).strip().lower() != "doctor":
            continue
        if str(d.get("date", "")).strip() != target_date:
            continue

        raw_room_id = str(d.get("roomId", "")).strip().lower()
        doc_name = str(d.get("personnelName", "")).strip()
        if not raw_room_id or not doc_name:
            continue

        autoq_room_id = _TASKVIEW_ROOM_MAP.get(raw_room_id, raw_room_id.replace("room-", ""))
        room_to_doctors.setdefault(autoq_room_id, [])
        if doc_name not in room_to_doctors[autoq_room_id]:
            room_to_doctors[autoq_room_id].append(doc_name)

    result = {r_id: ", ".join(names) for r_id, names in room_to_doctors.items() if names}
    _log(f"[FirestoreSync] Đồng bộ phân buồng ngày {target_date}: {len(result)} phòng có BS.")
    return result


def fetch_today_oncall_from_roster() -> dict | None:
    """Lấy bác sĩ trực hôm nay từ LỊCH TRỰC THÁNG (monthly roster).
    Đọc document 'assignments/roster_YYYY-MM', tra bảng dutySchedule theo ngày,
    ánh xạ ultrasoundEmployeeId → tên BS → SĐT từ personnel.

    Returns:
        {"name": str, "phone": str} hoặc None nếu không có dữ liệu.
    """
    today     = datetime.date.today()
    doc_id    = f"roster_{today.strftime('%Y-%m')}"
    today_str = today.strftime("%Y-%m-%d")

    # Lấy document lịch trực tháng (raw → tự parse)
    raw_doc = firestore_get(f"assignments/{urllib.parse.quote(doc_id)}")
    if not raw_doc:
        _log(f"[FirestoreSync] Không tìm thấy document {doc_id}")
        return None

    d = doc_to_dict(raw_doc)

    # 1. Lấy lịch trực ngày hôm nay
    duty_schedule = d.get("dutySchedule") or {}
    today_entry   = duty_schedule.get(today_str)

    if not today_entry or not isinstance(today_entry, dict):
        _log(f"[FirestoreSync] Không có lịch trực ngày {today_str}")
        return None

    us_id = today_entry.get("ultrasoundEmployeeId", "")
    if not us_id:
        _log("[FirestoreSync] Không có ultrasoundEmployeeId cho ngày này")
        return None

    # 2. Tìm tên bác sĩ trong danh sách ultrasoundEmployees
    us_employees = d.get("ultrasoundEmployees") or []
    doctor_name  = ""
    for emp in us_employees:
        if isinstance(emp, dict) and emp.get("id") == us_id:
            doctor_name = emp.get("name", "").strip()
            break

    if not doctor_name:
        _log(f"[FirestoreSync] Không tìm thấy tên BS cho ID '{us_id}'")
        return None

    # 3. Lấy số điện thoại từ collection personnel (khớp theo tên)
    phone = ""
    personnel = fetch_all_personnel()
    for p in personnel:
        if names_match(p["name"], doctor_name):
            phone = p["phone"]
            break

    _log(f"[FirestoreSync] BS trực hôm nay: {doctor_name} | SĐT: {phone or 'chưa có'}")
    return {"name": doctor_name, "phone": phone}


# ─── TEST ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== TEST: fetch_all_personnel (chỉ bác sĩ) ===")
    doctors = fetch_all_personnel()
    for p in doctors:
        print(f"  {p['name']} | {p['phone']} | ID: {p['id']}")

    print("\n=== TEST: fetch_today_oncall_from_roster ===")
    oncall = fetch_today_oncall_from_roster()
    if oncall:
        print(f"  BS trực: {oncall['name']} | SĐT: {oncall['phone']}")
    else:
        print("  Không có lịch trực hôm nay")
