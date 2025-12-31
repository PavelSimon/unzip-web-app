"""Web routes and UI for ZIP Extractor."""

from fasthtml.common import *
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from threading import Lock, Thread
from typing import Iterable
import itertools
import subprocess
import uuid

from starlette.responses import FileResponse

from .config import ALLOW_ANY_PATH, BASE_DIR, LOG_DIR, MAX_WORKERS
from .log_utils import log_event
from .zip_ops import (
    delete_zip_file,
    extract_zip,
    find_zip_files,
    is_zip_extracted,
    validate_base_dir,
)

__all__ = ["app", "rt", "format_size"]

FAVICON_PATH = Path(__file__).resolve().parent / "static" / "favicon.ico"

app, rt = fast_app(
    hdrs=[
        Link(rel="icon", href="/favicon.ico"),
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
            .progress {
                background: #e9ecef;
                border-radius: 6px;
                overflow: hidden;
                height: 12px;
                margin: 10px 0;
            }
            .progress-bar {
                background: #007bff;
                height: 100%;
                transition: width 0.3s ease;
            }
            .progress-bar.indeterminate {
                width: 100%;
                background: linear-gradient(90deg, #007bff 0%, #8cc0ff 50%, #007bff 100%);
                background-size: 200% 100%;
                animation: progress-move 1.2s linear infinite;
            }
            @keyframes progress-move {
                from { background-position: 0% 0; }
                to { background-position: 200% 0; }
            }
        """)
    ]
)

@dataclass
class Operation:
    """Track the state of a background extraction operation."""
    operation_id: str
    path: Path
    conflict_policy: str
    recursive: bool
    parallel: bool
    log_path: Path
    stats: dict[str, int] = field(
        default_factory=lambda: {
            "found": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "total_files": 0,
            "total_size": 0,
        }
    )
    results: list[dict[str, object]] = field(default_factory=list)
    status: str = "running"
    message: str = ""
    total: int | None = None
    current: str = ""


OPERATIONS: dict[str, Operation] = {}
OPERATIONS_LOCK = Lock()


def store_operation(operation: Operation) -> None:
    with OPERATIONS_LOCK:
        OPERATIONS[operation.operation_id] = operation


def get_operation(operation_id: str) -> Operation | None:
    with OPERATIONS_LOCK:
        return OPERATIONS.get(operation_id)


def format_size(size_bytes: int) -> str:
    """Format size in bytes to a human readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def open_directory_dialog() -> str:
    """Open GUI dialog for directory selection using yad."""
    try:
        result = subprocess.run(
            ["yad", "--file", "--directory", "--title=Vybrať adresár"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


@rt("/favicon.ico")
def get():
    """Serve the application favicon."""
    if not FAVICON_PATH.exists():
        return Div(Div("favicon.ico nenajdeny", cls="error-message"))
    return FileResponse(FAVICON_PATH, media_type="image/x-icon")


def _apply_result(operation: Operation, result: dict[str, object]) -> None:
    operation.results.append(result)
    operation.stats["found"] += 1
    if result["success"]:
        operation.stats["success"] += 1
        operation.stats["total_files"] += int(result["files_count"])
        operation.stats["total_size"] += int(result["total_size"])
    elif result["skipped"]:
        operation.stats["skipped"] += 1
    else:
        operation.stats["failed"] += 1


def _collect_results(
    operation: Operation,
    zip_files: Iterable[Path],
    process_zip,
    use_parallel: bool,
) -> None:
    if use_parallel:
        zip_list = list(zip_files)
        operation.total = len(zip_list)
        if not zip_list:
            operation.message = "V zadanom adresári sa nenašli žiadne ZIP súbory."
            operation.status = "done"
            return
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(process_zip, zip_file): zip_file for zip_file in zip_list}
            for future in as_completed(futures):
                zip_file = futures[future]
                operation.current = str(zip_file)
                result = future.result()
                _apply_result(operation, result)
    else:
        found_any = False
        for zip_file in zip_files:
            found_any = True
            operation.current = str(zip_file)
            result = process_zip(zip_file)
            _apply_result(operation, result)
        if not found_any:
            operation.message = "V zadanom adresári sa nenašli žiadne ZIP súbory."
            operation.status = "done"


def run_extraction(operation_id: str) -> None:
    operation = get_operation(operation_id)
    if operation is None:
        return
    try:
        log_event(operation.log_path, f"Start extrakcie v {operation.path}")

        def process_zip(zip_file: Path) -> dict:
            return extract_zip(zip_file, operation.conflict_policy, operation.log_path)

        zip_files = find_zip_files(operation.path, operation.recursive)
        use_parallel = operation.parallel and MAX_WORKERS > 1
        _collect_results(operation, zip_files, process_zip, use_parallel)
        if operation.status != "done":
            operation.status = "done"
    except Exception as exc:
        operation.status = "error"
        operation.message = f"Neocakavana chyba: {exc}"


def _result_items(operation: Operation) -> list:
    result_items = []
    for result in operation.results:
        relative_path = (
            result["path"].relative_to(operation.path)
            if result["path"].is_relative_to(operation.path)
            else result["path"]
        )
        if result["success"]:
            result_items.append(Div(f"✓ {relative_path} - {result['message']}", cls="result-item success"))
        elif result["skipped"]:
            result_items.append(Div(f"⚠ {relative_path} - {result['message']}", cls="result-item warning"))
        else:
            result_items.append(Div(f"✗ {relative_path} - {result['message']}", cls="result-item error"))
    return result_items


def render_progress(operation: Operation) -> object:
    total = operation.total
    processed = operation.stats["found"]
    if total:
        percent = min(100, int((processed / total) * 100))
        progress_bar = Div(cls="progress", children=Div(cls="progress-bar", style=f"width: {percent}%"))
        progress_label = P(f"Spracované: {processed}/{total} ({percent}%)")
    else:
        progress_bar = Div(cls="progress", children=Div(cls="progress-bar indeterminate"))
        progress_label = P(f"Spracované: {processed}")

    current = P(f"Aktuálne: {Path(operation.current).name}") if operation.current else ""

    return Div(
        H2("Prebieha extrakcia"),
        progress_bar,
        progress_label,
        current,
        Div(
            Div(Div(str(operation.stats["success"]), cls="stat-value"), Div("Úspešne", cls="stat-label"), cls="stat-item"),
            Div(Div(str(operation.stats["failed"]), cls="stat-value"), Div("Zlyhané", cls="stat-label"), cls="stat-item"),
            Div(Div(str(operation.stats["skipped"]), cls="stat-value"), Div("Preskočené", cls="stat-label"), cls="stat-item"),
            Div(
                Div(str(operation.stats["total_files"]), cls="stat-value"),
                Div("Extrahovaných súborov", cls="stat-label"),
                cls="stat-item",
            ),
            cls="stats-grid",
        ),
        P(f"Celková veľkosť extrahovaných dát: {format_size(operation.stats['total_size'])}"),
        P(f"ID operácie: {operation.operation_id}"),
        P(f"Log: {operation.log_path}"),
        cls="stats",
    )


def render_results(operation: Operation) -> object:
    if operation.message:
        return Div(Div(operation.message, cls="info-message"), A("← Späť", href="/", cls="back-link"))

    result_items = _result_items(operation)
    return Div(
        Div(
            H2("Štatistika"),
            Div(
                Div(Div(str(operation.stats["found"]), cls="stat-value"), Div("Nájdených ZIP", cls="stat-label"), cls="stat-item"),
                Div(
                    Div(str(operation.stats["success"]), cls="stat-value"),
                    Div("Úspešne extrahovaných", cls="stat-label"),
                    cls="stat-item",
                ),
                Div(Div(str(operation.stats["failed"]), cls="stat-value"), Div("Zlyhané", cls="stat-label"), cls="stat-item"),
                Div(Div(str(operation.stats["skipped"]), cls="stat-value"), Div("Preskočené", cls="stat-label"), cls="stat-item"),
                Div(
                    Div(str(operation.stats["total_files"]), cls="stat-value"),
                    Div("Extrahovaných súborov", cls="stat-label"),
                    cls="stat-item",
                ),
                cls="stats-grid",
            ),
            P(f"Celková veľkosť extrahovaných dát: {format_size(operation.stats['total_size'])}"),
            P(f"ID operácie: {operation.operation_id}"),
            P(f"Log: {operation.log_path}"),
            cls="stats",
        ),
        Div(H3("Detail operácií"), *result_items, cls="results"),
        A("← Nová extrakcia", href="/", cls="back-link"),
    )


@rt("/browse")
def get():
    """Open GUI dialog and return selected path."""
    path = open_directory_dialog()
    return Input(
        type="text",
        name="directory",
        id="directory",
        value=path,
        placeholder="/cesta/k/adresaru",
        required=True,
    )


@rt("/")
def get():
    """Main page with the form."""
    return Titled(
        "ZIP Extractor",
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
                            required=True,
                        ),
                        Button(
                            "Prehľadávať...",
                            type="button",
                            cls="btn-browse",
                            hx_get="/browse",
                            hx_target="#directory",
                            hx_swap="outerHTML",
                        ),
                        cls="input-group",
                    ),
                    cls="form-group",
                ),
                Div(
                    Input(type="checkbox", name="recursive", id="recursive", checked=True),
                    Label(" Rekurzívne (vrátane podadresárov)", fr="recursive"),
                    cls="checkbox-group",
                ),
                Div(
                    Input(type="checkbox", name="parallel", id="parallel", checked=(MAX_WORKERS > 1)),
                    Label(f" Paralelna extrakcia (max {MAX_WORKERS} workerov)", fr="parallel"),
                    cls="checkbox-group",
                ),
                Div(
                    Label("Pri konflikte cieloveho priecinka:", fr="conflict_policy"),
                    Select(
                        Option("Preskocit", value="skip", selected=True),
                        Option("Prepisat", value="overwrite"),
                        Option("Pridat suffix", value="suffix"),
                        name="conflict_policy",
                        id="conflict_policy",
                    ),
                    cls="form-group",
                ),
                Div(
                    Button("Extrahovať ZIP súbory", type="submit", formaction="/extract"),
                    Button(
                        "Vymazať extrahované ZIP súbory",
                        type="submit",
                        formaction="/cleanup",
                        cls="btn-danger",
                    ),
                    cls="action-buttons",
                ),
                method="post",
            ),
            P(f"Povoleny root: {BASE_DIR}" if not ALLOW_ANY_PATH else "Povoleny root: (neobmedzeny)"),
            cls="container",
        ),
    )


