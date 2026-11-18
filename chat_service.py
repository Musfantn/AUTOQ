# =============================================================================
# FILE: chat_service.py
# MÔ TẢ: Dịch vụ Chat Nhanh Nội Bộ giữa 11 Phòng khám & Trung tâm Admin (AUTOQ).
#        Kiến trúc Kênh Đôi Lai (Hybrid Dual-Channel):
#          1. LAN UDP Broadcast (Port 50506 - Độ trễ < 2ms trong mạng nội bộ)
#          2. Cloud Firestore Ring-Buffer (autoq_queues/room_chat_daily - Lưu tối đa
#             80 tin nhắn trong ngày, tự động xóa khi sang ngày mới & xuyên VLAN)
# =============================================================================

import os
import json
import time
import uuid
import socket
import threading
from datetime import datetime
from PySide6.QtCore import QObject, Signal

from config_manager import get_db_dir
from firestore_client import firestore_get_parsed, firestore_set, firestore_list, doc_to_dict, doc_id_from_name, _log
from speaker_hub import ALL_ROOM_IDS, ROOM_DEFINITIONS, get_room_short_name

CHAT_UDP_PORT = 50506
CHAT_FIRESTORE_PATH = "autoq_queues/room_chat_daily"
MAX_DAILY_MESSAGES = 80

DEFAULT_QUICK_TEMPLATES = [
    "🔄 Phòng đang quá tải, nhờ các phòng hỗ trợ chia bớt BN!",
    "🩺 Nhờ BS hội chẩn ca khó tại phòng",
    "🚨 Có ca Cấp cứu đang chuyển sang",
    "✅ Phòng đã vãn bệnh nhân, có thể nhận thêm ca",
    "📄 Mã máy phòng siêu âm đã đầy, đang đổi mã máy khác",
]


def get_room_or_admin_short_name(room_id: str) -> str:
    r = str(room_id or "").strip().lower()
    if r == "all":
        return "Toàn khoa"
    if r == "admin":
        return "Trung tâm Admin"
    return get_room_short_name(r)


def is_message_relevant_for_room(msg: dict, local_room_id: str) -> bool:
    """Kiểm tra tin nhắn có liên quan tới phòng hiện tại hay không.
    - Admin ('admin') nhìn thấy toàn bộ tin nhắn điều phối giữa các phòng.
    - Các phòng khám nhìn thấy: tin gửi 'ALL' (Toàn khoa), tin gửi đích danh phòng mình,
      hoặc tin do chính phòng mình gửi đi.
    """
    if not isinstance(msg, dict):
        return False
    local_r = str(local_room_id or "1").strip().lower()
    if local_r == "admin":
        return True
    target_r = str(msg.get("target_room", "ALL")).strip().lower()
    sender_r = str(msg.get("sender_room", "")).strip().lower()
    return target_r in ("all", local_r) or sender_r == local_r


def broadcast_chat_udp(msg_dict: dict) -> None:
    """Phát gói tin UDP Broadcast trong mạng LAN để các phòng nhận tức thì (< 2ms)."""
    payload = json.dumps({
        "type": "AUTOQ_CHAT",
        "msg": msg_dict,
    }, ensure_ascii=False).encode("utf-8")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.2)
        for target_ip in ("255.255.255.255", "127.0.0.1"):
            try:
                sock.sendto(payload, (target_ip, CHAT_UDP_PORT))
            except Exception:
                pass
        sock.close()
    except Exception as e:
        _log(f"[ChatUDP] Lỗi broadcast: {e}")


