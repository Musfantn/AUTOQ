# =============================================================================
# FILE: updater.py
# MÔ TẢ: Hệ thống Check Update & Auto Update cho AUTOQ (11 Phòng + Admin).
#        Sử dụng hạ tầng Server miễn phí 100%:
#          1. Cloud Firestore (autoq_queues/app_update_meta) - Kiểm tra bản mới tức thì,
#             không bị giới hạn Rate Limit khi 11 máy chung 1 IP bệnh viện.
#          2. GitHub Raw (version.json) & GitHub Releases CDN - Lưu trữ và tải bộ cài
#             tốc độ cao miễn phí kèm kiểm tra toàn vẹn tệp SHA-256.
#          3. Tự động cài đè Inno Setup (/VERYSILENT) bảo toàn 100% cấu hình phòng.
# =============================================================================

import os
import sys
import json
import time
import hashlib
import tempfile
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QFrame, QMessageBox, QLineEdit,
    QFormLayout, QCheckBox, QFileDialog, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal

from firestore_client import firestore_get_parsed, firestore_set, _log
from version import (
    APP_VERSION,
    APP_RELEASE_DATE,
    GITHUB_REPO,
    UPDATE_FIRESTORE_PATH,
    GITHUB_RAW_VERSION_URL,
    GITHUB_LATEST_RELEASE_API,
    DEFAULT_GITHUB_DOWNLOAD_URL,
    is_newer_version,
)


# ─── TIỆN ÍCH KIỂM TRA SHA-256 & LẤY METADATA CẬP NHẬT ───────────────────────

