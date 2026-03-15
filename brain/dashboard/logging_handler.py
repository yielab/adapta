"""Centralized logging handler with buffer"""

import logging
import time
from collections import deque
from typing import List, Dict, Any
from threading import Lock


class LogBuffer:
    """Thread-safe log buffer for dashboard"""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.logs: deque = deque(maxlen=max_size)
        self.lock = Lock()

    def add_log(self, record: logging.LogRecord):
        """Add a log record"""
        with self.lock:
            log_entry = {
                "timestamp": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(record.created)
                ),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }

            # Add exception info if present
            if record.exc_info:
                import traceback

                log_entry["exception"] = "".join(
                    traceback.format_exception(*record.exc_info)
                )

            self.logs.append(log_entry)

    def get_logs(
        self, level: str = "INFO", limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent logs filtered by level"""
        with self.lock:
            level_priority = {
                "DEBUG": 10,
                "INFO": 20,
                "WARNING": 30,
                "ERROR": 40,
                "CRITICAL": 50,
            }
            min_level = level_priority.get(level.upper(), 20)

            filtered = [
                log
                for log in self.logs
                if level_priority.get(log["level"], 0) >= min_level
            ]

            return list(filtered)[-limit:]

    def clear(self):
        """Clear all logs"""
        with self.lock:
            self.logs.clear()


class BufferHandler(logging.Handler):
    """Logging handler that stores logs in buffer"""

    def __init__(self, log_buffer: LogBuffer):
        super().__init__()
        self.log_buffer = log_buffer

    def emit(self, record: logging.LogRecord):
        """Emit a log record"""
        try:
            self.log_buffer.add_log(record)
        except Exception:
            self.handleError(record)


# Global log buffer
log_buffer = LogBuffer()


def setup_logging(level: str = "INFO"):
    """Setup logging with buffer handler"""
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Console handler with formatting
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, level.upper()))
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)

    # Buffer handler for dashboard
    buffer_handler = BufferHandler(log_buffer)
    buffer_handler.setLevel(logging.DEBUG)  # Capture all levels

    # Add handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(buffer_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)

    logging.info("Logging initialized")