class ChatService(QObject):
    """Quản lý gửi/nhận tin nhắn nội bộ theo thời gian thực cho một phòng hoặc Admin."""

    # (msg_dict, is_new_incoming_notification)
    message_received = Signal(dict, bool)
    # Danh sách toàn bộ tin nhắn liên quan khi tải lịch sử trong ngày
    history_loaded = Signal(list)
    # Số lượng tin nhắn chưa đọc thay đổi
    unread_count_changed = Signal(int)
    # Cập nhật danh sách Bác sĩ đang ngồi tại từng phòng {room_id: doctor_name}
    room_doctors_updated = Signal(dict)

    def __init__(self, local_room_id: str = "1", local_doctor_name: str = "", parent=None):
        super().__init__(parent)
        self.local_room_id = str(local_room_id or "1").strip().lower()
        self.local_doctor_name = str(local_doctor_name or "").strip()
        if self.local_doctor_name == "---":
            self.local_doctor_name = ""

        self._lock = threading.Lock()
        self._seen_msg_ids: set[str] = set()
        self._messages: list[dict] = []
        self._unread_count: int = 0
        self._window_is_open: bool = False
        self._running: bool = False
        self._cold_start_done: bool = False
        self._room_doctors: dict[str, str] = {}

        self._udp_thread: threading.Thread | None = None
        self._cloud_thread: threading.Thread | None = None

    # ─── CẤU HÌNH PHÒNG & BÁC SĨ HIỆN TẠI ───────────────────────────────────

    def set_identity(self, room_id: str, doctor_name: str = "") -> None:
        r = str(room_id or "1").strip().lower()
        d = str(doctor_name or "").strip()
        if d == "---":
            d = ""
        changed_room = (r != self.local_room_id)
        self.local_room_id = r
        self.local_doctor_name = d
        if changed_room:
            self.history_loaded.emit(self.get_visible_messages())

    def set_chat_window_open(self, is_open: bool) -> None:
        self._window_is_open = bool(is_open)
        if self._window_is_open:
            self.mark_all_read()

    def mark_all_read(self) -> None:
        with self._lock:
            self._unread_count = 0
        self.unread_count_changed.emit(0)

    def get_unread_count(self) -> int:
        with self._lock:
            return self._unread_count

    def get_visible_messages(self) -> list[dict]:
        with self._lock:
            return [
                m for m in self._messages
                if is_message_relevant_for_room(m, self.local_room_id)
            ]

    def get_room_doctors_map(self) -> dict[str, str]:
        with self._lock:
            return dict(self._room_doctors)

    # ─── CACHE CỤC BỘ ────────────────────────────────────────────────────────

    @staticmethod
    def _get_cache_file() -> str:
        db_dir = get_db_dir()
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, "room_chat_daily.json")

    def _load_local_cache(self) -> dict | None:
        path = self._get_cache_file()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def _save_local_cache(self, doc_data: dict) -> None:
        path = self._get_cache_file()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ─── XỬ LÝ TIN NHẮN & CHỐNG TRÙNG LẶP (DEDUPLICATION) ────────────────────

    def _ingest_message(self, msg: dict, is_realtime_event: bool = True) -> bool:
        """Đưa một tin nhắn vào bộ nhớ nếu chưa từng nhận (chống lặp giữa UDP và Firestore).
        Trả về True nếu đây là tin nhắn mới chưa từng thấy.
        """
        if not isinstance(msg, dict):
            return False
        msg_id = str(msg.get("msg_id", "")).strip()
        if not msg_id:
            return False

        today_str = datetime.now().strftime("%Y-%m-%d")
        msg_date = str(msg.get("date", today_str)).strip()
        if msg_date and msg_date != today_str:
            return False

        with self._lock:
            if msg_id in self._seen_msg_ids:
                return False
            self._seen_msg_ids.add(msg_id)
            self._messages.append(msg)
            self._messages.sort(key=lambda x: float(x.get("timestamp") or 0.0))
            if len(self._messages) > MAX_DAILY_MESSAGES:
                self._messages = self._messages[-MAX_DAILY_MESSAGES:]

            relevant = is_message_relevant_for_room(msg, self.local_room_id)
            sender_r = str(msg.get("sender_room", "")).strip().lower()
            is_from_other = (sender_r != self.local_room_id)

            if relevant and is_realtime_event and is_from_other and not self._window_is_open:
                self._unread_count += 1
                new_unread = self._unread_count
            else:
                new_unread = self._unread_count

        if relevant:
            self.unread_count_changed.emit(new_unread)
            self.message_received.emit(msg, bool(is_realtime_event and is_from_other))
        return True

    # ─── GỬI TIN NHẮN ────────────────────────────────────────────────────────

    def build_message(
        self,
        content: str,
        target_room: str = "ALL",
        is_urgent: bool = False,
    ) -> dict:
        now_ts = time.time()
        now_dt = datetime.fromtimestamp(now_ts)
        today_str = now_dt.strftime("%Y-%m-%d")
        time_str = now_dt.strftime("%H:%M:%S")
        target_clean = str(target_room or "ALL").strip()
        if target_clean.upper() == "ALL":
            target_clean = "ALL"
        else:
            target_clean = target_clean.lower()

        msg_id = f"{self.local_room_id}_{int(now_ts * 1000)}_{uuid.uuid4().hex[:6]}"
        return {
            "msg_id": msg_id,
            "date": today_str,
            "sender_room": self.local_room_id,
            "sender_room_name": get_room_or_admin_short_name(self.local_room_id),
            "sender_doctor": self.local_doctor_name,
            "target_room": target_clean,
            "target_room_name": get_room_or_admin_short_name(target_clean),
            "content": content.strip(),
            "is_urgent": bool(is_urgent),
            "timestamp": now_ts,
            "time_str": time_str,
        }

    def send_message(
        self,
        content: str,
        target_room: str = "ALL",
        is_urgent: bool = False,
        persist_cloud: bool = True,
    ) -> dict | None:
        """Gửi tin nhắn nội bộ tức thì:
        1. Hiển thị ngay trên UI máy gửi (0ms)
        2. Phát LAN UDP Broadcast (< 2ms)
        3. Ghi lên Cloud Firestore autoq_queues/room_chat_daily ở luồng phụ
        """
        text = (content or "").strip()
        if not text:
            return None

        msg = self.build_message(text, target_room=target_room, is_urgent=is_urgent)
        # 1. Cập nhật tại chỗ (Optimistic 0ms)
        self._ingest_message(msg, is_realtime_event=False)

        # 2. Phát UDP LAN
        threading.Thread(target=broadcast_chat_udp, args=(msg,), daemon=True).start()

        # 3. Lưu lên Cloud Firestore
        if persist_cloud:
            threading.Thread(target=self._persist_message_to_firestore, args=(msg,), daemon=True).start()

        return msg

    def _persist_message_to_firestore(self, new_msg: dict) -> bool:
        today_str = datetime.now().strftime("%Y-%m-%d")
        try:
            remote_doc = firestore_get_parsed(CHAT_FIRESTORE_PATH)
            if not remote_doc or remote_doc.get("date") != today_str:
                existing_msgs = []
            else:
                existing_msgs = remote_doc.get("messages") or []
                if not isinstance(existing_msgs, list):
                    existing_msgs = []

            # Chống trùng lặp msg_id trong mảng Firestore
            seen_ids = {str(m.get("msg_id", "")) for m in existing_msgs if isinstance(m, dict)}
            if new_msg["msg_id"] not in seen_ids:
                existing_msgs.append(new_msg)

            existing_msgs.sort(key=lambda x: float(x.get("timestamp") or 0.0) if isinstance(x, dict) else 0.0)
            existing_msgs = existing_msgs[-MAX_DAILY_MESSAGES:]

            payload = {
                "date": today_str,
                "updated_at": time.time(),
                "messages": existing_msgs,
            }
            self._save_local_cache(payload)
            return firestore_set(CHAT_FIRESTORE_PATH, payload)
        except Exception as e:
            _log(f"[ChatService] Lỗi lưu tin nhắn lên Firestore: {e}")
            return False

    # ─── KHỞI ĐỘNG / DỪNG DỊCH VỤ NGẦM ──────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        # Nạp cache cục bộ trong ngày trước (0ms)
        today_str = datetime.now().strftime("%Y-%m-%d")
        cached = self._load_local_cache()
        if cached and cached.get("date") == today_str:
            for m in cached.get("messages") or []:
                self._ingest_message(m, is_realtime_event=False)
            self.history_loaded.emit(self.get_visible_messages())

        self._udp_thread = threading.Thread(target=self._udp_listen_loop, daemon=True)
        self._udp_thread.start()

        self._cloud_thread = threading.Thread(target=self._firestore_poll_loop, daemon=True)
        self._cloud_thread.start()

    def stop(self) -> None:
        self._running = False

    def _udp_listen_loop(self) -> None:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", CHAT_UDP_PORT))
            sock.settimeout(0.5)
            while self._running:
                try:
                    data, _addr = sock.recvfrom(8192)
                    packet = json.loads(data.decode("utf-8"))
                    if isinstance(packet, dict) and packet.get("type") == "AUTOQ_CHAT":
                        msg = packet.get("msg")
                        if isinstance(msg, dict):
                            self._ingest_message(msg, is_realtime_event=True)
                except socket.timeout:
                    continue
                except Exception:
                    continue
        except Exception as e:
            _log(f"[ChatUDP] Không thể bind cổng UDP {CHAT_UDP_PORT} (chỉ dùng Firestore): {e}")
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def _firestore_poll_loop(self) -> None:
        poll_tick = 0
        while self._running:
            today_str = datetime.now().strftime("%Y-%m-%d")
            try:
                doc_data = firestore_get_parsed(CHAT_FIRESTORE_PATH)
                if doc_data is None and self._running:
                    # Tự động khởi tạo tài liệu chat ngày hôm nay nếu chưa có
                    init_doc = {
                        "date": today_str,
                        "updated_at": time.time(),
                        "messages": [],
                    }
                    firestore_set(CHAT_FIRESTORE_PATH, init_doc)
                    doc_data = init_doc

                if isinstance(doc_data, dict):
                    if doc_data.get("date") != today_str:
                        # Sang ngày mới -> Xóa lịch sử ngày cũ
                        with self._lock:
                            self._seen_msg_ids.clear()
                            self._messages.clear()
                            self._unread_count = 0
                        reset_doc = {
                            "date": today_str,
                            "updated_at": time.time(),
                            "messages": [],
                        }
                        firestore_set(CHAT_FIRESTORE_PATH, reset_doc)
                        self._save_local_cache(reset_doc)
                        self.history_loaded.emit([])
                    else:
                        msgs = doc_data.get("messages") or []
                        self._save_local_cache(doc_data)
                        is_realtime = self._cold_start_done
                        added_any = False
                        for m in msgs:
                            if self._ingest_message(m, is_realtime_event=is_realtime):
                                added_any = True
                        if not self._cold_start_done:
                            self._cold_start_done = True
                            self.history_loaded.emit(self.get_visible_messages())
                        elif added_any:
                            self.history_loaded.emit(self.get_visible_messages())

                # Mỗi 4 chu kỳ (~10 giây), cập nhật danh sách Bác sĩ đang ngồi ở từng phòng
                if poll_tick % 4 == 0 and self._running:
                    self._refresh_room_doctors_from_cloud(today_str)
                poll_tick += 1
            except Exception as e:
                _log(f"[ChatService] Lỗi đồng bộ Firestore: {e}")

            for _ in range(12):
                if not self._running:
                    break
                time.sleep(0.2)

    def _refresh_room_doctors_from_cloud(self, today_str: str) -> None:
        try:
            docs = firestore_list("autoq_queues", page_size=30)
            new_map: dict[str, str] = {}
            for raw_doc in docs:
                doc_id = doc_id_from_name(raw_doc)
                if doc_id.startswith("room_") and doc_id != "room_chat_daily":
                    r_id = doc_id.replace("room_", "").strip().lower()
                    if r_id in ROOM_DEFINITIONS:
                        parsed = doc_to_dict(raw_doc)
                        if parsed.get("date") == today_str:
                            doc_name = (
                                parsed.get("duty_doctor")
                                if parsed.get("is_duty_mode") and parsed.get("duty_doctor")
                                else parsed.get("doctor_name")
                            )
                            doc_clean = str(doc_name or "").strip()
                            if doc_clean and doc_clean != "---":
                                new_map[r_id] = doc_clean
            with self._lock:
                changed = (new_map != self._room_doctors)
                self._room_doctors = new_map
            if changed:
                self.room_doctors_updated.emit(dict(new_map))
        except Exception:
            pass
