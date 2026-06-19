import sqlite3
import os
import sys


def _get_db_dir() -> str:
    """Trả về thư mục database trong APPDATA (khi chạy exe) hoặc cạnh main.py (khi dev).
    
    Lý do dùng APPDATA: khi cài vào Program Files, thư mục đó read-only,
    app sẽ bị PermissionError nếu cố ghi database vào đó.
    APPDATA luôn ghi được với user hiện tại.
    """
    if getattr(sys, 'frozen', False):
        # Đang chạy từ file exe đã cài – lưu database vào %APPDATA%\AUTOQ
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        base = os.path.join(appdata, "AUTOQ")
    else:
        # Đang dev – lưu cạnh main.py
        base = os.path.abspath(".")
    db_dir = os.path.join(base, "database")
    os.makedirs(db_dir, exist_ok=True)
    return db_dir


class ConfigManager:

    def __init__(self):
        db_path = os.path.join(_get_db_dir(), "config.db")
        self.conn = sqlite3.connect(db_path)

        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS config(
        key TEXT PRIMARY KEY,
        value TEXT
        )
        """)

    def get(self,key,default=""):

        cur=self.conn.cursor()
        cur.execute("SELECT value FROM config WHERE key=?", (key,))
        row=cur.fetchone()

        if row:
            return row[0]

        return default


    def set(self,key,value):

        self.conn.execute(
            "REPLACE INTO config VALUES(?,?)",
            (key,str(value))
        )

        self.conn.commit()