def compute_file_sha256(file_path: str) -> str:
    """Tính mã băm SHA-256 của một tệp tin để kiểm tra tính toàn vẹn."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def _normalize_update_meta(raw: dict) -> dict:
    ver = str(raw.get("latest_version") or raw.get("tag_name") or APP_VERSION).strip().lstrip("vV")
    dl_url = str(raw.get("download_url") or "").strip()
    if not dl_url:
        dl_url = f"https://github.com/{GITHUB_REPO}/releases/download/v{ver}/AUTOQ_Setup_v{ver}.exe"
    return {
        "latest_version": ver,
        "release_date": str(raw.get("release_date") or APP_RELEASE_DATE).strip(),
        "download_url": dl_url,
        "fallback_url": str(raw.get("fallback_url") or dl_url).strip(),
        "sha256": str(raw.get("sha256") or "").strip().lower(),
        "file_size_mb": float(raw.get("file_size_mb") or 98.6),
        "is_mandatory": bool(raw.get("is_mandatory", False)),
        "changelog": str(raw.get("changelog") or "Nâng cấp hiệu năng và tính năng hệ thống AUTOQ.").strip(),
    }


def fetch_update_metadata() -> dict:
    """Truy vấn thông tin phiên bản mới nhất theo thứ tự ưu tiên:
    1. Cloud Firestore (autoq_queues/app_update_meta)
    2. GitHub Raw CDN (version.json trên nhánh main)
    3. GitHub Releases REST API
    """
    # 1. Thử đọc từ Cloud Firestore trước (nhanh, không giới hạn rate-limit IP chung)
    try:
        fs_data = firestore_get_parsed(UPDATE_FIRESTORE_PATH)
        if isinstance(fs_data, dict) and fs_data.get("latest_version"):
            return _normalize_update_meta(fs_data)
    except Exception as e:
        _log(f"[Updater] Lỗi đọc Firestore update meta: {e}")

    # 2. Dự phòng: Đọc version.json từ GitHub Raw CDN
    try:
        url = f"{GITHUB_RAW_VERSION_URL}?t={int(time.time())}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"AUTOQ-Updater/{APP_VERSION}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw_json = json.loads(resp.read().decode("utf-8"))
            if isinstance(raw_json, dict) and raw_json.get("latest_version"):
                meta = _normalize_update_meta(raw_json)
                # Đồng bộ ngược lên Firestore nếu Firestore chưa có
                try:
                    firestore_set(UPDATE_FIRESTORE_PATH, meta)
                except Exception:
                    pass
                return meta
    except Exception as e:
        _log(f"[Updater] Không đọc được GitHub Raw version.json: {e}")

    # 3. Dự phòng cuối: GitHub Releases REST API
    try:
        req = urllib.request.Request(
            GITHUB_LATEST_RELEASE_API,
            headers={"User-Agent": f"AUTOQ-Updater/{APP_VERSION}", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            rel = json.loads(resp.read().decode("utf-8"))
            tag = str(rel.get("tag_name") or "").strip().lstrip("vV")
            dl_url = ""
            size_mb = 98.6
            for asset in rel.get("assets") or []:
                name = str(asset.get("name") or "")
                if name.lower().endswith(".exe"):
                    dl_url = str(asset.get("browser_download_url") or "")
                    sz = int(asset.get("size") or 0)
                    if sz > 0:
                        size_mb = round(sz / (1024 * 1024), 1)
                    break
            if tag:
                return _normalize_update_meta({
                    "latest_version": tag,
                    "release_date": str(rel.get("published_at") or "")[:10],
                    "download_url": dl_url,
                    "file_size_mb": size_mb,
                    "changelog": str(rel.get("body") or ""),
                })
    except Exception:
        pass

    # Fallback về phiên bản hiện tại nếu đang offline
    return _normalize_update_meta({
        "latest_version": APP_VERSION,
        "release_date": APP_RELEASE_DATE,
        "download_url": DEFAULT_GITHUB_DOWNLOAD_URL,
    })


def publish_update_metadata(meta: dict) -> bool:
    """Lưu thông tin bản cập nhật mới lên Cloud Firestore để cả 11 phòng nhận thông báo."""
    norm = _normalize_update_meta(meta)
    norm["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return firestore_set(UPDATE_FIRESTORE_PATH, norm)


# ─── WORKER THREADS: KIỂM TRA & TẢI BỘ CÀI ĐẶT ──────────────────────────────

class UpdateCheckWorker(QThread):
    """Luồng chạy ngầm kiểm tra phiên bản mới."""
    checked = Signal(dict, bool)  # (metadata_dict, has_new_version)
    error = Signal(str)

    def run(self):
        try:
            meta = fetch_update_metadata()
            latest_ver = meta.get("latest_version", APP_VERSION)
            has_new = is_newer_version(latest_ver, APP_VERSION)
            self.checked.emit(meta, has_new)
        except Exception as e:
            self.error.emit(str(e))


class UpdateDownloadWorker(QThread):
    """Luồng tải bộ cài đặt .exe từ GitHub Releases CDN kèm kiểm tra SHA-256."""
    progress = Signal(int, float, float)  # (percent, downloaded_mb, total_mb)
    finished_download = Signal(str)       # local_installer_path
    error = Signal(str)

    def __init__(self, meta: dict):
        super().__init__()
        self.meta = meta
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        ver = self.meta.get("latest_version", APP_VERSION)
        urls = []
        for k in ("download_url", "fallback_url"):
            u = (self.meta.get(k) or "").strip()
            if u and u not in urls:
                urls.append(u)

        if not urls:
            self.error.emit("Không tìm thấy đường dẫn tải bộ cài đặt (download_url trống).")
            return

        update_dir = os.path.join(tempfile.gettempdir(), "AUTOQ_Update")
        os.makedirs(update_dir, exist_ok=True)
        dest_path = os.path.join(update_dir, f"AUTOQ_Setup_v{ver}.exe")
        expected_sha256 = (self.meta.get("sha256") or "").strip().lower()
        expected_mb = float(self.meta.get("file_size_mb") or 98.6)

        last_err = ""
        for url in urls:
            if self._cancelled:
                return
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": f"AUTOQ-Updater/{APP_VERSION}"},
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    total_bytes = int(resp.headers.get("Content-Length") or 0)
                    total_mb = round(total_bytes / (1024 * 1024), 1) if total_bytes > 0 else expected_mb

                    downloaded_bytes = 0
                    with open(dest_path, "wb") as out_f:
                        while True:
                            if self._cancelled:
                                return
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            out_f.write(chunk)
                            downloaded_bytes += len(chunk)
                            dl_mb = round(downloaded_bytes / (1024 * 1024), 1)
                            if total_bytes > 0:
                                pct = min(99, int((downloaded_bytes * 100) / total_bytes))
                            else:
                                pct = min(99, int((dl_mb * 100) / max(1.0, total_mb)))
                            self.progress.emit(pct, dl_mb, total_mb)

                # Kiểm tra chữ ký file thực thi Windows ('MZ')
                if not os.path.exists(dest_path) or os.path.getsize(dest_path) < 1024 * 100:
                    raise RuntimeError("File tải về có dung lượng không hợp lệ.")

                with open(dest_path, "rb") as chk_f:
                    magic = chk_f.read(2)
                if magic != b"MZ":
                    raise RuntimeError("File tải về không phải là bộ cài đặt Windows (.exe).")

                # Kiểm tra mã băm SHA-256 nếu metadata có cung cấp
                if expected_sha256:
                    actual_sha256 = compute_file_sha256(dest_path)
                    if actual_sha256 != expected_sha256:
                        raise RuntimeError(
                            f"Mã kiểm tra SHA-256 không khớp!\n"
                            f"Kỳ vọng: {expected_sha256[:16]}...\n"
                            f"Thực tế: {actual_sha256[:16]}..."
                        )

                self.progress.emit(100, total_mb, total_mb)
                self.finished_download.emit(dest_path)
                return
            except urllib.error.HTTPError as he:
                if he.code == 404:
                    last_err = (
                        f"Bản cài đặt v{ver} chưa được tải lên GitHub Releases (HTTP 404).\n"
                        f"URL: {url}"
                    )
                else:
                    last_err = f"Lỗi HTTP {he.code} khi tải từ {url}: {he.reason}"
            except Exception as e:
                last_err = str(e)

        self.error.emit(last_err or "Không thể tải bộ cài đặt từ máy chủ.")


# ─── KÍCH HOẠT CÀI ĐẶT NGẦM INNO SETUP (/VERYSILENT) & TỰ KHỞI ĐỘNG LẠI ────

def launch_silent_installer_and_restart(installer_path: str) -> bool:
    """Tạo script chạy độc lập để:
    1. Đợi ứng dụng hiện tại đóng hoàn toàn (2 giây)
    2. Chạy bộ cài Inno Setup 7 ở chế độ /VERYSILENT (bảo toàn 100% cấu hình phòng trong %PROGRAMDATA%)
    3. Tự động mở lại ứng dụng sau khi nâng cấp xong.
    """
    if not os.path.exists(installer_path):
        return False

    if getattr(sys, "frozen", False):
        current_exe = sys.executable
    else:
        # Nếu đang chạy từ mã nguồn Python trong môi trường dev
        current_exe = os.path.join(os.path.abspath("."), "dist", "RadiologyQueue.exe")

    update_dir = os.path.join(tempfile.gettempdir(), "AUTOQ_Update")
    os.makedirs(update_dir, exist_ok=True)
    bat_path = os.path.join(update_dir, "run_autoq_upgrade.bat")

    bat_content = f"""@echo off
