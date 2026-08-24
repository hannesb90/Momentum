# K1-DATA — Avanza Sector Recovery Probe

Datum: 2026-08-09  
Scope: publik Avanza-webbdata, data/provenance/QA endast. Ingen target, IC, alpha, feature eller backtest har lästs eller körts. K2 och H0/H1/H2 är orörda.

## Slutbesked

**Nej: Avanza + de tre V1-snapshotarna ger inte en survivorship-säker sektormapping för hela V2-universumet.**

Avanza korsverifierar de 352 aktuella instrumenten mycket starkt: samtliga returnerar exakt samma ISIN som V2 och samtliga har en komplett sektorshierarki. Men Avanza återvinner **0/68 terminalinstrument** via samma krav. Därför kan K1 endast bli **DELVIS TESTBAR** på en uttryckligt current-survivor-matchad population. Ett fullständigt historiskt V2-test är fortsatt blockerat eftersom terminalgapet annars döljs.

## Publik källa och metod

Proben använde endast två publika, oautentiserade webbendpoints:

1. `POST https://www.avanza.se/_api/search/filtered-search`
2. `GET https://www.avanza.se/_api/market-guide/stock/{orderBookId}`

Ingen session, cookie, API-nyckel, inloggning, CAPTCHA-hantering eller anti-bot-kringgående användes. Anropen var artigt throttlade.

Söksvaret exponerar titel, ticker, orderbook-ID, marknadsplats och `stockSectors`. Stock-info-svaret exponerar dessutom:

* `isin`
* `name`
* `orderbookId`
* `sectors[]` med `sectorId` och originalnamn
* `listing.tickerSymbol`
* `listing.marketPlaceCode`/`marketPlaceName`
* `listing.marketListName`

Varje mottaget svar sparades som mottagna bytes med request, timestamp, HTTP-status, content type och SHA256. RAW skrevs aldrig över.

En första run stoppade efter 50 instrument när samma orderbook gav olika bytes på grund av live quote. Den ligger kvar som ofullständig evidens. V2-runnen gav varje request en unik path och slutförde 420/420. Den preliminära parserns sju tickerträffar är explicit markerade superseded; QA-resultatet är auktoritativt.

## Identitetsregel

Utgångsidentiteten kom från V2:s frysta MFN-routingtabell: instrument-ID, ISIN och exakt namn för samtliga 420 instrument. MFN användes inte som sektorkälla.

Acceptansordning:

1. `EXACT_ISIN_MATCH`: stock-info returnerar exakt V2-ISIN.
2. `VERIFIED_HISTORICAL_TICKER`: kräver oberoende historiskt bevis för samma ekonomiska enhet; lika ticker räcker inte.
3. `VERIFIED_EXACT_NAME`: kräver exakt namn och inga identitetskonflikter.
4. Annars `UNRESOLVED`.

Ingen fuzzy namnmatchning användes.

## Coverage

| Grupp | Totalt | Exakt ISIN | Med sektor | Med bransch/industry | Unresolved |
|---|---:|---:|---:|---:|---:|
| Aktuella | 352 | 352 | 352 | 352 | 0 |
| Terminala | 68 | 0 | 0 | 0 | 68 |

### Terminalcoverage per avnoteringsår

| År | Terminala | Exakt ISIN | Med sektor | Unresolved |
|---:|---:|---:|---:|---:|
| 2020 | 12 | 0 | 0 | 12 |
| 2021 | 12 | 0 | 0 | 12 |
| 2022 | 15 | 0 | 0 | 15 |
| 2023 | 4 | 0 | 0 | 4 |
| 2024 | 9 | 0 | 0 | 9 |
| 2025 | 14 | 0 | 0 | 14 |
| 2026 | 2 | 0 | 0 | 2 |

### Tickeråteranvändning

Sju terminaltickers gav publika Avanza-träffar, men samtliga var andra ekonomiska enheter:

| V2 | Förväntat | Avanza returnerade | Marknad | Utfall |
|---|---|---|---|---|
| AGRO | Agromino, DK0060823516 | Adecoagro, LU0584671464 | NYSE | UNRESOLVED |
| COLL | Collector, SE0007048020 | Collegium Pharmaceutical, US19459J1043 | Nasdaq US | UNRESOLVED |
| CS | CoinShares, JE00BLD8Y945 | Capstone Copper, CA14071L1085 | Toronto | UNRESOLVED |
| LEO | LeoVegas, SE0008091904 | Lion Copper and Gold, CA53620R1091 | Kanada | UNRESOLVED |
| NWG | Nordic Waterproofing, DK0060738409 | NatWest ADR, US6390572070 | NYSE | UNRESOLVED |
| SSM | SSM Holding, SE0009663511 | Sono Group, NL0015002AM0 | Nasdaq US | UNRESOLVED |
| ZETA | ZetaDisplay, SE0001105511 | Zeta Global, US98956A1051 | NYSE | UNRESOLVED |

