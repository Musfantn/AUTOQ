# =============================================================================
# FILE: firestore_client.py
# MÔ TẢ: Module dùng chung cho mọi thao tác Firestore REST API.
#        Tập trung cấu hình Firebase, các hàm chuyển đổi dữ liệu,
#        và HTTP helpers để tránh code trùng lặp.
# =============================================================================

import urllib.request
import urllib.parse
import json
import os
import sys
import re

# Đảm bảo stdout hỗ trợ UTF-8 trên Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


# ─── CẤU HÌNH FIREBASE ──────────────────────────────────────────────────────
# Ưu tiên biến môi trường, fallback giá trị mặc định (Web API Key — không phải secret)
FIREBASE_API_KEY = os.environ.get(
    "FIREBASE_API_KEY",
    "AIzaSyCzwZJ_STEXN3bhEUXEDhaeLcjkx5kVvxQ"
)
FIREBASE_PROJECT = os.environ.get("FIREBASE_PROJECT", "tasksched")
FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/"
    f"{FIREBASE_PROJECT}/databases/(default)/documents"
)
TIMEOUT_SECONDS = 10


# ─── LOGGING ─────────────────────────────────────────────────────────────────

def _log(msg: str):
    """In ra console an toàn trên mọi hệ điều hành (tránh UnicodeEncodeError)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('utf-8', errors='replace').decode('ascii', errors='replace'))


# ─── CHUYỂN ĐỔI DỮ LIỆU: Python ↔ Firestore JSON ──────────────────────────

def py_to_firestore(val):
    """Chuyển đổi dữ liệu Python sang định dạng Field Value của Firestore."""
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
        if not val:
            return {"arrayValue": {}}
        return {"arrayValue": {"values": [py_to_firestore(v) for v in val]}}
    if isinstance(val, dict):
        return {"mapValue": {"fields": {k: py_to_firestore(v) for k, v in val.items()}}}
    return {"stringValue": str(val)}


def parse_field(fv: dict):
    """Chuyển đổi Firestore field value sang Python type.
    Hỗ trợ: string, integer, boolean, null, double, map, array, timestamp.
    """
    if not isinstance(fv, dict):
        return None
    if "stringValue"    in fv: return fv["stringValue"]
    if "integerValue"   in fv: return int(fv["integerValue"])
    if "doubleValue"    in fv: return fv["doubleValue"]
    if "booleanValue"   in fv: return fv["booleanValue"]
    if "nullValue"      in fv: return None
    if "timestampValue" in fv: return fv["timestampValue"]
    if "mapValue"       in fv:
        return {k: parse_field(v)
                for k, v in fv["mapValue"].get("fields", {}).items()}
    if "arrayValue"     in fv:
        return [parse_field(v)
                for v in fv["arrayValue"].get("values", [])]
    return None


def doc_to_dict(doc: dict) -> dict:
    """Chuyển toàn bộ fields của một Firestore document thành Python dict."""
    return {k: parse_field(v) for k, v in doc.get("fields", {}).items()}


def doc_id_from_name(doc: dict) -> str:
    """Trích xuất document ID từ trường 'name' đầy đủ của Firestore."""
    return doc.get("name", "").split("/")[-1]


# ─── HTTP HELPERS ────────────────────────────────────────────────────────────

def firestore_get(path: str) -> dict | None:
    """GET một document. Trả về raw JSON dict hoặc None nếu lỗi / không tồn tại."""
    url = f"{FIRESTORE_BASE}/{path}?key={FIREBASE_API_KEY}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        _log(f"[FirestoreClient] Lỗi GET '{path}': {e}")
        return None


def firestore_get_parsed(path: str) -> dict | None:
    """GET một document và parse fields sang Python dict. Trả về None nếu lỗi."""
    raw = firestore_get(path)
    if not raw:
        return None
    return doc_to_dict(raw)


def firestore_set(path: str, data: dict) -> bool:
    """PATCH (upsert) một document với data Python dict. Trả True nếu thành công."""
    url = f"{FIRESTORE_BASE}/{path}?key={FIREBASE_API_KEY}"
    body = json.dumps({
        "fields": {k: py_to_firestore(v) for k, v in data.items()}
    }).encode("utf-8")
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
        _log(f"[FirestoreClient] Lỗi SET '{path}': {e}")
        return False


def firestore_list(collection: str, page_size: int = 100) -> list[dict]:
    """Lấy tất cả documents trong một collection. Trả về list raw docs."""
    url = f"{FIRESTORE_BASE}/{collection}?key={FIREBASE_API_KEY}&pageSize={page_size}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("documents", [])
    except Exception as e:
        _log(f"[FirestoreClient] Lỗi LIST '{collection}': {e}")
        return []


# ─── NAME MATCHING HELPER ───────────────────────────────────────────────────

def clean_name(s: str) -> str:
    """Chuẩn hóa tên: bỏ tiền tố BS./TK./KTV., lowercase, gộp khoảng trắng."""
    s = re.sub(r'^(bs\.|tk\.|ktv\.)\s*', '', s.strip().lower())
    return re.sub(r'\s+', ' ', s).strip()


def names_match(a: str, b: str) -> bool:
    """So khớp tên gần đúng (bỏ qua hoa/thường, khoảng trắng thừa, tiền tố)."""
    ca, cb = clean_name(a), clean_name(b)
    return ca == cb or ca in cb or cb in ca


# ─── DATE PARSING HELPER ────────────────────────────────────────────────────

def extract_birth_year(ngay_sinh: str) -> str:
    """Trích xuất năm sinh từ chuỗi ngày sinh (hỗ trợ dd/MM/yyyy và yyyy-MM-dd)."""
    if not ngay_sinh:
        return ""
    ngay_sinh_str = str(ngay_sinh).strip()
    if "/" in ngay_sinh_str:
        return ngay_sinh_str.split("/")[-1]
    if "-" in ngay_sinh_str:
        return ngay_sinh_str.split("-")[0]
    return ngay_sinh_str
