from datetime import datetime
from pathlib import Path
import re

from .config import LOG_DIR

__all__ = ["log_event", "sanitize_log_message"]


def sanitize_log_message(message: str) -> str:
    """Sanitize message for safe logging - remove control characters and limit length."""
    # Remove control characters (except newline/tab which we also remove for single-line logs)
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', message)
    # Limit length to prevent log flooding
    max_length = 1000
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "...[truncated]"
    return sanitized


def log_event(log_path: Path, message: str) -> None:
    """Write a single log line for an operation."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_message = sanitize_log_message(message)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {safe_message}\n")
