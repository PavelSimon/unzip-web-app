# Analýza: ZIP Extractor Web Aplikácia

## Prehľad

Web aplikácia postavená na **FastHTML** frameworku, ktorá umožňuje používateľovi vybrať adresár na lokálnom počítači a automaticky extrahuje všetky ZIP súbory v tomto adresári (vrátane podadresárov).

---

## Technológie

| Technológia | Účel |
|-------------|------|
| **Python 3.11+** | Programovací jazyk |
| **FastHTML** | Web framework (minimalistický, moderný) |
| **zipfile** | Štandardná knižnica pre prácu so ZIP |
| **pathlib** | Práca s cestami súborov |
| **asyncio** | Asynchrónne spracovanie (voliteľné) |

---

## Architektúra

```
unzip/
├── main.py               # Minimalny entrypoint
├── unzip_app/            # Logika aplikacie
│   ├── config.py         # Konfiguracia a limity
│   ├── log_utils.py      # Logovanie
│   ├── zip_ops.py        # Operacie so ZIP
│   └── web.py            # UI a routes
├── ANALYZA.md            # Tento súbor
└── requirements.txt      # Závislosti
```

---

## Funkcionálne požiadavky

### 1. Vstup adresára
- Používateľ zadá cestu k adresáru cez textové pole
- Validácia: kontrola či adresár existuje
- Bezpečnosť: kontrola prístupových práv

### 1a. Nastavenia extrakcie
- Politika konfliktu cieloveho priecinka: skip/overwrite/suffix
- Volitelna paralelna extrakcia (max workerov z ENV)

### 2. Vyhľadanie ZIP súborov
- Rekurzívne prehľadanie adresára (vrátane podadresárov)
- Vyhľadanie všetkých súborov s príponou `.zip`
- Zobrazenie zoznamu nájdených súborov pred extrakciou

### 3. Extrakcia súborov
- Každý ZIP sa extrahuje do rovnakého adresára kde sa nachádza
- Názov cieľového priečinka = názov ZIP súboru (bez .zip)
- Ošetrenie chýb: poškodené ZIP súbory, nedostatok miesta, práva

### 4. Štatistika
Po dokončení zobraziť:
- Celkový počet nájdených ZIP súborov
- Počet úspešne extrahovaných
- Počet zlyhaných (s dôvodom)
- Celkový počet extrahovaných súborov
- Celková veľkosť extrahovaných dát

---

## Návrh UI

### Hlavná stránka

```
┌─────────────────────────────────────────────────┐
│          ZIP Extractor                          │
├─────────────────────────────────────────────────┤
│                                                 │
│  Adresár: [________________________] [Spustiť]  │
│                                                 │
│  ☑ Rekurzívne (vrátane podadresárov)           │
│                                                 │
├─────────────────────────────────────────────────┤
│  Priebeh:                                       │
│  ████████████░░░░░░░░ 60% (3/5 súborov)        │
│                                                 │
│  Aktuálne: archive.zip                          │
├─────────────────────────────────────────────────┤
│  Log:                                           │
│  ✓ data.zip - OK (15 súborov)                  │
│  ✓ backup.zip - OK (8 súborov)                 │
│  ✗ corrupted.zip - CHYBA: Poškodený archív    │
├─────────────────────────────────────────────────┤
│  ŠTATISTIKA                                     │
│  ─────────────                                  │
│  Nájdených ZIP: 5                               │
│  Úspešne: 4                                     │
│  Zlyhané: 1                                     │
│  Extrahovaných súborov: 47                      │
│  Celková veľkosť: 128.5 MB                      │
└─────────────────────────────────────────────────┘
```

---

## Implementačný plán

### Krok 1: Základná štruktúra
- Vytvorenie `main.py` s FastHTML aplikáciou
- Definícia routes: `/` (hlavná stránka), `/extract` (POST)

