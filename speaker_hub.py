# =============================================================================
# FILE: speaker_hub.py
# MÔ TẢ: Trạm Phát Loa Trung Tâm (Central Speaker Hub - Mặc định tại Phòng 2).
#        Nhận tín hiệu gọi số từ tất cả các phòng siêu âm (Phòng 1..5) qua 2 kênh:
#          1. LAN UDP Broadcast (Port 50505 - Độ trễ < 2ms, chạy được cả khi mất Internet)
#          2. Cloud Firestore Multi-Room Listener (autoq_queues/room_1..5 - Độ trễ < 100ms)
#        Tích hợp bộ lọc chống đọc lặp (Deduplicator) và Cold-Start Suppression.
# =============================================================================

import json
import time
import socket
import threading
from datetime import datetime
from PySide6.QtCore import QObject, Signal

import firestore_queue
from firestore_client import _log, firestore_list, doc_to_dict, doc_id_from_name

UDP_PORT = 50505
SPEAKER_MODE_HUB = "hub"        # Máy Trạm Phát Loa Trung Tâm (Mặc định cho Phòng Siêu Âm 2)
SPEAKER_MODE_CLIENT = "client"  # Máy Trạm Phòng Khám Phụ (Gửi tín hiệu về Phòng Siêu Âm 2, tắt loa tại chỗ)
SPEAKER_MODE_LOCAL = "local"    # Chỉ phát loa riêng của phòng hiện tại

# Danh mục toàn bộ 10 phòng khám / phòng chức năng trong hệ thống AUTOQ
ROOM_DEFINITIONS: dict[str, dict[str, str]] = {
    "1": {
        "id": "1",
        "code": "SA1",
        "display_name": "PHÒNG SIÊU ÂM 1",
        "short_name": "Phòng SA 1",
        "combo_label": "1 — Phòng Siêu Âm 1",
        "spoken": "phòng siêu âm 1",
        "offline_mp3": "vao_phong_sa_1.mp3",
    },
    "2": {
        "id": "2",
        "code": "SA2",
        "display_name": "PHÒNG SIÊU ÂM 2",
        "short_name": "Phòng SA 2",
        "combo_label": "2 — Phòng Siêu Âm 2 (Trạm Loa Trung Tâm)",
        "spoken": "phòng siêu âm 2",
        "offline_mp3": "vao_phong_sa_2.mp3",
    },
    "3": {
        "id": "3",
        "code": "SA3",
        "display_name": "PHÒNG SIÊU ÂM 3",
        "short_name": "Phòng SA 3",
        "combo_label": "3 — Phòng Siêu Âm 3",
        "spoken": "phòng siêu âm 3",
        "offline_mp3": "vao_phong_sa_3.mp3",
    },
    "4": {
        "id": "4",
        "code": "SA4",
        "display_name": "PHÒNG SIÊU ÂM 4",
        "short_name": "Phòng SA 4",
        "combo_label": "4 — Phòng Siêu Âm 4",
        "spoken": "phòng siêu âm 4",
        "offline_mp3": "vao_phong_sa_4.mp3",
    },
    "5": {
        "id": "5",
        "code": "SA5",
        "display_name": "PHÒNG SIÊU ÂM 5",
        "short_name": "Phòng SA 5",
        "combo_label": "5 — Phòng Siêu Âm 5",
        "spoken": "phòng siêu âm 5",
        "offline_mp3": "vao_phong_sa_5.mp3",
    },
    "tmh": {
        "id": "tmh",
        "code": "TMH",
        "display_name": "PHÒNG NỘI SOI TAI MŨI HỌNG",
        "short_name": "Nội Soi TMH",
        "combo_label": "TMH — Phòng Nội Soi Tai Mũi Họng (TMH)",
        "spoken": "phòng nội soi tai mũi họng",
        "offline_mp3": "vao_phong_tmh.mp3",
    },
    "nsth": {
        "id": "nsth",
        "code": "NSTH",
        "display_name": "PHÒNG NỘI SOI TIÊU HÓA",
        "short_name": "Nội Soi Tiêu Hóa",
        "combo_label": "NSTH — Phòng Nội Soi Tiêu Hóa",
        "spoken": "phòng nội soi tiêu hóa",
        "offline_mp3": "vao_phong_nsth.mp3",
    },
    "dtd": {
        "id": "dtd",
        "code": "ĐTĐ",
        "display_name": "PHÒNG ĐIỆN TÂM ĐỒ",
        "short_name": "Điện Tâm Đồ",
        "combo_label": "ĐTĐ — Phòng Điện Tâm Đồ",
        "spoken": "phòng điện tâm đồ",
        "offline_mp3": "vao_phong_dtd.mp3",
    },
    "dnd": {
        "id": "dnd",
        "code": "ĐNĐ",
        "display_name": "PHÒNG ĐIỆN NÃO ĐỒ",
        "short_name": "Điện Não Đồ",
        "combo_label": "ĐNĐ — Phòng Điện Não Đồ",
        "spoken": "phòng điện não đồ",
        "offline_mp3": "vao_phong_dnd.mp3",
    },
    "lhn": {
        "id": "lhn",
        "code": "LHN",
        "display_name": "PHÒNG ĐO LƯU HUYẾT NÃO",
        "short_name": "Đo Lưu Huyết Não",
        "combo_label": "LHN — Phòng Đo Lưu Huyết Não",
        "spoken": "phòng đo lưu huyết não",
        "offline_mp3": "vao_phong_lhn.mp3",
    },
    "cnhh": {
        "id": "cnhh",
        "code": "CNHH",
        "display_name": "PHÒNG ĐO CHỨC NĂNG HÔ HẤP",
        "short_name": "Đo CN Hô Hấp",
        "combo_label": "CNHH — Phòng Đo Chức Năng Hô Hấp",
        "spoken": "phòng đo chức năng hô hấp",
        "offline_mp3": "vao_phong_cnhh.mp3",
    },
}

