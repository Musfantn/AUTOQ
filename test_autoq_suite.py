# =============================================================================
# FILE: test_autoq_suite.py
# MÔ TẢ: Bộ kiểm thử tự động toàn diện (Comprehensive Automated Test Suite)
#        cho Hệ thống Gọi số Tự động & Trạm Loa Trung Tâm AUTOQ (11 Phòng).
# =============================================================================

import os
import sys
import time
import json
import unittest
import threading
from datetime import datetime

os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg*=false")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, Qt

import firestore_client
import firestore_queue
from config_manager import ConfigManager, get_db_dir
from oncall_manager import OnCallManager
from tts_service import (
    TTSService,
    number_to_vietnamese_tokens,
    normalize_room_speech,
    ROOM_SPEECH_MAP,
)
from speaker_hub import (
    ALL_ROOM_IDS,
    ROOM_DEFINITIONS,
    SPEAKER_MODE_HUB,
    SPEAKER_MODE_CLIENT,
    SPEAKER_MODE_LOCAL,
    CentralSpeakerHub,
    broadcast_speaker_event,
    get_default_speaker_mode,
    get_room_display_name,
    get_room_short_name,
)
from admin_app import (
    is_winter_season,
    get_seasonal_shift_config,
    extract_first_case_time_str,
    write_autoq_excel_xlsx,
    AdminApp,
    AdminLoginDialog,
)
from tv_display import TVDisplay
from settings import SettingsWindow
from dashboard import Dashboard
from chat_service import ChatService, is_message_relevant_for_room
from chat_window import ChatWindow, ChatToastPopup
from version import APP_VERSION, parse_semver, is_newer_version
from updater import compute_file_sha256, UpdateDialog, AdminPublishUpdateDialog
from user_guide_dialog import UserGuideDialog


# Khởi tạo QApplication dùng chung cho toàn bộ test suite
_APP = QApplication.instance() or QApplication(sys.argv)


class Test01_RoomRegistryAndSpeakerModes(unittest.TestCase):
    """Kiểm thử danh mục 11 phòng khám & chế độ Trạm Loa Trung Tâm mặc định."""

    def test_all_11_rooms_registered(self):
        expected_ids = ["1", "2", "3", "4", "5", "tmh", "nsth", "dtd", "dnd", "lhn", "cnhh"]
        self.assertEqual(ALL_ROOM_IDS, expected_ids)
        self.assertEqual(len(ROOM_DEFINITIONS), 11)

        for r_id in expected_ids:
            info = ROOM_DEFINITIONS[r_id]
            self.assertEqual(info["id"], r_id)
            self.assertTrue(info["display_name"].startswith("PHÒNG "))
            self.assertTrue(len(info["short_name"]) > 0)
            self.assertTrue(len(info["combo_label"]) > 0)
            self.assertTrue(info["offline_mp3"].endswith(".mp3"))
            self.assertEqual(get_room_display_name(r_id), info["display_name"])
            self.assertEqual(get_room_short_name(r_id), info["short_name"])

    def test_default_speaker_mode_room2_is_hub(self):
        self.assertEqual(get_default_speaker_mode("2"), SPEAKER_MODE_HUB)
        for r_id in ALL_ROOM_IDS:
            if r_id != "2":
                self.assertEqual(
                    get_default_speaker_mode(r_id),
                    SPEAKER_MODE_CLIENT,
                    f"Phòng {r_id} phải mặc định là SPEAKER_MODE_CLIENT",
                )


