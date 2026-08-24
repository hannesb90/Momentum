# D/F – reparation av exekveringstid

Datum: 2026-08-09  
Status: **REPARERAD, BYTE-REPRODUCERAD OCH IMMUTABLE FRYST**  
Spår G: **INTE ÅTERSTARTAT**

## Preregistrerad regel

Regeln låstes i `repair_df/execution_timing_preregistration.json` före ombyggda
resultat granskades:

* ranking och signal beräknas efter officiell stängning på paneldatum T;
* ingen order får exekveras till close T eller ett äldre historiskt close;
* order antas lämnas som market-on-close efter beslut T;
* exekveringspris är justerad stängningskurs på första observerade handelsdatum
  strikt efter T;
* periodvärdering sker vid första observerade close strikt efter nästa frysta
  paneldatum;
* terminalstatus påverkar aldrig selection, men verifierad ekonomisk terminalexit
  kan avsluta ett redan ägt innehav;
* benchmark använder exakt samma targetfria decision universe och samma
  post-decision prisregel.

Fryst daglig data innehåller inte verifierade open-/intradaypriser. Nästa close
valdes därför som första direkt observerbara, reproducerbara pris där en order
lagd efter close T faktiskt kan fyllas. Ingen alternativ executionvariant testades.

## Regressionstester

Samtliga passerar:

1. varje utförd BUY/SELL har `execution_price_date > decision_date`;
2. verifierad terminalexit bokförs som `TERMINAL_EXIT` efter det holdingsbeslut
   som skapade exponeringen, inte retroaktivt som ett senare SELL-beslut;
3. de 60 tidigare felaktiga holiday-holdingarna använder framtida handelsdatum;
4. ändrad targetavailability ändrar inte ranking eller holdingsbeslut;
5. sista OOS-panelen använder den redan frysta nästa panelgränsen 2026.

De 60 särskilda fallen är:

| Paneldatum | Holdingrader | Ny periodstart/exekvering |
|---|---:|---|
| 2025-04-18, stängd marknad | 30 | 2025-04-22 |
| 2025-12-26, stängd marknad | 30 | 2025-12-29 |

I nya championartefakten har 775/780 holdingperioder vanlig post-decision
mark-to-market och fem perioder verifierad terminalexit. Det finns inga
unfilled-/saknad-exit-statusar bland championens holdings.

## Oförändrad signal/ranking/IC

Reparationen berör endast portföljlagret:

| Artefakt | V2 SHA256 | V3 SHA256 | Resultat |
|---|---|---|---|
| D predictions | `3579a2c8…409c9bf` | samma | byte-identisk |
| D rankings | `bb54dab2…89fe76` | samma | byte-identisk |
| F scores | `ede1ad43…fb349f` | samma | byte-identisk |
| F rankings | `98ee056d…e90722` | samma | byte-identisk |

Samtliga D-IC-objekt och samtliga F1–F7-IC-objekt är strukturellt exakt lika.
A/B/C, target, featurevärden, modeller, kandidatgrid och signalformler ändrades inte.

## Spår D: ogiltig V2 → exekverbar V3

| Modell | CAGR | Sharpe | MaxDD | Benchmark | Turnover |
|---|---:|---:|---:|---:|---:|
| 12m momentum | 17,29 → **18,67 %** | 0,574 → **0,687** | −13,58 → **−12,77 %** | 10,50 → **10,07 %** | 0,297 → **0,297** |
| Ridge | 16,12 → **12,38 %** | 0,344 → **0,206** | −20,84 → **−22,43 %** | 10,50 → **10,07 %** | 0,236 → **0,236** |
| ElasticNet | 11,32 → **5,46 %** | 0,141 → **−0,101** | −23,33 → **−26,28 %** | 10,50 → **10,07 %** | 0,213 → **0,213** |
| LightGBM | 30,88 → **32,96 %** | 1,005 → **1,210** | −15,25 → **−10,08 %** | 10,50 → **10,07 %** | 0,379 → **0,379** |
| XGBoost | 26,14 → **25,08 %** | 0,843 → **0,869** | −15,33 → **−12,35 %** | 10,50 → **10,07 %** | 0,381 → **0,381** |
| CatBoost | 30,09 → **27,66 %** | 0,908 → **0,896** | −16,97 → **−13,24 %** | 10,50 → **10,07 %** | 0,410 → **0,410** |

