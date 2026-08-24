# Slutlig pre–Spår D-audit — dataset_v1.0

## Slutbesked

**REDO FÖR SPÅR D.** Inga kvarvarande kända reparerbara buggar eller blockerare hittades.
Ingen modellträning, feature selection, tuning eller targetbaserad optimering utfördes.

Den exakta universumdefinitionen är: **svenska aktier i det rekonstruerade Nasdaq
Stockholm-universumet med observerbar handel, med efterföljande PIT-filter där historisk
membership faktiskt är källdaterad**. Datan är inte och får inte beskrivas som fullständigt
PIT-verifierad historisk Large/Mid/Small-membership.

## Klassificering

### Godkänt

- A: 420 instrument, 581 115 prisrader. `adj` används för totalavkastning och `close`
  reserveras för pris×volym. Tidigare aktieslags-, entity-, valuta- och last-one-wins-fynd
  passerar regression.
- B: år 4 847, kvartal 12 280 och R12 12 269 rader. Ingen dubbel currencyRatio-konvertering.
- C: 30 073 CORE-, CORE+FUNDAMENTA- och targetnycklar; full PIT-/targetåterräkning gav noll fel.
- Target: 24 714 `forward_52w`, faktisk horisont min/median/max 357/364/371 dagar.
  Noll under 350 och tre över 370; de tre 371-dagarsfallen följer den fasta endpointlaggen
  0–8 dagar eftersom startpriset kan ligga före paneldagen. Endpointlagg utanför 8 dagar
  är förbjuden i både byggare och regression.
- Terminal: 68 verifierade ekonomiska events och 828 separata terminalutfall. De blandas
  aldrig med `forward_52w`; QA-trunkering/prisserieslut kan inte skapa event.
- Entity resolution: 24 multipostgrupper löses explicit. De sju tidigare kända fallen
  SBB-B, Hufvudstaden, Sagax, Kinnevik, VEF, FastPartner och Stenhus Fastigheter är fortsatt
  korrekta; inga implicita last-one-wins-val finns.
- Extern EODHD: 5 119 filer, full relativ fillista, storlek och SHA256 per fil, kombinerad
  hash `fe2d2c13a935500e598d83a4272b625134538e0d4c0d2418353545cb62f6eb4d`.
  Produktionsbyggaren verifierar snapshoten före läsning. Mutationstest visar att ändrad,
  tillagd eller borttagen fil faller.
- Alla 13 aktiva dataartefakter plus registry byte-matchar sina manifest. Registryversion 1.2.0.
- Två rebuilds från låsta inputs gav identiska bytes/SHA256 för samtliga kontrollerade aktiva
  outputs och manifest. Wall-clock-tid serialiseras inte; release-timestampen är deterministisk.

### Kända datasetbegränsningar

1. **Historisk membership.** 9/420 instrument (2,14 %) och 431/30 073 panelrader
   (1,43 %) har `membership_verified=True`; 411 instrument och 29 642 rader är explicit
   okända. AJA-B och CCC identifierades i sensitivity-auditen och 131 rader före deras
   verifierade admissions togs bort. Efter rebuild finns noll kända pre-admission-rader.
   Okända fall har `member_from=null`, aldrig en konstruerad 2020-entry.
2. **Fundamental survivorship.** 67/68 avnoterade bolag saknar fundamenta. `has_fundamenta`
   är explicit; ingen nollimputering sker. CORE ska vara huvudbenchmark i Spår D och
   CORE+FUNDAMENTA en separat challenger med dokumenterad bias.
3. **Blockerade features.** `turnover_13w_msek`, `illiquidity_amihud_13w`,
   `dividend_yield_ttm` och `fcf_yield_ttm` har 0 % coverage och räknas inte som features.
   Buybacks/shareholder yield och Capex-kvoter är också uteslutna/blockerade enligt nedan.
4. **Extern RAW.** EODHD ligger utanför V2 men är en explicit `IMMUTABLE EXTERNAL RAW SOURCE`;
   reproducerbarheten bygger på den kryptografiska snapshotkontrollen, inte katalognamnet.

