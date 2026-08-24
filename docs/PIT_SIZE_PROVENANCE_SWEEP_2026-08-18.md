# FULLSTÄNDIG PROVENANCE-SÖKNING: ALL TIDIGARE SIZE-DATA

Datum 2026-08-18 · **Ingenting ändrat, inga size-tester körda**
Föranledd av korrekt invändning: den tidigare slutsatsen `PIT SIZE DATA AVAILABLE: NO`
byggde på tre kontrollerade källor, inte på en fullständig sökning.

## Rättelse av föregående audit

Sökningen har hittat något min förra audit missade: **en PIT-korrekt källklass för
Large/Mid/Small existerar, är dokumenterad, och 7 av ~16 årgångar är redan
hämtade** — i legacy-repot `momentum_prod_work`, inte i `momentum_v2`.

Det ändrar inte slutdomen om att ett användbart *dataset* saknas, men det ändrar
fyndets karaktär helt: från *"ingen källa finns"* till *"rätt källa finns,
är verifierbar, och arbetet är påbörjat"*.

---

## Sökningens omfattning

| Arbetsyta | Storlek | Genomsökt |
|---|---|---|
| `/home/hannesb/momentum_v2` | — | filnamn + innehåll |
| `/home/hannesb/momentum_prod_work` | 6,7 GB | filnamn + innehåll + git-historik |
| `/opt/momentum` | 5,4 GB | **0 filer utanför `venv/`** |
| `momentum_exports_2026-08-02` + 4 zip-arkiv | — | arkivlistning |

Sökta termer: `market_list`, `market_cap`, `marketcap`, `mcap`, `market_value`,
`marknadsvärde`, `segment`, `list_segment`, `size_class`, `size_segment`,
`cap_segment`, `cap_tier`, `large_cap`, `mid_cap`, `small_cap`,
`number_of_shares`, `shares`, `membership`, `Nasdaq`.

Filtyper: JSON, CSV, Python, Markdown, HTML, zip-arkiv.
**SQLite / DuckDB / Parquet: noll filer i hela arbetsytan.**
Git-historik i `momentum_prod_work`: **inga borttagna** size-/segment-datafiler.

---

## KANDIDATKÄLLOR — klassificering

### 1. Nasdaq Market Cap Segment Review-ledger — **POTENTIALLY_PIT_VALID**

`momentum_prod_work/results/niva3_nasdaq_segment_ledger_stage79_evidence.json`
Byggd av `momentum_ml/run_nasdaq_segment_evidence_stage79.py`, 2026-08-02.

**Detta är den enda källan i hela arbetsytan med korrekt PIT-semantik för Size.**

| Attribut | Innehåll |
|---|---|
| **Source** | Nasdaq Nordics officiella årliga *Market Cap Segment Review*-pressmeddelanden |
| **Segmentdefinition** | Large ≥ EUR 1 mdr · Mid EUR 150 m–1 mdr · Small < EUR 150 m |
| **Observation date** | publiceras i december |
| **Effective date** | **första handelsdagen i januari** därpå |
| **Beslutsunderlag** | novembers genomsnittliga börsvärde |
| **Känt vid beslutstidpunkt?** | **JA** — publicerat ~2 veckor före ikraftträdande |
| **Faktiska segmentbyten** | **JA — daterade `from`/`to`-övergångar** |
| **Avnoterade bolag** | **JA — ledgern är uttryckligen scoopad till avnoterade** |
| **Coverage, årgångar** | **7 av ~16** (2013, 2017, 2019, 2020, 2022, ~2022-23, 2025). Saknas: 2010-2012, 2014-2016, 2018, 2021, 2023-2024 |
| **Coverage, instrument** | 12 `CONFIRMED_DATED` + 4 `CORROBORATED_UNDATED` + 1 tidigare = **15 av 90 avnoterade** |
| **Strukturell begränsning** | pressmeddelandena listar **endast bolag som BYTTE** segment. Utan en baslinjeroster kan nivån inte härledas för bolag som aldrig bytte |
| **Källans egen varning** | *"absence here is not proof of Small/Micro status"* |

#### Konkreta bolag med daterad segmenthistorik

Exakt det mönster invändningen efterfrågade — ett bolag som faktiskt byter segment
över tid:

| Ticker | Segment över tid | Källbelagda övergångar |
|---|---|---|
| **BIOT.ST** (Biotage) | Small → **Mid** (2017-01-02) → **Large** (2022-01-03) | två `CONFIRMED_DATED` |
| **COLL.ST** (Collector) | Mid → **Large** (2017-01-02) → **Mid** (2019-01-02) | två `CONFIRMED_DATED` |
| **SAS.ST** | Mid → **Large** (2022-01-03) → Mid (~2022-23, datum obekräftat) | en bekräftad, en approximativ |
| **MAG.ST** | Mid → **Small** (2020-01-02) | en `CONFIRMED_DATED` |
| **ELOS-B.ST** | Small → **Mid** (2022-01-03) | en `CONFIRMED_DATED` |
| **RESURS.ST** | Large → **Mid** (2022-01-03) | en `CONFIRMED_DATED` |

BIOT.ST är alltså Small 2015, Mid 2018 och Large 2022 — precis den tidsvariation
som en 2026-etikett raderar.

### 2. `niva3_pit_size_factor_stage91.json` — **INSUFFICIENT_PROVENANCE**

Legacy försökte faktiskt använda ledgern. Utfallet är dokumenterat och entydigt:

| | |
|---|---:|
| `total_ticker_date_observations` | 33 623 |
| `pit_corrected_ticker_date_observations` | **0** |
| `pit_coverage_fraction` | **0.0** |
| Överlapp mellan ledgerns 17 tickers och regressionsuniversumet | **0** |
| Tillämpade PIT-overrides | **1** (`KLED.ST`, 2017-01-02 → Large Cap) |
| `factor_attribution_gate` | **FAIL** · `selection_allowed: false` · `production: false` |

Den PIT-korrigerade intercepten är identisk med den statiska till 15 decimaler —
eftersom ingenting ändrades. Skriptets egen kommentar: N3-79 var scoopad till
**avnoterade** bolag, medan factor-regressionen behöver **kvarvarande** bolags
segmenthistorik, vilket *"would require a NEW evidence-gathering effort"*.

Detta är inte en size-källa. Det är en dokumenterad misslyckad tillämpning.

### 3. `momentum_ml/data/sweden_universe.csv` — **CURRENT_SNAPSHOT_ONLY**

Legacys faktiska size-variabel. Matar `config.CAP_TIER_MAP` via
`load_sweden_universe()` och används av ett stort antal legacy-stages.

| | |
|---|---|
| Kolumner | `ticker, name, sector, market_cap_category` — **noll datumkolumner** |
| Rader | 893 |
| Källa | JerBouma/FinanceDatabase `STO.csv` |
| Filter | *"filtrerat till **icke-avnoterade** aktier"* |

**Avnoterade bolag finns inte alls i filen.** Det är i ett avseende sämre än
Avanza-skrapningen: där märks avnoterade felaktigt som `Terminal`, här saknas de
helt, vilket ger tyst survivorship snarare än synlig kontaminering.

### 4. `momentum_ml/data/omx30_membership_pit.csv` — **PIT_VALID, men inte Size**

50 rader, `member_from` / `member_to`, källa `indexes.nasdaqomx.com`. Genuint
daterad tidsserie — men **OMXS30-indexmedlemskap**, inte Large/Mid/Small. Att
använda den som size-proxy är förbjudet enligt uppdragets egen regel att en proxy
inte får användas bara för att den korrelerar med size.

### 5. `validated/membership_main_list_pit.json` — **PIT_VALID, men inte Size**

V2:s venue-ledger, byggd av `build_membership_main_list_pit.py`. Rigoröst arbete:
*"a price history, a Börsdata marketId, or a later name/domicile change is never
treated as proof of main-market membership"*. Men den avser **Main Market mot
First North**, inte segment. Coverage: **9 av 420** daterade verifierade
inträden, 411 `member_from: null`.

### 6. `validated/prices_h1419/membership_h1419_v2.json` — **EX_POST_CONTAMINATED**

`membership_verified: false`, basis `DAGENS_MAIN_MARKET_ISIN_BAKATPROJICERAD`.
Inget segmentfält. Venue-medlemskap bakåtprojicerat från dagens ISIN-lista.

### 7. Avanza `market_list` — **CURRENT_SNAPSHOT_ONLY**

Redan fastställt. `marketListName` är ett odaterat nuvärde ur en live-endpoint.

### 8. Börsdata `number_Of_Shares` — **INSUFFICIENT_PROVENANCE**

K2A-auditen: fältet är empiriskt EPS-denominator (median avvikelse 0,0015 % mot
rapporterad EPS på 12 263 rader), inte periodslutets utestående aktier. 201 av 273
rapportpar följde inte splitfaktorn. Täckning **0/68** terminala. K2A:s dom:
market cap **BLOCKERAD**.

### 9. `_coll_market_cap_evidence` i `run_expanded_delisted_inclusion_stage80.py` — **INSUFFICIENT_PROVENANCE**

