# =============================================================================
# FILE: his_bridge/logger.py
# MÔ TẢ: Structured logging cho HIS Bridge.
#         Ghi file logs/his_bridge.log + console.
#         Hỗ trợ log thời gian xử lý (performance tracking).
# =============================================================================

from __future__ import annotations

import functools
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable

from his_bridge.config import LoggingConfig

# Singleton logger instance
_logger: logging.Logger | None = None

# Format chuẩn cho log output
_LOG_FORMAT = "[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(config: LoggingConfig | None = None) -> logging.Logger:
    """Khởi tạo và cấu hình logger cho toàn bộ HIS Bridge module.

    Args:
        config: Cấu hình logging từ HisConfig.
                Nếu None, sử dụng giá trị mặc định.

    Returns:
        Logger instance đã cấu hình sẵn.
    """
    global _logger

    if _logger is not None:
        return _logger

    if config is None:
        config = LoggingConfig()

    logger = logging.getLogger("his_bridge")
    logger.setLevel(getattr(logging, config.level.upper(), logging.INFO))

    # Tránh duplicate handlers khi gọi lại
    if logger.handlers:
        return logger

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler — luôn ghi ra stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler — RotatingFileHandler với giới hạn dung lượng
    try:
        log_path = Path(config.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning(
            "Không thể tạo file log '%s': %s. Chỉ ghi ra console.",
            config.file,
            exc,
        )

    _logger = logger
    return logger


def get_logger(name: str = "his_bridge") -> logging.Logger:
    """Lấy logger con cho một sub-module cụ thể.

    Args:
        name: Tên module (ví dụ: "his_bridge.vnpt_client").

    Returns:
        Logger instance.
    """
    global _logger

    if _logger is None:
        setup_logger()

    return logging.getLogger(name)


def log_timing(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator ghi log thời gian thực thi cho hàm async.

    Ví dụ output:
        [INFO] [his_bridge.vnpt_client] search_patient completed in 120 ms
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger = get_logger(func.__module__ or "his_bridge")
        start = time.perf_counter()
        func_name = func.__qualname__

        logger.info("%s — bắt đầu", func_name)
        try:
            result = await func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "%s — hoàn thành trong %.0f ms",
                func_name,
                elapsed_ms,
            )
            return result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "%s — lỗi sau %.0f ms: %s",
                func_name,
                elapsed_ms,
                exc,
            )
            raise

    return wrapper


def log_timing_sync(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator ghi log thời gian thực thi cho hàm đồng bộ (sync)."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger = get_logger(func.__module__ or "his_bridge")
        start = time.perf_counter()
        func_name = func.__qualname__

        try:
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "%s — hoàn thành trong %.0f ms",
                func_name,
                elapsed_ms,
            )
            return result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "%s — lỗi sau %.0f ms: %s",
                func_name,
                elapsed_ms,
                exc,
            )
            raise

    return wrapper
