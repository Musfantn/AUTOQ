# =============================================================================
# PACKAGE: his_bridge
# MÔ TẢ: Module tích hợp VNPT HIS RestService cho hệ thống gọi số CĐHA.
#         Giao tiếp trực tiếp qua REST API — không dùng Selenium/HTML parsing.
# =============================================================================

from his_bridge.config import HisConfig
from his_bridge.models import PatientInfo, ServiceInfo, HisIdentifiers, HisDocument
from his_bridge.bridge import HisBridge

__all__ = [
    "HisConfig",
    "PatientInfo",
    "ServiceInfo",
    "HisIdentifiers",
    "HisDocument",
    "HisBridge",
]

__version__ = "1.0.0"