class Test02_VietnameseTTSAndOfflineVoicePack(unittest.TestCase):
    """Kiểm thử chuẩn hóa câu đọc Tiếng Việt, tách âm tiết số 1..999 và bộ âm thanh Offline."""

    def test_number_to_vietnamese_tokens(self):
        cases = {
            1: ["1"],
            4: ["4"],
            5: ["5"],
            10: ["muoi"],
            11: ["muoi", "1"],
            14: ["muoi", "4"],
            15: ["muoi", "lam"],
            20: ["2", "muoi_tone"],
            21: ["2", "muoi_tone", "mot_tone"],
            24: ["2", "muoi_tone", "tu"],
            25: ["2", "muoi_tone", "lam"],
            100: ["1", "tram"],
            101: ["1", "tram", "le", "1"],
            104: ["1", "tram", "le", "4"],
            105: ["1", "tram", "le", "5"],
            115: ["1", "tram", "muoi", "lam"],
            234: ["2", "tram", "3", "muoi_tone", "tu"],
            999: ["9", "tram", "9", "muoi_tone", "9"],
        }
        for num, expected in cases.items():
            self.assertEqual(number_to_vietnamese_tokens(num), expected, f"Sai token cho số {num}")

    def test_normalize_room_speech_all_11_rooms(self):
        self.assertEqual(normalize_room_speech("PHÒNG SIÊU ÂM 2", "2"), "phòng siêu âm 2")
        self.assertEqual(normalize_room_speech("phòng siêu âm 4 tim -mạch", "4"), "phòng siêu âm 4")
        self.assertEqual(normalize_room_speech("PHÒNG SIÊU ÂM 4 TIM - MẠCH"), "phòng siêu âm 4")
        self.assertEqual(normalize_room_speech("PHÒNG SIÊU ÂM 3 SẢN PHỤ KHOA", "3"), "phòng siêu âm 3")
        self.assertEqual(normalize_room_speech("PHÒNG NỘI SOI TMH", "tmh"), "phòng nội soi tai mũi họng")
        self.assertEqual(normalize_room_speech("PHÒNG NSTH", "nsth"), "phòng nội soi tiêu hóa")
        self.assertEqual(normalize_room_speech("PHÒNG ĐTĐ", "dtd"), "phòng điện tâm đồ")
        self.assertEqual(normalize_room_speech("PHÒNG ĐNĐ", "dnd"), "phòng điện não đồ")
        self.assertEqual(normalize_room_speech("PHÒNG ĐO LHN", "lhn"), "phòng đo lưu huyết não")
        self.assertEqual(normalize_room_speech("PHÒNG ĐO CNHH", "cnhh"), "phòng đo chức năng hô hấp")
        # Khi truyền tên rỗng -> tự động suy từ mã phòng
        for r_id in ALL_ROOM_IDS:
            spoken = normalize_room_speech("", r_id)
            self.assertEqual(spoken, ROOM_SPEECH_MAP[r_id][0])

    def test_offline_voice_pack_and_custom_dingdong_wav(self):
        tts = TTSService()
        self.assertTrue(os.path.exists(tts.chime_path), "File nhạc hiệu dingdong.wav không tồn tại")
        self.assertGreater(os.path.getsize(tts.chime_path), 10000, "File dingdong.wav kích thước bất thường")

        # Kiểm tra đủ segment âm thanh Offline cho cả 11 phòng với các số phức tạp
        for r_id in ALL_ROOM_IDS:
            for sample_num in (1, 15, 24, 105, 321):
                segments = tts._get_offline_segments(sample_num, r_id)
                self.assertGreaterEqual(len(segments), 3, f"Thiếu segment offline cho phòng {r_id}, số {sample_num}")
                for seg_path in segments:
                    self.assertTrue(os.path.exists(seg_path), f"File offline không tồn tại: {seg_path}")
                    self.assertGreater(os.path.getsize(seg_path), 256)


class Test03_TTSMultiRoomFIFOQueueAndCoalescing(unittest.TestCase):
    """Kiểm thử hàng đợi FIFO đa phòng và gộp lệnh thông minh khi cùng 1 phòng bấm liên tiếp."""

    def test_fifo_multi_room_and_same_room_coalescing(self):
        tts = TTSService()
        # Giả lập loa đang bận phát câu của Phòng 2 để kiểm tra hàng đợi chờ (_announcement_queue)
        tts._is_playing = True
        tts._current_room_playing = "2"
        dummy_file = tts.chime_path

        # Phòng 1 bấm gọi 005 -> Phòng TMH bấm gọi 012 -> Phòng 1 bấm tiếp 006 -> Phòng NSTH bấm gọi 003
        tts._enqueue_announcement("1", "005", "Mời BN 5 vào phòng siêu âm 1", [dummy_file])
        tts._enqueue_announcement("tmh", "012", "Mời BN 12 vào phòng nội soi TMH", [dummy_file])
        tts._enqueue_announcement("1", "006", "Mời BN 6 vào phòng siêu âm 1", [dummy_file])
        tts._enqueue_announcement("nsth", "003", "Mời BN 3 vào phòng nội soi tiêu hóa", [dummy_file])

        # Kỳ vọng: Phòng 1 được cập nhật tại chỗ từ 005 -> 006, giữ nguyên thứ tự FIFO: [Phòng 1 (006), Phòng tmh (012), Phòng nsth (003)]
        queue_list = list(tts._announcement_queue)
        self.assertEqual(len(queue_list), 3)
        self.assertEqual((queue_list[0]["room"], queue_list[0]["stt"]), ("1", "006"))
        self.assertEqual((queue_list[1]["room"], queue_list[1]["stt"]), ("tmh", "012"))
        self.assertEqual((queue_list[2]["room"], queue_list[2]["stt"]), ("nsth", "003"))

        tts.set_enabled(False)


