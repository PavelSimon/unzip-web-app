"""
ZIP Extractor - Web aplikácia pre hromadnú extrakciu ZIP súborov
Postavené na FastHTML frameworku
"""

from fasthtml.common import *
from pathlib import Path, PurePosixPath
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import itertools
import os
import shutil
import stat
import subprocess
import tempfile
import uuid
import zipfile

app, rt = fast_app(
    hdrs=[
        Style("""
            body {
                font-family: system-ui, -apple-system, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
                border-bottom: 2px solid #007bff;
                padding-bottom: 10px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            input[type="text"] {
                width: 100%;
                padding: 12px;
                border: 2px solid #ddd;
                border-radius: 5px;
                font-size: 16px;
                box-sizing: border-box;
            }
            input[type="text"]:focus {
                border-color: #007bff;
                outline: none;
            }
            .checkbox-group {
                margin: 15px 0;
            }
            .checkbox-group label {
                cursor: pointer;
            }
            button {
                background: #007bff;
                color: white;
                padding: 12px 30px;
                border: none;
                border-radius: 5px;
                font-size: 16px;
                cursor: pointer;
                width: 100%;
            }
            button:hover {
                background: #0056b3;
            }
            .stats {
                background: #e8f4fd;
                padding: 20px;
                border-radius: 8px;
                margin-top: 20px;
            }
            .stats h2 {
                margin-top: 0;
                color: #0056b3;
            }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 15px;
            }
            .stat-item {
                background: white;
                padding: 15px;
                border-radius: 5px;
                text-align: center;
            }
            .stat-value {
                font-size: 24px;
                font-weight: bold;
                color: #007bff;
            }
            .stat-label {
                color: #666;
                font-size: 14px;
            }
            .results {
                margin-top: 20px;
            }
            .result-item {
                padding: 10px;
                border-bottom: 1px solid #eee;
                font-family: monospace;
            }
            .result-item.success {
                color: #28a745;
            }
            .result-item.error {
                color: #dc3545;
            }
            .error-message {
                background: #f8d7da;
                color: #721c24;
                padding: 15px;
                border-radius: 5px;
                margin-top: 20px;
            }
            .info-message {
                background: #fff3cd;
                color: #856404;
                padding: 15px;
                border-radius: 5px;
                margin-top: 20px;
            }
            .back-link {
                display: inline-block;
                margin-top: 20px;
                color: #007bff;
                text-decoration: none;
            }
            .back-link:hover {
                text-decoration: underline;
            }
            .input-group {
                display: flex;
                gap: 10px;
            }
            .input-group input[type="text"] {
                flex: 1;
            }
            .btn-browse {
                background: #6c757d;
                white-space: nowrap;
                width: auto;
                padding: 12px 20px;
            }
            .btn-browse:hover {
                background: #5a6268;
            }
            .btn-danger {
                background: #dc3545;
                margin-top: 10px;
            }
            .btn-danger:hover {
                background: #c82333;
            }
            .action-buttons {
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            .result-item.warning {
                color: #856404;
            }
        """)
    ]
)

BASE_DIR = Path(os.environ.get("UNZIP_BASE_DIR", str(Path.home()))).expanduser().resolve()
ALLOW_ANY_PATH = os.environ.get("UNZIP_ALLOW_ANY_PATH", "").lower() in {"1", "true", "yes"}
LOG_DIR = Path(os.environ.get("UNZIP_LOG_DIR", "logs")).expanduser().resolve()

MAX_TOTAL_SIZE = int(os.environ.get("UNZIP_MAX_TOTAL_SIZE", str(1024 * 1024 * 1024)))  # 1GB
MAX_FILES = int(os.environ.get("UNZIP_MAX_FILES", "10000"))
MAX_FILE_SIZE = int(os.environ.get("UNZIP_MAX_FILE_SIZE", str(100 * 1024 * 1024)))  # 100MB
MAX_COMPRESSION_RATIO = float(os.environ.get("UNZIP_MAX_COMPRESSION_RATIO", "200"))
MAX_ZIP_SIZE = int(os.environ.get("UNZIP_MAX_ZIP_SIZE", str(2 * 1024 * 1024 * 1024)))  # 2GB
MAX_WORKERS = int(os.environ.get("UNZIP_MAX_WORKERS", str(min(4, (os.cpu_count() or 1)))))


