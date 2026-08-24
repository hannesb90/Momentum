# Oberoende second opinion — Momentum V2, Spår A/B/C

**Auditdatum:** 2026-08-08  
**Metod:** read-only forensic QA av den V2-kod och de dataartefakter som faktiskt används. Inga fixes, rebuilds eller ändringar av pipeline/data har gjorts. Den enda skrivningen är denna rapport.

## 1. Identitet, scope och aktuell kedja

### Git/versionsidentitet

`/home/hannesb/momentum_v2` är **inte ett git-repository**: det finns ingen `.git`, branch eller commit/hash att knyta V2-koden och artefakterna till. Den närliggande legacy-/produktionsrepon `/home/hannesb/momentum_prod_work` står på branch `research/exit-entry-diagnostics-2026-08-06`, commit `4782696e32813c9bb7adaa54ddc016cb8fb71ce4` (commitdatum 2026-08-07 20:42:16 +0200), men den hashens versionskontroll omfattar inte `momentum_v2`.

Detta är ett reproducerbarhetsproblem: Spår A läser dessutom prisarkivet direkt från den andra working treen, medan V2-kod, dokumentation och finalartefakter saknar egen commitidentitet.

### Var V2 definieras

- Plattform-/statusdefinition: `README.md`.
- V2-root: `/home/hannesb/momentum_v2`.
- Instrumentuniversum/entity resolution: `tools/instrument_master_v2.py` → `docs/probes/instrument_master.json`.
- RAW Börsdata: `tools/fetch_v2_raw_borsdata.py` → `raw/borsdata/{year,quarter,r12}/`, `_manifest.jsonl`, `_matchning.json`.
- RAW Skatteverket: `raw/skatteverket/`; parsing via `tools/skatteverket_universe.py` och aktuell reparerad master via `tools/instrument_master_v2.py`.

### Spår, entrypoints och artefakter

| Spår | Aktuell kod/entrypoint | Faktisk input | Producerad/faktisk final |
|---|---|---|---|
| A | `tools/instrument_master_v2.py`; `tools/build_validated_prices.py`; QA: `tools/price_qa.py`, `tools/price_qa2.py` | Skatteverket-RAW samt EODHD active/delisted-kataloger och `.json.gz` under `/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST` | `docs/probes/instrument_master.json`; `validated/prices/prices_validated.json`; `validated/manifest_sparA.json` |
| B | fetch: `tools/fetch_v2_raw_borsdata.py`; build: `tools/build_validated_fundamentals_final.py` | `raw/borsdata/year`, `quarter`, `r12` och `raw/borsdata/_matchning.json` | tre filer under `validated/fundamentals/`; `validated/manifest_sparB.json` |
| C target | `tools/spar_c_target.py` | Spår A-priser | `panels/target_table.json`; `docs/probes/target_manifest.json` |
| C CORE | `tools/spar_c_features_core_v2.py` | Spår A-priser | `panels/core_panel.json`; `docs/probes/internal_index_series.json` |
| C FUND | `tools/spar_c_features_fundamenta_v2.py` | CORE-panel, Spår A-priser, Spår B R12 | `panels/core_fundamenta_panel.json`; feature registry/buildprobe |
| C QA/frysning | `tools/spar_c_qa.py`; `tools/spar_c_freeze.py` | panelerna, A/B-manifest, registry | `docs/probes/spar_c_qa.json`; `validated/manifest_sparC.json` |

### Dokumenterad kontra faktisk aktuell/fryst status

- Spår A beskrivs i `README.md` som reparerad och fryst baslinje: **420 instrument, 581 115 rader**, dataset/hash `c75d3de58d828dfd513f1f187f339cb0efbc20bd61a01daadecbce5cf928dba4`. Detta stämmer med aktuell prisfil och manifest.
- Spår B är valutareparerad men enligt `README.md` och manifestet **inte formellt fryst**. Aktuell kombinerad hash är `93b0e884c58fe8076b852248711b04fb69dad59303655dd877cc20a241ae7f97`; 4 847 års-, 12 280 kvartals- och 12 269 R12-rader.
- Spår C-manifest v1.1.0 säger fortfarande “SLUTLIGT FRYST”, men är uttryckligen återkallat i `README.md`. Artefakten är byggd på gamla A-hashen `f0182d35…` (404 instrument) och gamla, valuta-invalid B-hash `9da73a88…`. Den är inte aktuell.