class Test04_CentralSpeakerHubDeduplicationAndUDP(unittest.TestCase):
    """Kiểm thử Trạm Phát Loa Trung Tâm (Phòng 2): Chống đọc lặp, chặn vọng ngược local_room, và UDP."""

    def test_deduplicator_and_local_room_suppression(self):
        tts = TTSService()
        tts.set_enabled(False)
        hub = CentralSpeakerHub(tts, local_room="2")

        # 1. Kiểm tra mark_and_should_announce chặn trùng lặp trong thời gian cooldown
        self.assertTrue(hub.mark_and_should_announce("tmh", "015", cooldown_sec=1.5))
        self.assertFalse(hub.mark_and_should_announce("tmh", "015", cooldown_sec=1.5))
        # Số khác hoặc phòng khác vẫn được phép đọc ngay lập tức
        self.assertTrue(hub.mark_and_should_announce("tmh", "016", cooldown_sec=1.5))
        self.assertTrue(hub.mark_and_should_announce("nsth", "015", cooldown_sec=1.5))

        # 2. Kiểm tra _process_room_snapshot KHÔNG phát lại lệnh của chính local_room ("2")
        received_events = []
        hub.remote_call_received.connect(lambda r, rn, s: received_events.append((r, rn, s)))

        today_str = datetime.now().strftime("%Y-%m-%d")
        now_ts = time.time()

        # Bước Cold-start sync lần đầu cho phòng 2 và phòng dtd
        hub._process_room_snapshot("2", {"date": today_str, "current_calling": None})
        hub._process_room_snapshot("dtd", {"date": today_str, "current_calling": None})
        self.assertEqual(len(received_events), 0)

        # Phòng 2 có số mới trên Firestore -> Hub phải BỎ QUA vì local_room == "2" đã phát trực tiếp 0ms
        hub._process_room_snapshot("2", {
            "date": today_str,
            "current_calling": {"stt": "001", "called_at": now_ts, "call_count": 1},
        })
        QCoreApplication.processEvents()
        self.assertEqual(len(received_events), 0, "Lỗi: Hub phát lặp lại sự kiện của chính Phòng 2 từ Firestore!")

        # Phòng Điện Tâm Đồ (dtd) có số mới trên Firestore -> Hub PHẢI nhận và phát loa
        hub._process_room_snapshot("dtd", {
            "date": today_str,
            "current_calling": {"stt": "008", "called_at": now_ts, "call_count": 1},
        })
        QCoreApplication.processEvents()
        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0][0], "dtd")
        self.assertEqual(received_events[0][2], "008")