def log_event(log_path: Path, message: str) -> None:
    """Zapise udalost do logu operacie."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def normalize_member_path(member: str) -> PurePosixPath:
    """Normalizuje cestu v ZIP archive."""
    return PurePosixPath(member.replace("\\", "/"))


def is_safe_member_path(member: str) -> bool:
    """Overi, ze cesta v ZIP neobsahuje path traversal ani absolutne cesty."""
    path = normalize_member_path(member)
    if path.is_absolute():
        return False
    if ".." in path.parts:
        return False
    if ":" in path.parts[0] if path.parts else False:
        return False
    return True


def is_symlink_info(info: zipfile.ZipInfo) -> bool:
    """Deteguje symlink v ZIP archive (unix external_attr)."""
    mode = (info.external_attr >> 16) & 0o170000
    return stat.S_ISLNK(mode)


def validate_base_dir(path: Path) -> tuple[bool, str]:
    """Overi, ze cesta je v povolenom base dir."""
    if ALLOW_ANY_PATH:
        return True, ""
    try:
        path.resolve().relative_to(BASE_DIR)
        return True, ""
    except ValueError:
        return False, f"Cesta musi byt pod povolenym rootom: {BASE_DIR}"


def resolve_target_dir(extract_to: Path, policy: str) -> tuple[Path | None, str]:
    """Urcuje cielovy adresar pri konflikte."""
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


def format_size(size_bytes: int) -> str:
    """Formátuje veľkosť v bajtoch na čitateľný formát."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def find_zip_files(directory: Path, recursive: bool = True):
    """Nájde všetky ZIP súbory v adresári (generator)."""
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
    """
    Extrahuje ZIP súbor do priečinka s rovnakým názvom.
    Vráti slovník s výsledkom operácie.
    """
    result = {
        "path": zip_path,
        "success": False,
        "skipped": False,
        "message": "",
        "files_count": 0,
        "total_size": 0
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

        with zipfile.ZipFile(zip_path, 'r') as zf:
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
    """
    Overí, či je ZIP súbor správne extrahovaný.
    Kontroluje, či existuje priečinok s rovnakým názvom a obsahuje všetky súbory.
    """
    result = {
        "path": zip_path,
        "extracted": False,
        "can_delete": False,
        "message": "",
        "zip_size": 0
    }

    extract_dir = zip_path.parent / zip_path.stem
    result["zip_size"] = zip_path.stat().st_size

    # Kontrola, či existuje cieľový priečinok
    if not extract_dir.exists():
        result["message"] = "Priečinok s extrahovanými súbormi neexistuje"
        return result

    if not extract_dir.is_dir():
        result["message"] = "Cieľová cesta nie je priečinok"
        return result

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Získanie zoznamu súborov v ZIP
            zip_members = set()
            for info in zf.infolist():
                if not info.is_dir():
                    zip_members.add(normalize_member_path(info.filename).as_posix())

            # Kontrola, ci vsetky subory existuju (jedna mapa)
            existing_files = set()
            for file_path in extract_dir.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(extract_dir).as_posix()
                    existing_files.add(rel_path)

            missing_files = [member for member in zip_members if member not in existing_files]

            if missing_files:
                result["message"] = f"Chýba {len(missing_files)} súborov"
                result["extracted"] = False
            else:
                result["extracted"] = True
                result["can_delete"] = True
                result["message"] = f"OK ({len(zip_members)} súborov overených)"

    except zipfile.BadZipFile:
        result["message"] = "Poškodený ZIP súbor"
    except Exception as e:
        result["message"] = f"Chyba: {str(e)}"

    return result


def delete_zip_file(zip_path: Path) -> dict:
    """Vymaže ZIP súbor."""
    result = {
        "path": zip_path,
        "deleted": False,
        "message": "",
        "freed_size": 0
    }

    try:
        size = zip_path.stat().st_size
        zip_path.unlink()
        result["deleted"] = True
        result["freed_size"] = size
        result["message"] = "Vymazaný"
    except PermissionError:
        result["message"] = "Nedostatočné oprávnenia"
    except Exception as e:
        result["message"] = f"Chyba: {str(e)}"

    return result


def open_directory_dialog() -> str:
    """Otvorí GUI dialóg pre výber adresára pomocou yad."""
    try:
        result = subprocess.run(
            ["yad", "--file", "--directory", "--title=Vybrať adresár"],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


@rt("/browse")
def get():
    """Otvorí GUI dialóg a vráti vybranú cestu."""
    path = open_directory_dialog()
    return Input(
        type="text",
        name="directory",
        id="directory",
        value=path,
        placeholder="/cesta/k/adresaru",
        required=True
    )


@rt("/")
def get():
    """Hlavná stránka s formulárom."""
    return Titled("ZIP Extractor",
        Div(
            P("Zadajte cestu k adresáru, v ktorom chcete extrahovať všetky ZIP súbory."),
            Form(
                Div(
                    Label("Cesta k adresáru:", fr="directory"),
                    Div(
                        Input(
                            type="text",
                            name="directory",
                            id="directory",
                            placeholder="/cesta/k/adresaru",
                            required=True
                        ),
                        Button(
                            "Prehľadávať...",
                            type="button",
                            cls="btn-browse",
                            hx_get="/browse",
                            hx_target="#directory",
                            hx_swap="outerHTML"
                        ),
                        cls="input-group"
                    ),
                    cls="form-group"
                ),
                Div(
                    Input(type="checkbox", name="recursive", id="recursive", checked=True),
                    Label(" Rekurzívne (vrátane podadresárov)", fr="recursive"),
                    cls="checkbox-group"
                ),
                Div(
                    Input(type="checkbox", name="parallel", id="parallel", checked=(MAX_WORKERS > 1)),
                    Label(f" Paralelna extrakcia (max {MAX_WORKERS} workerov)", fr="parallel"),
                    cls="checkbox-group"
                ),
                Div(
                    Label("Pri konflikte cieloveho priecinka:", fr="conflict_policy"),
                    Select(
                        Option("Preskocit", value="skip", selected=True),
                        Option("Prepisat", value="overwrite"),
                        Option("Pridat suffix", value="suffix"),
                        name="conflict_policy",
                        id="conflict_policy"
                    ),
                    cls="form-group"
                ),
                Div(
                    Button("Extrahovať ZIP súbory", type="submit", formaction="/extract"),
                    Button("Vymazať extrahované ZIP súbory", type="submit", formaction="/cleanup", cls="btn-danger"),
                    cls="action-buttons"
                ),
                method="post"
            ),
            P(f"Povoleny root: {BASE_DIR}" if not ALLOW_ANY_PATH else "Povoleny root: (neobmedzeny)"),
            cls="container"
        )
    )


@rt("/extract")
def post(directory: str, recursive: str | None = None, conflict_policy: str = "skip", parallel: str | None = None):
    """Spracuje extrakciu ZIP súborov."""
    is_recursive = recursive is not None
    use_parallel = parallel is not None and MAX_WORKERS > 1
    path = Path(directory).expanduser().resolve()

    # Validácia adresára
    if not path.exists():
        return Titled("ZIP Extractor",
            Div(
                Div(f"Adresár '{directory}' neexistuje!", cls="error-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container"
            )
        )

    if not path.is_dir():
        return Titled("ZIP Extractor",
            Div(
                Div(f"'{directory}' nie je adresár!", cls="error-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container"
            )
        )

    is_allowed, message = validate_base_dir(path)
    if not is_allowed:
        return Titled("ZIP Extractor",
            Div(
                Div(message, cls="error-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container"
            )
        )

    # Vyhľadanie ZIP súborov
    zip_files = find_zip_files(path, is_recursive)
    first_zip = next(zip_files, None)
    if first_zip is None:
        return Titled("ZIP Extractor",
            Div(
                Div("V zadanom adresári sa nenašli žiadne ZIP súbory.", cls="info-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container"
            )
        )
    zip_files = itertools.chain([first_zip], zip_files)

    operation_id = uuid.uuid4().hex[:8]
    log_path = LOG_DIR / f"extract_{operation_id}.log"
    log_event(log_path, f"Start extrakcie v {path}")

    # Extrakcia a zbieranie štatistík
    stats = {
        "found": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "total_files": 0,
        "total_size": 0
    }
    results = []

    def process_zip(zip_file: Path) -> dict:
        return extract_zip(zip_file, conflict_policy, log_path)

    if use_parallel:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for result in executor.map(process_zip, zip_files):
                results.append(result)
                stats["found"] += 1
                if result["success"]:
                    stats["success"] += 1
                    stats["total_files"] += result["files_count"]
                    stats["total_size"] += result["total_size"]
                elif result["skipped"]:
                    stats["skipped"] += 1
                else:
                    stats["failed"] += 1
    else:
        for zip_file in zip_files:
            result = process_zip(zip_file)
            results.append(result)
            stats["found"] += 1
            if result["success"]:
                stats["success"] += 1
                stats["total_files"] += result["files_count"]
                stats["total_size"] += result["total_size"]
            elif result["skipped"]:
                stats["skipped"] += 1
            else:
                stats["failed"] += 1

    # Vytvorenie výstupu
    result_items = []
    for r in results:
        relative_path = r["path"].relative_to(path) if r["path"].is_relative_to(path) else r["path"]
        if r["success"]:
            result_items.append(
                Div(f"✓ {relative_path} - {r['message']}", cls="result-item success")
            )
        elif r["skipped"]:
            result_items.append(
                Div(f"⚠ {relative_path} - {r['message']}", cls="result-item warning")
            )
        else:
            result_items.append(
                Div(f"✗ {relative_path} - {r['message']}", cls="result-item error")
            )

    return Titled("ZIP Extractor - Výsledky",
        Div(
            H2("Štatistika"),
            Div(
                Div(
                    Div(str(stats["found"]), cls="stat-value"),
                    Div("Nájdených ZIP", cls="stat-label"),
                    cls="stat-item"
                ),
                Div(
                    Div(str(stats["success"]), cls="stat-value"),
                    Div("Úspešne extrahovaných", cls="stat-label"),
                    cls="stat-item"
                ),
                Div(
                    Div(str(stats["failed"]), cls="stat-value"),
                    Div("Zlyhané", cls="stat-label"),
                    cls="stat-item"
                ),
                Div(
                    Div(str(stats["skipped"]), cls="stat-value"),
                    Div("Preskocene", cls="stat-label"),
                    cls="stat-item"
                ),
                Div(
                    Div(str(stats["total_files"]), cls="stat-value"),
                    Div("Extrahovaných súborov", cls="stat-label"),
                    cls="stat-item"
                ),
                cls="stats-grid"
            ),
            P(f"Celková veľkosť extrahovaných dát: {format_size(stats['total_size'])}"),
            P(f"ID operacie: {operation_id}"),
            P(f"Log: {log_path}"),
            cls="stats"
        ),
        Div(
            H3("Detail operácií"),
            *result_items,
            cls="results"
        ),
        A("← Nová extrakcia", href="/", cls="back-link"),
        cls="container"
    )


@rt("/cleanup")
def post(directory: str, recursive: str | None = None):
    """Vymaže ZIP súbory, ktoré boli úspešne extrahované."""
    is_recursive = recursive is not None
    path = Path(directory).expanduser().resolve()

    # Validácia adresára
    if not path.exists():
        return Titled("ZIP Extractor",
            Div(
                Div(f"Adresár '{directory}' neexistuje!", cls="error-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container"
            )
        )

    if not path.is_dir():
        return Titled("ZIP Extractor",
            Div(
                Div(f"'{directory}' nie je adresár!", cls="error-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container"
            )
        )

    is_allowed, message = validate_base_dir(path)
    if not is_allowed:
        return Titled("ZIP Extractor",
            Div(
                Div(message, cls="error-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container"
            )
        )

    # Vyhľadanie ZIP súborov
    zip_files = find_zip_files(path, is_recursive)
    first_zip = next(zip_files, None)
    if first_zip is None:
        return Titled("ZIP Extractor",
            Div(
                Div("V zadanom adresári sa nenašli žiadne ZIP súbory.", cls="info-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container"
            )
        )
    zip_files = itertools.chain([first_zip], zip_files)

    operation_id = uuid.uuid4().hex[:8]
    log_path = LOG_DIR / f"cleanup_{operation_id}.log"
    log_event(log_path, f"Start cistenia v {path}")

    # Kontrola a mazanie
    stats = {
        "found": 0,
        "extracted": 0,
        "deleted": 0,
        "skipped": 0,
        "failed": 0,
        "freed_size": 0
    }
    results = []

    for zip_file in zip_files:
        stats["found"] += 1
        # Najprv overíme, či je ZIP extrahovaný
        check_result = is_zip_extracted(zip_file)

        if check_result["can_delete"]:
            stats["extracted"] += 1
            # Vymazať ZIP
            delete_result = delete_zip_file(zip_file)
            if delete_result["deleted"]:
                stats["deleted"] += 1
                stats["freed_size"] += delete_result["freed_size"]
                results.append({
                    "path": zip_file,
                    "status": "deleted",
                    "message": f"Vymazaný (uvoľnené {format_size(delete_result['freed_size'])})"
                })
                log_event(log_path, f"OK: {zip_file} - deleted")
            else:
                stats["failed"] += 1
                results.append({
                    "path": zip_file,
                    "status": "error",
                    "message": f"Chyba mazania: {delete_result['message']}"
                })
                log_event(log_path, f"ERROR: {zip_file} - {delete_result['message']}")
        else:
            stats["skipped"] += 1
            results.append({
                "path": zip_file,
                "status": "skipped",
                "message": f"Preskočený: {check_result['message']}"
            })
            log_event(log_path, f"SKIP: {zip_file} - {check_result['message']}")

    # Vytvorenie výstupu
    result_items = []
    for r in results:
        relative_path = r["path"].relative_to(path) if r["path"].is_relative_to(path) else r["path"]
        if r["status"] == "deleted":
            result_items.append(
                Div(f"✓ {relative_path} - {r['message']}", cls="result-item success")
            )
        elif r["status"] == "skipped":
            result_items.append(
                Div(f"⚠ {relative_path} - {r['message']}", cls="result-item warning")
            )
        else:
            result_items.append(
                Div(f"✗ {relative_path} - {r['message']}", cls="result-item error")
            )

    return Titled("ZIP Extractor - Čistenie",
        Div(
            H2("Štatistika čistenia"),
            Div(
                Div(
                    Div(str(stats["found"]), cls="stat-value"),
                    Div("Nájdených ZIP", cls="stat-label"),
                    cls="stat-item"
                ),
                Div(
                    Div(str(stats["deleted"]), cls="stat-value"),
                    Div("Vymazaných", cls="stat-label"),
                    cls="stat-item"
                ),
                Div(
                    Div(str(stats["skipped"]), cls="stat-value"),
                    Div("Preskočených", cls="stat-label"),
                    cls="stat-item"
                ),
                Div(
                    Div(str(stats["failed"]), cls="stat-value"),
                    Div("Zlyhané", cls="stat-label"),
                    cls="stat-item"
                ),
                cls="stats-grid"
            ),
            P(f"Uvoľnené miesto: {format_size(stats['freed_size'])}"),
            P(f"ID operacie: {operation_id}"),
            P(f"Log: {log_path}"),
            cls="stats"
        ),
        Div(
            H3("Detail operácií"),
            *result_items,
            cls="results"
        ),
        A("← Späť", href="/", cls="back-link"),
        cls="container"
    )


if __name__ == "__main__":
    serve()