## 2. Sammanfattning av fynd

| ID | Allvar | Fynd |
|---|---|---|
| C-1 | **CRITICAL** | Hela nuvarande Spår C är stale/ogiltigt mot aktuell Spår A och B. |
| C-2 | **HIGH** | Avnoterade/tidigt avslutade serier högercensureras som okända targets; detta skapar informativ censurering/survivorship-bias. |
| C-3 | **HIGH** | `trend_strength_52w` och `trend_consistency_52w` beräknas på 26 veckor, trots namn/registry/formel 52v. |
| B-1 | **HIGH** | Fundamenta är inte survivorship-säkert: 67/68 avnoterade saknar data; downstream fundamentalmodeller får överlevarselektion. |
| V-1 | **HIGH** | V2 saknar gitidentitet och Spår A läser ett externt, modifierbart legacy-cachearkiv; full source-to-output-reproduktion kan inte bindas till en commit. |
| B-2 | **MEDIUM** | Samma Börsdata `insId=147` och ISIN mappas till två V2-koder/namn utan tidsdimension; fundamenta kan dupliceras/attribueras över juridiskt namn/kodbyte. |
| C-4 | **MEDIUM** | Spår C:s QA testar inte det faktiska framtida targetdatumet/terminalutfallet och missar C-2; “target PIT passed” ger falsk trygghet. |
| A-1 | **MEDIUM** | Universum är inte historiskt segment-PIT; nutida Nasdaq/segmentinformation används bakåt. |
| A-2 | **MEDIUM** | Prisbyggaren använder `x.get("volume") or 0`; saknad volym blir äkta noll och förorenar tre volym/likviditetsfeatures. |
| B-3 | **LOW** | 151 R12-rader avviker >10 % från EPS-identiteten, trots god aggregerad nivå; dessa behöver radvis klassning före slutlig frysning. |
| D-1 | **LOW** | Dokumentation/manifests innehåller motsägelser om fryst status och gamla featureantal/begränsningar. |

## 3. Detaljerade fynd

### C-1 — CRITICAL: Spår C är byggt på ersatta A- och B-inputs

**Filer:** `validated/manifest_sparC.json`, `validated/manifest_sparA.json`, `validated/manifest_sparB.json`, samtliga filer i `panels/`.

**Konkret bevis:**

- C-manifestets beroende A = `f0182d35…`; aktuell A = `c75d3de5…`.
- C-manifestets beroende B = `9da73a88…`; aktuell B = `93b0e884…`.
- Aktuell A har 420 instrument/581 115 prisrader. CORE, FUND och target har fortfarande 404 instrument/28 539 panelrader.
- 23 aktuella A-koder saknas i CORE (bl.a. `ABB`, `NDA-SE`, `SAND`, `VOLV-B`, `SEB-A`, `SHB-A`), medan sju gamla CORE-koder inte finns i aktuell A (`ALIV-SDB`, `CTM`, `KAMBI`, `KLARA-B`, `SEB-C`, `SHB-B`, `SKF-B`).
- Oberoende diff mot den supersedade B-filen visar 1 146 ändrade R12-rader för 39 koder. Den stale FUND-panelen innehåller 2 288 rader för 35 av dessa koder.

**Omfattning/downstream:** alla C-paneler, targetnycklar, registry-QA och C-manifest är versionsmässigt inkompatibla med aktuell bas. CORE saknar A-reparationens instrument; FUND innehåller dubbelkonverterade värden; varje modell/downstream-resultat som läst panelerna är ogiltigt.

### C-2 — HIGH: avnotering behandlas som vanlig högercensurering

**Fil:** `tools/spar_c_target.py:157-169`.

**Bevis:** om `T+52v > serie_slut` sätts target ovillkorligen till `null`. Koden skiljer inte datamaterialets gemensamma slut från att ett instrument avnoterats, gått i konkurs, blivit uppköpt eller fått sin serie trunkerad. Auditen fann **806 null-labels för 66 instrument vars aktuella A-serie slutade före 2026**. Exempel: `ABLI` får null från 2024-03-22 till 2025-02-21 när serien slutar 2025-03-17; `ADAPT` får motsvarande null före serieslut 2021-09-10.

