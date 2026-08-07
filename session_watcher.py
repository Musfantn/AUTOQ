# =============================================================================
# FILE: D:\AUTOQ\session_watcher.py
# MÔ TẢ: Background session watcher app (QSystemTrayIcon + Custom GUI Reminder).
#         Tự động kết nối Chrome Debugging Port (9222), trích xuất JSESSIONID,
#         SESSIONID, và uuid (JWT) rồi lưu vào config.yaml của his_bridge.
#         Hiện thông báo nhắc nhở dạng UI hiện đại, không block người dùng.
# =============================================================================

import sys
import os
import json
import time
import socket
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget, QLabel, 
    QVBoxLayout, QHBoxLayout, QPushButton, QGraphicsDropShadowEffect,
    QFrame
)
from PySide6.QtCore import Qt, QTimer, Slot, QPropertyAnimation, QRect, QEasingCurve
from PySide6.QtGui import QIcon, QFont, QColor, QPainter, QBrush, QPen

import websocket

# Import config parser & Chrome debug helper
sys.path.append(str(Path(__file__).parent.resolve()))
from his_bridge.config import HisConfig
from his_lookup import open_chrome_debug, is_port_open

class PremiumNotification(QWidget):
    """Custom Glassmorphic notification dialog reminding the user not to close Chrome."""
    
    def __init__(self, message: str, parent=None):
        super().__init__(parent, Qt.WindowFlags.FramelessWindowHint | Qt.WindowFlags.WindowStaysOnTopHint | Qt.WindowFlags.SubWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(380, 160)
        self._message = message
        self._setup_ui()
        self._animate_in()

    def _setup_ui(self):
        # Shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 4)
        
        # Main background container
        self.container = QWidget(self)
        self.container.setGeometry(10, 10, 360, 140)
        self.container.setGraphicsEffect(shadow)
        
        # Stylesheet for glassmorphism look
        self.container.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 23, 42, 0.95);
                border: 1px solid rgba(233, 69, 96, 0.4);
                border-radius: 12px;
            }
        """)
        
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        
        # Header layout (Icon + Title)
        header_layout = QHBoxLayout()
        
        lbl_icon = QLabel("⚠️")
        lbl_icon.setStyleSheet("font-size: 24px; border: none; background: transparent;")
        header_layout.addWidget(lbl_icon)
        
        lbl_title = QLabel("CẢNH BÁO HỆ THỐNG")
        lbl_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #e94560; border: none; background: transparent;")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()
        
        # Close button
        btn_close = QPushButton("×")
        btn_close.setFixedSize(20, 20)
        btn_close.setStyleSheet("""
            QPushButton {
                color: #94a3b8;
                font-size: 16px;
                font-weight: bold;
                border: none;
                background: transparent;
            }
            QPushButton:hover {
                color: #e94560;
            }
        """)
        btn_close.clicked.connect(self._animate_out)
        header_layout.addWidget(btn_close)
        
        layout.addLayout(header_layout)
        
        # Message content
        lbl_msg = QLabel(self._message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setFont(QFont("Segoe UI", 10))
        lbl_msg.setStyleSheet("color: #f1f5f9; border: none; background: transparent; line-height: 1.4;")
        layout.addWidget(lbl_msg)
        
        # Bottom Accent Line
        accent = QFrame()
        accent.setFixedHeight(3)
        accent.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e94560, stop:1 #0f172a); border: none;")
        layout.addWidget(accent)

    def _animate_in(self):
        """Slide in notification from the bottom-right corner."""
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - self.width() - 20
        y_start = screen.height()
        y_end = screen.height() - self.height() - 60
        
        self.move(x, y_start)
        self.show()
        
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(600)
        self.anim.setStartValue(QRect(x, y_start, self.width(), self.height()))
        self.anim.setEndValue(QRect(x, y_end, self.width(), self.height()))
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()
        
        # Auto dismiss after 10 seconds
        QTimer.singleShot(10000, self._animate_out)

    def _animate_out(self):
        """Fade out and close the notification."""
        self.anim_fade = QPropertyAnimation(self, b"windowOpacity")
        self.anim_fade.setDuration(400)
        self.anim_fade.setStartValue(1.0)
        self.anim_fade.setEndValue(0.0)
        self.anim_fade.finished.connect(self.close)
        self.anim_fade.start()


class SessionWatcher(QSystemTrayIcon):
    """Background service that watches Chrome port 9222 and extracts cookies/tokens."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolTip("AutoQ Session Watcher")
        
        # Load sample or current config path (Ưu tiên ProgramData -> AppData -> Local Path)
        programdata = os.environ.get("PROGRAMDATA")
        pdata_cfg = Path(programdata) / "AUTOQ" / "his_bridge" / "config.yaml" if programdata else None
        if pdata_cfg and pdata_cfg.exists():
            self.config_path = pdata_cfg
        elif getattr(sys, 'frozen', False):
            appdata = os.environ.get("APPDATA", "")
            appdata_cfg = Path(appdata) / "AUTOQ" / "his_bridge" / "config.yaml" if appdata else None
            self.config_path = appdata_cfg if (appdata_cfg and appdata_cfg.exists()) else (Path(sys.executable).parent / "his_bridge" / "config.yaml")
        else:
            self.config_path = Path(__file__).parent / "his_bridge" / "config.yaml"
        
        self._setup_tray()
        
        # Polling timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_session)
        self.timer.start(5000) # Check every 5 seconds
        
        # Stored values to check for changes
        self.last_jsessionid = ""
        self.last_sessionid = ""
        self.last_uuid = ""

    def _setup_tray(self):
        # System Tray Menu
        self.menu = QMenu()
        
        self.action_status = self.menu.addAction("Trạng thái: Đang kết nối...")
        self.action_status.setEnabled(False)
        
        self.menu.addSeparator()
        
        action_launch = self.menu.addAction("Mở Chrome Debug (Port 9222)")
        action_launch.triggered.connect(open_chrome_debug)
        
        self.menu.addSeparator()
        
        action_exit = self.menu.addAction("Thoát")
        action_exit.triggered.connect(QApplication.quit)
        
        self.setContextMenu(self.menu)
        
        # Set a default tray icon (use warning emoji as a fallback icon)
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            self.setIcon(QIcon(str(icon_path)))
        else:
            # Create a simple colored square icon if file is missing
            self.setIcon(QIcon.fromTheme("browser"))

    def check_session(self):
        """Main check callback."""
        if not is_port_open(9222):
            self.action_status.setText("Trạng thái: Mất kết nối Chrome Debug")
            return
            
        self.action_status.setText("Trạng thái: Đang theo dõi...")
        
        try:
            # Query open tabs
            req = urllib.request.Request("http://127.0.0.1:9222/json", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                tabs = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return

        # Find VNPT HIS tab
        target_tab = None
        for tab in tabs:
            url = tab.get("url", "")
            if "bvhatinh.vncare.vn" in url and "webSocketDebuggerUrl" in tab:
                target_tab = tab
                break
                
        if not target_tab:
            return
            
        # Connect to CDP websocket
        ws_url = target_tab["webSocketDebuggerUrl"]
        try:
            ws = websocket.create_connection(ws_url, timeout=3, suppress_origin=True)
            
            # 1. Get All Cookies from Chrome (to bypass path /vnpthis/ filtering issues)
            cookie_cmd = {
                "id": 1,
                "method": "Network.getAllCookies",
                "params": {}
            }
            ws.send(json.dumps(cookie_cmd))
            cookie_res = json.loads(ws.recv())
            
            # 2. Get JWT Token - search across multiple locations
            js_script = """
            (function() {
                // Priority 1: cookie named 'uuid' or 'jwt' or 'token'
                var cookieMatch = document.cookie.match(/(?:uuid|jwt|token|access_token)=([A-Za-z0-9._-]+)/);
                if (cookieMatch && cookieMatch[1].startsWith('eyJ')) return cookieMatch[1];

                // Priority 2: localStorage - find any JWT (eyJ header)
                for (var i = 0; i < localStorage.length; i++) {
                    var key = localStorage.key(i);
                    var val = localStorage.getItem(key);
                    if (val && val.startsWith('eyJ') && val.split('.').length === 3) return val;
                    // Sometimes stored as JSON with token field
                    try {
                        var parsed = JSON.parse(val);
                        if (parsed && parsed.token && parsed.token.startsWith('eyJ')) return parsed.token;
                        if (parsed && parsed.uuid && parsed.uuid.startsWith('eyJ')) return parsed.uuid;
                        if (parsed && parsed.accessToken && parsed.accessToken.startsWith('eyJ')) return parsed.accessToken;
                    } catch(e) {}
                }

                // Priority 3: sessionStorage
                for (var j = 0; j < sessionStorage.length; j++) {
                    var sk = sessionStorage.key(j);
                    var sv = sessionStorage.getItem(sk);
                    if (sv && sv.startsWith('eyJ') && sv.split('.').length === 3) return sv;
                    try {
                        var sp = JSON.parse(sv);
                        if (sp && sp.token && sp.token.startsWith('eyJ')) return sp.token;
                        if (sp && sp.uuid && sp.uuid.startsWith('eyJ')) return sp.uuid;
                    } catch(e) {}
                }

                // Priority 4: global window variables
                if (window.token && window.token.startsWith && window.token.startsWith('eyJ')) return window.token;
                if (window.uuid && window.uuid.startsWith && window.uuid.startsWith('eyJ')) return window.uuid;
                if (window.accessToken && window.accessToken.startsWith && window.accessToken.startsWith('eyJ')) return window.accessToken;
                if (window.AppConfig && window.AppConfig.token) return window.AppConfig.token;
                if (window.appInfo && window.appInfo.token) return window.appInfo.token;

                return "";
            })()
            """
            eval_cmd = {
                "id": 2,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": js_script,
                    "returnByValue": True
                }
            }
            ws.send(json.dumps(eval_cmd))
            eval_res = json.loads(ws.recv())
            ws.close()
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] CDP websocket error: {e}")
            return
            
        # Parse results
        cookies = cookie_res.get("result", {}).get("cookies", [])
        jsessionid = ""
        sessionid = ""
        for c in cookies:
            domain = c.get("domain", "")
            if "bvhatinh.vncare.vn" in domain:
                name = c.get("name")
                value = c.get("value")
                if name == "JSESSIONID":
                    jsessionid = value
                elif name == "SESSIONID":
                    sessionid = value
                # Also check for uuid in cookies as fallback JWT source
                elif name in ("uuid", "jwt", "token", "access_token") and not jsessionid:
                    pass  # will pick up from eval_res below
                
        uuid_val = eval_res.get("result", {}).get("result", {}).get("value", "")
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] CDP Result: JSESSIONID={'OK' if jsessionid else 'MISSING'}, SESSIONID={'OK' if sessionid else 'MISSING'}, UUID_JWT={'OK (' + str(len(uuid_val)) + ' chars)' if uuid_val else 'MISSING'}")
        
        # If successfully retrieved valid cookies
        if jsessionid and sessionid:
            # Check if values changed
            if (jsessionid != self.last_jsessionid or 
                sessionid != self.last_sessionid or 
                uuid_val != self.last_uuid):
                
                self.update_config(jsessionid, sessionid, uuid_val)
                
                # Show notification reminder
                msg = (
                    "Da tu dong dong bo Cookies & Token VNPT HIS moi thanh cong!\n\n"
                    "QUAN TRONG: Vui long GIU cua so Chrome nay dang mo (khong tat Chrome) "
                    "de he thong tiep tuc hoat dong on dinh."
                )
                self.notifier = PremiumNotification(msg)
                
                # Update last known values
                self.last_jsessionid = jsessionid
                self.last_sessionid = sessionid
                self.last_uuid = uuid_val
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] WARNING: Chrome HIS tab found but cookies incomplete. Tab URL: {target_tab.get('url', '')}")

    def update_config(self, jsessionid: str, sessionid: str, uuid_val: str):
        """Update values inside config.yaml safely. Ghi vào cả hai vị trí."""
        # Danh sách đường dẫn config cần cập nhật
        paths_to_update = [self.config_path]
        
        # Thêm đường dẫn ProgramData nếu khác config_path
        programdata = os.environ.get("PROGRAMDATA")
        if programdata:
            pdata_cfg = Path(programdata) / "AUTOQ" / "his_bridge" / "config.yaml"
            if pdata_cfg != self.config_path:
                # Đảm bảo thư mục tồn tại
                pdata_cfg.parent.mkdir(parents=True, exist_ok=True)
                paths_to_update.append(pdata_cfg)
        
        updated_count = 0
        for cfg_path in paths_to_update:
            if not cfg_path.exists():
                # Nếu file ProgramData chưa tồn tại, copy từ source
                try:
                    if self.config_path.exists() and cfg_path != self.config_path:
                        import shutil
                        shutil.copy2(self.config_path, cfg_path)
                except Exception as copy_err:
                    print(f"Error copying config to {cfg_path}: {copy_err}")
                    continue
                if not cfg_path.exists():
                    continue
                    
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    
                new_lines = []
                in_session = False
                
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("session:"):
                        in_session = True
                        new_lines.append(line)
                        continue
                        
                    if in_session:
                        if stripped.startswith("jsessionid:"):
                            indent = line[:line.find("jsessionid:")]
                            new_lines.append(f'{indent}jsessionid: "{jsessionid}"\n')
                            continue
                        elif stripped.startswith("sessionid:"):
                            indent = line[:line.find("sessionid:")]
                            new_lines.append(f'{indent}sessionid: "{sessionid}"\n')
                            continue
                        elif stripped.startswith("uuid_jwt:"):
                            indent = line[:line.find("uuid_jwt:")]
                            new_lines.append(f'{indent}uuid_jwt: "{uuid_val}"\n')
                            in_session = False
                            continue
                            
                    new_lines.append(line)
                    
                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                    
                updated_count += 1
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [OK] Session saved to: {cfg_path}")
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [ERROR] Cannot save to {cfg_path}: {e}")
        
        if updated_count > 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Session sync complete ({updated_count} file(s) updated). JSESSIONID: ...{jsessionid[-10:]}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] WARNING: No config files were updated!")



def main():
    app = QApplication(sys.argv)
    
    # Avoid app closing if notification window is closed
    QApplication.setQuitOnLastWindowClosed(False)
    
    watcher = SessionWatcher()
    watcher.show()
    
    # Auto-launch Chrome debug if not open
    if not is_port_open(9222):
        print("Chrome Debug is not running. Launching it...")
        open_chrome_debug()
        
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
