# =============================================================================
# FILE: tts_service.py
# MÔ TẢ: Hệ thống đọc loa gọi số tự động (Text-to-Speech) Tiếng Việt cho AUTOQ.
#        Hỗ trợ chế độ Trạm Phát Loa Trung Tâm (Central Speaker Hub - Phòng 2):
#          - Hàng đợi phát âm thanh tuần tự FIFO đa phòng (không ngắt lời phòng khác)
#          - Gộp lệnh thông minh nếu cùng 1 phòng bấm liên tiếp khi đang chờ tới lượt
#          - Tầng 1: Local Audio Cache + Background Pre-fetching 3 số tiếp theo (0ms)
#          - Tầng 2: Google Translate TTS Vietnamese (Mặc định chính: nhanh ~0.15s)
#          - Tầng 3: Offline Vietnamese Voice Pack (assets/tts_offline - 100% không cần mạng)
#          - Tầng 4: Qt QTextToSpeech / Windows SAPI5 Fallback
# =============================================================================

import os
import sys
import re
import math
import wave
import struct
import hashlib
import threading
import glob
import ctypes
import urllib.request
import urllib.parse
from collections import deque

os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg*=false")

from PySide6.QtCore import QObject, Signal, QUrl, QTimer
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
import PySide6

# Ẩn cảnh báo C-level của FFmpeg ("[mp3 @ ...] Estimating duration from bitrate")
try:
    for _av_dll in glob.glob(os.path.join(os.path.dirname(PySide6.__file__), "*avutil*.dll")):
        ctypes.CDLL(_av_dll).av_log_set_level(16)  # AV_LOG_ERROR = 16
except Exception:
    pass

from config_manager import get_db_dir
from firestore_client import _log