**Effekt:** de sista upp till 52 veckorna före ett negativt terminalutfall försvinner ur supervised sample. Censureringen är informativ, inte slumpmässig, och kan systematiskt förbättra uppmätt modellprestanda. Uppköp och konkurs kan inte ges samma mekaniska utfall; corporate-action-typ och eventuell kontant/successor-return måste modelleras explicit.

### C-3 — HIGH: två 52v-features är faktiskt 26v

**Fil:** `tools/spar_c_features_core_v2.py:208-221` (kodblocket som skapar `win26`).

**Bevis:** `trend_strength_52w` och `trend_consistency_52w` beräknas båda från `win26`, alltså data från `panel_date - 26 veckor`. Registry anger 52 veckor och fältnamnen säger 52w. **1 981 panelrader** har `trend_strength_52w` trots att den riktiga 52v-featurefamiljens `price_vs_sma52w` är null, vilket empiriskt bekräftar den kortare lookbacken.

**Effekt:** semantiskt fel featurevärde, fel coverage och missvisande modellförklaring. Alla C CORE/FUND-paneler och downstreammodeller som använder dessa två fält måste byggas/köras om.

### B-1 — HIGH: fundamental-survivorship är strukturell och stor

**Filer:** `validated/manifest_sparB.json`, `tools/spar_c_features_fundamenta_v2.py:154-166`.

**Bevis:** 67/68 avnoterade Nasdaq-bolag saknar fundamentaldata; `has_fundamenta=False` sätts när ingen R12-rad finns. Detta är dokumenterat men tidigare “GODKÄND/FRYST” neutraliserar inte biasen.

**Effekt:** missingness korrelerar med överlevnad och eventuellt finansiell stress. Complete-case, implicit nullhantering och coveragebaserade urval blir survivor-biased. CORE-prisdata kan användas separat; FUND kan inte betecknas survivorship-säkert.

### V-1 — HIGH: V2 är inte versionsbunden och A:s RAW är externt

**Filer:** hela `/home/hannesb/momentum_v2`; `tools/build_validated_prices.py:17-20`; `tools/instrument_master_v2.py` (`LEGACY`, `LC`, `EOD`).

**Bevis:** V2 saknar `.git`. A-buildern läser EODHD-filer direkt ur `/home/hannesb/momentum_prod_work/momentum_ml/cache`, vars repo dessutom hade många working-tree-ändringar vid audit. V2:s README säger “Ingen import från legacy”, men faktisk dataaccess är ett runtimeberoende till legacy-sökvägen. Källfilshashar finns i A-manifestet, vilket hjälper integritet, men ersätter inte versionskontroll av builder/master/QA eller en immutabel RAW-snapshot.

**Effekt:** samma påstådda V2-version kan betyda annan kod eller annan katalogstate. Oberoende reproduktion och ansvarskedja är ofullständig.

### B-2 — MEDIUM: kolliderande insId/ISIN utan tidsdimension

**Filer:** `raw/borsdata/_matchning.json`; `tools/build_validated_fundamentals_final.py:106-107`.

**Bevis:** två matchposter har samma `insid=147`, samma ISIN `SE0010769182`, men olika kod/namn: `EMPIR-B`/Ledstiernan AB och `SAFETY-B`/mySafety Group AB. Dict comprehension `insid2post = {m["insid"]: m ...}` gör att sista posten vinner; all insId-147-fundamenta får därmed en enda kod utan effektiv-från/till-datum.

**Effekt:** historiska reports kan attribueras till fel ticker/entitetsperiod och successor/predecessor kan blandas. Om koderna representerar ett legitimt namn-/kodbyte behövs en daterad aliasrelation, inte två samtidiga matchrader eller “last wins”.

### C-4 — MEDIUM: target-QA verifierar inte sitt påstående

**Fil:** `tools/spar_c_qa.py:156-169`.

**Bevis:** kontrollen med rubriken “target-fönstret 52v FRAMÅT” testar endast att `price_date <= panel_date`. Targettabellen lagrar inte `target_price_date`, och QA återräknar inte `adj[T+52v]/adj[T]`, toleransen eller terminalklassningen. C-2 passerar därför QA med noll fel.