`shares × price` för **ett** bolag (Collector), med ett `conservative_mid_floor_msek: 2000`.
En enskild försvarbarhetskontroll, inte ett size-lager.

### 10. `trackj/validated_mfn_events_v1/validated_mfn_events.jsonl` — **PIT_VALID, men inte Size**

66 402 pressmeddelandehändelser med `published_at`, `market_known_time`,
`market_known_time_basis`, `is_terminal_instrument` och `raw_sha256` — ett
rigoröst PIT-stämplat korpus.

**75 rader** nämner segment- eller listtermer, men samtliga granskade avser
**venue-byten** (First North → Nasdaq Stockholm: Fastator, Genova, Maha Energy,
Trianon), inte Large/Mid/Small-segmentbyten. Det är förväntat: Market Cap Segment
Review är ett **börsmeddelande**, inte ett bolagsmeddelande, och hamnar därför
inte i bolagens MFN-flöde.

Korpuset bekräftar alltså venue-övergångar med korrekt PIT-stämpel, men innehåller
inte segmentklassificeringen.

---

## SAMMANSTÄLLNING

| # | Källa | Klassificering | Segment? | Datum? | Avnoterade? |
|---:|---|---|:---:|:---:|:---:|
| 1 | **Nasdaq Segment Review-ledger** | **POTENTIALLY_PIT_VALID** | **JA** | **JA** | **JA** |
| 2 | PIT size factor stage 91 | INSUFFICIENT_PROVENANCE | — | — | — |
| 3 | `sweden_universe.csv` | CURRENT_SNAPSHOT_ONLY | ja | nej | **nej** |
| 4 | `omx30_membership_pit.csv` | PIT_VALID (index, ej size) | nej | ja | ja |
| 5 | `membership_main_list_pit.json` | PIT_VALID (venue, ej size) | nej | delvis | ja |
| 6 | `membership_h1419_v2.json` | EX_POST_CONTAMINATED | nej | nej | delvis |
| 7 | Avanza `market_list` | CURRENT_SNAPSHOT_ONLY | ja | **nej** | nej |
| 8 | Börsdata `number_Of_Shares` | INSUFFICIENT_PROVENANCE | — | ja | **nej** |
| 9 | COLL market cap-evidens | INSUFFICIENT_PROVENANCE | — | ja | ja |
| 10 | MFN-eventkorpus (66 402 rader) | PIT_VALID (venue, ej size) | nej | ja | ja |

**Ingen källa är `PIT_VALID` som Large/Mid/Small-klassificering.** Källa 1 är den
enda som har rätt semantik, och den är ofullständig i två dimensioner samtidigt:
7 av 16 årgångar, och 15 av 90 bolag — dessutom enbart avnoterade.

---

## SLUTSATS

```
PIT SIZE DATA AVAILABLE:        NO  (som dataset)
PIT-KORREKT KÄLLKLASS FINNS:    JA  (Nasdaq Market Cap Segment Review)
ARBETE REDAN UTFÖRT:            7 av ~16 årgångar, 15 av 90 avnoterade bolag
SIZE-TESTER KÖRDA:              0
ÄNDRINGAR GJORDA:               0
```

### Vad som återstår — nu konkret, inte öppet

Min förra audit beskrev datauppdraget som att en källa behövde *hittas*. Det var
fel. Källan är identifierad, dess semantik är verifierad, och en del är hämtad.
Kvar är tre avgränsade uppgifter:

1. **Hämta de ~9 saknade årgångarna** av Market Cap Segment Review
   (2010-2012, 2014-2016, 2018, 2021, 2023-2024). Samma metod som Stage 79 använde,
   via `view.news.eu.nasdaq.com`-spegeln.
2. **En baslinjeroster** vid en historisk tidpunkt — pressmeddelandena listar bara
   *förändringar*. Utan en fullständig segmentlista vid en startpunkt kan nivån
   inte härledas för bolag som aldrig bytte. Detta är den enda posten som saknar
   identifierad källa.
3. **Utvidga från avnoterade till hela universumet.** Stage 79 var scoopad till
   survivorship-arbetet; Stage 91 visade att överlappet med det handelsbara
   universumet var noll.

Punkt 2 är den kritiska. Punkt 1 och 3 är mekaniskt arbete mot en verifierad källa.

### Vad som inte får göras

Ingen av källorna 3–9 får användas som historisk size. `sweden_universe.csv` är
särskilt farlig eftersom den ser ut som ett dataset med en size-kolumn men saknar
både datum och avnoterade bolag.