class Test05_QueueEngineLogic(unittest.TestCase):
    """Kiểm thử toàn bộ nghiệp vụ gọi số, gọi lại, qua lượt, nhảy số, cấp cứu và ca đầu tiên."""

    def setUp(self):
        self.test_room = "cnhh"
        self._backup_data = firestore_queue.get_room_queue(self.test_room)

    def tearDown(self):
        if self._backup_data:
            firestore_queue.save_room_queue(self.test_room, self._backup_data)

    def test_full_queue_lifecycle(self):
        # 1. Reset về 000
        q = firestore_queue.reset_queue(self.test_room)
        self.assertEqual(q["last_number"], 0)
        self.assertIsNone(q["current_calling"])
        self.assertEqual(q["first_call_at"], 0.0)

        # 2. Gọi số đầu tiên (001) -> kiểm tra first_call_at được ghi nhận
        q = firestore_queue.next_patient(self.test_room)
        self.assertEqual(q["last_number"], 1)
        self.assertEqual(q["current_calling"]["stt"], "001")
        self.assertEqual(q["current_calling"]["call_count"], 1)
        self.assertGreater(q["first_call_at"], 0.0)
        first_ts = q["first_call_at"]

        # 3. Gọi lại số hiện tại (001) -> call_count tăng lên 2, is_recall = True
        q = firestore_queue.recall_current_patient(self.test_room)
        self.assertEqual(q["current_calling"]["stt"], "001")
        self.assertEqual(q["current_calling"]["call_count"], 2)
        self.assertTrue(q["current_calling"]["is_recall"])

        # 4. Bệnh nhân 001 chưa vào -> Bấm QUA LƯỢT (skip_current_and_next)
        #    001 vào missed_list, tự động gọi sang 002
        q = firestore_queue.skip_current_and_next(self.test_room)
        self.assertEqual(q["last_number"], 2)
        self.assertEqual(q["current_calling"]["stt"], "002")
        self.assertEqual(len(q["missed_list"]), 1)
        self.assertEqual(q["missed_list"][0]["stt"], "001")

        # 5. Gọi tiếp số 003 -> 002 được lưu vào history
        q = firestore_queue.next_patient(self.test_room)
        self.assertEqual(q["last_number"], 3)
        self.assertEqual(q["current_calling"]["stt"], "003")
        self.assertTrue(any(h["stt"] == "002" for h in q["history"]))

        # 6. Bệnh nhân 001 quay lại -> Gọi đích danh số 001 (recall_specific_number)
        #    001 biến mất khỏi missed_list, đang gọi là 001, NHƯNG last_number vẫn bảo toàn là 3!
        q = firestore_queue.recall_specific_number(self.test_room, "001")
        self.assertEqual(q["current_calling"]["stt"], "001")
        self.assertTrue(q["current_calling"]["is_recall"])
        self.assertEqual(q["last_number"], 3, "last_number phải được bảo toàn bằng 3 khi gọi lại số cũ!")
        self.assertEqual(len(q["missed_list"]), 0)

        # 7. Bấm TIẾP THEO sau khi khám xong cho 001 -> Phải nhảy lên 004 (không bị lùi về 002)
        q = firestore_queue.next_patient(self.test_room)
        self.assertEqual(q["last_number"], 4)
        self.assertEqual(q["current_calling"]["stt"], "004")
        self.assertEqual(q["first_call_at"], first_ts, "first_call_at trong ngày không được bị ghi đè!")

        # 8. Nhảy đến số 010 (set_number)
        q = firestore_queue.set_number(self.test_room, 10)
        self.assertEqual(q["last_number"], 10)
        self.assertEqual(q["current_calling"]["stt"], "010")

        # 9. Bật / Tắt Cấp cứu (toggle_emergency)
        q = firestore_queue.toggle_emergency(self.test_room)
        self.assertEqual(q["current_calling"]["stt"], "CC")
        q = firestore_queue.toggle_emergency(self.test_room)
        self.assertIsNone(q["current_calling"])