**Effekt:** felaktiga/censurerade labels kan godkännas. Manifestets “target PIT passed” är för starkt.

### A-1 — MEDIUM: historiskt universum/segment är inte fullt PIT

**Filer:** `tools/build_validated_prices.py:54-70`; `tools/spar_c_target.py:124-127`.

**Bevis:** live-instrumentens nuvarande marketId/ISIN används för universum, kompletterat med avnoterade identifierade historiskt. Dokumentationen medger att Large/Mid/Small-medlemskap tas vid byggtid och appliceras bakåt.

**Effekt:** instrument som tillkommit, flyttat segment/marknad eller i efterhand klassats som Nasdaq kan ingå före historisk eligibility. “PIT-dynamiskt medlemskap via prisseriens existens” är inte samma sak som historisk index-/listmedlemskap.

### A-2 — MEDIUM: nullvolym förvandlas till noll

**Fil:** `tools/build_validated_prices.py` vid raden som skriver `{"d": dt, "adj": ac, "v": x.get("volume") or 0}`.

**Bevis:** både `None` och faktisk `0` kollapsar till värdet 0 utan provenanceflagga.

**Effekt:** `turnover_13w_msek`, `volume_trend_13w` och `illiquidity_amihud_13w` kan tolka saknad leverantörsdata som verklig nollhandel. Coverage-QA ser värdena som observerade.

### B-3 — LOW: kvarvarande radvisa EPS-identitetsavvikelser

**Filer:** aktuell `validated/fundamentals/fundamentals_r12_validated.json`; `validated/manifest_sparB.json`.

**Bevis:** av 12 263 R12-rader med alla komponenter har medianfelet i `EPS ≈ profit_To_Equity_Holders / number_Of_Shares` 0,0015 % och p95 0,924 %, men **151 rader avviker mer än 10 %**. Det kan vara legitima weighted-average shares/split/definitionsskillnader, men den befintliga riktade kontrollen bevisar inte varje rad.

**Effekt:** främst `eps_growth_yoy`; kräver klassning, inte automatisk kassering.

### D-1 — LOW: status- och dokumentationsdrift

**Filer:** `README.md`, `validated/manifest_sparB.json`, `validated/manifest_sparC.json`.

**Bevis:** C-manifestet säger slutligt fryst medan README återkallar status. B-builderns kod skapar texten “SPÅR B FRYST”, medan den faktiska efterredigerade manifeststatusen säger ej slutgiltigt fryst. C-manifestets begränsningstext säger samtidigt att materialitetsfilter “inte är infört” och att bara 13+11 features finns, trots att samma manifest anger filter och 31+21 registryfält.

**Effekt:** maskinella konsumenter och människor kan välja fel artefakt/status.

## 4. Oberoende verifiering av känt valutafynd och samma felklass

### Valutafelet verifierat

`tools/build_validated_fundamentals_final.py:90-99` använder nu råvärdet oförändrat. Den supersedade datan visar däremot multiplikationseffekten för icke-SEK-bolag. Oberoende RAW→final-jämförelse på `revenues`, `total_Assets`, `profit_To_Equity_Holders` och `free_Cash_Flow` gav:

- år: 19 388 jämförelser, 0 avvikelser;
- kvartal: 49 109 jämförelser, 0 avvikelser;
- R12: 49 055 jämförelser, 0 avvikelser.

Slutsats: misstanken var korrekt för den gamla B-versionen. Den nuvarande B-finalen dubbelkonverterar inte dessa fält. Spår C innehåller fortfarande den gamla felklassen eftersom panelen inte byggts om.

### Sökning efter motsvarande enhets-/konverteringsfel

- Ingen ytterligare `currency_Ratio`-multiplikation hittades i de aktuella V2-builders som producerar A/B/C.
- Balansidentiteten `total_Assets = total_Liabilities_And_Equity` är stark: endast 1/4 847 års-, 22/12 280 kvartals- och 22/12 269 R12-rader avviker >1 %.
- EPS-identiteten stöder i stort gemensam enhetsskala, men B-3 kvarstår.
- `fcf_yield_ttm = FCF/(pris×aktier)` är dimensionsmässigt rimlig endast om Börsdatas FCF och antal aktier använder kompatibla miljonenheter; EPS-identiteten ger stöd för detta men fältets enhetsmetadata är inte explicit sparad per kolumn.

