# =============================================================================
# FILE: publish_release.py
# MÔ TẢ: Công cụ tự động phát hành phiên bản mới lên Server miễn phí
#        (GitHub Releases CDN + Cloud Firestore autoq_queues/app_update_meta).
# CÁCH DÙNG:
#   python publish_release.py
# =============================================================================

import os
import sys
import json
import shutil
import subprocess
from datetime import datetime

from version import APP_VERSION, GITHUB_REPO
from updater import compute_file_sha256, publish_update_metadata


def main():
    ver = APP_VERSION
    installer_path = os.path.join("installer", f"AUTOQ_Setup_v{ver}.exe")
    if not os.path.exists(installer_path):
        # Tìm file bộ cài mới nhất trong thư mục installer/
        if os.path.exists("installer"):
            exes = [
                os.path.join("installer", f)
                for f in os.listdir("installer")
                if f.startswith("AUTOQ_Setup_v") and f.endswith(".exe")
            ]
            if exes:
                exes.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                installer_path = exes[0]

    sha256_hash = ""
    size_mb = 98.6
    if os.path.exists(installer_path):
        print(f"[Publish] Đang tính SHA-256 cho: {installer_path} ...")
        sha256_hash = compute_file_sha256(installer_path)
        size_mb = round(os.path.getsize(installer_path) / (1024 * 1024), 1)
        print(f"[Publish] SHA-256: {sha256_hash} ({size_mb} MB)")
    else:
        print(f"[Publish] Cảnh báo: Chưa tìm thấy {installer_path}, chỉ cập nhật metadata.")

    download_url = f"https://github.com/{GITHUB_REPO}/releases/download/v{ver}/AUTOQ_Setup_v{ver}.exe"
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Đọc changelog hiện tại từ version.json nếu có
    changelog = (
        "- Bổ sung tính năng Kiểm tra cập nhật & Tự động cập nhật phần mềm (Auto-Update)\n"
        "- Tính năng Chat Nhanh Nội Bộ giữa 11 phòng khám & Admin (Hybrid LAN UDP + Firestore)\n"
        "- Đồng bộ Bác sĩ phụ trách từng phòng & Xuất báo cáo Excel (.xlsx) chuẩn OOXML"
    )
    if os.path.exists("version.json"):
        try:
            with open("version.json", "r", encoding="utf-8") as f:
                old_v = json.load(f)
                if old_v.get("changelog"):
                    changelog = old_v["changelog"]
        except Exception:
            pass

    meta = {
        "latest_version": ver,
        "release_date": today_str,
        "download_url": download_url,
        "fallback_url": download_url,
        "sha256": sha256_hash,
        "file_size_mb": size_mb,
        "is_mandatory": False,
        "changelog": changelog,
    }

    # 1. Cập nhật file version.json
    with open("version.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("[Publish] Đã cập nhật version.json.")

    # 2. Đẩy metadata lên Cloud Firestore (autoq_queues/app_update_meta)
    if publish_update_metadata(meta):
        print(f"[Publish] ✅ Đã đồng bộ metadata v{ver} lên Cloud Firestore (autoq_queues/app_update_meta)!")
    else:
        print("[Publish] ⚠️ Không thể ghi lên Cloud Firestore.")

    # 3. Nếu máy có cài GitHub CLI (gh) và có file bộ cài, thử tạo GitHub Release tự động
    if os.path.exists(installer_path) and shutil.which("gh"):
        tag = f"v{ver}"
        print(f"[Publish] Đang kiểm tra / đẩy bộ cài lên GitHub Releases ({tag})...")
        try:
            subprocess.run(
                [
                    "gh", "release", "create", tag, installer_path,
                    "--repo", GITHUB_REPO,
                    "--title", f"AUTOQ v{ver} ({today_str})",
                    "--notes", changelog,
                ],
                check=False,
            )
        except Exception as e:
            print(f"[Publish] Bỏ qua gh release create: {e}")


if __name__ == "__main__":
    main()