Detta bekräftar varför ticker aldrig får vara automatisk historisk identitet.

## Sektor- och branschextraktion

Avanzas originalhierarki bevaras verbatim i `avanza_sector_objects_raw` och `avanza_sector_path_raw`. Exempelordningen är mest specifik först och bredast sist:

`Digitala Tjänster → IT-Service → Teknologi`.

Ingen normalisering till Börsdata eller GICS har gjorts. Den maskinläsbara QA-filen innehåller en explicit observations-crosswalk:

* Börsdata `sectorId` → Avanza broad sector
* Börsdata `branchId` → Avanza fine industry

Crosswalken är en associationstabell, inte en påstådd ett-till-ett-taxonomi. Ett Börsdata-ID kan motsvara flera Avanza-grenar eftersom taxonomierna har olika granularitet och klassificeringsprinciper. Sådana skillnader räknas inte automatiskt som verkliga konflikter.

## Cross-validation av aktuella instrument

* 352/352 aktuella instrument fick exakt ISIN-verifierad liveklassificering.
* 342 av dessa finns även i V1:s `avanza_sectors.csv`.
* Samtliga 342 har byte-semantiskt identisk sektorväg mellan den äldre V1-cachen och liveproben.
* De återstående 10 har liveklassificering men saknas i den äldre Avanza-cachen.
* Börsdatas tre snapshots har sinsemellan identiska `sectorId`/`branchId` för alla 352.

Det finns alltså inget observerat aktuellt klassificeringsdriftproblem. Taxonomierna är däremot inte samma: Börsdata kan exempelvis samla investmentbolag, banker och fastigheter under ett gemensamt högre ID där Avanza separerar dem i olika broad sectors. Crosswalken måste därför frysas som en separat metodologisk artefakt om data senare används.

## Stabil entity classification kontra PIT-finansiell data

Sektor är rimligen stabilare än ett rapporterat finansiellt värde. Snapshotdatumet diskvalificerar därför inte automatiskt användning bakåt. Evidensen stödjer följande begränsade påstående:

* för 342 nuvarande bolag är samma Avanza-klassificering observerad vid två tillfällen och stöds dessutom av stabil Börsdata-klassificering,
* för ytterligare 10 finns en exakt liveklassificering,
* detta är stöd för en stabil **current entity classification**, inte bevis för klassificering från V2-entry.

Proben kan inte tidsbestämma verksamhetsbyten, omvända förvärv, shells/relisting, mergers eller redomicilieringar. Kända namn-/identitetshändelser i V2:s instrumenthistorik får därför inte automatiskt ärva dagens sektor före händelsen. Utan en daterad historisk källa måste sådana perioder vara `UNKNOWN` eller manuellt verifieras före featurebygge.

Det avgörande hindret är dock större: samtliga terminalinstrument är `UNKNOWN`. Att beräkna historisk sector breadth eller sector momentum enbart från dagens överlevare skulle skapa precis det survivorshipproblem som K1 ska undvika.

## K1-bedömning

| Hypotes | Klassificering | Tillåten scope nu |
|---|---|---|
| Sector momentum | DELVIS TESTBAR | endast current-survivor matched diagnostic, 352/420 |
| Sector-relative stock momentum | DELVIS TESTBAR | endast samma matched population |
| Sector breadth | DELVIS TESTBAR | endast samma population; historisk breadth för fulla V2 är blockerad |
| Industry-relative momentum | DELVIS TESTBAR | endast samma population; Avanza fine taxonomy |

För ett fullständigt, survivorship-säkert historiskt V2-test är samtliga fyra **FORTSATT BLOCKERADE**.

En senare preregistrering måste uttryckligen välja mellan:

1. en begränsad current-survivor-diagnostik som inte får generaliseras till hela V2, eller
2. att först hämta en annan historisk sektorkälla som täcker terminalinstrument och verksamhetsbyten.

Ingen K1-feature eller ranking har byggts.

## Artefakter

* `research_k/avanza_sector_recovery_probe/QA_RESULTS.json`
* `research_k/avanza_sector_recovery_probe/qa_identity_sector_evidence.json`
* `research_k/avanza_sector_recovery_probe/raw/AVANZA_SECTOR_RECOVERY_20260809_V2/`
* `research_k/avanza_sector_recovery_probe/manifest.json`
* `tools/spark_avanza_sector_recovery_probe.py`
* `tools/spark_avanza_sector_recovery_qa.py`

Manifestets aggregate SHA256 redovisas i slutleveransen efter reproduktionskontroll.
