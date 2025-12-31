from datetime import datetime
from pathlib import Path

from .config import LOG_DIR

__all__ = ["log_event"]


def log_event(log_path: Path, message: str) -> None:
    """Write a single log line for an operation."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")
