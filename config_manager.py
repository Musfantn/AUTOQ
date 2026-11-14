# =============================================================================
# FILE: config_manager.py
# MÔ TẢ: Quản lý cấu hình app, lưu vào SQLite local (config.db).
# =============================================================================

import sqlite3
import os
import sys
import threading


def get_db_dir() -> str:
    """Trả về thư mục database.
    - Ưu tiên %PROGRAMDATA%/AUTOQ/database/ (đảm bảo không bị lỗi Access Denied trên Windows)
    - Fallback APPDATA/AUTOQ/database/ hoặc ./database/
    """
    programdata = os.environ.get("PROGRAMDATA")
    if programdata:
        base = os.path.join(programdata, "AUTOQ")
    elif getattr(sys, 'frozen', False):
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        base = os.path.join(appdata, "AUTOQ")
    else:
        base = os.path.abspath(".")
    db_dir = os.path.join(base, "database")
    os.makedirs(db_dir, exist_ok=True)
    return db_dir


class ConfigManager:
    """Đọc/ghi cấu hình key-value vào SQLite (An toàn đa luồng với WAL mode + Lock)."""

    def __init__(self):
        self._lock = threading.Lock()
        db_path = os.path.join(get_db_dir(), "config.db")
        self.conn = sqlite3.connect(db_path, timeout=10.0, check_same_thread=False)
        with self._lock:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS config(
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            self.conn.commit()

    def get(self, key: str, default: str = "") -> str:
        """Đọc giá trị config. Trả default nếu key không tồn tại."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT value FROM config WHERE key=?", (key,))
            row = cur.fetchone()
            return row[0] if row else default

    def set(self, key: str, value) -> None:
        """Ghi giá trị config (upsert)."""
        with self._lock:
            self.conn.execute(
                "REPLACE INTO config VALUES(?,?)",
                (key, str(value))
            )
            self.conn.commit()

    def close(self) -> None:
        """Đóng kết nối database an toàn."""
        with self._lock:
            if self.conn:
                self.conn.close()
                self.conn = None