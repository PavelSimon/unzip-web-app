# Analýza projektu: stabilita, bezpečnosť, výkon

## Rozsah
- Aplikácia: ZIP Extractor (FastHTML)
- Súbory: `main.py`, `requirements.txt`
- Ciele: zvýšiť stabilitu, bezpečnosť a výkon pri extrakcii ZIP súborov

## Rýchle zhrnutie
- Stabilita: chýbajú ochrany proti čiastočnej extrakcii, konflikty existujúcich priečinkov, dlhé operácie bežia v requeste bez progresu.
- Bezpečnosť: základná ochrana proti path traversal existuje, ale chýba ochrana pred symlink útokmi a limitovanie rozsahu prístupu k FS.
- Výkon: zbytočné materializovanie veľkých zoznamov a opakované prechádzanie ZIP metadát spomaľuje spracovanie veľkých stromov.

## Stabilita (odporúčania)
- Ošetriť čiastočnú extrakciu a konflikty cieľového priečinka.
  - Extrahovať do dočasného priečinka a po úspechu atomicky premenovať.
  - Ak cieľový priečinok existuje, ponúknuť režim "preskočiť/prehrať/pridať suffix".
- Pridať ochranu proti dlhým requestom a zablokovaniu UI.
  - Presunúť extrakciu do background tasku (thread/process) a zobrazovať priebeh.
  - Pri veľkých operáciách vypnúť detailný log alebo ho stránkovať.
- Zlepšiť diagnostiku.
  - Zber logu do súboru s timestampom a jednoznačným ID operácie.
  - Jednotná štruktúra chýb v UI (kód + popis).
- Zvýšiť robustnosť voči nečakanému FS stavu.
  - `find_zip_files` obaliť ošetrením PermissionError z hlbších priečinkov.
  - Pri extrakcii overiť dostupné miesto (`shutil.disk_usage`) pred spustením.

## Bezpečnosť (odporúčania)
- Zamedziť symlink útokom pri extrakcii.
  - Pred extrakciou filtrovať položky so symlink bitom (`ZipInfo.external_attr`) a odmietnuť ich.
  - Zvážiť povoliť len regulárne súbory a adresáre.
- Obmedziť prístup k súborovému systému.
  - Zaviesť "root" adresár (allowlist) a zakázať extrakciu mimo neho.
  - Validovať vstup tak, aby bol pod povolenou cestou (napr. `BASE_DIR`).
- Sprísniť ochranu proti ZIP bombám.
  - Pridať limity: max počet súborov, max veľkosť jedného súboru, max celková veľkosť.
  - Skontrolovať kompresný pomer (ratio) a odmietnuť extrémne hodnoty.
- Minimalizovať nežiaduce prepísanie súborov.
  - Pred extrakciou skontrolovať, či cieľové súbory existujú, a vyžadovať explicitné povolenie prepísania.
- Prevádzkové zabezpečenie.
  - Ak je app prístupná po sieti, pridať autentifikáciu alebo obmedziť host/port na localhost.
  - Zvážiť CSRF ochranu pri POST ak sa nasadí verejne.

## Výkon (odporúčania)
- Spracovávať ZIP súbory streamovo, nie do veľkého listu.
  - `find_zip_files` nech vracia generator a spracovanie nech iteruje priamo.
  - Znížiť špičkovú pamäť pri veľkých stromoch.
- Minimalizovať opakované čítanie metadát ZIP.
  - `extract_zip` už prechádza `infolist`; to isté nepoužívať ešte raz.
  - Pri čistení znovupoužiť uložené metadáta, alebo zjednodušiť overenie.
- Znížiť počet FS operácií v `is_zip_extracted`.
  - Namiesto opakovaných `exists()` pre každý súbor použiť jednu mapu existujúcich súborov (hash set).
- Paralelizácia s limitom.
  - Voliteľne spracovať viac ZIP súborov paralelne (ThreadPool) s obmedzeným počtom workerov.
  - Stále preferovať I/O limity a postupné uvoľňovanie zdrojov.

## Konkrétne zmeny v kóde (najvyššia hodnota)
1) Bezpečná extrakcia bez symlinkov a s prísnejšími limitmi.
2) Dočasný extrakčný adresár + atomický rename pre stabilitu.
3) Limitovanie prístupu na definovaný root adresár.
4) Streamové spracovanie ZIP súborov bez materializácie listu.

## Poznámky k testovaniu
- ZIP s path traversal (`../`) a absolútnymi cestami.
- ZIP so symlinkom smerujúcim mimo cieľového adresára.
- ZIP bomb (veľa súborov, vysoký pomer kompresie).
- Extrakcia do existujúceho priečinka s konfliktmi.
- Veľký strom adresárov (výkon a stabilita).