chcp 65001 >nul
timeout /t 2 /nobreak >nul
"{installer_path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /SP-
timeout /t 2 /nobreak >nul
if exist "{current_exe}" (
    start "" "{current_exe}"
)
del "%~f0"
"""
    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            creationflags=creation_flags,
            close_fds=True,
        )
        return True
    except Exception as e:
        _log(f"[Updater] Lỗi kích hoạt bộ cài đặt: {e}")
        return False


# ─── HỘP THOẠI KIỂM TRA & CẬP NHẬT PHẦN MỀM (UPDATEDIALOG) ──────────────────

class UpdateDialog(QDialog):
    """Hộp thoại kiểm tra phiên bản mới, hiển thị Changelog, tải bộ cài từ GitHub
    Releases CDN và tự động nâng cấp phần mềm.
    """

    def __init__(self, initial_meta: dict | None = None, parent=None):
        super().__init__(parent)
        self.meta = initial_meta
        self._check_worker: UpdateCheckWorker | None = None
        self._dl_worker: UpdateDownloadWorker | None = None

        self.setWindowTitle("Cập Nhật Phần Mềm Tự Động — AUTOQ")
        self.setMinimumSize(540, 440)
        self.setStyleSheet("""
            QDialog {
                background-color: #f8fafc;
                color: #0f172a;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                background: transparent;
                color: #0f172a;
            }
            QTextEdit {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
            }
            QProgressBar {
                border: 1px solid #94a3b8;
                border-radius: 7px;
                text-align: center;
                background-color: #e2e8f0;
                color: #0f172a;
                font-weight: bold;
                font-size: 12px;
                min-height: 22px;
            }
            QProgressBar::chunk {
                background-color: #16a34a;
                border-radius: 6px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # Title
        lbl_title = QLabel("🚀 KIỂM TRA & CẬP NHẬT PHẦN MỀM AUTOQ")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("font-size: 17px; font-weight: bold; color: #0B5FA5;")
        root.addWidget(lbl_title)

        # Info Box
        info_card = QFrame()
        info_card.setStyleSheet(
            "QFrame { background: #e0f2fe; border: 1px solid #7dd3fc; border-radius: 10px; }"
        )
        ic_layout = QVBoxLayout(info_card)
        ic_layout.setContentsMargins(14, 10, 14, 10)
        ic_layout.setSpacing(5)

        self.lbl_curr_ver = QLabel(f"📌 Phiên bản đang chạy trên máy:  v{APP_VERSION}")
        self.lbl_curr_ver.setStyleSheet("font-size: 14px; font-weight: bold; color: #0369a1; border: none;")

        self.lbl_latest_ver = QLabel("⏳ Đang kiểm tra phiên bản mới nhất trên máy chủ...")
        self.lbl_latest_ver.setStyleSheet("font-size: 14px; font-weight: bold; color: #0f172a; border: none;")

        self.lbl_server_info = QLabel("☁️ Máy chủ: Cloud Firestore + GitHub Releases CDN (Miễn phí)")
        self.lbl_server_info.setStyleSheet("font-size: 12px; color: #475569; border: none;")

        ic_layout.addWidget(self.lbl_curr_ver)
        ic_layout.addWidget(self.lbl_latest_ver)
        ic_layout.addWidget(self.lbl_server_info)
        root.addWidget(info_card)

        # Changelog
        lbl_log = QLabel("📋 Nội dung bản cập nhật (Changelog):")
        lbl_log.setStyleSheet("font-size: 13px; font-weight: bold; color: #334155;")
        root.addWidget(lbl_log)

        self.txt_changelog = QTextEdit()
        self.txt_changelog.setReadOnly(True)
        root.addWidget(self.txt_changelog, 1)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #0369a1;")
        root.addWidget(self.lbl_status)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_recheck = QPushButton("🔄 Kiểm tra lại")
        self.btn_recheck.setStyleSheet(
            "QPushButton { background: #0284c7; color: white; font-size: 13px; "
            "font-weight: bold; padding: 9px 14px; border-radius: 7px; border: none; }"
            "QPushButton:hover { background: #0369a1; }"
            "QPushButton:disabled { background: #94a3b8; }"
        )
        self.btn_recheck.clicked.connect(self.start_check)

        self.btn_install = QPushButton("⬆️ TẢI & CẬP NHẬT NGAY")
        self.btn_install.setEnabled(False)
        self.btn_install.setStyleSheet(
            "QPushButton { background: #16a34a; color: white; font-size: 14px; "
            "font-weight: bold; padding: 9px 18px; border-radius: 7px; border: none; }"
            "QPushButton:hover { background: #15803d; }"
            "QPushButton:disabled { background: #cbd5e1; color: #64748b; }"
        )
        self.btn_install.clicked.connect(self.start_download_and_install)

        self.btn_close = QPushButton("Đóng")
        self.btn_close.setStyleSheet(
            "QPushButton { background: #64748b; color: white; font-size: 13px; "
            "font-weight: bold; padding: 9px 14px; border-radius: 7px; border: none; }"
            "QPushButton:hover { background: #475569; }"
        )
        self.btn_close.clicked.connect(self.close)

        btn_row.addWidget(self.btn_recheck)
        btn_row.addWidget(self.btn_install, 1)
        btn_row.addWidget(self.btn_close)
        root.addLayout(btn_row)

        if self.meta:
            self._apply_meta_to_ui(self.meta, is_newer_version(self.meta.get("latest_version", APP_VERSION)))
        else:
            self.start_check()

    def start_check(self):
        if self._check_worker and self._check_worker.isRunning():
            return
        self.btn_recheck.setEnabled(False)
        self.btn_install.setEnabled(False)
        self.lbl_latest_ver.setText("⏳ Đang kiểm tra phiên bản mới nhất trên máy chủ...")
        self.lbl_status.setText("")

        self._check_worker = UpdateCheckWorker()
        self._check_worker.checked.connect(self._on_check_done)
        self._check_worker.error.connect(self._on_check_error)
        self._check_worker.start()

    def _on_check_done(self, meta: dict, has_new: bool):
        self.btn_recheck.setEnabled(True)
        self.meta = meta
        self._apply_meta_to_ui(meta, has_new)

    def _on_check_error(self, err_msg: str):
        self.btn_recheck.setEnabled(True)
        self.lbl_latest_ver.setText("⚠️ Không thể kết nối máy chủ cập nhật.")
        self.lbl_status.setText(f"Lỗi: {err_msg}")
        self.lbl_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #dc2626;")

    def _apply_meta_to_ui(self, meta: dict, has_new: bool):
        latest_ver = meta.get("latest_version", APP_VERSION)
        rel_date = meta.get("release_date", "")
        size_mb = meta.get("file_size_mb", 98.6)
        self.txt_changelog.setPlainText(meta.get("changelog") or "Không có ghi chú phát hành.")

        if has_new:
            self.lbl_latest_ver.setText(
                f"🎉 Đã có phiên bản mới:  v{latest_ver}  (Phát hành: {rel_date} · {size_mb} MB)"
            )
            self.lbl_latest_ver.setStyleSheet("font-size: 14px; font-weight: bold; color: #15803d; border: none;")
            self.lbl_status.setText(
                "Nhấn 'TẢI & CẬP NHẬT NGAY' để tự động nâng cấp (giữ nguyên 100% cấu hình phòng hiện tại)."
            )
            self.lbl_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #15803d;")
            self.btn_install.setEnabled(True)
            self.btn_install.setText(f"⬆️ TẢI & CẬP NHẬT LÊN v{latest_ver}")
        else:
            self.lbl_latest_ver.setText(
                f"✅ Bạn đang sử dụng phiên bản mới nhất (v{APP_VERSION})"
            )
            self.lbl_latest_ver.setStyleSheet("font-size: 14px; font-weight: bold; color: #0f766e; border: none;")
            self.lbl_status.setText(
                "Phần mềm đã ở phiên bản mới nhất. Bạn vẫn có thể bấm 'Cài đặt lại bản này' nếu muốn."
            )
            self.lbl_status.setStyleSheet("font-size: 12px; color: #475569;")
            self.btn_install.setEnabled(True)
            self.btn_install.setText(f"🔄 Tải & Cài đặt lại (v{latest_ver})")

    def start_download_and_install(self):
        if not self.meta:
            return
        if self._dl_worker and self._dl_worker.isRunning():
            return

        self.btn_install.setEnabled(False)
        self.btn_recheck.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.lbl_status.setText("⏳ Đang kết nối GitHub Releases CDN để tải bộ cài đặt...")
        self.lbl_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #0284c7;")

        self._dl_worker = UpdateDownloadWorker(self.meta)
        self._dl_worker.progress.connect(self._on_dl_progress)
        self._dl_worker.finished_download.connect(self._on_dl_finished)
        self._dl_worker.error.connect(self._on_dl_error)
        self._dl_worker.start()

    def _on_dl_progress(self, pct: int, dl_mb: float, total_mb: float):
        self.progress_bar.setValue(pct)
        self.progress_bar.setFormat(f"Đang tải: {dl_mb:.1f} / {total_mb:.1f} MB ({pct}%)")
        self.lbl_status.setText(f"⬇️ Đang tải bộ cài đặt từ GitHub Releases CDN ({dl_mb:.1f} MB / {total_mb:.1f} MB)...")

    def _on_dl_finished(self, installer_path: str):
        self.progress_bar.setValue(100)
        self.lbl_status.setText("✅ Đã tải & xác thực toàn vẹn tệp thành công! Đang khởi chạy nâng cấp tự động...")
        self.lbl_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #15803d;")

        ok = launch_silent_installer_and_restart(installer_path)
        if ok:
            QMessageBox.information(
                self,
                "Bắt đầu nâng cấp tự động",
                "Bộ cài đặt đã sẵn sàng!\n\n"
                "Phần mềm sẽ tự động đóng lại, nâng cấp ngầm trong ~5 giây và tự mở lại phiên bản mới.",
            )
            QApplication.quit()
        else:
            self.btn_install.setEnabled(True)
            self.btn_recheck.setEnabled(True)
            QMessageBox.warning(
                self,
                "Lỗi khởi chạy bộ cài",
                f"Đã tải bộ cài về:\n{installer_path}\n\nNhưng không thể tự kích hoạt. Vui lòng mở file trên để cài đặt.",
            )

    def _on_dl_error(self, err_msg: str):
        self.btn_install.setEnabled(True)
        self.btn_recheck.setEnabled(True)
        self.lbl_status.setText(f"❌ Lỗi tải bản cập nhật: {err_msg}")
        self.lbl_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #dc2626;")
        QMessageBox.warning(
            self,
            "Không thể tải bộ cài đặt",
            f"Quá trình tải bản cập nhật gặp sự cố:\n\n{err_msg}",
        )

    def closeEvent(self, event):
        if self._dl_worker and self._dl_worker.isRunning():
            self._dl_worker.cancel()
            self._dl_worker.wait(1000)
        if self._check_worker and self._check_worker.isRunning():
            self._check_worker.wait(1000)
        super().closeEvent(event)


# ─── HỘP THOẠI DÀNH CHO ADMIN: PHÁT HÀNH BẢN CẬP NHẬT LÊN SERVER MIỄN PHÍ ────

class AdminPublishUpdateDialog(QDialog):
    """Hộp thoại dành cho Admin để đẩy thông báo phiên bản mới (kèm link GitHub Releases
    và mã SHA-256 tự động tính từ file bộ cài) lên Cloud Firestore cho toàn bộ 11 phòng.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Phát Hành Bản Cập Nhật Tới 11 Phòng (Firestore + GitHub Releases)")
        self.setMinimumSize(580, 460)
        self.setStyleSheet("""
            QDialog { background-color: #0f172a; color: #f1f5f9; font-family: 'Segoe UI', Arial; }
            QLabel { color: #e2e8f0; font-size: 13px; font-weight: bold; }
            QLineEdit, QTextEdit {
                background-color: #1e293b; border: 1px solid #475569; border-radius: 6px;
                padding: 7px 10px; color: #ffffff; font-size: 13px;
            }
            QCheckBox { color: #fbbf24; font-size: 13px; font-weight: bold; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        lbl_head = QLabel("🚀 PHÁT HÀNH BẢN CẬP NHẬT MỚI CHO 11 PHÒNG KHÁM")
        lbl_head.setAlignment(Qt.AlignCenter)
        lbl_head.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        root.addWidget(lbl_head)

        form = QFormLayout()
        form.setSpacing(10)

        self.txt_version = QLineEdit(APP_VERSION)
        self.txt_version.setPlaceholderText("Ví dụ: 7.1.0")
        self.txt_version.textChanged.connect(self._on_version_text_changed)

        self.txt_url = QLineEdit(DEFAULT_GITHUB_DOWNLOAD_URL)
        self.txt_url.setPlaceholderText("Link tải trực tiếp file .exe trên GitHub Releases")

        sha_row = QHBoxLayout()
        self.txt_sha256 = QLineEdit("")
        self.txt_sha256.setPlaceholderText("Tùy chọn: Mã SHA-256 (Bấm 'Chọn file .exe' để tự tính)")
        btn_pick_exe = QPushButton("📂 Chọn file .exe để lấy SHA-256")
        btn_pick_exe.setStyleSheet("background: #0284c7; color: white; padding: 6px 10px; border-radius: 6px;")
        btn_pick_exe.clicked.connect(self._pick_local_installer)
        sha_row.addWidget(self.txt_sha256, 1)
        sha_row.addWidget(btn_pick_exe)

        self.txt_changelog = QTextEdit()
        self.txt_changelog.setPlaceholderText("Nhập nội dung nâng cấp để hiển thị trên màn hình các phòng...")
        self.txt_changelog.setPlainText(
            "- Cập nhật tính năng Auto-Update tự động từ GitHub Releases & Firestore\n"
            "- Tối ưu Chat Nhanh Nội Bộ 11 phòng và Báo cáo Excel (.xlsx)"
        )

        self.chk_mandatory = QCheckBox("Bắt buộc cập nhật ngay khi các phòng mở phần mềm")

        form.addRow("Số phiên bản mới:", self.txt_version)
        form.addRow("Link GitHub Releases:", self.txt_url)
        form.addRow("Mã toàn vẹn SHA-256:", sha_row)
        form.addRow("Nội dung thay đổi:", self.txt_changelog)
        form.addRow("", self.chk_mandatory)
        root.addLayout(form)

        self._file_size_mb = 98.6

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.setStyleSheet("background: #475569; color: white; padding: 9px 16px; border-radius: 6px;")
        btn_cancel.clicked.connect(self.reject)

        btn_pub = QPushButton("☁️ ĐẨY LÊN FIRESTORE CHO 11 PHÒNG")
        btn_pub.setStyleSheet("background: #16a34a; color: white; font-weight: bold; padding: 9px 18px; border-radius: 6px;")
        btn_pub.clicked.connect(self._publish_now)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_pub, 1)
        root.addLayout(btn_row)

        # Nạp thông tin đang có trên Firestore
        meta = fetch_update_metadata()
        if meta:
            self.txt_version.setText(meta.get("latest_version", APP_VERSION))
            self.txt_url.setText(meta.get("download_url", DEFAULT_GITHUB_DOWNLOAD_URL))
            self.txt_sha256.setText(meta.get("sha256", ""))
            if meta.get("changelog"):
                self.txt_changelog.setPlainText(meta["changelog"])
            self.chk_mandatory.setChecked(bool(meta.get("is_mandatory", False)))

    def _on_version_text_changed(self, ver_text: str):
        v = ver_text.strip().lstrip("vV")
        if v:
            self.txt_url.setText(
                f"https://github.com/{GITHUB_REPO}/releases/download/v{v}/AUTOQ_Setup_v{v}.exe"
            )

    def _pick_local_installer(self):
        init_dir = os.path.join(os.path.abspath("."), "installer")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn file bộ cài đặt AUTOQ_Setup_v*.exe",
            init_dir if os.path.exists(init_dir) else "",
            "Executable Files (*.exe)",
        )
        if not file_path:
            return
        sha = compute_file_sha256(file_path)
        self.txt_sha256.setText(sha)
        self._file_size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 1)

    def _publish_now(self):
        ver = self.txt_version.text().strip().lstrip("vV")
        url = self.txt_url.text().strip()
        if not ver or not url:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập Số phiên bản và Link tải bộ cài đặt.")
            return

        meta = {
            "latest_version": ver,
            "release_date": datetime.now().strftime("%Y-%m-%d"),
            "download_url": url,
            "fallback_url": url,
            "sha256": self.txt_sha256.text().strip().lower(),
            "file_size_mb": self._file_size_mb,
            "is_mandatory": self.chk_mandatory.isChecked(),
            "changelog": self.txt_changelog.toPlainText().strip(),
        }
        if publish_update_metadata(meta):
            QMessageBox.information(
                self,
                "Phát hành thành công",
                f"Đã đẩy thông báo phiên bản v{ver} lên Cloud Firestore!\n"
                "Tất cả 11 phòng khám sẽ tự động nhận được thông báo cập nhật.",
            )
            self.accept()
        else:
            QMessageBox.critical(self, "Lỗi", "Không thể kết nối Cloud Firestore để lưu thông tin cập nhật.")
