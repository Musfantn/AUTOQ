# =============================================================================
# FILE: his_bridge/config.py
# MÔ TẢ: Dataclass HisConfig — đọc toàn bộ cấu hình từ config.yaml.
#         Không hardcode bất kỳ giá trị nghiệp vụ nào.
#         Hỗ trợ override qua biến môi trường.
# =============================================================================

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Đường dẫn mặc định tới config.yaml (cùng thư mục với module)
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


@dataclass(frozen=True)
class StoredProcedures:
    """Tên các stored procedure của VNPT HIS — lấy từ config, không hardcode."""

    search: str = "CLS02C001.SIDS"
    patient_info: str = "NGT02K016.EV003"
    services: str = "CLS02C001.DSKQ"


@dataclass(frozen=True)
class HisSessionConfig:
    """Thông tin session để xác thực với VNPT HIS RestService."""

    jsessionid: str = ""   # JSESSIONID — session Java app server
    sessionid: str = ""    # SESSIONID — BIG-IP load balancer sticky session
    uuid_jwt: str = ""


@dataclass(frozen=True)
class HisServerConfig:
    """Cấu hình kết nối tới VNPT HIS RestService."""

    base_url: str = "https://bvhatinh.vncare.vn/vnpthis/RestService"
    hospital_id: str = ""
    department_id: str = ""
    room_id: str = ""
    database_name: str = ""
    extra_id: str = ""
    stored_procedures: StoredProcedures = field(default_factory=StoredProcedures)
    headers: dict[str, str] = field(default_factory=lambda: {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    })
    session: HisSessionConfig = field(default_factory=HisSessionConfig)


@dataclass(frozen=True)
class NetworkConfig:
    """Cấu hình mạng: timeout, retry, connection pool."""

    timeout_seconds: int = 10
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    connection_pool_size: int = 5


@dataclass(frozen=True)
class CacheConfig:
    """Cấu hình cache TTL để tránh gọi HIS trùng lặp."""

    ttl_seconds: int = 5


@dataclass(frozen=True)
class FirestoreConfig:
    """Cấu hình kết nối Firestore."""

    api_key: str = ""
    project: str = "tasksched"
    collection: str = "autoq_queues"


@dataclass(frozen=True)
class LoggingConfig:
    """Cấu hình logging."""

    level: str = "INFO"
    file: str = "logs/his_bridge.log"
    max_bytes: int = 5_242_880  # 5 MB
    backup_count: int = 3


@dataclass(frozen=True)
class HisConfig:
    """Cấu hình tổng hợp cho toàn bộ HIS Bridge module.

    Đọc từ file config.yaml và cho phép override qua biến môi trường.
    Tất cả tham số nghiệp vụ (hospital_id, department_id, SP names, ...)
    đều nằm trong config — không hardcode trong mã nguồn.
    """

    his: HisServerConfig = field(default_factory=HisServerConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    firestore: FirestoreConfig = field(default_factory=FirestoreConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @staticmethod
    def load(config_path: str | Path | None = None) -> HisConfig:
        """Đọc config từ YAML file và override bằng biến môi trường.
        Ưu tiên: 1. explicit path (nếu tồn tại), 2. ProgramData, 3. AppData, 4. default path.
        """
        paths_to_try = []
        if config_path:
            paths_to_try.append(Path(config_path))
            
        programdata = os.environ.get("PROGRAMDATA")
        if programdata:
            paths_to_try.append(Path(programdata) / "AUTOQ" / "his_bridge" / "config.yaml")
            
        appdata = os.environ.get("APPDATA")
        if appdata:
            paths_to_try.append(Path(appdata) / "AUTOQ" / "his_bridge" / "config.yaml")
            
        paths_to_try.append(_DEFAULT_CONFIG_PATH)
        
        raw: dict[str, Any] = {}
        loaded_path = None
        
        for path in paths_to_try:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        raw = yaml.safe_load(fh) or {}
                    loaded_path = path
                    break
                except Exception:
                    continue
                    
        # Nếu không có file nào tồn tại, load rỗng để lấy defaults
        return _build_config(raw)


def _build_config(raw: dict[str, Any]) -> HisConfig:
    """Xây dựng HisConfig từ raw dict (YAML) với override từ env vars."""

    his_raw = raw.get("his", {})
    network_raw = raw.get("network", {})
    cache_raw = raw.get("cache", {})
    firestore_raw = raw.get("firestore", {})
    logging_raw = raw.get("logging", {})

    # --- HIS Server ---
    sp_raw = his_raw.get("stored_procedures", {})
    stored_procedures = StoredProcedures(
        search=sp_raw.get("search", StoredProcedures.search),
        patient_info=sp_raw.get("patient_info", StoredProcedures.patient_info),
        services=sp_raw.get("services", StoredProcedures.services),
    )

    session_raw = his_raw.get("session", {})
    session = HisSessionConfig(
        jsessionid=os.environ.get(
            "HIS_JSESSIONID",
            session_raw.get("jsessionid", ""),
        ),
        sessionid=os.environ.get(
            "HIS_SESSIONID",
            session_raw.get("sessionid", ""),
        ),
        uuid_jwt=os.environ.get(
            "HIS_UUID_JWT",
            session_raw.get("uuid_jwt", ""),
        ),
    )

    headers_default = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    headers_raw = his_raw.get("headers", None)
    headers = headers_raw if headers_raw else dict(headers_default)

    his = HisServerConfig(
        base_url=os.environ.get(
            "HIS_BASE_URL",
            his_raw.get("base_url", HisServerConfig.base_url),
        ),
        hospital_id=his_raw.get("hospital_id", ""),
        department_id=his_raw.get("department_id", ""),
        room_id=his_raw.get("room_id", ""),
        database_name=his_raw.get("database_name", ""),
        extra_id=his_raw.get("extra_id", ""),
        stored_procedures=stored_procedures,
        headers=headers,
        session=session,
    )

    # --- Network ---
    network = NetworkConfig(
        timeout_seconds=network_raw.get(
            "timeout_seconds", NetworkConfig.timeout_seconds,
        ),
        max_retries=network_raw.get("max_retries", NetworkConfig.max_retries),
        retry_delay_seconds=network_raw.get(
            "retry_delay_seconds", NetworkConfig.retry_delay_seconds,
        ),
        connection_pool_size=network_raw.get(
            "connection_pool_size", NetworkConfig.connection_pool_size,
        ),
    )

    # --- Cache ---
    cache = CacheConfig(
        ttl_seconds=cache_raw.get("ttl_seconds", CacheConfig.ttl_seconds),
    )

    # --- Firestore ---
    firestore = FirestoreConfig(
        api_key=os.environ.get(
            "FIREBASE_API_KEY",
            firestore_raw.get("api_key", ""),
        ),
        project=os.environ.get(
            "FIREBASE_PROJECT",
            firestore_raw.get("project", FirestoreConfig.project),
        ),
        collection=firestore_raw.get(
            "collection", FirestoreConfig.collection,
        ),
    )

    # --- Logging ---
    logging_cfg = LoggingConfig(
        level=logging_raw.get("level", LoggingConfig.level),
        file=logging_raw.get("file", LoggingConfig.file),
        max_bytes=logging_raw.get("max_bytes", LoggingConfig.max_bytes),
        backup_count=logging_raw.get(
            "backup_count", LoggingConfig.backup_count,
        ),
    )

    return HisConfig(
        his=his,
        network=network,
        cache=cache,
        firestore=firestore,
        logging=logging_cfg,
    )
