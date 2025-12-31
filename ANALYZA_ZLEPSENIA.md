# Analýza projektu: stabilita, bezpečnosť, výkon

## Prehľad aplikácie
- **Názov**: ZIP Extractor
- **Framework**: FastHTML (Python ASGI)
- **Účel**: Hromadná extrakcia ZIP archívov s webovým rozhraním
- **Hlavné súbory**: `unzip_app/` (config.py, zip_ops.py, web.py, log_utils.py)

---

## Aktuálny stav implementácie

### Už implementované bezpečnostné opatrenia
- Path traversal ochrana (`is_safe_member_path`)
- Symlink detekcia a odmietnutie (`is_symlink_info`)
- ZIP bomb ochrana (limity: MAX_FILES, MAX_FILE_SIZE, MAX_TOTAL_SIZE, MAX_COMPRESSION_RATIO)
- BASE_DIR obmedzenie prístupu k súborovému systému
- Atomická extrakcia (temp dir + rename)
- Overenie voľného miesta na disku pred extrakciou

### Už implementované opatrenia pre stabilitu
- Background spracovanie s progress tracking (HTMX)
- Konfliktné politiky (skip/overwrite/suffix)
- Logovanie s timestampom a ID operácie
- PermissionError handling
- Thread-safe prístup k operáciám (Lock)

### Už implementované optimalizácie výkonu
- Generátor pre find_zip_files (streamové spracovanie)
- Paralelná extrakcia (ThreadPoolExecutor)
- Hash set pre porovnanie súborov v is_zip_extracted

---

## Oblasti na zlepšenie

### 1. BEZPEČNOSŤ

#### 1.1 Kritické (vysoká priorita)

| Problém | Popis | Odporúčanie |
|---------|-------|-------------|
| **Žiadna autentifikácia** | Aplikácia je prístupná bez prihlásenia | Pridať HTTP Basic Auth alebo session-based autentifikáciu |
| **Chýba CSRF ochrana** | POST endpointy nemajú CSRF tokeny | Implementovať CSRF tokeny pre všetky formuláre |
| **Subprocess injection** | `yad` command v `open_directory_dialog` - teoreticky bezpečné, ale treba overiť | Použiť `shlex.quote()` pre všetky externé parametre |
| **Command injection cez PATH** | Ak environment obsahuje malicious PATH | Použiť absolútne cesty pre externé programy |

#### 1.2 Stredná priorita

| Problém | Popis | Odporúčanie |
|---------|-------|-------------|
| **Bez rate limitingu** | Útočník môže zahltiť server requesty | Implementovať rate limiting (napr. slowapi) |
| **Development server** | Uvicorn bez HTTPS | Pre produkciu použiť reverse proxy (nginx) s HTTPS |
| **Informácie v error messages** | Stack traces môžu odhaliť internú štruktúru | Sanitizovať chybové správy pre produkciu |
| **Log injection** | User input sa zapisuje do logov bez sanitizácie | Escapovať špeciálne znaky v log správach |
| **Weak operation IDs** | 8-znakový hex z UUID - 32 bitov entropie | Zvážiť dlhšie ID alebo cryptographically secure random |

#### 1.3 Nízka priorita (best practices)

| Problém | Popis | Odporúčanie |
|---------|-------|-------------|
| **Bezpečné mazanie** | Súbory sa mažú štandardne | Pre citlivé dáta zvážiť secure delete |
| **Audit logging** | Chýba štruktúrovaný security audit log | Pridať samostatný audit log pre bezpečnostné udalosti |
| **Content-Security-Policy** | Žiadne CSP headers | Pridať CSP headers pre ochranu pred XSS |

---

### 2. STABILITA

#### 2.1 Kritické

| Problém | Umiestnenie | Odporúčanie |
|---------|-------------|-------------|
| **Memory leak v OPERATIONS** | `web.py:238` - slovník operácií sa nikdy nečistí | Implementovať TTL s automatickým čistením starých operácií |
| **Žiadny timeout na extrakciu** | `zip_ops.py` | Pridať timeout pre jednotlivé ZIP súbory |
| **Žiadne zrušenie operácie** | `web.py` | Pridať možnosť cancellation pre bežiace operácie |
| **Exception v ThreadPool** | `web.py:339` - `future.result()` môže hodiť exception | Obaliť do try-except s proper error handling |

#### 2.2 Stredná priorita

| Problém | Umiestnenie | Odporúčanie |
|---------|-------------|-------------|
| **Log súbory bez rotácie** | `log_utils.py` | Implementovať log rotation (napr. RotatingFileHandler) |
| **Validácia konfigurácie** | `config.py` | Pridať validáciu hodnôt na štarte (napr. MAX_WORKERS > 0) |
| **Graceful shutdown** | `web.py` | Pri ukončení počkať na dokončenie bežiacich operácií |
| **Disk space monitoring** | `zip_ops.py` | Kontrolovať miesto aj počas extrakcie, nielen pred |

#### 2.3 Nízka priorita

| Problém | Umiestnenie | Odporúčanie |
|---------|-------------|-------------|
| **Health check endpoint** | `web.py` | Pridať `/health` endpoint pre monitoring |
| **Metrics** | - | Pridať Prometheus metriky (počet operácií, chyby, etc.) |
| **Structured logging** | `log_utils.py` | Použiť JSON logging pre jednoduchší parsing |

---

### 3. VÝKON

#### 3.1 Stredná priorita