def _resource_path(relative_path: str) -> str:
    """Lấy đường dẫn tài nguyên tương thích cả bộ cài đặt Inno Setup ({app}/assets),
    PyInstaller EXE (_MEIPASS) lẫn môi trường chạy code trực tiếp.
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        ext_path = os.path.join(exe_dir, relative_path)
        if os.path.exists(ext_path):
            return ext_path
    if hasattr(sys, "_MEIPASS"):
        mei_path = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(mei_path):
            return mei_path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, relative_path)


def number_to_vietnamese_tokens(n: int) -> list[str]:
    """Chuyển số nguyên dương (1..999) thành danh sách mã token âm thanh tiếng Việt chuẩn
    để phát âm Offline khi mất mạng.
    """
    n = int(n)
    if n <= 0:
        return ["0"]
    if n >= 1000:
        n = n % 1000

    tokens: list[str] = []
    hundreds = n // 100
    remainder = n % 100
    tens = remainder // 10
    units = remainder % 10

    if hundreds > 0:
        tokens.extend([str(hundreds), "tram"])
        if remainder == 0:
            return tokens
        if tens == 0:
            tokens.extend(["le", str(units)])
            return tokens

    if tens == 1:
        tokens.append("muoi")
        if units == 5:
            tokens.append("lam")
        elif units > 0:
            tokens.append(str(units))
    elif tens >= 2:
        tokens.extend([str(tens), "muoi_tone"])
        if units == 1:
            tokens.append("mot_tone")
        elif units == 4:
            tokens.append("tu")
        elif units == 5:
            tokens.append("lam")
        elif units > 0:
            tokens.append(str(units))
    else:
        tokens.append(str(units))

    return tokens


# Ánh xạ mã phòng sang câu đọc chuẩn tự nhiên & file âm thanh Offline dự phòng
ROOM_SPEECH_MAP: dict[str, tuple[str, str]] = {
    "1": ("phòng siêu âm 1", "vao_phong_sa_1.mp3"),
    "2": ("phòng siêu âm 2", "vao_phong_sa_2.mp3"),
    "3": ("phòng siêu âm 3", "vao_phong_sa_3.mp3"),
    "4": ("phòng siêu âm 4", "vao_phong_sa_4.mp3"),
    "5": ("phòng siêu âm 5", "vao_phong_sa_5.mp3"),
    "tmh": ("phòng nội soi tai mũi họng", "vao_phong_tmh.mp3"),
    "nsth": ("phòng nội soi tiêu hóa", "vao_phong_nsth.mp3"),
    "dtd": ("phòng điện tâm đồ", "vao_phong_dtd.mp3"),
    "dnd": ("phòng điện não đồ", "vao_phong_dnd.mp3"),
    "lhn": ("phòng đo lưu huyết não", "vao_phong_lhn.mp3"),
    "cnhh": ("phòng đo chức năng hô hấp", "vao_phong_cnhh.mp3"),
}


def normalize_room_speech(room_name: str, room_number: str = "1") -> str:
    """Chuẩn hóa tên phòng để câu đọc tự nhiên (VD: 'phòng siêu âm 1',
    'phòng nội soi tai mũi họng', 'phòng điện tâm đồ', ...).
    """
    r_id = str(room_number or "1").strip().lower()
    raw = (room_name or "").strip().lower()

    # Mở rộng các từ viết tắt phổ biến để giọng TTS đọc tròn vành rõ chữ
    raw = re.sub(r"\btmh\b", "tai mũi họng", raw)
    raw = re.sub(r"\bnsth\b", "nội soi tiêu hóa", raw)
    raw = re.sub(r"\bđtđ\b", "điện tâm đồ", raw)
    raw = re.sub(r"\bđnđ\b", "điện não đồ", raw)
    raw = re.sub(r"\blhn\b", "lưu huyết não", raw)
    raw = re.sub(r"\bcnhh\b", "chức năng hô hấp", raw)

    if not raw or raw == "---":
        if r_id in ROOM_SPEECH_MAP:
            return ROOM_SPEECH_MAP[r_id][0]
        return f"phòng siêu âm {r_id}"

    raw = re.sub(r"\b0+(\d+)\b", r"\1", raw)
    return raw


class TTSService(QObject):
    """Dịch vụ phát loa gọi bệnh nhân đa phòng (Central Speaker Hub FIFO Queue)."""

    # (room_number, stt_str, sentence, file_list)
    announcement_ready = Signal(str, str, str, list)
    # Phát tín hiệu cho UI khi bắt đầu đọc 1 câu của phòng bất kỳ: (room_number, stt_str, sentence)
    announcement_started = Signal(str, str, str)
    fallback_speak = Signal(str)

    VOICE_GOOGLE_DEFAULT = "google-vi"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cache_dir = os.path.join(get_db_dir(), "tts_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

        self.offline_dir = _resource_path(os.path.join("assets", "tts_offline"))

        # Ưu tiên sử dụng file nhạc hiệu assets/dingdong.wav do người dùng cung cấp;
        # nếu không có mới fallback sang chuông WAV tự tổng hợp trong cache_dir
        custom_chime_wav = _resource_path(os.path.join("assets", "dingdong.wav"))
        if os.path.exists(custom_chime_wav) and os.path.getsize(custom_chime_wav) > 1000:
            self.chime_path = custom_chime_wav
        else:
            self.chime_path = os.path.join(self.cache_dir, "chime_dingdong.wav")
            self._ensure_chime_wav()

        self.enabled = True
        self.volume = 1.0
        self.voice = self.VOICE_GOOGLE_DEFAULT
        self.play_chime = True

        # Hàng đợi cấp độ Lượt Gọi (FIFO đa phòng: mỗi phần tử là 1 dict {room, stt, sentence, files})
        self._announcement_queue: deque[dict] = deque()
        # Hàng đợi các file audio con của lượt gọi ĐANG phát hiện tại ([chime.wav, speech.mp3])
        self._current_files_queue: deque[str] = deque()
        self._is_playing = False
        self._current_room_playing = ""

        # Khởi tạo QMediaPlayer trên Main UI Thread
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(self.volume)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.errorOccurred.connect(self._on_player_error)

        # Khởi tạo QTextToSpeech dự phòng cuối cùng (nếu hệ điều hành có SAPI)
        self._qtts = None
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            self._qtts = QTextToSpeech(self)
        except Exception:
            self._qtts = None

        self.announcement_ready.connect(self._enqueue_announcement)
        self.fallback_speak.connect(self._speak_with_qtts)

    # ─── CẤU HÌNH ────────────────────────────────────────────────────────────

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        if not self.enabled:
            self._announcement_queue.clear()
            self._current_files_queue.clear()
            self._player.stop()
            self._is_playing = False
            self._current_room_playing = ""

    def set_volume(self, volume_0_to_100: int):
        self.volume = max(0.0, min(1.0, float(volume_0_to_100) / 100.0))
        self._audio_output.setVolume(self.volume)

    def set_voice(self, voice_name: str):
        if voice_name:
            self.voice = voice_name

    # ─── API GỌI SỐ CHÍNH & TẢI TRƯỚC (PRE-FETCH) ────────────────────────────

    def announce_patient(self, stt: str | int, room_name: str = "PHÒNG SIÊU ÂM 1", room_number: str = "1"):
        """Đọc loa mời bệnh nhân theo số thứ tự vào phòng siêu âm.
        Mẫu câu chuẩn: "Mời bệnh nhân số thứ tự 24 vào phòng siêu âm 1"
        Hỗ trợ xếp hàng FIFO an toàn khi gọi từ cả 5 phòng siêu âm.
        """
        if not self.enabled:
            return

        stt_str = str(stt).strip()
        if not stt_str or stt_str == "000" or stt_str == "CC":
            return

        try:
            num_int = int(stt_str)
        except ValueError:
            return

        r_num = str(room_number).strip() or "1"
        room_spoken = normalize_room_speech(room_name, r_num)
        sentence = f"Mời bệnh nhân số thứ tự {num_int} vào {room_spoken}"
        _log(f"[TTS Hub] Xếp hàng phát loa (Phòng {r_num}): '{sentence}'")

        threading.Thread(
            target=self._synthesize_worker,
            args=(sentence, num_int, r_num, room_spoken, f"{num_int:03d}"),
            daemon=True,
        ).start()

    def prefetch_upcoming(self, current_num: int, room_name: str = "PHÒNG SIÊU ÂM 1", room_number: str = "1"):
        """Tải ngầm trước 3 số tiếp theo của phòng vào ổ cứng để khi bấm TIẾP THEO phát ngay 0ms."""
        r_num = str(room_number).strip() or "1"
        room_spoken = normalize_room_speech(room_name, r_num)

        def _bg():
            for n in range(int(current_num) + 1, int(current_num) + 4):
                if n > 999:
                    break
                sentence = f"Mời bệnh nhân số thứ tự {n} vào {room_spoken}"
                cache_key = hashlib.md5(f"gtts_vi|{sentence}".encode("utf-8")).hexdigest()
                cached_mp3 = os.path.join(self.cache_dir, f"tts_{cache_key}.mp3")
                if not os.path.exists(cached_mp3) or os.path.getsize(cached_mp3) <= 256:
                    self._try_google_tts(sentence, cached_mp3)

        threading.Thread(target=_bg, daemon=True).start()

    def speak_custom(self, text: str):
        """Đọc một câu thông báo tùy chỉnh."""
        if not self.enabled or not text.strip():
            return
        threading.Thread(
            target=self._synthesize_worker,
            args=(text.strip(), None, "0", "phòng siêu âm", "---"),
            daemon=True,
        ).start()

    # ─── WORKER TỔNG HỢP ÂM THANH ĐA TẦNG (MẶC ĐỊNH GOOGLE TTS) ──────────────

    def _synthesize_worker(
        self,
        text: str,
        num_int: int | None,
        room_number: str,
        room_spoken: str,
        stt_formatted: str,
    ):
        cache_key = hashlib.md5(f"gtts_vi|{text}".encode("utf-8")).hexdigest()
        cached_mp3 = os.path.join(self.cache_dir, f"tts_{cache_key}.mp3")
        chime_list = [self.chime_path] if (self.play_chime and os.path.exists(self.chime_path)) else []

        # TẦNG 1: Kiểm tra Cache cục bộ (0ms latency, hoạt động cả khi mất mạng)
        if os.path.exists(cached_mp3) and os.path.getsize(cached_mp3) > 256:
            self.announcement_ready.emit(room_number, stt_formatted, text, chime_list + [cached_mp3])
            if num_int is not None:
                self.prefetch_upcoming(num_int, room_spoken, room_number)
            return

        # TẦNG 2 (MẶC ĐỊNH CHÍNH): Google Translate TTS Vietnamese (Tốc độ cao ~0.15s)
        if self._try_google_tts(text, cached_mp3):
            self.announcement_ready.emit(room_number, stt_formatted, text, chime_list + [cached_mp3])
            if num_int is not None:
                self.prefetch_upcoming(num_int, room_spoken, room_number)
            return

        # TẦNG 3 (DỰ PHÒNG OFFLINE TỨC THÌ): Bộ âm thanh Tiếng Việt đóng gói sẵn (assets/tts_offline)
        if num_int is not None:
            offline_segments = self._get_offline_segments(num_int, room_number)
            if offline_segments:
                _log(f"[TTS Hub] Đang phát Offline Backup Voice cho số {num_int} (Phòng {room_number})")
                self.announcement_ready.emit(room_number, stt_formatted, text, chime_list + offline_segments)
                return

        # TẦNG 4: Fallback cuối cùng qua QTextToSpeech / SAPI
        _log("[TTS Hub] Chuyển sang fallback QTextToSpeech nội bộ.")
        self.fallback_speak.emit(text)

    def _try_google_tts(self, text: str, out_path: str) -> bool:
        """Tổng hợp giọng đọc tự nhiên tiếng Việt qua Google Translate TTS."""
        try:
            q = urllib.parse.quote(text)
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=vi&client=tw-ob&q={q}"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                },
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                audio_bytes = resp.read()
                if len(audio_bytes) > 256:
                    with open(out_path, "wb") as f:
                        f.write(audio_bytes)
                    return True
        except Exception as e:
            _log(f"[TTS Hub] Google-TTS không khả dụng ({e}), chuyển sang Offline Backup...")
        return False

    def _get_offline_segments(self, num_int: int, room_number: str) -> list[str]:
        """Lấy danh sách các file âm thanh từ vựng tiếng Việt có sẵn trong assets/tts_offline/
        để phát tuần tự khi mất kết nối mạng Internet hoàn toàn.
        """
        try:
            if not os.path.isdir(self.offline_dir):
                return []

            prefix_file = os.path.join(self.offline_dir, "prefix_moi_bn.mp3")
            r_id = str(room_number).strip().lower()
            if r_id in ROOM_SPEECH_MAP:
                room_key = ROOM_SPEECH_MAP[r_id][1]
            else:
                room_key = f"vao_phong_sa_{r_id}.mp3"
            suffix_file = os.path.join(self.offline_dir, room_key)
            if not os.path.exists(suffix_file):
                suffix_file = os.path.join(self.offline_dir, "vao_phong_sa_1.mp3")

            if not os.path.exists(prefix_file) or not os.path.exists(suffix_file):
                return []

            tokens = number_to_vietnamese_tokens(num_int)
            segment_files = [prefix_file]
            for tok in tokens:
                tok_file = os.path.join(self.offline_dir, f"num_{tok}.mp3")
                if not os.path.exists(tok_file):
                    return []
                segment_files.append(tok_file)
            segment_files.append(suffix_file)
            return segment_files
        except Exception as e:
            _log(f"[TTS Hub] Lỗi chuẩn bị Offline segments: {e}")
            return []

    # ─── HÀNG ĐỢI PHÁT ÂM THANH FIFO ĐA PHÒNG (KHÔNG NGẮT LỜI PHÒNG KHÁC) ────

    def _enqueue_announcement(self, room_number: str, stt_str: str, sentence: str, files: list):
        """Xếp yêu cầu phát loa vào hàng đợi FIFO đa phòng.
        - Không bao giờ ngắt ngang câu đang đọc dở của phòng khác.
        - Nếu cùng một phòng bấm liên tiếp khi câu trước của phòng đó vẫn đang nằm chờ
          trong hàng đợi (chưa phát), tự động cập nhật sang số mới nhất của phòng đó.
        """
        if not self.enabled or not files:
            return

        valid_files = [f for f in files if f and os.path.exists(f)]
        if not valid_files:
            return

        new_item = {
            "room": str(room_number),
            "stt": str(stt_str),
            "sentence": sentence,
            "files": valid_files,
        }

        # Kiểm tra xem phòng này đã có lệnh nào đang nằm chờ trong _announcement_queue chưa
        replaced = False
        for idx, pending in enumerate(self._announcement_queue):
            if pending["room"] == str(room_number):
                self._announcement_queue[idx] = new_item
                replaced = True
                break

        if not replaced:
            # Giới hạn tối đa 10 lệnh trong hàng đợi
            if len(self._announcement_queue) >= 10:
                self._announcement_queue.popleft()
            self._announcement_queue.append(new_item)

        # Nếu hiện tại loa đang rảnh, bắt đầu phát ngay lập tức
        if not self._is_playing:
            self._start_next_announcement()

    def _start_next_announcement(self):
        """Lấy lượt gọi tiếp theo từ hàng đợi FIFO các phòng để bắt đầu phát."""
        if not self._announcement_queue:
            self._is_playing = False
            self._current_room_playing = ""
            return

        item = self._announcement_queue.popleft()
        self._current_room_playing = item["room"]
        self._current_files_queue = deque(item["files"])
        self._is_playing = True

        self.announcement_started.emit(item["room"], item["stt"], item["sentence"])
        self._play_next_file_in_current()

    def _play_next_file_in_current(self):
        """Phát file tiếp theo trong lượt gọi hiện tại (VD: chime.wav -> speech.mp3)."""
        if not self._current_files_queue:
            # Đã phát xong trọn vẹn 1 câu thông báo của phòng hiện tại -> nghỉ 120ms rồi đọc phòng kế tiếp
            QTimer.singleShot(120, self._start_next_announcement)
            return

        next_file = self._current_files_queue.popleft()
        self._is_playing = True
        self._audio_output.setVolume(self.volume)
        self._player.setSource(QUrl.fromLocalFile(next_file))
        self._player.play()

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._play_next_file_in_current()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._play_next_file_in_current()

    def _on_player_error(self, error, error_string):
        _log(f"[TTS Hub] MediaPlayer error ({error}): {error_string}")
        self._play_next_file_in_current()

    def _speak_with_qtts(self, text: str):
        if self._qtts:
            try:
                self._qtts.setVolume(self.volume)
                self._qtts.say(text)
            except Exception as e:
                _log(f"[TTS Hub] Lỗi QTextToSpeech: {e}")

    # ─── TẠO CHUÔNG DING-DONG WAV MẶC ĐỊNH (0.50 GIÂY, PHẢN HỒI TỨC THÌ) ─────

    def _ensure_chime_wav(self):
        """Tổng hợp file chuông báo 'Ding-Dong' WAV chuẩn (0.50s gọn, không khoảng lặng thừa)."""
        if os.path.exists(self.chime_path) and os.path.getsize(self.chime_path) > 1000:
            return
        try:
            sample_rate = 22050
            notes = [
                (783.99, 0.20),  # Nốt G5 (Ding - 0.20s)
                (659.25, 0.30),  # Nốt E5 (Dong - 0.30s)
            ]
            samples = []
            for freq, duration in notes:
                num_samples = int(sample_rate * duration)
                for i in range(num_samples):
                    t = i / sample_rate
                    attack = min(1.0, t / 0.012)
                    decay = math.exp(-5.0 * t / duration)
                    amp = 0.34 * attack * decay
                    val = amp * (0.82 * math.sin(2 * math.pi * freq * t) + 0.18 * math.sin(4 * math.pi * freq * t))
                    samples.append(int(max(-1.0, min(1.0, val)) * 32767))

            with wave.open(self.chime_path, "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
        except Exception as e:
            _log(f"[TTS Hub] Không thể tạo file chuông báo: {e}")
