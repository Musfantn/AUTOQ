# =============================================================================
# FILE: firestore_queue.py
# MÔ TẢ: API thao tác hàng đợi gọi số (Cloud Firestore).
#        Mọi HTTP/parse logic đã chuyển sang firestore_client.py.
# =============================================================================

import time
from datetime import datetime
from firestore_client import firestore_get_parsed, firestore_set, _log


# =============================================================================
# CÁC API THAO TÁC HÀNG ĐỢI GỌI SỐ
# =============================================================================

def get_room_queue(room_num) -> dict:
    """Lấy thông tin hàng đợi của phòng siêu âm chỉ định.
    Tự động kiểm tra và reset khi qua ngày mới.
    """
    path = f"autoq_queues/room_{room_num}"
    data = firestore_get_parsed(path)
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Nếu tài liệu chưa tồn tại hoặc thuộc về ngày cũ → reset số thứ tự
    if not data or data.get("date") != today_str:
        data = _new_queue(room_num, today_str)
        firestore_set(path, data)

    return data


def save_room_queue(room_num, queue_data) -> bool:
    """Lưu toàn bộ hàng đợi của phòng lên Firestore."""
    path = f"autoq_queues/room_{room_num}"
    return firestore_set(path, queue_data)


def push_patient(room_num, ma_bn, ten_bn, tuoi, ngay_sinh, dich_vu) -> str | None:
    """Đẩy bệnh nhân mới vào phòng khám chỉ định, tự động gán STT tiếp theo."""
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


def _archive_current_to_history(queue_data: dict):
    """Lưu bệnh nhân đang gọi hiện tại vào danh sách lịch sử bệnh nhân đã thực hiện kèm thời gian thực hiện."""
    curr = queue_data.get("current_calling")
    if curr and isinstance(curr, dict) and curr.get("stt") != "CC":
        if "history" not in queue_data or not isinstance(queue_data["history"], list):
            queue_data["history"] = []
        curr_stt = curr.get("stt")
        if not any(h.get("stt") == curr_stt for h in queue_data["history"]):
            now_ts = time.time()
            curr["completed_at"] = now_ts
            start_ts = curr.get("called_at") or curr.get("timestamp") or now_ts
            curr["exam_duration_sec"] = max(0, int(now_ts - start_ts))
            queue_data["history"].append(curr)
            queue_data["history"] = queue_data["history"][-300:]  # Lưu tối đa 300 ca đã khám trong ngày


def next_patient(room_num) -> dict:
    """Gọi bệnh nhân tiếp theo trong hàng đợi."""
    queue_data = get_room_queue(room_num)
    _archive_current_to_history(queue_data)

    if queue_data.get("waiting_list"):
        next_pat = queue_data["waiting_list"].pop(0)
        next_pat["called_at"] = time.time()
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
        _archive_current_to_history(queue_data)
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
    """Đặt hàng đợi gọi trực tiếp đến số thứ tự mong muốn.
    Đọc lại Firestore, tìm đúng bệnh nhân có số thứ tự này để hiển thị thông tin chính xác.
    """
    queue_data = get_room_queue(room_num)
    _archive_current_to_history(queue_data)
    queue_data["last_number"] = max(queue_data["last_number"], num)
    
    stt_str = f"{num:03d}"
    stt_variants = {stt_str, str(num), f"{num:02d}", str(num).zfill(3)}

    # 1. Tìm trong hàng chờ của phòng hiện tại
    found_idx = -1
    for idx, pat in enumerate(queue_data.get("waiting_list", [])):
        pat_stt = str(pat.get("stt", "")).strip()
        if pat_stt in stt_variants or (pat_stt.isdigit() and int(pat_stt) == num):
            found_idx = idx
            break

    if found_idx != -1:
        queue_data["current_calling"] = queue_data["waiting_list"].pop(found_idx)
    else:
        # 2. Nếu không có ở phòng hiện tại, tìm trong hàng chờ tất cả các phòng khác trên Firestore
        matched_patient = None
        for r in range(1, 6):
            if str(r) == str(room_num):
                continue
            other_q = firestore_get_parsed(f"autoq_queues/room_{r}")
            if other_q and "waiting_list" in other_q:
                for pat in other_q.get("waiting_list", []):
                    pat_stt = str(pat.get("stt", "")).strip()
                    if pat_stt in stt_variants or (pat_stt.isdigit() and int(pat_stt) == num):
                        matched_patient = pat
                        break
            if matched_patient:
                break

        if matched_patient:
            queue_data["current_calling"] = {
                "stt": stt_str,
                "ma_bn": matched_patient.get("ma_bn", ""),
                "ten_bn": matched_patient.get("ten_bn", ""),
                "tuoi": matched_patient.get("tuoi", ""),
                "ngay_sinh": matched_patient.get("ngay_sinh", ""),
                "dich_vu": matched_patient.get("dich_vu", ""),
                "timestamp": time.time()
            }
        else:
            # 3. Nếu chưa có thông tin bệnh nhân trong hệ thống
            queue_data["current_calling"] = {
                "stt": stt_str,
                "ma_bn": f"BN_{stt_str}",
                "ten_bn": f"BỆNH NHÂN SỐ {stt_str}",
                "tuoi": "",
                "ngay_sinh": "",
                "dich_vu": "",
                "timestamp": time.time()
            }

    save_room_queue(room_num, queue_data)
    return queue_data


