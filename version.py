# =============================================================================
# FILE: version.py
# MÔ TẢ: Quản lý tập trung thông tin phiên bản của hệ thống AUTOQ và hàm
#        so sánh phiên bản ngữ nghĩa (Semantic Versioning) cho Auto-Update.
# =============================================================================

import re

APP_VERSION = "7.2.0"
APP_RELEASE_DATE = "2026-11-21"
GITHUB_REPO = "Musfantn/AUTOQ"

# Kênh 1 (Ưu tiên cao nhất - Không giới hạn Rate Limit cho 11 phòng chung IP WAN):
UPDATE_FIRESTORE_PATH = "autoq_queues/app_update_meta"

# Kênh 2 (Dự phòng qua GitHub Raw CDN):
GITHUB_RAW_VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.json"

# Kênh 3 (Dự phòng qua GitHub Releases REST API):
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# Link tải trực tiếp mặc định từ GitHub Releases
DEFAULT_GITHUB_DOWNLOAD_URL = (
    f"https://github.com/{GITHUB_REPO}/releases/download/v{APP_VERSION}/AUTOQ_Setup_v{APP_VERSION}.exe"
)


def parse_semver(ver_str: str) -> tuple[int, int, int]:
    """Chuyển chuỗi phiên bản (VD: 'v7.1.0', '7.1', '7.2.1-beta') thành bộ 3 số nguyên (major, minor, patch)."""
    if not ver_str:
        return (0, 0, 0)
    cleaned = str(ver_str).strip().lstrip("vV")
    nums = re.findall(r"\d+", cleaned)
    major = int(nums[0]) if len(nums) > 0 else 0
    minor = int(nums[1]) if len(nums) > 1 else 0
    patch = int(nums[2]) if len(nums) > 2 else 0
    return (major, minor, patch)


def is_newer_version(remote_ver: str, current_ver: str = APP_VERSION) -> bool:
    """Trả về True nếu remote_ver mới hơn current_ver."""
    return parse_semver(remote_ver) > parse_semver(current_ver)