class Test06_AdminSeasonalShiftsAndAuth(unittest.TestCase):
    """Kiểm thử lịch làm việc Mùa Đông / Mùa Hè, trích xuất Ca đầu tiên và Mật khẩu Admin."""

    def test_winter_and_summer_boundary_dates(self):
        # Mùa Đông: 16/10 -> 15/04
        self.assertTrue(is_winter_season(datetime(2026, 10, 16)))
        self.assertTrue(is_winter_season(datetime(2026, 12, 25)))
        self.assertTrue(is_winter_season(datetime(2026, 1, 15)))
        self.assertTrue(is_winter_season(datetime(2026, 4, 15)))

        # Mùa Hè: 16/04 -> 15/10
        self.assertFalse(is_winter_season(datetime(2026, 4, 16)))
        self.assertFalse(is_winter_season(datetime(2026, 7, 1)))
        self.assertFalse(is_winter_season(datetime(2026, 10, 15)))

    def test_seasonal_shift_exact_minutes(self):
        w_cfg = get_seasonal_shift_config(force_season="WINTER")
        self.assertEqual(w_cfg["morning_start_min"], 7 * 60)          # 07:00
        self.assertEqual(w_cfg["morning_end_min"], 11 * 60 + 30)      # 11:30
        self.assertEqual(w_cfg["afternoon_start_min"], 13 * 60 + 30)  # 13:30
        self.assertEqual(w_cfg["afternoon_end_min"], 17 * 60)         # 17:00

        s_cfg = get_seasonal_shift_config(force_season="SUMMER")
        self.assertEqual(s_cfg["morning_start_min"], 7 * 60)          # 07:00
        self.assertEqual(s_cfg["morning_end_min"], 11 * 60 + 30)      # 11:30
        self.assertEqual(s_cfg["afternoon_start_min"], 14 * 60)       # 14:00
        self.assertEqual(s_cfg["afternoon_end_min"], 17 * 60 + 30)    # 17:30

    def test_extract_first_case_time_str(self):
        self.assertEqual(extract_first_case_time_str({}), "---")
        ts_0715 = datetime(2026, 11, 13, 7, 15, 30).timestamp()
        ts_0800 = datetime(2026, 11, 13, 8, 0, 0).timestamp()
        sample_q = {
            "first_call_at": ts_0715,
            "history": [{"stt": "001", "called_at": ts_0800}],
        }
        self.assertEqual(extract_first_case_time_str(sample_q), "07:15:30")

    def test_admin_password_cloud_roundtrip(self):
        orig_pwd = firestore_queue.get_admin_password()
        try:
            self.assertTrue(firestore_queue.set_admin_password("999"))
            self.assertEqual(firestore_queue.get_admin_password(), "999")
        finally:
            firestore_queue.set_admin_password(orig_pwd or "123")
        self.assertEqual(firestore_queue.get_admin_password(), orig_pwd or "123")


