# =============================================================================
# FILE: oncall_manager.py
# MÔ TẢ: Quản lý danh sách bác sĩ trực, lưu vào SQLite local.
#        Hỗ trợ đồng bộ từ Firestore (TaskView).
# =============================================================================

import os
import re
import sqlite3
import threading

from config_manager import get_db_dir
from firestore_client import clean_name


class OnCallManager:
    """Quản lý danh sách bác sĩ trực, lưu vào SQLite local.
    Hỗ trợ đồng bộ từ Firestore (TaskView).
    """

    def __init__(self):
        self._lock = threading.Lock()
        db_path = os.path.join(get_db_dir(), "config.db")
        # check_same_thread=False cho phép dùng connection từ nhiều thread
        # _lock đảm bảo đồng bộ đọc/ghi an toàn giữa UI và SyncWorker
        self.conn = sqlite3.connect(db_path, timeout=10.0, check_same_thread=False)
        self._migrate()

    def _migrate(self):
        """Tạo / nâng cấp bảng oncall_doctors."""
        with self._lock:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS oncall_doctors(
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT    NOT NULL,
                phone        TEXT    NOT NULL DEFAULT '',
                firestore_id TEXT,
                role         TEXT    DEFAULT 'doctor',
                specialty    TEXT    DEFAULT ''
            )
            """)
            # Nâng cấp schema cũ nếu thiếu cột
            cols = [row[1] for row in self.conn.execute("PRAGMA table_info(oncall_doctors)")]
            for col, ddl in [
                ("firestore_id", "TEXT"),
                ("role",         "TEXT DEFAULT 'doctor'"),
                ("specialty",    "TEXT DEFAULT ''"),
            ]:
                if col not in cols:
                    self.conn.execute(f"ALTER TABLE oncall_doctors ADD COLUMN {col} {ddl}")
            self.conn.commit()

    # ─── CRUD cơ bản ──────────────────────────────────────────────────────────

    def get_all(self) -> list[tuple]:
        """Trả về [(id, name, phone), ...] – tương thích code cũ."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT id, name, phone FROM oncall_doctors ORDER BY role, name")
            return cur.fetchall()

    def get_all_full(self) -> list[dict]:
        """Trả về danh sách đầy đủ dưới dạng dict."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT id, name, phone, firestore_id, role, specialty
                FROM oncall_doctors ORDER BY role, name
            """)
            cols = ["id", "name", "phone", "firestore_id", "role", "specialty"]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def add(self, name: str, phone: str, firestore_id: str = None,
            role: str = "doctor", specialty: str = "") -> int:
        """Thêm BS trực mới. Trả về id mới."""
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO oncall_doctors(name, phone, firestore_id, role, specialty) VALUES(?,?,?,?,?)",
                (name.strip(), phone.strip(), firestore_id, role, specialty)
            )
            self.conn.commit()
            return cur.lastrowid

    def update(self, doc_id: int, name: str, phone: str):
        """Cập nhật thông tin BS trực."""
        with self._lock:
            self.conn.execute(
                "UPDATE oncall_doctors SET name=?, phone=? WHERE id=?",
                (name.strip(), phone.strip(), doc_id)
            )
            self.conn.commit()

    def delete(self, doc_id: int):
        """Xóa BS trực theo id."""
        with self._lock:
            self.conn.execute("DELETE FROM oncall_doctors WHERE id=?", (doc_id,))
            self.conn.commit()

    def get_by_id(self, doc_id: int) -> tuple | None:
        """Lấy (id, name, phone) hoặc None."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT id, name, phone FROM oncall_doctors WHERE id=?", (doc_id,))
            return cur.fetchone()

    # ─── Tìm kiếm ─────────────────────────────────────────────────────────────

    def find_by_name(self, name: str) -> dict | None:
        """Tìm nhân sự theo tên (chuẩn hóa lowercase + bỏ tiền tố BS./TK.)."""
        target = clean_name(name)
        all_rows = self.get_all_full()
        for row in all_rows:
            if clean_name(row["name"]) == target:
                return row
        # Thử khớp gần đúng (contains)
        for row in all_rows:
            n = clean_name(row["name"])
            if target in n or n in target:
                return row
        return None

    def find_by_firestore_id(self, firestore_id: str) -> dict | None:
        """Tìm nhân sự theo Firestore document ID."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT id, name, phone, firestore_id, role, specialty FROM oncall_doctors WHERE firestore_id=?",
                (firestore_id,)
            )
            row = cur.fetchone()
            if row:
                return dict(zip(["id", "name", "phone", "firestore_id", "role", "specialty"], row))
            return None

    # ─── Đồng bộ Firestore ────────────────────────────────────────────────────

    def sync_from_firestore(self, personnel_list: list[dict]) -> dict:
        """Xóa toàn bộ danh sách cũ và thêm mới từ Firestore (chỉ bác sĩ).

        Returns:
            {"added": int, "updated": 0, "total": int}
        """
        with self._lock:
            self.conn.execute("DELETE FROM oncall_doctors")
            self.conn.commit()

        added = 0
        for p in personnel_list:
            name  = p.get("name", "").strip()
            phone = p.get("phone", "").strip()
            role  = p.get("role", "doctor").strip()
            spec  = p.get("specialty", "").strip()
            fid   = p.get("id", "")

            if not name:
                continue

            self.add(name, phone, firestore_id=fid, role=role, specialty=spec)
            added += 1

        total = len(self.get_all())
        print(f"[OnCallManager] Sync: +{added} bác sĩ. Tổng: {total}")
        return {"added": added, "updated": 0, "total": total}
