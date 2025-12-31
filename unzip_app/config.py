from pathlib import Path
import os

__all__ = [
    "ALLOW_ANY_PATH",
    "BASE_DIR",
    "LOG_DIR",
    "MAX_COMPRESSION_RATIO",
    "MAX_FILES",
    "MAX_FILE_SIZE",
    "MAX_TOTAL_SIZE",
    "MAX_WORKERS",
    "MAX_ZIP_SIZE",
]

BASE_DIR = Path(os.environ.get("UNZIP_BASE_DIR", str(Path.home()))).expanduser().resolve()
ALLOW_ANY_PATH = os.environ.get("UNZIP_ALLOW_ANY_PATH", "").lower() in {"1", "true", "yes"}
LOG_DIR = Path(os.environ.get("UNZIP_LOG_DIR", "logs")).expanduser().resolve()

MAX_TOTAL_SIZE = int(os.environ.get("UNZIP_MAX_TOTAL_SIZE", str(1024 * 1024 * 1024)))
MAX_FILES = int(os.environ.get("UNZIP_MAX_FILES", "10000"))
MAX_FILE_SIZE = int(os.environ.get("UNZIP_MAX_FILE_SIZE", str(100 * 1024 * 1024)))
MAX_COMPRESSION_RATIO = float(os.environ.get("UNZIP_MAX_COMPRESSION_RATIO", "200"))
MAX_ZIP_SIZE = int(os.environ.get("UNZIP_MAX_ZIP_SIZE", str(2 * 1024 * 1024 * 1024)))
MAX_WORKERS = int(os.environ.get("UNZIP_MAX_WORKERS", str(min(4, (os.cpu_count() or 1)))))


def _validate_config() -> None:
    """Validate configuration values on startup."""
    errors = []

    if MAX_WORKERS < 1:
        errors.append(f"MAX_WORKERS must be >= 1 (got {MAX_WORKERS})")
    if MAX_WORKERS > 32:
        errors.append(f"MAX_WORKERS should be <= 32 (got {MAX_WORKERS})")

    if MAX_ZIP_SIZE < 1:
        errors.append(f"MAX_ZIP_SIZE must be >= 1 (got {MAX_ZIP_SIZE})")

    if MAX_TOTAL_SIZE < 1:
        errors.append(f"MAX_TOTAL_SIZE must be >= 1 (got {MAX_TOTAL_SIZE})")

    if MAX_FILE_SIZE < 1:
        errors.append(f"MAX_FILE_SIZE must be >= 1 (got {MAX_FILE_SIZE})")

    if MAX_FILES < 1:
        errors.append(f"MAX_FILES must be >= 1 (got {MAX_FILES})")

    if MAX_COMPRESSION_RATIO < 1:
        errors.append(f"MAX_COMPRESSION_RATIO must be >= 1 (got {MAX_COMPRESSION_RATIO})")

    if not ALLOW_ANY_PATH and not BASE_DIR.exists():
        errors.append(f"BASE_DIR does not exist: {BASE_DIR}")

    if errors:
        raise ValueError("Configuration errors:\n  - " + "\n  - ".join(errors))


_validate_config()