class Test07_SQLiteConcurrencyAndGUIComponents(unittest.TestCase):
    """Kiểm thử đa luồng SQLite (ConfigManager / OnCallManager) và khởi tạo GUI 11 phòng."""

    def test_sqlite_multithread_safety(self):
        cfg = ConfigManager()
        oncall = OnCallManager()
        errors = []

        def worker_cfg():
            try:
                for _ in range(10):
                    _ = cfg.get("room_number", "1")
            except Exception as e:
                errors.append(e)

        def worker_oncall():
            try:
                for _ in range(10):
                    _ = oncall.get_all()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker_cfg) for _ in range(3)] + [
            threading.Thread(target=worker_oncall) for _ in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Lỗi truy cập SQLite đa luồng: {errors}")

    def test_gui_widgets_all_11_rooms(self):
        tv = TVDisplay("PHÒNG SIÊU ÂM 1")
        for r_id in ALL_ROOM_IDS:
            r_name = get_room_display_name(r_id)
            tv.update_room(r_name)
            self.assertEqual(tv.room_label.text(), r_name)

        tv.update_queue_data(
            {"stt": "042", "call_count": 2, "is_recall": True},
            [{"stt": "039", "call_count": 1}],
            42,
        )
        self.assertEqual(tv.number.text(), "042")
        self.assertEqual(tv.upcoming_cards[0]["badge"].text(), "043")
        self.assertEqual(tv.missed_cards[0]["badge"].text(), "039")

        sw = SettingsWindow()
        self.assertEqual(sw.room_number.count(), 11)
        self.assertFalse(sw.room_number.view().window().testAttribute(Qt.WA_TranslucentBackground))
        self.assertFalse(sw.cbo_speaker_mode.view().window().testAttribute(Qt.WA_TranslucentBackground))
        self.assertFalse(sw.doctor.view().window().testAttribute(Qt.WA_TranslucentBackground))
        self.assertFalse(sw.ktv.view().window().testAttribute(Qt.WA_TranslucentBackground))

        # Kiểm thử tính năng tự viết thêm KTV phụ máy vào dropdown KTV
        orig_custom_ktvs = sw._get_custom_ktv_list()
        try:
            test_ktv_name = "KTV. Nguyễn Thị Phụ Máy Test"
            self.assertTrue(sw.add_custom_ktv_name(test_ktv_name))
            self.assertEqual(sw.ktv.text(), test_ktv_name)
            self.assertIn(test_ktv_name, sw._get_custom_ktv_list())
        finally:
            sw._save_custom_ktv_list(orig_custom_ktvs)
            sw._populate_ktv_dropdown()

        from duty_mode_dialog import DutyModeDialog
        duty_dlg = DutyModeDialog(OnCallManager())
        self.assertFalse(duty_dlg.combo.view().window().testAttribute(Qt.WA_TranslucentBackground))
        duty_dlg.close()

        admin = AdminApp()
        self.assertEqual(len(admin.room_cards), 11)
        # Kiểm thử gắn Bác sĩ phụ trách vào phòng và thay thế tên phòng bằng tên Bác sĩ trong thống kê/báo cáo
        admin.room_doctor_map["1"] = "BS. Nguyễn Việt Phương"
        admin.apply_report_filter()
        self.assertEqual(admin.get_room_doctor_label("1"), "BS. Nguyễn Việt Phương")
        self.assertEqual(admin.table_room_summary.item(0, 0).text(), "BS. Nguyễn Việt Phương")

        # Kiểm thử xuất file Excel (.xlsx) chuẩn OOXML
        import tempfile
        import zipfile
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tf:
            tmp_xlsx = tf.name
        try:
            write_autoq_excel_xlsx(tmp_xlsx, [
                (["BÁO CÁO THỐNG KÊ"], "title"),
                (["Bác sĩ phụ trách", "Đã khám"], "header"),
                (["BS. Nguyễn Việt Phương", "15"], "data"),
            ])
            self.assertTrue(os.path.exists(tmp_xlsx))
            self.assertGreater(os.path.getsize(tmp_xlsx), 500)
            with zipfile.ZipFile(tmp_xlsx, "r") as zf:
                names = zf.namelist()
                self.assertIn("xl/workbook.xml", names)
                self.assertIn("xl/worksheets/sheet1.xml", names)
                sheet_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
                self.assertIn("BS. Nguyễn Việt Phương", sheet_xml)
        finally:
            if os.path.exists(tmp_xlsx):
                os.remove(tmp_xlsx)

        admin.close()
        sw.close()
        tv.close()

    def test_dashboard_optimistic_rapid_calls(self):
        tv = TVDisplay("PHÒNG SIÊU ÂM 1")
        dash = Dashboard(tv)
        dash.tts.set_enabled(False)
        dash.stop_realtime_listener()
        dash.speaker_hub.stop_hub()
        dash.heartbeat_timer.stop()

        dash.latest_queue_data = firestore_queue._new_queue("1")
        # Giả lập bác sĩ bấm liên tiếp 3 lần (Optimistic UI 0ms trước khi HTTP kịp trả về)
        dash._apply_optimistic_call("001", 1)
        self.assertEqual(dash.number.text(), "001")
        self.assertEqual(tv.number.text(), "001")

        last_n = int(dash.latest_queue_data["last_number"])
        dash._apply_optimistic_call(f"{last_n + 1:03d}", last_n + 1)
        self.assertEqual(dash.number.text(), "002")
        self.assertEqual(tv.number.text(), "002")

        last_n = int(dash.latest_queue_data["last_number"])
        dash._apply_optimistic_call(f"{last_n + 1:03d}", last_n + 1)
        self.assertEqual(dash.number.text(), "003")
        self.assertEqual(tv.number.text(), "003")

        dash.close()


class Test08_InterRoomChatServiceAndWindow(unittest.TestCase):
    """Kiểm thử tính năng Chat Nhanh Nội Bộ giữa các phòng (Deduplication, Lọc phòng nhận, Unread Badge, GUI)."""

    def test_chat_relevance_deduplication_and_unread_badge(self):
        chat_r2 = ChatService(local_room_id="2", local_doctor_name="BS. Lê Văn Linh")
        chat_r3 = ChatService(local_room_id="3", local_doctor_name="BS. Nguyễn Thị Mỹ Hạnh")
        chat_admin = ChatService(local_room_id="admin", local_doctor_name="Admin")

        # 1. Phòng 1 gửi tin nhắn riêng cho Phòng 2
        chat_r1 = ChatService(local_room_id="1", local_doctor_name="BS. Nguyễn Việt Phương")
        msg_1_to_2 = chat_r1.build_message("Nhờ Phòng 2 nhận giúp 3 ca siêu âm bụng!", target_room="2", is_urgent=True)

        self.assertTrue(is_message_relevant_for_room(msg_1_to_2, "1"))
        self.assertTrue(is_message_relevant_for_room(msg_1_to_2, "2"))
        self.assertTrue(is_message_relevant_for_room(msg_1_to_2, "admin"))
        self.assertFalse(is_message_relevant_for_room(msg_1_to_2, "3"))

        # 2. Phòng 2 nhận tin lần 1 (qua UDP) -> unread_count tăng lên 1
        self.assertTrue(chat_r2._ingest_message(msg_1_to_2, is_realtime_event=True))
        self.assertEqual(chat_r2.get_unread_count(), 1)
        self.assertEqual(len(chat_r2.get_visible_messages()), 1)

        # 3. Phòng 2 nhận lại cùng tin đó lần 2 (qua Firestore sync) -> Bộ lọc chống lặp chặn lại
        self.assertFalse(chat_r2._ingest_message(msg_1_to_2, is_realtime_event=True))
        self.assertEqual(chat_r2.get_unread_count(), 1, "Không được tăng unread khi trùng msg_id!")

        # 4. Phòng 3 nhận gói tin này nhưng không phải gửi cho Phòng 3 -> Không tăng unread, không hiển thị
        chat_r3._ingest_message(msg_1_to_2, is_realtime_event=True)
        self.assertEqual(chat_r3.get_unread_count(), 0)
        self.assertEqual(len(chat_r3.get_visible_messages()), 0)

        # 5. Admin nhận mọi tin nhắn điều phối giữa các phòng
        chat_admin._ingest_message(msg_1_to_2, is_realtime_event=True)
        self.assertEqual(chat_admin.get_unread_count(), 1)
        self.assertEqual(len(chat_admin.get_visible_messages()), 1)

        # 6. Khi Phòng 2 mở cửa sổ ChatWindow -> unread_count tự động reset về 0
        win = ChatWindow(chat_r2)
        self.assertFalse(win.cbo_target.view().window().testAttribute(Qt.WA_TranslucentBackground))
        quick_menu = win._build_quick_templates_menu()
        self.assertGreaterEqual(len(quick_menu.actions()), 6)
        chat_r2.set_chat_window_open(True)
        self.assertEqual(chat_r2.get_unread_count(), 0)

        toast = ChatToastPopup()
        toast.show_message_toast(msg_1_to_2)
        self.assertIn("Nhờ Phòng 2", toast.lbl_content.text())
        toast.close()
        win.close()


class Test09_AutoUpdateAndVersionCheck(unittest.TestCase):
    """Kiểm thử tính năng So sánh phiên bản SemVer, tính mã SHA-256 và hộp thoại Check/Auto Update."""

    def test_semver_comparison_and_sha256(self):
        self.assertEqual(parse_semver("v7.1.0"), (7, 1, 0))
        self.assertEqual(parse_semver("7.2"), (7, 2, 0))
        self.assertTrue(is_newer_version("7.2.0", "7.1.0"))
        self.assertTrue(is_newer_version("v7.1.1", "7.1.0"))
        self.assertFalse(is_newer_version("7.1.0", "7.1.0"))
        self.assertFalse(is_newer_version("6.9.9", "7.1.0"))

        import tempfile
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tf:
            tf.write(b"AUTOQ_TEST_INSTALLER_PAYLOAD")
            tmp_path = tf.name
        try:
            sha = compute_file_sha256(tmp_path)
            self.assertEqual(len(sha), 64)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_update_dialogs_initialization(self):
        sample_meta = {
            "latest_version": "99.0.0",
            "release_date": "2026-11-21",
            "download_url": "https://github.com/Musfantn/AUTOQ/releases/download/v99.0.0/AUTOQ_Setup_v99.0.0.exe",
            "file_size_mb": 98.6,
            "changelog": "- Bản cập nhật thử nghiệm v99.0.0",
        }
        dlg = UpdateDialog(initial_meta=sample_meta)
        self.assertTrue(dlg.btn_install.isEnabled())
        self.assertIn("99.0.0", dlg.lbl_latest_ver.text())
        dlg.close()

        guide = UserGuideDialog()
        self.assertEqual(guide.tabs.count(), 4)
        guide.close()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    os._exit(0 if result.wasSuccessful() else 1)
