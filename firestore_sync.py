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