@rt("/extract")
def post(directory: str, recursive: str | None = None, conflict_policy: str = "skip", parallel: str | None = None):
    """Handle ZIP extraction."""
    is_recursive = recursive is not None
    use_parallel = parallel is not None and MAX_WORKERS > 1
    path = Path(directory).expanduser().resolve()

    if not path.exists():
        return Titled(
            "ZIP Extractor",
            Div(
                Div(f"Adresár '{directory}' neexistuje!", cls="error-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container",
            ),
        )

    if not path.is_dir():
        return Titled(
            "ZIP Extractor",
            Div(
                Div(f"'{directory}' nie je adresár!", cls="error-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container",
            ),
        )

    is_allowed, message = validate_base_dir(path)
    if not is_allowed:
        return Titled(
            "ZIP Extractor",
            Div(
                Div(message, cls="error-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container",
            ),
        )

    operation_id = uuid.uuid4().hex[:8]
    log_path = LOG_DIR / f"extract_{operation_id}.log"
    operation = Operation(
        operation_id=operation_id,
        path=path,
        conflict_policy=conflict_policy,
        recursive=is_recursive,
        parallel=use_parallel,
        log_path=log_path,
    )
    store_operation(operation)
    Thread(target=run_extraction, args=(operation_id,), daemon=True).start()

    return Titled(
        "ZIP Extractor - Priebeh",
        Div(
            Div(
                "Extrakcia beží na pozadí. Stránka sa bude automaticky aktualizovať.",
                cls="info-message",
            ),
            Div(
                id=f"operation-{operation_id}",
                hx_get=f"/status/{operation_id}",
                hx_trigger="load, every 1s",
                hx_swap="outerHTML",
            ),
            cls="container",
        ),
    )


@rt("/status/{operation_id}")
def get(operation_id: str):
    """Return progress or results for a background extraction."""
    operation = get_operation(operation_id)
    if operation is None:
        return Div(Div("Operácia neexistuje alebo expirovala.", cls="error-message"))

    if operation.status == "error":
        return Div(
            id=f"operation-{operation_id}",
            children=Div(operation.message or "Neocakavana chyba.", cls="error-message"),
        )

    if operation.status == "done":
        return Div(
            id=f"operation-{operation_id}",
            children=render_results(operation),
        )

    return Div(
        id=f"operation-{operation_id}",
        children=render_progress(operation),
        hx_get=f"/status/{operation_id}",
        hx_trigger="load, every 1s",
        hx_swap="outerHTML",
    )


@rt("/cleanup")
def post(directory: str, recursive: str | None = None):
    """Delete ZIP files that were extracted successfully."""
    is_recursive = recursive is not None
    path = Path(directory).expanduser().resolve()

    if not path.exists():
        return Titled(
            "ZIP Extractor",
            Div(
                Div(f"Adresár '{directory}' neexistuje!", cls="error-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container",
            ),
        )

    if not path.is_dir():
        return Titled(
            "ZIP Extractor",
            Div(
                Div(f"'{directory}' nie je adresár!", cls="error-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container",
            ),
        )

    is_allowed, message = validate_base_dir(path)
    if not is_allowed:
        return Titled(
            "ZIP Extractor",
            Div(
                Div(message, cls="error-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container",
            ),
        )

    zip_files = find_zip_files(path, is_recursive)
    first_zip = next(zip_files, None)
    if first_zip is None:
        return Titled(
            "ZIP Extractor",
            Div(
                Div("V zadanom adresári sa nenašli žiadne ZIP súbory.", cls="info-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container",
            ),
        )
    zip_files = itertools.chain([first_zip], zip_files)

    operation_id = uuid.uuid4().hex[:8]
    log_path = LOG_DIR / f"cleanup_{operation_id}.log"
    log_event(log_path, f"Start cistenia v {path}")

    stats = {
        "found": 0,
        "extracted": 0,
        "deleted": 0,
        "skipped": 0,
        "failed": 0,
        "freed_size": 0,
    }
    results = []

    for zip_file in zip_files:
        stats["found"] += 1
        check_result = is_zip_extracted(zip_file)

        if check_result["can_delete"]:
            stats["extracted"] += 1
            delete_result = delete_zip_file(zip_file)
            if delete_result["deleted"]:
                stats["deleted"] += 1
                stats["freed_size"] += delete_result["freed_size"]
                results.append(
                    {
                        "path": zip_file,
                        "status": "deleted",
                        "message": f"Vymazaný (uvoľnené {format_size(delete_result['freed_size'])})",
                    }
                )
                log_event(log_path, f"OK: {zip_file} - deleted")
            else:
                stats["failed"] += 1
                results.append(
                    {
                        "path": zip_file,
                        "status": "error",
                        "message": f"Chyba mazania: {delete_result['message']}",
                    }
                )
                log_event(log_path, f"ERROR: {zip_file} - {delete_result['message']}")
        else:
            stats["skipped"] += 1
            results.append(
                {
                    "path": zip_file,
                    "status": "skipped",
                    "message": f"Preskočený: {check_result['message']}",
                }
            )
            log_event(log_path, f"SKIP: {zip_file} - {check_result['message']}")

    result_items = []
    for r in results:
        relative_path = r["path"].relative_to(path) if r["path"].is_relative_to(path) else r["path"]
        if r["status"] == "deleted":
            result_items.append(Div(f"✓ {relative_path} - {r['message']}", cls="result-item success"))
        elif r["status"] == "skipped":
            result_items.append(Div(f"⚠ {relative_path} - {r['message']}", cls="result-item warning"))
        else:
            result_items.append(Div(f"✗ {relative_path} - {r['message']}", cls="result-item error"))

    return Titled(
        "ZIP Extractor - Čistenie",
        Div(
            H2("Štatistika čistenia"),
            Div(
                Div(Div(str(stats["found"]), cls="stat-value"), Div("Nájdených ZIP", cls="stat-label"), cls="stat-item"),
                Div(Div(str(stats["deleted"]), cls="stat-value"), Div("Vymazaných", cls="stat-label"), cls="stat-item"),
                Div(Div(str(stats["skipped"]), cls="stat-value"), Div("Preskočených", cls="stat-label"), cls="stat-item"),
                Div(Div(str(stats["failed"]), cls="stat-value"), Div("Zlyhané", cls="stat-label"), cls="stat-item"),
                cls="stats-grid",
            ),
            P(f"Uvoľnené miesto: {format_size(stats['freed_size'])}"),
            P(f"ID operacie: {operation_id}"),
            P(f"Log: {log_path}"),
            cls="stats",
        ),
        Div(H3("Detail operácií"), *result_items, cls="results"),
        A("← Späť", href="/", cls="back-link"),
        cls="container",
    )