ALL_ROOM_IDS: list[str] = list(ROOM_DEFINITIONS.keys())


def get_room_display_name(room_id: str) -> str:
    """Trả về tên hiển thị đầy đủ in hoa của phòng (VD: 'PHÒNG NỘI SOI TAI MŨI HỌNG')."""
    rid = str(room_id).strip().lower()
    info = ROOM_DEFINITIONS.get(rid)
    if info:
        return info["display_name"]
    return f"PHÒNG SIÊU ÂM {room_id}"


def get_room_short_name(room_id: str) -> str:
    """Trả về tên ngắn gọn của phòng dùng cho bảng thống kê Admin & Banner."""
    rid = str(room_id).strip().lower()
    info = ROOM_DEFINITIONS.get(rid)
    if info:
        return info["short_name"]
    return f"Phòng {room_id}"


def get_default_speaker_mode(room_number: str) -> str:
    """Mặc định Phòng Siêu Âm 2 là Trạm Phát Loa Trung Tâm ('hub'),
    tất cả các phòng khác (Siêu âm 1, 3, 4, 5, TMH, Điện tâm đồ, Điện não đồ,
    Lưu huyết não, Chức năng hô hấp) là máy trạm gửi tín hiệu về Phòng 2 ('client').
    """
    return SPEAKER_MODE_HUB if str(room_number).strip().lower() == "2" else SPEAKER_MODE_CLIENT


def broadcast_speaker_event(room_number: str, room_name: str, stt: str):
    """Phát gói tin UDP Broadcast trong mạng LAN (và localhost) để báo cho
    Máy Trạm Phát Loa Trung Tâm (Phòng Siêu Âm 2) đọc loa tức thì (< 2ms).
    """
    stt_str = str(stt).strip()
    if not stt_str or stt_str == "000" or stt_str == "CC":
        return

    r_id = str(room_number).strip().lower()
    payload = json.dumps({
        "type": "AUTOQ_CALL",
        "room": r_id,
        "room_name": str(room_name).strip() or get_room_display_name(r_id),
        "stt": stt_str,
        "ts": time.time(),
    }, ensure_ascii=False).encode("utf-8")

    def _send():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.2)
            # Gửi tới cả LAN broadcast và localhost (hỗ trợ cả khi test trên cùng 1 máy)
            for target_ip in ("255.255.255.255", "127.0.0.1"):
                try:
                    sock.sendto(payload, (target_ip, UDP_PORT))
                except Exception:
                    pass
            sock.close()
        except Exception as e:
            _log(f"[SpeakerHub] Lỗi gửi UDP Broadcast: {e}")

    threading.Thread(target=_send, daemon=True).start()


