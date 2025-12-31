from pathlib import Path, PurePosixPath
import os
import shutil
import stat
import tempfile
import zipfile

from .config import (
    ALLOW_ANY_PATH,
    BASE_DIR,
    MAX_COMPRESSION_RATIO,
    MAX_FILES,
    MAX_FILE_SIZE,
    MAX_TOTAL_SIZE,
    MAX_ZIP_SIZE,
)
from .log_utils import log_event


def normalize_member_path(member: str) -> PurePosixPath:
    """Normalize archive paths to POSIX style."""
    return PurePosixPath(member.replace("\\", "/"))


def is_safe_member_path(member: str) -> bool:
    """Return True when archive path is relative and traversal-free."""
    path = normalize_member_path(member)
    if path.is_absolute():
        return False
    if ".." in path.parts:
        return False
    if ":" in path.parts[0] if path.parts else False:
        return False
    return True


def is_symlink_info(info: zipfile.ZipInfo) -> bool:
    """Detect symlink entry in a zip archive (unix external_attr)."""
    mode = (info.external_attr >> 16) & 0o170000
    return stat.S_ISLNK(mode)


def validate_base_dir(path: Path) -> tuple[bool, str]:
    """Ensure the path is within the allowed base directory."""
    if ALLOW_ANY_PATH:
        return True, ""
    try:
        path.resolve().relative_to(BASE_DIR)
        return True, ""
    except ValueError:
        return False, f"Cesta musi byt pod povolenym rootom: {BASE_DIR}"


def resolve_target_dir(extract_to: Path, policy: str) -> tuple[Path | None, str]:
    """Resolve target directory based on conflict policy."""
    if not extract_to.exists():
        return extract_to, ""
    if policy == "skip":
        return None, "Cielovy priecinok uz existuje"
    if policy == "overwrite":
        return extract_to, ""
    if policy == "suffix":
        counter = 1
        while True:
            candidate = extract_to.parent / f"{extract_to.name} ({counter})"
            if not candidate.exists():
                return candidate, ""
            counter += 1
    return None, "Neznama politika konfliktu"


def find_zip_files(directory: Path, recursive: bool = True):
    """Yield zip files in the given directory."""
    if recursive:
        for root, _, files in os.walk(directory, onerror=lambda _: None):
            for name in files:
                if name.lower().endswith(".zip"):
                    yield Path(root) / name
    else:
        try:
            for entry in directory.iterdir():
                if entry.is_file() and entry.name.lower().endswith(".zip"):
                    yield entry
        except PermissionError:
            return


