"""
ZIP Extractor - Web aplikácia pre hromadnú extrakciu ZIP súborov
Postavené na FastHTML frameworku
"""

from fasthtml.common import *
from pathlib import Path
import zipfile
import subprocess

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


def format_size(size_bytes: int) -> str:
    """Formátuje veľkosť v bajtoch na čitateľný formát."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def find_zip_files(directory: Path, recursive: bool = True) -> list[Path]:
    """Nájde všetky ZIP súbory v adresári."""
    if recursive:
        return list(directory.rglob("*.zip"))
    else:
        return list(directory.glob("*.zip"))


def extract_zip(zip_path: Path) -> dict:
    """
    Extrahuje ZIP súbor do priečinka s rovnakým názvom.
    Vráti slovník s výsledkom operácie.
    """
    result = {
        "path": zip_path,
        "success": False,
        "message": "",
        "files_count": 0,
        "total_size": 0
    }

    extract_to = zip_path.parent / zip_path.stem

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Kontrola na ZIP bomb (max 1GB po extrakcii)
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > 1024 * 1024 * 1024:  # 1GB limit
                result["message"] = "Príliš veľký archív (>1GB)"
                return result

            # Kontrola na path traversal
            for member in zf.namelist():
                member_path = extract_to / member
                try:
                    member_path.resolve().relative_to(extract_to.resolve())
                except ValueError:
                    result["message"] = "Bezpečnostná chyba: path traversal"
                    return result

            # Vytvorenie cieľového adresára
            extract_to.mkdir(exist_ok=True)

            # Extrakcia
            zf.extractall(extract_to)

            result["success"] = True
            result["files_count"] = len(zf.namelist())
            result["total_size"] = total_size
            result["message"] = f"OK ({result['files_count']} súborov)"

    except zipfile.BadZipFile:
        result["message"] = "Poškodený ZIP súbor"
    except PermissionError:
        result["message"] = "Nedostatočné oprávnenia"
    except OSError as e:
        result["message"] = f"Chyba systému: {e.strerror}"
    except Exception as e:
        result["message"] = f"Neočakávaná chyba: {str(e)}"

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
                    zip_members.add(info.filename)

            # Kontrola, či všetky súbory existujú
            missing_files = []
            for member in zip_members:
                member_path = extract_dir / member
                if not member_path.exists():
                    missing_files.append(member)

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
                    Button("Extrahovať ZIP súbory", type="submit", formaction="/extract"),
                    Button("Vymazať extrahované ZIP súbory", type="submit", formaction="/cleanup", cls="btn-danger"),
                    cls="action-buttons"
                ),
                method="post"
            ),
            cls="container"
        )
    )


@rt("/extract")
def post(directory: str, recursive: bool = False):
    """Spracuje extrakciu ZIP súborov."""
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

    # Vyhľadanie ZIP súborov
    zip_files = find_zip_files(path, recursive)

    if not zip_files:
        return Titled("ZIP Extractor",
            Div(
                Div("V zadanom adresári sa nenašli žiadne ZIP súbory.", cls="info-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container"
            )
        )

    # Extrakcia a zbieranie štatistík
    stats = {
        "found": len(zip_files),
        "success": 0,
        "failed": 0,
        "total_files": 0,
        "total_size": 0
    }
    results = []

    for zip_file in zip_files:
        result = extract_zip(zip_file)
        results.append(result)

        if result["success"]:
            stats["success"] += 1
            stats["total_files"] += result["files_count"]
            stats["total_size"] += result["total_size"]
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
                    Div(str(stats["total_files"]), cls="stat-value"),
                    Div("Extrahovaných súborov", cls="stat-label"),
                    cls="stat-item"
                ),
                cls="stats-grid"
            ),
            P(f"Celková veľkosť extrahovaných dát: {format_size(stats['total_size'])}"),
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
def post(directory: str, recursive: bool = False):
    """Vymaže ZIP súbory, ktoré boli úspešne extrahované."""
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

    # Vyhľadanie ZIP súborov
    zip_files = find_zip_files(path, recursive)

    if not zip_files:
        return Titled("ZIP Extractor",
            Div(
                Div("V zadanom adresári sa nenašli žiadne ZIP súbory.", cls="info-message"),
                A("← Späť", href="/", cls="back-link"),
                cls="container"
            )
        )

    # Kontrola a mazanie
    stats = {
        "found": len(zip_files),
        "extracted": 0,
        "deleted": 0,
        "skipped": 0,
        "failed": 0,
        "freed_size": 0
    }
    results = []

    for zip_file in zip_files:
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
            else:
                stats["failed"] += 1
                results.append({
                    "path": zip_file,
                    "status": "error",
                    "message": f"Chyba mazania: {delete_result['message']}"
                })
        else:
            stats["skipped"] += 1
            results.append({
                "path": zip_file,
                "status": "skipped",
                "message": f"Preskočený: {check_result['message']}"
            })

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
