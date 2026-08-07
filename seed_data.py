#!/usr/bin/env python3
# =============================================================================
# FILE: seed_data.py
# MÔ TẢ: Script quản lý dữ liệu mẫu Firestore cho testing.
#
# CÁCH DÙNG:
#   python seed_data.py              → Seed tất cả (personnel + rooms + queues mẫu)
#   python seed_data.py --dump       → Dump dữ liệu hiện tại từ Firestore ra JSON
#   python seed_data.py --reset      → Reset tất cả queues về trạng thái rỗng
#   python seed_data.py --seed-only  → Chỉ seed queues với bệnh nhân mẫu (không đụng personnel/rooms)
# =============================================================================

import sys
import os
import json
import time
import argparse
from datetime import datetime

# Đảm bảo stdout hỗ trợ UTF-8 trên Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from firestore_client import (
    firestore_get, firestore_set, firestore_list,
    doc_to_dict, doc_id_from_name, parse_field,
    _log, FIRESTORE_BASE, FIREBASE_API_KEY
)

# ─── ĐƯỜNG DẪN FILE SEED DATA ───────────────────────────────────────────────
SEED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_data_firestore.json")


# ─── DỮ LIỆU BỆNH NHÂN MẪU ────────────────────────────────────────────────

SAMPLE_PATIENTS = {
    "1": {
        "room": "1",
        "last_number": 5,
        "current_calling": {
            "stt": "003",
            "ma_bn": "BN24001",
            "ten_bn": "NGUYỄN VĂN AN",
            "tuoi": 45,
            "ngay_sinh": "15/03/1981",
            "dich_vu": "Siêu âm ổ bụng (gan mật, tụy, lách, thận, bàng quang)",
            "timestamp": 0
        },
        "waiting_list": [
            {
                "stt": "004",
                "ma_bn": "BN24002",
                "ten_bn": "TRẦN THỊ BÍCH",
                "tuoi": 32,
                "ngay_sinh": "22/08/1994",
                "dich_vu": "Siêu âm thai\nSiêu âm ổ bụng",
                "timestamp": 0
            },
            {
                "stt": "005",
                "ma_bn": "BN24003",
                "ten_bn": "LÊ HOÀNG CƯỜNG",
                "tuoi": 58,
                "ngay_sinh": "10/01/1968",
                "dich_vu": "Siêu âm Doppler tim, van tim",
                "timestamp": 0
            },
        ]
    },
    "2": {
        "room": "2",
        "last_number": 3,
        "current_calling": {
            "stt": "002",
            "ma_bn": "BN24004",
            "ten_bn": "PHẠM THỊ DUNG",
            "tuoi": 67,
            "ngay_sinh": "05/11/1959",
            "dich_vu": "Siêu âm tuyến giáp",
            "timestamp": 0
        },
        "waiting_list": [
            {
                "stt": "003",
                "ma_bn": "BN24005",
                "ten_bn": "VÕ MINH ĐỨC",
                "tuoi": 28,
                "ngay_sinh": "30/06/1998",
                "dich_vu": "Siêu âm phần mềm\nSiêu âm khớp gối",
                "timestamp": 0
            },
        ]
    },
    "3": {
        "room": "3",
        "last_number": 4,
        "current_calling": {
            "stt": "003",
            "ma_bn": "BN24006",
            "ten_bn": "HOÀNG THỊ GIANG",
            "tuoi": 41,
            "ngay_sinh": "18/04/1985",
            "dich_vu": "Siêu âm vú hai bên",
            "timestamp": 0
        },
        "waiting_list": [
            {
                "stt": "004",
                "ma_bn": "BN24007",
                "ten_bn": "ĐẶNG VĂN HẢI",
                "tuoi": 73,
                "ngay_sinh": "02/09/1953",
                "dich_vu": "Siêu âm Doppler mạch máu chi dưới",
                "timestamp": 0
            },
        ]
    },
    "4": {
        "room": "4",
        "last_number": 2,
        "current_calling": None,
        "waiting_list": [
            {
                "stt": "001",
                "ma_bn": "BN24008",
                "ten_bn": "NGUYỄN THỊ KIM",
                "tuoi": 55,
                "ngay_sinh": "25/12/1971",
                "dich_vu": "Siêu âm ổ bụng\nSiêu âm tuyến giáp",
                "timestamp": 0
            },
            {
                "stt": "002",
                "ma_bn": "BN24009",
                "ten_bn": "BÙI QUANG LÂM",
                "tuoi": 36,
                "ngay_sinh": "14/07/1990",
                "dich_vu": "Siêu âm hệ tiết niệu",
                "timestamp": 0
            },
        ]
    },
    "5": {
        "room": "5",
        "last_number": 1,
        "current_calling": {
            "stt": "001",
            "ma_bn": "BN24010",
            "ten_bn": "TRỊNH THỊ MAI",
            "tuoi": 29,
            "ngay_sinh": "08/05/1997",
            "dich_vu": "Siêu âm thai 4D\nSiêu âm Doppler thai",
            "timestamp": 0
        },
        "waiting_list": []
    },
}


