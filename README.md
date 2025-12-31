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
- Volitelne pouzi "Extrahovat a vymazat ZIP subory" pre okamzite cistenie.
- Po spusteni extrakcie sa zobrazi priebeh s poctom spracovanych ZIP a stranka sa automaticky aktualizuje.
- Spusti extrakciu alebo cistenie ZIP suborov.

## Struktura projektu
- `main.py` - minimalny entrypoint
- `unzip_app/config.py` - konfiguracia a limity
- `unzip_app/log_utils.py` - logovanie operacii
- `unzip_app/security.py` - CSRF, rate limiting, auth, security headers
- `unzip_app/zip_ops.py` - vykonne operacie so ZIP subormi
- `unzip_app/web.py` - UI a HTTP routes
- `unzip_app/static/favicon.ico` - favicon aplikacie
- `unzip_app/__init__.py` - verejne exporty balika

## Konfiguracia (ENV)

### Zakladne nastavenia
- `UNZIP_BASE_DIR` - povoleny root adresar (default: domovsky adresar)
- `UNZIP_ALLOW_ANY_PATH` - povoli akukolvek cestu (`1/true/yes`)
- `UNZIP_LOG_DIR` - adresar pre logy (default: `logs`)
- `UNZIP_MAX_TOTAL_SIZE` - max velkost po rozbaleni (bytes)
- `UNZIP_MAX_FILES` - max pocet suborov v archive
- `UNZIP_MAX_FILE_SIZE` - max velkost jedneho suboru (bytes)
- `UNZIP_MAX_COMPRESSION_RATIO` - max kompresny pomer
- `UNZIP_MAX_ZIP_SIZE` - max velkost ZIP suboru (bytes)
- `UNZIP_MAX_WORKERS` - max pocet workerov pre paralelnu extrakciu

### Bezpecnostne nastavenia
- `UNZIP_SECRET_KEY` - tajny kluc pre CSRF tokeny (default: nahodny)
- `UNZIP_AUTH_ENABLED` - zapne HTTP Basic Auth (`1/true/yes`)
- `UNZIP_AUTH_USERNAME` - meno pre autentifikaciu (default: `admin`)
- `UNZIP_AUTH_PASSWORD` - heslo pre autentifikaciu (povinne ak AUTH_ENABLED)
- `UNZIP_RATE_LIMIT_ENABLED` - zapne rate limiting (default: `true`)
- `UNZIP_RATE_LIMIT_MAX_REQUESTS` - max pocet requestov (default: `60`)
- `UNZIP_RATE_LIMIT_WINDOW_SECONDS` - casove okno v sekundach (default: `60`)

## Bezpecnost a stabilita
- Kontroly proti path traversal a symlink utokom.
- Limity na velkost a pocet suborov pre ochranu pred ZIP bombami.
- Extrakcia do docasneho adresara a atomicke premenovanie.
- CSRF ochrana pre vsetky POST requesty.
- Rate limiting pre ochranu pred zahltenim (60 req/min default).
- Volitelna HTTP Basic Auth pre produkcne nasadenie.
- Security headers (CSP, X-Frame-Options, X-Content-Type-Options).
- Logy operacii v `UNZIP_LOG_DIR` s ID operacie.
  - Adresar `logs/` je v `.gitignore`.
  - Logy je bezpecne cistit.

## Pravidla prace
Pozri `PROJECT_RULES.md`.

## Verification
- Manualna extrakcia: vytvoreny `test_data/sample.zip` a uspesne rozbaleny do `test_data/sample/`
- Log: `logs/manual_extract.log`