# =============================================================================
# REALTIME WATCHER LISTENER WORKER (PySide6 QThread)
# =============================================================================

from PySide6.QtCore import QThread, Signal

class FirestoreQueueListenerWorker(QThread):
    """Worker thread lắng nghe sự thay đổi thời gian thực (Realtime Watcher)
    từ Cloud Firestore cho hàng đợi của phòng chỉ định.
    """
    queue_updated = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, room_num: str, parent=None):
        super().__init__(parent)
        self.room_num = str(room_num).strip()
        self._is_running = True
        self._doc_watch = None

    def run(self):
        try:
            from google.cloud import firestore
            from google.auth.credentials import AnonymousCredentials
            from firestore_client import FIREBASE_PROJECT

            db = firestore.Client(project=FIREBASE_PROJECT, credentials=AnonymousCredentials())
            doc_ref = db.collection("autoq_queues").document(f"room_{self.room_num}")

            def on_snapshot(doc_snapshots, changes, read_time):
                if not self._is_running:
                    return
                for doc in doc_snapshots:
                    if doc.exists:
                        data = doc.to_dict()
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        if data.get("date") != today_str:
                            data = _new_queue(self.room_num, today_str)
                            firestore_set(f"autoq_queues/room_{self.room_num}", data)
                        self.queue_updated.emit(data)

            self._doc_watch = doc_ref.on_snapshot(on_snapshot)
            _log(f"[RealtimeWatcher] Đã kích hoạt Firestore Realtime Listener cho Phòng {self.room_num}")

            while self._is_running:
                self.msleep(200)

        except Exception as e:
            _log(f"[RealtimeWatcher] Lỗi Listener phòng {self.room_num}: {e}")
            self.error_occurred.emit(str(e))

    def stop(self):
        self._is_running = False
        if self._doc_watch:
            try:
                self._doc_watch.unsubscribe()
            except Exception:
                pass
        self.quit()
        self.wait()



def reset_queue(room_num) -> dict:
    """Reset toàn bộ dữ liệu hàng đợi của phòng chỉ định."""
    queue_data = _new_queue(room_num)
    save_room_queue(room_num, queue_data)
    return queue_data


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _new_queue(room_num, date_str: str | None = None) -> dict:
    """Tạo cấu trúc hàng đợi rỗng mặc định."""
    return {
        "room": str(room_num),
        "current_calling": None,
        "waiting_list": [],
        "history": [],
        "last_number": 0,
        "date": date_str or datetime.now().strftime("%Y-%m-%d")
    }