# ─── FUNCTIONS ───────────────────────────────────────────────────────────────

def seed_queues_with_samples():
    """Seed tất cả 5 phòng với bệnh nhân mẫu."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    now = time.time()

    _log("\n=== SEED HÀNG ĐỢI VỚI BỆNH NHÂN MẪU ===")

    for room_num, data in SAMPLE_PATIENTS.items():
        data["date"] = today_str

        # Cập nhật timestamp cho tất cả bệnh nhân
        if data.get("current_calling"):
            data["current_calling"]["timestamp"] = now

        for i, pat in enumerate(data.get("waiting_list", [])):
            pat["timestamp"] = now + (i + 1) * 60  # Mỗi BN cách nhau 1 phút

        path = f"autoq_queues/room_{room_num}"
        ok = firestore_set(path, data)
        status = "✅" if ok else "❌"

        bn_count = len(data.get("waiting_list", []))
        calling = data.get("current_calling")
        calling_name = calling.get("ten_bn", "") if calling else "(trống)"
        _log(f"  {status} Phòng {room_num}: Đang gọi={calling_name}, Chờ={bn_count} BN")

    _log("Xong!\n")


def reset_all_queues():
    """Reset tất cả 5 phòng về trạng thái rỗng."""
    today_str = datetime.now().strftime("%Y-%m-%d")

    _log("\n=== RESET TẤT CẢ HÀNG ĐỢI ===")

    for room_num in range(1, 6):
        data = {
            "room": str(room_num),
            "current_calling": None,
            "waiting_list": [],
            "last_number": 0,
            "date": today_str,
        }
        path = f"autoq_queues/room_{room_num}"
        ok = firestore_set(path, data)
        status = "✅" if ok else "❌"
        _log(f"  {status} Phòng {room_num}: Reset thành công")

    _log("Xong!\n")


def seed_from_file():
    """Seed toàn bộ dữ liệu từ file seed_data_firestore.json lên Firestore.
    Bao gồm: personnel, rooms, assignments.
    Sau đó seed queues với bệnh nhân mẫu.
    """
    if not os.path.exists(SEED_FILE):
        _log(f"❌ File seed data không tồn tại: {SEED_FILE}")
        _log("   Chạy 'python seed_data.py --dump' trước để tạo file này.")
        return False

    with open(SEED_FILE, 'r', encoding='utf-8') as f:
        all_data = json.load(f)

    _log("\n=== SEED DỮ LIỆU TỪ FILE ===")

    # 1. Seed personnel
    personnel_docs = all_data.get("personnel", {}).get("documents", [])
    _log(f"\n--- Personnel: {len(personnel_docs)} documents ---")
    for doc in personnel_docs:
        doc_id = doc_id_from_name(doc)
        fields_data = doc_to_dict(doc)
        ok = firestore_set(f"personnel/{doc_id}", fields_data)
        name = fields_data.get("name", "?")
        status = "✅" if ok else "❌"
        _log(f"  {status} {doc_id}: {name}")

    # 2. Seed rooms
    rooms_docs = all_data.get("rooms", {}).get("documents", [])
    _log(f"\n--- Rooms: {len(rooms_docs)} documents ---")
    for doc in rooms_docs:
        doc_id = doc_id_from_name(doc)
        fields_data = doc_to_dict(doc)
        ok = firestore_set(f"rooms/{doc_id}", fields_data)
        name = fields_data.get("name", "?")
        status = "✅" if ok else "❌"
        _log(f"  {status} {doc_id}: {name}")

    # 3. Seed assignments (roster)
    assignment_docs = all_data.get("assignments", {}).get("documents", [])
    _log(f"\n--- Assignments: {len(assignment_docs)} documents ---")
    for doc in assignment_docs:
        doc_id = doc_id_from_name(doc)
        fields_data = doc_to_dict(doc)
        ok = firestore_set(f"assignments/{doc_id}", fields_data)
        status = "✅" if ok else "❌"
        _log(f"  {status} {doc_id}")

    # 4. Seed queues với bệnh nhân mẫu
    seed_queues_with_samples()

    _log("=== SEED HOÀN TẤT ===\n")
    return True


def dump_firestore_data():
    """Dump toàn bộ dữ liệu hiện tại từ Firestore ra file JSON."""
    import urllib.request

    _log("\n=== DUMP DỮ LIỆU TỪ FIRESTORE ===")

    all_data = {}
    collections = ['autoq_queues', 'personnel', 'rooms']

    for col in collections:
        url = f"{FIRESTORE_BASE}/{col}?key={FIREBASE_API_KEY}&pageSize=100"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                all_data[col] = data
                docs = data.get("documents", [])
                _log(f"  ✅ {col}: {len(docs)} documents")
        except Exception as e:
            _log(f"  ❌ {col}: {e}")

    # Fetch assignments (roster cho tháng hiện tại và trước)
    today = datetime.now()
    roster_ids = [
        f"roster_{today.strftime('%Y-%m')}",
    ]
    # Thêm tháng trước
    if today.month == 1:
        roster_ids.append(f"roster_{today.year - 1}-12")
    else:
        roster_ids.append(f"roster_{today.year}-{today.month - 1:02d}")

    all_data["assignments"] = {"documents": []}
    for doc_id in roster_ids:
        url = f"{FIRESTORE_BASE}/assignments/{doc_id}?key={FIREBASE_API_KEY}"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                all_data["assignments"]["documents"].append(data)
                _log(f"  ✅ assignments/{doc_id}: found")
        except Exception as e:
            _log(f"  ⚠️  assignments/{doc_id}: {e}")

    # Lưu ra file
    output_path = SEED_FILE
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    file_size = os.path.getsize(output_path)
    _log(f"\n  💾 Đã lưu: {output_path} ({file_size:,} bytes)")
    _log("=== DUMP HOÀN TẤT ===\n")


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Quản lý dữ liệu mẫu Firestore cho AUTOQ testing"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dump", action="store_true",
                       help="Dump dữ liệu hiện tại từ Firestore ra file JSON")
    group.add_argument("--reset", action="store_true",
                       help="Reset tất cả hàng đợi về trạng thái rỗng")
    group.add_argument("--seed-only", action="store_true",
                       help="Chỉ seed hàng đợi với bệnh nhân mẫu (không đụng personnel/rooms)")

    args = parser.parse_args()

    if args.dump:
        dump_firestore_data()
    elif args.reset:
        reset_all_queues()
    elif args.seed_only:
        seed_queues_with_samples()
    else:
        # Mặc định: seed toàn bộ
        seed_from_file()


if __name__ == "__main__":
    main()