| Problém | Umiestnenie | Odporúčanie |
|---------|-------------|-------------|
| **Materializácia ZIP listu** | `web.py:326` - `list(zip_files)` | Pre veľmi veľké adresáre zvážiť streaming s počítadlom |
| **Duplicitné čítanie ZIP** | `is_zip_extracted` | Cache ZIP metadata ak sa používa opakovane |
| **Synchronous file I/O** | `zip_ops.py` | Pre async framework zvážiť `aiofiles` |
| **No connection pooling** | - | Pre budúce DB/API integrácie použiť connection pools |

#### 3.2 Nízka priorita

| Problém | Umiestnenie | Odporúčanie |
|---------|-------------|-------------|
| **CSS inline** | `web.py:31-204` | Presunúť do externého súboru s cache headers |
| **No gzip compression** | - | Pridať gzip middleware pre responses |
| **Static files caching** | `web.py:277` | Pridať cache headers pre favicon |

---

## Konkrétne návrhy implementácie

### A. Memory leak fix (kritické)

```python
# web.py - pridať cleanup funkcionalitu
import time

OPERATION_TTL = 3600  # 1 hodina

def cleanup_old_operations():
    """Odstráni operácie staršie ako TTL."""
    now = time.time()
    with OPERATIONS_LOCK:
        expired = [
            op_id for op_id, op in OPERATIONS.items()
            if op.status == "done" and (now - op.created_at) > OPERATION_TTL
        ]
        for op_id in expired:
            del OPERATIONS[op_id]

# Spustiť periodicky (napr. cez background task)
```

### B. Exception handling v ThreadPool

```python
# web.py:336-340
for future in as_completed(futures):
    zip_file = futures[future]
    operation.current = str(zip_file)
    try:
        result = future.result()
    except Exception as e:
        result = {
            "path": zip_file,
            "success": False,
            "skipped": False,
            "message": f"Výnimka: {str(e)}",
            "files_count": 0,
            "total_size": 0,
        }
    _apply_result(operation, result)
```

### C. Konfiguračná validácia

```python
# config.py - pridať na koniec
def validate_config():
    """Validuje konfiguráciu na štarte."""
    errors = []
    if MAX_WORKERS < 1:
        errors.append("MAX_WORKERS musí byť >= 1")
    if MAX_ZIP_SIZE < 1:
        errors.append("MAX_ZIP_SIZE musí byť >= 1")
    if MAX_COMPRESSION_RATIO < 1:
        errors.append("MAX_COMPRESSION_RATIO musí byť >= 1")
    if not LOG_DIR.parent.exists():
        errors.append(f"Rodičovský adresár pre LOG_DIR neexistuje: {LOG_DIR.parent}")
    if errors:
        raise ValueError("Konfiguračné chyby:\n" + "\n".join(errors))

validate_config()
```

### D. CSRF ochrana (FastHTML)

```python
# web.py - pridať CSRF token
import secrets

def generate_csrf_token():
    return secrets.token_hex(32)

# V session uložiť token a validovať pri POST
```

---

## Prioritný plán implementácie

### Fáza 1: Kritické bezpečnostné a stabilizačné opravy ✅ IMPLEMENTOVANÉ
1. ✅ Fix memory leak v OPERATIONS dict - `web.py`: pridaný TTL a automatický cleanup
2. ✅ Exception handling v ThreadPool - `web.py`: try-except okolo `future.result()`
3. ✅ Validácia konfigurácie na štarte - `config.py`: `_validate_config()` funkcia
4. ✅ Log sanitization - `log_utils.py`: `sanitize_log_message()` funkcia

### Fáza 2: Bezpečnostné vylepšenia ✅ IMPLEMENTOVANÉ
5. ✅ CSRF ochrana - `security.py`: HMAC-based tokens s časovým obmedzením
6. ✅ Rate limiting - `security.py`: sliding window rate limiter (60 req/min default)
7. ✅ HTTP Basic Auth - `security.py`: voliteľná autentifikácia (UNZIP_AUTH_ENABLED)
8. ✅ Security headers - `security.py`: CSP, X-Frame-Options, X-Content-Type-Options, etc.

### Fáza 3: Stabilita a UX
9. Operation cancellation
10. Extraction timeout
11. Health check endpoint
12. Log rotation

### Fáza 4: Výkon a monitoring
13. Structured logging
14. Metrics (Prometheus)
15. Static files optimization

---

## Testovanie

### Bezpečnostné testy
- [ ] ZIP s path traversal (`../`, absolútne cesty)
- [ ] ZIP so symlinkom mimo target directory
- [ ] ZIP bomb (vysoký kompresný pomer, veľa súborov)
- [ ] CSRF attack simulácia
- [ ] Rate limit test
- [ ] Invalid/malformed input

### Stabilizačné testy
- [ ] Veľký počet concurrent operácií
- [ ] Dlho bežiace operácie
- [ ] Náhle ukončenie servera počas extrakcie
- [ ] Disk full scenario
- [ ] Permission denied scenarios

### Výkonnostné testy
- [ ] Veľký strom adresárov (10000+ ZIP súborov)
- [ ] Veľké ZIP súbory (blízko MAX_ZIP_SIZE)
- [ ] Memory profiling pri dlhodobom behu
- [ ] Response time pod záťažou

---

## Záver

Aplikácia má solídny základ s dobrými bezpečnostnými praktikami (path traversal ochrana, ZIP bomb limity, atomická extrakcia). Hlavné oblasti na zlepšenie sú:

1. **Kritické**: Memory management (OPERATIONS cleanup), exception handling
2. **Dôležité**: Autentifikácia a CSRF pre produkčné nasadenie
3. **Odporúčané**: Structured logging, monitoring, graceful shutdown

Pre lokálne použitie je aplikácia pripravená. Pre produkčné nasadenie s prístupom z siete je potrebné implementovať minimálne autentifikáciu, CSRF ochranu a nasadenie za reverse proxy s HTTPS.
