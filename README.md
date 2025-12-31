# ZIP Extractor

Web aplikacia na hromadnu extrakciu ZIP suborov v zadanom adresari.

## Poziadavky
- Python 3.11+
- python-fasthtml
- (volitelne) `yad` pre GUI vyber adresara

## Spustenie (uv)
```bash
uv venv .venv
uv pip install -r requirements.txt
uv run python main.py
```

Alternativy:
```bash
make setup
make run
```

alebo:
```bash
./scripts/run.sh
```

Otvor `http://localhost:5001` (default FastHTML).

## Pouzitie
- Zadaj cestu k adresaru.
- Zvol politiku konfliktu cieloveho priecinka: skip/overwrite/suffix.
- Volitelne zapni paralelnu extrakciu.
- Spusti extrakciu alebo cistenie ZIP suborov.

## Struktura projektu
- `main.py` - minimalny entrypoint
- `unzip_app/config.py` - konfiguracia a limity
- `unzip_app/log_utils.py` - logovanie operacii
- `unzip_app/zip_ops.py` - vykonne operacie so ZIP subormi
- `unzip_app/web.py` - UI a HTTP routes
- `unzip_app/__init__.py` - verejne exporty balika

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

## Bezpecnost a stabilita
- Kontroly proti path traversal a symlink utokom.
- Limity na velkost a pocet suborov pre ochranu pred ZIP bombami.
- Extrakcia do docasneho adresara a atomicke premenovanie.
- Logy operacii v `UNZIP_LOG_DIR` s ID operacie.
  - Adresar `logs/` je v `.gitignore`.
  - Logy je bezpecne cistit.

## Pravidla prace
Pozri `PROJECT_RULES.md`.

## Verification
- Manualna extrakcia: vytvoreny `test_data/sample.zip` a uspesne rozbaleny do `test_data/sample/`
- Log: `logs/manual_extract.log`
