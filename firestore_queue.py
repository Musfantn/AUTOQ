# =============================================================================
# FILE: firestore_queue.py
# MÔ TẢ: API thao tác hàng đợi gọi số theo số thứ tự đơn giản cho từng phòng
#        (Cloud Firestore + Offline Local Cache Fallback).
# =============================================================================

import os
import json
import time
import threading
from datetime import datetime
from firestore_client import firestore_get_parsed, firestore_set, _log
from config_manager import get_db_dir

_cache_lock = threading.Lock()


# ─── OFFLINE CACHE HELPERS ──────────────────────────────────────────────────

def _get_local_cache_path(room_num) -> str:
    db_dir = get_db_dir()
    os.makedirs(db_dir, exist_ok=True)
    r_str = str(room_num).strip().lower()
    return os.path.join(db_dir, f"queue_room_{r_str}.json")


def _load_local_cache(room_num) -> dict | None:
    path = _get_local_cache_path(room_num)
    with _cache_lock:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                _log(f"[QueueCache] Lỗi đọc cache phòng {room_num}: {e}")
    return None


def _save_local_cache(room_num, queue_data: dict):
    path = _get_local_cache_path(room_num)
    with _cache_lock:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(queue_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log(f"[QueueCache] Lỗi ghi cache phòng {room_num}: {e}")


def _ensure_schema(data: dict, room_num) -> dict:
    """Đảm bảo đủ các trường dữ liệu cần thiết cho cơ chế gọi số."""
    r_str = str(room_num).strip().lower()
    data.setdefault("room", r_str)
    data.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
    data.setdefault("last_number", 0)
    data.setdefault("first_call_at", 0.0)
    data.setdefault("current_calling", None)
    data.setdefault("missed_list", [])
    data.setdefault("waiting_list", [])
    data.setdefault("history", [])
    data.setdefault("is_duty_mode", False)
    if not isinstance(data.get("missed_list"), list):
        data["missed_list"] = []
    if not isinstance(data.get("history"), list):
        data["history"] = []
    return data


# =============================================================================
# CÁC API THAO TÁC HÀNG ĐỢI GỌI SỐ TỰ ĐỘNG THEO PHÒNG
# =============================================================================

def get_room_queue(room_num) -> dict:
    """Lấy thông tin hàng đợi của phòng khám chỉ định.
    Tự động kiểm tra và reset khi qua ngày mới. Có fallback cache cục bộ khi mất mạng.
    """
    room_str = str(room_num).strip().lower()
    path = f"autoq_queues/room_{room_str}"
    today_str = datetime.now().strftime("%Y-%m-%d")

    data = firestore_get_parsed(path)
    if data is None:
        # Fallback sang cache cục bộ nếu có, hoặc tạo mới và khởi tạo luôn tài liệu phòng lên Firestore
        cached = _load_local_cache(room_str)
        if cached and cached.get("date") == today_str:
            data = _ensure_schema(cached, room_str)
            firestore_set(path, data)
            return data
        data = _new_queue(room_str, today_str)
        _save_local_cache(room_str, data)
        firestore_set(path, data)
        return data

    # Nếu tài liệu thuộc về ngày cũ → reset số thứ tự cho ngày mới
    if data.get("date") != today_str:
        data = _new_queue(room_str, today_str)
        firestore_set(path, data)

    data = _ensure_schema(data, room_str)
    _save_local_cache(room_str, data)
    return data


def save_room_queue(room_num, queue_data: dict) -> bool:
    """Lưu toàn bộ trạng thái gọi số của phòng lên Firestore và cache cục bộ."""
    room_str = str(room_num).strip().lower()
    queue_data = _ensure_schema(queue_data, room_str)
    _save_local_cache(room_str, queue_data)
    path = f"autoq_queues/room_{room_str}"
    return firestore_set(path, queue_data)


def _archive_current_to_history(queue_data: dict):
    """Lưu số thứ tự đang gọi hiện tại vào lịch sử đã khám kèm thời lượng thực hiện."""
    curr = queue_data.get("current_calling")
    if curr and isinstance(curr, dict) and curr.get("stt") and curr.get("stt") != "CC":
        if "history" not in queue_data or not isinstance(queue_data["history"], list):
            queue_data["history"] = []
        now_ts = time.time()
        entry = dict(curr)
        entry["completed_at"] = now_ts
        start_ts = entry.get("called_at") or entry.get("timestamp") or now_ts
        entry["exam_duration_sec"] = max(0, int(now_ts - start_ts))
        queue_data["history"].append(entry)
        queue_data["history"] = queue_data["history"][-300:]  # Giữ tối đa 300 lượt trong ngày


def next_patient(room_num) -> dict:
    """Gọi số thứ tự tiếp theo (tự động tăng last_number + 1)."""
    queue_data = get_room_queue(room_num)
    _archive_current_to_history(queue_data)

    new_num = int(queue_data.get("last_number", 0)) + 1
    queue_data["last_number"] = new_num
    stt_str = f"{new_num:03d}"
    now_ts = time.time()
    if not queue_data.get("first_call_at"):
        queue_data["first_call_at"] = now_ts

    # Nếu số này đang nằm trong danh sách chưa vào (missed_list) thì bỏ ra
    queue_data["missed_list"] = [
        m for m in queue_data.get("missed_list", [])
        if str(m.get("stt", "")).strip() != stt_str
    ]

    queue_data["current_calling"] = {
        "stt": stt_str,
        "timestamp": now_ts,
        "called_at": now_ts,
        "call_count": 1,
        "is_recall": False,
    }

    save_room_queue(room_num, queue_data)
    return queue_data


def recall_current_patient(room_num) -> dict:
    """Gọi lại bệnh nhân đang ở trạng thái current_calling (chưa nghe thấy hoặc chưa vào)."""
    queue_data = get_room_queue(room_num)
    curr = queue_data.get("current_calling")
    now_ts = time.time()

    if curr and isinstance(curr, dict) and curr.get("stt") and curr.get("stt") != "CC":
        curr["call_count"] = int(curr.get("call_count", 1)) + 1
        curr["recalled_at"] = now_ts
        curr["is_recall"] = True
        queue_data["current_calling"] = curr
        save_room_queue(room_num, queue_data)

    return queue_data


def skip_current_and_next(room_num) -> dict:
    """Đánh dấu số đang gọi là 'Chưa vào phòng / Qua lượt' (đưa vào missed_list)
    và tự động gọi số thứ tự tiếp theo.
    """
    queue_data = get_room_queue(room_num)
    curr = queue_data.get("current_calling")
    now_ts = time.time()

    if curr and isinstance(curr, dict) and curr.get("stt") and curr.get("stt") != "CC":
        stt_curr = str(curr.get("stt")).strip()
        missed_list = queue_data.get("missed_list", [])
        # Tránh trùng lặp trong missed_list
        missed_list = [m for m in missed_list if str(m.get("stt", "")).strip() != stt_curr]
        missed_entry = {
            "stt": stt_curr,
            "timestamp": curr.get("timestamp", now_ts),
            "called_at": curr.get("called_at", now_ts),
            "skipped_at": now_ts,
            "call_count": int(curr.get("call_count", 1)),
        }
        missed_list.insert(0, missed_entry)
        queue_data["missed_list"] = missed_list[:50]

    # Gọi luôn số tiếp theo
    new_num = int(queue_data.get("last_number", 0)) + 1
    queue_data["last_number"] = new_num
    stt_next = f"{new_num:03d}"
    if not queue_data.get("first_call_at"):
        queue_data["first_call_at"] = now_ts

    queue_data["current_calling"] = {
        "stt": stt_next,
        "timestamp": now_ts,
        "called_at": now_ts,
        "call_count": 1,
        "is_recall": False,
    }

    save_room_queue(room_num, queue_data)
    return queue_data


def recall_specific_number(room_num, target_num_or_stt) -> dict:
    """Gọi lại một số thứ tự cụ thể (từ danh sách chưa vào phòng hoặc lịch sử gọi).
    Bảo toàn last_number để sau đó bấm TIẾP THEO vẫn tăng đúng tiến độ.
    """
    queue_data = get_room_queue(room_num)
    _archive_current_to_history(queue_data)

    try:
        num = int(str(target_num_or_stt).strip())
    except ValueError:
        num = 1

    stt_str = f"{num:03d}"
    now_ts = time.time()

    # Kiểm tra xem số này có trong missed_list không để lấy call_count cũ và xóa khỏi missed_list
    prev_call_count = 1
    new_missed = []
    for m in queue_data.get("missed_list", []):
        if str(m.get("stt", "")).strip() == stt_str:
            prev_call_count = int(m.get("call_count", 1))
        else:
            new_missed.append(m)
    queue_data["missed_list"] = new_missed

    # Nếu gọi số lớn hơn last_number thì cập nhật last_number, ngược lại giữ nguyên mốc last_number
    queue_data["last_number"] = max(int(queue_data.get("last_number", 0)), num)
    if not queue_data.get("first_call_at"):
        queue_data["first_call_at"] = now_ts

    queue_data["current_calling"] = {
        "stt": stt_str,
        "timestamp": now_ts,
        "called_at": now_ts,
        "recalled_at": now_ts,
        "call_count": prev_call_count + 1,
        "is_recall": True,
    }

    save_room_queue(room_num, queue_data)
    return queue_data


def toggle_emergency(room_num) -> dict:
    """Kích hoạt hoặc hủy trạng thái CẤP CỨU."""
    queue_data = get_room_queue(room_num)
    curr = queue_data.get("current_calling")

    if curr and curr.get("stt") == "CC":
        queue_data["current_calling"] = None
    else:
        _archive_current_to_history(queue_data)
        now_ts = time.time()
        queue_data["current_calling"] = {
            "stt": "CC",
            "timestamp": now_ts,
            "called_at": now_ts,
            "call_count": 1,
            "is_recall": False,
        }

    save_room_queue(room_num, queue_data)
    return queue_data


def set_number(room_num, num: int) -> dict:
    """Đặt bộ đếm gọi trực tiếp đến số thứ tự mong muốn (NHẢY ĐẾN SỐ).
    Các lần bấm TIẾP THEO sau đó sẽ tiếp tục tăng từ số này.
    """
    queue_data = get_room_queue(room_num)
    _archive_current_to_history(queue_data)

    num = max(1, int(num))
    queue_data["last_number"] = num
    stt_str = f"{num:03d}"
    now_ts = time.time()
    if not queue_data.get("first_call_at"):
        queue_data["first_call_at"] = now_ts

    # Nếu số này có trong missed_list thì xóa khỏi missed_list
    queue_data["missed_list"] = [
        m for m in queue_data.get("missed_list", [])
        if str(m.get("stt", "")).strip() != stt_str
    ]

    queue_data["current_calling"] = {
        "stt": stt_str,
        "timestamp": now_ts,
        "called_at": now_ts,
        "call_count": 1,
        "is_recall": False,
    }

    save_room_queue(room_num, queue_data)
    return queue_data


def set_duty_mode(room_num, is_duty: bool, doctor_name: str = "", doctor_phone: str = "") -> dict:
    """Cập nhật trạng thái Chế độ phòng trực lên Firestore để Admin giám sát."""
    queue_data = get_room_queue(room_num)
    queue_data["is_duty_mode"] = bool(is_duty)
    queue_data["duty_doctor"] = doctor_name if is_duty else ""
    queue_data["duty_phone"] = doctor_phone if is_duty else ""
    save_room_queue(room_num, queue_data)
    return queue_data


def reset_queue(room_num) -> dict:
    """Reset toàn bộ dữ liệu gọi số của phòng chỉ định về 0."""
    queue_data = _new_queue(room_num)
    save_room_queue(room_num, queue_data)
    return queue_data


# =============================================================================
# REALTIME WATCHER LISTENER WORKER (PySide6 QThread)
# =============================================================================

from PySide6.QtCore import QThread, Signal


class FirestoreQueueListenerWorker(QThread):
    """Worker thread lắng nghe sự thay đổi thời gian thực (Realtime Watcher)
    từ Cloud Firestore cho hàng đợi của phòng chỉ định (Hỗ trợ cả gRPC Stream và REST API).
    """
    queue_updated = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, room_num: str, parent=None):
        super().__init__(parent)
        self.room_num = str(room_num).strip().lower()
        self._is_running = True
        self._doc_watch = None
        self._last_serialized = ""

    def _emit_if_changed(self, data: dict):
        today_str = datetime.now().strftime("%Y-%m-%d")
        if data.get("date") != today_str:
            data = _new_queue(self.room_num, today_str)
            firestore_set(f"autoq_queues/room_{self.room_num}", data)
        data = _ensure_schema(data, self.room_num)
        serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
        if serialized != self._last_serialized:
            self._last_serialized = serialized
            _save_local_cache(self.room_num, data)
            self.queue_updated.emit(data)

    def run(self):
        # Ưu tiên thử gRPC on_snapshot nếu môi trường có cài google-cloud-firestore,
        # nếu không có thì tự động dùng Firestore REST Watcher (không báo lỗi giả).
        has_grpc = False
        try:
            from google.cloud import firestore  # type: ignore
            from google.auth.credentials import AnonymousCredentials  # type: ignore
            from firestore_client import FIREBASE_PROJECT
            has_grpc = True
        except ImportError:
            has_grpc = False

        if has_grpc:
            try:
                db = firestore.Client(project=FIREBASE_PROJECT, credentials=AnonymousCredentials())
                doc_ref = db.collection("autoq_queues").document(f"room_{self.room_num}")

                def on_snapshot(doc_snapshots, changes, read_time):
                    if not self._is_running:
                        return
                    for doc in doc_snapshots:
                        if doc.exists:
                            self._emit_if_changed(doc.to_dict() or {})

                self._doc_watch = doc_ref.on_snapshot(on_snapshot)
                _log(f"[RealtimeWatcher] Đã kích hoạt Firestore gRPC Listener cho Phòng {self.room_num}")

                while self._is_running:
                    self.msleep(200)
                return
            except Exception as e:
                _log(f"[RealtimeWatcher] Chuyển sang chế độ REST Watcher cho Phòng {self.room_num} ({e})")

        # Chế độ chuẩn: Đồng bộ qua Firestore REST API (nhẹ, không cần thư viện google-cloud)
        _log(f"[RealtimeWatcher] Đã kích hoạt Firestore REST Watcher cho Phòng {self.room_num}")
        while self._is_running:
            try:
                path = f"autoq_queues/room_{self.room_num}"
                data = firestore_get_parsed(path)
                if data is None and self._is_running:
                    # Nếu phòng mới chưa có tài liệu trên Firestore -> Tự động khởi tạo ngay
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    data = _new_queue(self.room_num, today_str)
                    firestore_set(path, data)
                if data is not None and self._is_running:
                    self._emit_if_changed(data)
            except Exception as e:
                _log(f"[RealtimeWatcher] Lỗi REST Watcher phòng {self.room_num}: {e}")
            # Ngủ chia nhỏ để dừng thread tức thì khi đóng ứng dụng
            for _ in range(10):
                if not self._is_running:
                    break
                self.msleep(200)

    def stop(self):
        self._is_running = False
        if self._doc_watch:
            try:
                self._doc_watch.unsubscribe()
            except Exception:
                pass
        self.quit()
        self.wait()


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _new_queue(room_num, date_str: str | None = None) -> dict:
    """Tạo cấu trúc hàng đợi rỗng mặc định."""
    return {
        "room": str(room_num),
        "current_calling": None,
        "missed_list": [],
        "waiting_list": [],
        "history": [],
        "last_number": 0,
        "first_call_at": 0.0,
        "is_duty_mode": False,
        "duty_doctor": "",
        "duty_phone": "",
        "date": date_str or datetime.now().strftime("%Y-%m-%d"),
    }