## 5. Övriga kontroller utan konstaterat blockerande fel

- Inga dubbletter på `(insid, year, period)` i år/kvartal/R12.
- Inga null-koder eller null report/report-end dates i validerade B-tabeller.
- Periodfördelning är strukturellt rimlig: årsdata period 5; kvartal/R12 period 1–4.
- Inga `(kod, report_date)`-ties i aktuell R12, så as-of-lookupens sortering är deterministisk för nuvarande data.
- Valutareparerad final är råvärdesbevarande, inte omräknad.
- CORE:s as-of-prislogik använder endast priser `<= panel_date`; den uppenbara look-ahead-risken ligger i universum/status och labelhantering, inte i momentumdivisionernas datumriktning.

## 6. Vad som måste repareras

1. Versionsbind hela V2 (kod, docs, manifests) till ett eget git-commit och gör A:s verkliga EODHD-input till en immutabel, hashad V2 RAW-snapshot eller ett explicit versionslåst externt dataset.
2. Lös `insId=147`/ISIN-kollisionen med daterad predecessor/successor-/tickeraliasmodell och verifiera samtliga insId/ISIN/kod-relationer för många-till-en över tid.
3. Klassificera terminalhändelser och definiera target för konkurs, kontantuppköp, aktiebyte/successor och vanlig datacutoff. Censurera bara genuint okända framtider.
4. Ändra de felberäknade trendfeatures till verkligt 52v, eller byt namn/registry till 26v i en ny version.
5. Bevara saknad volym som null med provenance; skilj den från rapporterad noll.
6. Gör historisk eligibility/segment/listmedlemskap PIT eller begränsa och märk datasetet så att nuvarande medlemskap inte påstås vara historiskt PIT.
7. Utöka C-QA med full targetåterräkning inklusive lagrat `target_price_date`, datumtolerans och terminalklass; verifiera alla featureformler mot registry, inte bara mom_4w-stickprov.
8. Radklassificera EPS-identitetsavvikelserna och dokumentera explicit enhet för varje B-fält.
9. Generera manifests atomiskt från builders; ta bort motsägande fryststatus/featureantal och vägra frysning vid dependency-hash mismatch.

## 7. Vad som måste köras om

- Spår A från immutable RAW efter volym-/PIT-/mappingbeslut, inklusive pris-QA och manifest. Om endast C ska räddas innan A-förbättringarna är klara måste åtminstone aktuell redan reparerad A (`c75d3de5…`) vara den explicita basen.
- Spår B efter entity-resolution för insId 147 och eventuell radvis EPS/enhetsåtgärd; år, kvartal och R12 samt full RAW→final/identity/PIT-QA och manifest.
- Hela Spår C: target, internt index, CORE, CORE+FUNDAMENTA, registry, coverage/PIT/formel-QA och manifest. Partiell patch av FUND-panelen räcker inte eftersom även A-universumet ändrats.
- Alla downstream featuresets, train/test-splittar, modeller, backtester, rankningar, feature importance/ablation och rapporterade resultat som läst nuvarande `panels/*.json` eller C-manifestet.

## 8. Slutomdöme

- **Spår A V2: MED RESERVATION** — aktuell prisartefakt är internt konsistent och reparerad, men full historisk eligibility är inte PIT, saknad volym förvandlas till noll och käll-/kodversionen är inte reproducerbart låst.
- **Spår B V2: MED RESERVATION** — den kända dubbelkonverteringen är faktiskt borttagen i aktuell B och RAW→final stämmer, men B är ännu inte fryst, är inte fundamental-survivorship-säkert och har minst en olöst insId/ISIN/kod-kollision.
- **Spår C V2: EJ OK** — faktiska artefakter bygger på ersatta A/B-versioner, innehåller valuta-invalid FUND-data, har fel lookback i två 52v-features och en biased terminaltarget/censureringsregel.

**Audit stoppad här. Inga fixes eller rebuilds har utförts.**