class CentralSpeakerHub(QObject):
    """Dịch vụ chạy trên Máy Trạm Phát Loa Trung Tâm (Phòng 2):
    Lắng nghe lệnh gọi số của cả 5 phòng siêu âm qua UDP LAN + Cloud Firestore
    và điều phối phát loa qua TTSService.
    """

    # Signal chuyển về Main UI Thread: (room_number, room_name, stt_str)
    remote_call_received = Signal(str, str, str)

    def __init__(self, tts_service, parent=None, local_room: str = "2"):
        super().__init__(parent)
        self.tts = tts_service
        self.local_room = str(local_room).strip()
        self._running = False
        self._udp_sock = None
        self._firestore_watch = None

        # Lưu vết chữ ký trạng thái của từng phòng trên Firestore để tránh đọc số cũ lúc mới mở app
        self._room_signatures: dict[str, str] = {}
        self._initial_sync_done: set[str] = set()

        # Bộ lọc chống đọc trùng giữa UDP (<2ms), Local Click (0ms) và Firestore (~1-3s)
        # Key: (room_str, stt_int) -> timestamp phát gần nhất
        self._recent_calls: dict[tuple[str, int], float] = {}
        self._dedup_lock = threading.Lock()

        self.remote_call_received.connect(self._on_remote_call_ui)

    def set_local_room(self, room_number: str):
        """Ghi nhận mã phòng của chính máy Trạm Loa Trung Tâm để bỏ qua vọng ngược từ Firestore."""
        self.local_room = str(room_number).strip().lower()

    # ─── QUẢN LÝ VÒNG ĐỜI HUB ────────────────────────────────────────────────

    def start_hub(self):
        """Khởi động Trạm Phát Loa Trung Tâm (lắng nghe toàn bộ 10 phòng khám/thăm dò chức năng)."""
        if self._running:
            return
        self._running = True
        self._room_signatures.clear()
        self._initial_sync_done.clear()

        # 1. Khởi động UDP Listener Thread (nhận tín hiệu LAN < 2ms)
        threading.Thread(target=self._udp_listener_loop, daemon=True).start()

        # 2. Khởi động Firestore Collection Watcher cho cả 11 phòng
        threading.Thread(target=self._firestore_multi_room_loop, daemon=True).start()

        _log(f"[SpeakerHub] Đã kích hoạt Trạm Phát Loa Trung Tâm (Lắng nghe {len(ALL_ROOM_IDS)} phòng khám & chức năng)")

    def stop_hub(self):
        """Dừng Trạm Phát Loa Trung Tâm."""
        self._running = False
        if self._udp_sock:
            try:
                self._udp_sock.close()
            except Exception:
                pass
            self._udp_sock = None

        if self._firestore_watch:
            try:
                self._firestore_watch.unsubscribe()
            except Exception:
                pass
            self._firestore_watch = None

    # ─── KHỬ TRÙNG LẶP & KÍCH HOẠT ĐỌC LOA ───────────────────────────────────

    def mark_and_should_announce(self, room_number: str, stt: str, cooldown_sec: float = 1.8) -> bool:
        """Kiểm tra xem lượt gọi (room_number, stt) đã vừa được kích hoạt trong khoảng
        `cooldown_sec` gần đây chưa (tránh việc UDP và Firestore kích hoạt trùng nhau).
        """
        r_str = str(room_number).strip().lower()
        try:
            num_int = int(str(stt).strip())
        except ValueError:
            return False

        now = time.time()
        key = (r_str, num_int)
        with self._dedup_lock:
            last_ts = self._recent_calls.get(key, 0.0)
            if now - last_ts < cooldown_sec:
                return False
            self._recent_calls[key] = now
            return True

    def trigger_announcement(self, room_number: str, room_name: str, stt: str, cooldown_sec: float = 1.8):
        """Gọi trực tiếp từ UI hoặc từ sự kiện nhận được để phát loa (có khử trùng lặp)."""
        r_str = str(room_number).strip().lower()
        r_name = str(room_name).strip() or get_room_display_name(r_str)
        if self.mark_and_should_announce(r_str, stt, cooldown_sec=cooldown_sec):
            self.remote_call_received.emit(r_str, r_name, str(stt).strip())

    def _on_remote_call_ui(self, room_number: str, room_name: str, stt: str):
        """Thực thi trên Main UI Thread: Đẩy vào hàng đợi FIFO của TTSService."""
        self.tts.announce_patient(stt=stt, room_name=room_name, room_number=room_number)

    # ─── KÊNH 1: LAN UDP BROADCAST LISTENER (< 2ms) ──────────────────────────

    def _udp_listener_loop(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", UDP_PORT))
            sock.settimeout(1.0)
            self._udp_sock = sock
        except Exception as e:
            _log(f"[SpeakerHub] Không thể mở cổng UDP {UDP_PORT}: {e}")
            return

        while self._running:
            try:
                data, _addr = sock.recvfrom(2048)
                msg = json.loads(data.decode("utf-8"))
                if msg.get("type") == "AUTOQ_CALL":
                    r_num = str(msg.get("room", "1")).strip().lower()
                    r_name = str(msg.get("room_name", "")).strip() or get_room_display_name(r_num)
                    stt = str(msg.get("stt", "")).strip()
                    if stt and stt != "000" and stt != "CC":
                        # Cho phép gọi lại liên tiếp cách nhau >= 0.8s qua UDP
                        self.trigger_announcement(r_num, r_name, stt, cooldown_sec=0.8)
            except socket.timeout:
                continue
            except Exception:
                if not self._running:
                    break

    # ─── KÊNH 2: CLOUD FIRESTORE MULTI-ROOM WATCHER (10 PHÒNG) ───────────────

    def _fetch_all_rooms_rest(self) -> dict[str, dict]:
        """Lấy dữ liệu toàn bộ 10 phòng khám chỉ bằng 1 HTTP GET duy nhất tới collection `autoq_queues`."""
        result: dict[str, dict] = {}
        docs = firestore_list("autoq_queues", page_size=30)
        for raw_doc in docs:
            doc_id = doc_id_from_name(raw_doc)  # VD: "room_1" .. "room_5", "room_tmh", ...
            if doc_id.startswith("room_"):
                r_str = doc_id.replace("room_", "").strip().lower()
                if r_str in ROOM_DEFINITIONS:
                    result[r_str] = doc_to_dict(raw_doc)
        return result

    def _firestore_multi_room_loop(self):
        """Lắng nghe thay đổi của toàn bộ 10 phòng trên Cloud Firestore (1-Request Batch REST + gRPC nếu có)."""
        # Bước 1: Đọc trạng thái ban đầu của các phòng chỉ bằng 1 request để ghi nhận chữ ký gốc
        # (Cold-Start Suppression) và tải trước (prefetch) 3 số tiếp theo cho các phòng đang hoạt động!
        try:
            initial_rooms = self._fetch_all_rooms_rest()
        except Exception:
            initial_rooms = {}

        for r_str in ALL_ROOM_IDS:
            if not self._running:
                return
            try:
                q_data = initial_rooms.get(r_str)
                if q_data is None:
                    self._room_signatures[r_str] = "EMPTY"
                    self._initial_sync_done.add(r_str)
                    continue
                sig = self._compute_signature(q_data)
                self._room_signatures[r_str] = sig
                self._initial_sync_done.add(r_str)

                last_num = int(q_data.get("last_number", 0))
                if last_num > 0 or r_str in ("1", "2", "3", "4", "5"):
                    self.tts.prefetch_upcoming(last_num, get_room_display_name(r_str), r_str)
            except Exception:
                self._initial_sync_done.add(r_str)

        # Bước 2: Thử dùng gRPC Stream nếu có cài đặt `google-cloud-firestore`,
        # nếu không có thì chạy chế độ Batch REST Watcher (1 HTTP GET / 1.5s cho cả 10 phòng)
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
                col_ref = db.collection("autoq_queues")

                def on_col_snapshot(col_snapshots, changes, read_time):
                    if not self._running:
                        return
                    for change in changes:
                        doc = change.document
                        if not doc.exists:
                            continue
                        doc_id = doc.id
                        if not doc_id.startswith("room_"):
                            continue
                        r_str = doc_id.replace("room_", "").strip().lower()
                        data = doc.to_dict() or {}
                        self._process_room_snapshot(r_str, data)

                self._firestore_watch = col_ref.on_snapshot(on_col_snapshot)
                _log("[SpeakerHub] Đã kết nối Firestore gRPC Multi-Room Stream cho tất cả các phòng")

                while self._running:
                    time.sleep(0.3)
                return
            except Exception as e:
                _log(f"[SpeakerHub] Chuyển sang Batch REST Watcher ({e})")

        _log(f"[SpeakerHub] Đã kích hoạt Firestore Batch REST Watcher cho {len(ALL_ROOM_IDS)} phòng (kết hợp LAN UDP < 2ms)")
        while self._running:
            try:
                rooms_map = self._fetch_all_rooms_rest()
                for r_str, q_data in rooms_map.items():
                    if not self._running:
                        break
                    self._process_room_snapshot(r_str, q_data)
            except Exception:
                pass
            for _ in range(15):
                if not self._running:
                    break
                time.sleep(0.1)

    def _compute_signature(self, q_data: dict) -> str:
        if not q_data:
            return "EMPTY"
        curr = q_data.get("current_calling")
        if not curr or not isinstance(curr, dict) or not curr.get("stt"):
            return "NONE"
        stt = str(curr.get("stt", "000"))
        called_at = curr.get("called_at", 0)
        recalled_at = curr.get("recalled_at", 0)
        call_cnt = curr.get("call_count", 1)
        return f"{stt}|{called_at}|{recalled_at}|{call_cnt}"

    def _process_room_snapshot(self, room_str: str, q_data: dict):
        """Xử lý dữ liệu mới của một phòng từ Firestore."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        if q_data.get("date") != today_str:
            return

        new_sig = self._compute_signature(q_data)
        old_sig = self._room_signatures.get(room_str)

        # Nếu phòng này chưa qua bước khởi tạo lần đầu -> chỉ lưu signature, không phát loa số cũ
        if room_str not in self._initial_sync_done:
            self._room_signatures[room_str] = new_sig
            self._initial_sync_done.add(room_str)
            return

        if new_sig == old_sig:
            return

        self._room_signatures[room_str] = new_sig

        # Bỏ qua phòng nội bộ của chính máy Hub (vì nút bấm trên Dashboard máy Hub đã kích hoạt loa trực tiếp 0ms)
        if room_str == self.local_room:
            return

        if new_sig in ("EMPTY", "NONE"):
            return

        curr = q_data.get("current_calling") or {}
        stt = str(curr.get("stt", "")).strip()
        if not stt or stt == "000" or stt == "CC":
            return

        # Kiểm tra thời gian gọi: chỉ đọc nếu sự kiện mới diễn ra trong vòng 30 giây gần đây
        event_ts = float(curr.get("recalled_at") or curr.get("called_at") or curr.get("timestamp") or 0)
        if event_ts > 0 and abs(time.time() - event_ts) > 30.0:
            return

        room_name = get_room_display_name(room_str)
        # Dùng cooldown_sec=12.0 cho kênh thụ động Firestore để không bao giờ đọc lặp lại lệnh đã nhận qua UDP (<2ms)
        self.trigger_announcement(room_str, room_name, stt, cooldown_sec=12.0)