# =============================================================================
# QUẢN LÝ MẬT KHẨU ADMIN TRÊN CLOUD FIRESTORE (`autoq_queues/admin_auth`)
# =============================================================================

ADMIN_AUTH_PATH = "autoq_queues/admin_auth"
DEFAULT_ADMIN_PASSWORD = "123"


def _get_admin_cache_path() -> str:
    db_dir = get_db_dir()
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "admin_auth_cache.json")


def get_admin_password() -> str:
    """Lấy mật khẩu Admin từ Cloud Firestore (mặc định: '123').
    Tự động khởi tạo lên Firestore nếu chưa có và lưu cache cục bộ để dự phòng khi mất mạng.
    """
    data = firestore_get_parsed(ADMIN_AUTH_PATH)
    if data and isinstance(data, dict) and data.get("password"):
        pwd = str(data.get("password")).strip()
        try:
            with open(_get_admin_cache_path(), "w", encoding="utf-8") as f:
                json.dump({"password": pwd}, f)
        except Exception:
            pass
        return pwd

    # Nếu trên Firestore chưa tồn tại tài liệu admin_auth → Khởi tạo mật khẩu mặc định "123"
    if data is None:
        cache_file = _get_admin_cache_path()
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    if cached.get("password"):
                        return str(cached["password"]).strip()
            except Exception:
                pass
        # Khởi tạo mặc định lên Firestore ở luồng phụ
        firestore_set(ADMIN_AUTH_PATH, {
            "password": DEFAULT_ADMIN_PASSWORD,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    return DEFAULT_ADMIN_PASSWORD


def set_admin_password(new_password: str) -> bool:
    """Đổi mật khẩu Admin và lưu trực tiếp lên Cloud Firestore (`autoq_settings/admin_auth`)."""
    pwd = str(new_password).strip()
    if not pwd:
        return False
    try:
        with open(_get_admin_cache_path(), "w", encoding="utf-8") as f:
            json.dump({"password": pwd}, f)
    except Exception:
        pass
    return firestore_set(ADMIN_AUTH_PATH, {
        "password": pwd,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