### Krok 2: Backend logika
- Funkcia `find_zip_files(directory, recursive=True)` - vyhľadanie ZIP súborov
- Funkcia `extract_zip(zip_path)` - extrakcia jedného ZIP súboru
- Funkcia `process_directory(directory)` - orchestrácia celého procesu

### Krok 3: Frontend
- Formulár pre zadanie adresára
- Zobrazenie priebehu (progress bar)
- Výpis logu a štatistiky

### Krok 4: Ošetrenie chýb
- Neexistujúci adresár
- Poškodené ZIP súbory
- Nedostatok miesta na disku
- Problémy s právami

---

## Bezpečnostné aspekty

1. **Path traversal** - validácia cesty, zabránenie prístupu mimo povolené adresáre
2. **ZIP bomb** - limit na veľkosť extrahovaných dát
3. **Symlink útoky** - kontrola symbolických odkazov v ZIP archívoch
4. **Root limit** - spracovanie len pod urcenym base adresarom (UNZIP_BASE_DIR)
5. **Konflikty** - politika pre existujuci cielovy priecinok (skip/overwrite/suffix)
6. **Logovanie** - zapis operacii do `logs/` pre audit a diagnostiku

---

## Konfiguracia (ENV)

- `UNZIP_BASE_DIR` - povoleny root adresar (default: domovsky adresar)
- `UNZIP_ALLOW_ANY_PATH` - povoli akukolvek cestu (`1/true/yes`)
- `UNZIP_LOG_DIR` - adresar pre logy (default: `logs`)
- `UNZIP_MAX_TOTAL_SIZE` - max velkost po rozbaleni (bytes)
- `UNZIP_MAX_FILES` - max pocet suborov v archive
- `UNZIP_MAX_FILE_SIZE` - max velkost jedneho suboru (bytes)
- `UNZIP_MAX_COMPRESSION_RATIO` - max kompresny pomer
- `UNZIP_MAX_ZIP_SIZE` - max velkost ZIP suboru (bytes)
- `UNZIP_MAX_WORKERS` - max pocet workerov pre paralelnu extrakciu

---

## Príklad kódu (kostra)

```python
from fasthtml.common import *
from pathlib import Path
import zipfile

app, rt = fast_app()

@rt("/")
def get():
    return Titled("ZIP Extractor",
        Form(
            Input(type="text", name="directory", placeholder="Cesta k adresáru"),
            Button("Spustiť", type="submit"),
            method="post", action="/extract"
        )
    )

@rt("/extract")
def post(directory: str):
    path = Path(directory)
    if not path.exists() or not path.is_dir():
        return P("Adresár neexistuje!", cls="error")

    stats = {"found": 0, "success": 0, "failed": 0, "files": 0}
    results = []

    for zip_file in path.rglob("*.zip"):
        stats["found"] += 1
        try:
            with zipfile.ZipFile(zip_file, 'r') as zf:
                extract_to = zip_file.parent / zip_file.stem
                zf.extractall(extract_to)
                stats["success"] += 1
                stats["files"] += len(zf.namelist())
                results.append(f"✓ {zip_file.name} - OK")
        except Exception as e:
            stats["failed"] += 1
            results.append(f"✗ {zip_file.name} - {str(e)}")

    return Div(
        H2("Štatistika"),
        Ul(*[Li(r) for r in results]),
        P(f"Nájdených: {stats['found']}"),
        P(f"Úspešne: {stats['success']}"),
        P(f"Zlyhané: {stats['failed']}")
    )

serve()
```

---

## Závislosti (requirements.txt)

```
python-fasthtml
```

---

## Rozšírenia (voliteľné, budúcnosť)

- Výber cieľového adresára pre extrakciu
- Podpora hesiel pre ZIP súbory
- Podpora ďalších formátov (RAR, 7z, tar.gz)
- Drag & drop priečinkov
- História operácií

---

## Odhad rozsahu

- **Súbory:** 2-3 (main.py, requirements.txt, prípadne static CSS)
- **Riadky kódu:** ~100-150

---

## Schválenie

Po schválení tejto analýzy začnem s implementáciou.