Spår D:s modellslutsats ändras inte. IC och negativ Top-30 IC är oförändrade,
och de positiva ML-resultaten förblir koncentrationssköra enligt ursprunglig regel.

## Spår F: ogiltig V2 → exekverbar V3

### F1, ren 12m

| Mått | V2 ogiltig execution | V3 post-decision execution |
|---|---:|---:|
| CAGR | 17,29 % | **18,67 %** |
| Sharpe | 0,574 | **0,687** |
| MaxDD | −13,58 % | **−12,77 %** |
| Benchmark-CAGR | 10,50 % | **10,07 %** |
| Turnover | 0,297 | **0,297** |
| Leave-top-3 CAGR | 7,21 % | **8,11 %** |

### Slutlig champion

Hela F1→F7 kördes om med exakt samma kandidater och beslutskriterier. Samma
champion vann på nytt:

> 0,5 × rank(mom_12m) + 0,5 × rank(mom_18m) → Top 30 → equal weight → 8v.

| Mått | V2 `INVALIDATED_BY_EXECUTION_TIMING` | V3 exekverbar |
|---|---:|---:|
| CAGR | 23,59 % | **25,29 %** |
| Sharpe | 1,390 | **1,379** |
| MaxDD | −5,86 % | **−4,43 %** |
| Benchmark-CAGR | 10,50 % | **10,07 %** |
| Turnover | 0,196 | **0,196** |
| Leave-top-3 CAGR | 13,47 % | **14,65 %** |

Att CAGR steg är ett resultat, inte ett urval: endast den preregistrerade nästa-close-
regeln kördes. Det gamla 23,59-procentsresultatet är uttryckligen märkt
`INVALIDATED_BY_EXECUTION_TIMING` och får endast användas som revisionshistorik.

## Artefakter och SHA256

### D V3

* Aggregate: `4aeb38829bba18a8773142f8b7f9aaf0b4d81e0fa0aa0a6cf713cf8bf0605579`
* Holdings: `a7f3454e664e0f6660fbd36e762724fc4c781f08b964880eafe255321ed8ce51`
* Trades: `58730508f0dfdf26d6edb6234784b5879a7695b4d0c37ed968dd4dd45d006c60`
* Returns: `c69af82aa6209b660e2a972e090fd1fc0030d5e11a4db7490ff076bb7ed7cb2d`
* Metrics: `1920d38a986ca11661d8c1bcce994412841b2f4fb9fc81de34984e09c8ed563b`

### F V3

* Aggregate: `514dd0d476c6145b88ece108941b342086c5c097d3faac36415af53018e595c2`
* Holdings: `af5fabf631c494822bbdfbc2ac8f1dfda77826d87cc924f039f3c7872f9879cb`
* Trades: `09d133d5f9222aa8679ae42553c3a84aa7818c17557669ec06eee7cddbe98183`
* Returns: `5d692ee441174c7287ae34983da3c7c98d8d048a0e4c4451f492b4aa3d5375dc`
* Final decision: `41e15ddc0f1a94b6117e35bffc72f95ecbaa4e2c47f8a73b6dd922641b4a2781`

## Reproduktion och ny freeze

Efter första V3-körningen skapades en före-snapshot. D och hela F byggdes därefter
om ännu en gång:

* D: 8/8 filer byte-identiska;
* F: 15/15 filer byte-identiska;
* totalt manifest: 43/43 paths, bytes, SHA256 och JSON-räkningar PASS;
* A/B/C: fortsatt 13/13 manifestmatchade.

Ny freeze-ID:

`DF_EXECUTION_TIMING_REPAIR_V4_IMMUTABLE_2026-08-09`

Freeze-manifest SHA256:

`6716e083c570bcf3b9f86d7583e85ad72e2d00e4089295214a746deb2d7f5c3d`

Spår G har inte återstartats.
