from pathlib import Path
import os

BASE_DIR = Path(os.environ.get("UNZIP_BASE_DIR", str(Path.home()))).expanduser().resolve()
ALLOW_ANY_PATH = os.environ.get("UNZIP_ALLOW_ANY_PATH", "").lower() in {"1", "true", "yes"}
LOG_DIR = Path(os.environ.get("UNZIP_LOG_DIR", "logs")).expanduser().resolve()

MAX_TOTAL_SIZE = int(os.environ.get("UNZIP_MAX_TOTAL_SIZE", str(1024 * 1024 * 1024)))
MAX_FILES = int(os.environ.get("UNZIP_MAX_FILES", "10000"))
MAX_FILE_SIZE = int(os.environ.get("UNZIP_MAX_FILE_SIZE", str(100 * 1024 * 1024)))
MAX_COMPRESSION_RATIO = float(os.environ.get("UNZIP_MAX_COMPRESSION_RATIO", "200"))
MAX_ZIP_SIZE = int(os.environ.get("UNZIP_MAX_ZIP_SIZE", str(2 * 1024 * 1024 * 1024)))
MAX_WORKERS = int(os.environ.get("UNZIP_MAX_WORKERS", str(min(4, (os.cpu_count() or 1)))))