def extract_zip(zip_path: Path, conflict_policy: str, log_path: Path | None = None) -> dict:
    """Extract a zip file into a sibling directory."""
    result = {
        "path": zip_path,
        "success": False,
        "skipped": False,
        "message": "",
        "files_count": 0,
        "total_size": 0,
    }

    extract_to = zip_path.parent / zip_path.stem

    try:
        zip_size = zip_path.stat().st_size
        if zip_size > MAX_ZIP_SIZE:
            result["message"] = "ZIP je prilis velky"
            return result

        target_dir, conflict_message = resolve_target_dir(extract_to, conflict_policy)
        if target_dir is None:
            result["skipped"] = True
            result["message"] = conflict_message
            return result

        temp_dir = Path(tempfile.mkdtemp(prefix=f".{target_dir.name}.", dir=target_dir.parent))

        with zipfile.ZipFile(zip_path, "r") as zf:
            infos = zf.infolist()

            if len(infos) > MAX_FILES:
                result["message"] = "Prilis vela suborov v archive"
                return result

            total_size = 0
            for info in infos:
                if info.is_dir():
                    continue
                if is_symlink_info(info):
                    result["message"] = "Bezpecnostna chyba: symlink v archive"
                    return result
                if not is_safe_member_path(info.filename):
                    result["message"] = "Bezpecnostna chyba: path traversal"
                    return result
                if info.file_size > MAX_FILE_SIZE:
                    result["message"] = "Subor v archive je prilis velky"
                    return result
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > MAX_COMPRESSION_RATIO:
                    result["message"] = "Podozrivy kompresny pomer"
                    return result
                total_size += info.file_size

            if total_size > MAX_TOTAL_SIZE:
                result["message"] = "Prilis velky archiv po rozbaleni"
                return result

            free_space = shutil.disk_usage(target_dir.parent).free
            if total_size > free_space:
                result["message"] = "Nedostatok miesta na disku"
                return result

            for info in infos:
                member_path = normalize_member_path(info.filename)
                if info.is_dir():
                    (temp_dir / Path(*member_path.parts)).mkdir(parents=True, exist_ok=True)
                    continue
                dest_path = temp_dir / Path(*member_path.parts)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, dest_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

            if target_dir.exists() and conflict_policy == "overwrite":
                if target_dir.is_dir():
                    shutil.rmtree(target_dir)
                else:
                    target_dir.unlink()

            temp_dir.replace(target_dir)

            result["success"] = True
            result["files_count"] = len([i for i in infos if not i.is_dir()])
            result["total_size"] = total_size
            result["message"] = f"OK ({result['files_count']} suborov)"

    except zipfile.BadZipFile:
        result["message"] = "Poskodeny ZIP subor"
    except PermissionError:
        result["message"] = "Nedostatocne opravnenia"
    except OSError as e:
        result["message"] = f"Chyba systemu: {e.strerror}"
    except Exception as e:
        result["message"] = f"Neocakavana chyba: {str(e)}"
    finally:
        if not result["success"]:
            try:
                if "temp_dir" in locals() and temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except Exception:
                pass

    if log_path is not None:
        status = "OK" if result["success"] else "SKIP" if result["skipped"] else "ERROR"
        log_event(log_path, f"{status}: {zip_path} - {result['message']}")

    return result


def is_zip_extracted(zip_path: Path) -> dict:
    """Check whether the zip file has been fully extracted."""
    result = {
        "path": zip_path,
        "extracted": False,
        "can_delete": False,
        "message": "",
        "zip_size": 0,
    }

    extract_dir = zip_path.parent / zip_path.stem
    result["zip_size"] = zip_path.stat().st_size

    if not extract_dir.exists():
        result["message"] = "Priecinok s extrahovanymi subormi neexistuje"
        return result

    if not extract_dir.is_dir():
        result["message"] = "Cielova cesta nie je priecinok"
        return result

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zip_members = set()
            for info in zf.infolist():
                if not info.is_dir():
                    zip_members.add(normalize_member_path(info.filename).as_posix())

            existing_files = set()
            for file_path in extract_dir.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(extract_dir).as_posix()
                    existing_files.add(rel_path)

            missing_files = [member for member in zip_members if member not in existing_files]

            if missing_files:
                result["message"] = f"Chyba {len(missing_files)} suborov"
                result["extracted"] = False
            else:
                result["extracted"] = True
                result["can_delete"] = True
                result["message"] = f"OK ({len(zip_members)} suborov overenych)"

    except zipfile.BadZipFile:
        result["message"] = "Poskodeny ZIP subor"
    except Exception as e:
        result["message"] = f"Chyba: {str(e)}"

    return result


def delete_zip_file(zip_path: Path) -> dict:
    """Delete a zip file after verification."""
    result = {
        "path": zip_path,
        "deleted": False,
        "message": "",
        "freed_size": 0,
    }

    try:
        size = zip_path.stat().st_size
        zip_path.unlink()
        result["deleted"] = True
        result["freed_size"] = size
        result["message"] = "Vymazany"
    except PermissionError:
        result["message"] = "Nedostatocne opravnenia"
    except Exception as e:
        result["message"] = f"Chyba: {str(e)}"

    return result