### B-extra

- EBITDA: 28 437 rader, 346 instrument, median 16 år; PIT/valuta/enhet godkända.
  6 803/6 812 jämförbara helårs/R12-observationer klarar EBITDA≥EBIT-toleransen.
  `ebitda_margin_ttm` byggdes utan targetkontakt och har 24 811/30 073 användbara värden.
  Extremvärden lämnas synliga; samma ekonomiska 1 %-materialitetsgrind som övriga marginaler används.
- Capex: rådimensionen är PIT-/valuta-/enhetsmanifesterad, men tecknet är inte stabilt:
  R12 har 10 557 negativa, 271 noll och 1 077 positiva värden. `Capex/revenue` och
  `Capex/assets` är därför **UTESLUTNA**; ingen teckennormalisering gissas.
- Buybacks/KPI 213–215/shareholder yield: **UTESLUTNA** på grund av ofullständig historisk
  PIT-täckning och avsaknad av QA-godkänd FX/correction/cashflow/denominator.
- `roic_proxy_ttm` förblir uttryckligen en före-skatt-proxy
  `operating_Income/(total_Equity+net_Debt)`, inte sann ROIC/NOPAT.

## Blueprint och faktisk panel

- 71 kandidater: 50 markerade IMPLEMENTERAD i blueprinten, 11 KAN BYGGAS MEN UPPSKJUTEN,
  8 BLOCKERAD/SAKNAR DATA och 2 BÖR INTE BYGGAS.
- Faktiskt användbara numeriska features: **29 CORE + 18 FUNDAMENTA**. Provenance och
  UTESLUTEN/0 %-kolumner räknas inte.

## De 15 toleranscensurerade targetfallen

Två gäller CARA (närmaste äldre endpoint 11 respektive 15 dagar gammal). Tretton gäller
NEOBO under ett prisgap 2022-02-04–2023-02-10 (äldre endpoint 21–357 dagar gammal).
Samtliga returnerar null; inget gammalt pris eller terminalevent används.

## Aktiva SHA256

| Artefakt | SHA256 |
|---|---|
| A priser | `e3ed38b8e89a25149e61b71c8e0c91b8adbd2dab22b282bc156b1214987f17b4` |
| B år | `7cead0b764c81e7d0bb6cb758c40a66ec1379b9f97d090b483732ce46d4e7d6b` |
| B kvartal | `e7c6ec8a1096189ab2bd20ad959f7c37ab94be38e378668f6cbac7bedc17e932` |
| B R12 | `487f212237f9bdd48d159eeddd8a2da30e342c01bfb05ff8d6a0a061f391bbfd` |
| B-extra KPI | `48a10a53c17cbb7a2a385f2ccc36cabb28a9bdcf82c7236ccc8c7b108ad8ad0a` |
| CORE | `220e258669b1eed774e533065dec5ed8e5780edc0e31ec4eb3e841c128a1c974` |
| CORE+FUNDAMENTA | `117ac6e811ff62ea62168fea2f55a6da430c43774794bed8733573dc4dd1eaaa` |
| target | `6c2b87aad0e1853837b8d60a3b11e100bca781486b7c12966a27b9a8bd671d21` |
| terminalevents | `f437650e06e7a4405a922725d8415dc5b55fdca4df511aa72cc31bf6e47c7a8a` |
| membership | `61cc933e52cc40951184dbabde89a7b57a755ded10cbfe0d7f613f37cfd3fc16` |
| extern EODHD-manifest | `02efe784a0c400d054126d0ffb5df4c7cfd4d88ac54ecb5e1ea36472f9e8dc60` |

## Slutlig adversarial falsifiering

Targethorisont, PIT/as-of, framtidsläckage, terminalevents, corporate actions,
adjusted/unadjusted-priser, membership-semantik, entity resolution, valuta,
missing/sentinel, featureformler, 0 %-features, B/C-completeness, manifeststaleness,
tysta defaults, externa beroenden och fundamental survivorship testades på nytt.
Inget nytt strukturellt fel eller reparerbar blockerare hittades.

**REDO FÖR SPÅR D.**
