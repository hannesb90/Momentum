# LOOK-AHEAD-REPARATION D/F

Datum: 2026-08-09  
Status: **REPARERAD, OMBYGGD OCH FRYST – SPÅR G HAR INTE ÅTERSTARTATS**

## Slutsats

Den bekräftade look-ahead-buggen är reparerad i ett nytt, separat portföljflöde. Ranking, urval, benchmark och holdings byggs nu från ett targetfritt `decision_universe`. `target_fwd52w` ansluts först i ett separat `evaluation_sample` för efterhandsberäkning av IC. Automatiska ablationstester visar att ändrad eller borttagen framtida target-, pris-/retur- eller terminalinformation inte ändrar tidigare ranking, holdings eller trades.

Spår D och hela den ursprungligt preregistrerade Spår F-sekvensen har körts om från låsta A/B/C/target-inputs. Berörda E1/E4-jämförelser har också körts om. Gamla artefakter har bevarats och märkts `INVALIDATED_BY_TARGET_AVAILABILITY_LOOKAHEAD`.

Den korrigerade F-vinnaren är fortfarande:

> 0,5 × rank(mom_12m) + 0,5 × rank(mom_18m) → Top 30 → lika vikt → 8 veckors rebalance → inga gates → inga separata entry/exit-regler.

Detta är en ny, korrigerad frysning – inte en validering av den gamla 25,4-procentsuppgiften. Korrigerad netto-CAGR är 23,59 %, Sharpe 1,390 och MaxDD −5,86 %. Spår G måste fortsatt betraktas som stoppat tills användaren uttryckligen startar ett nytt G mot denna frysning.

## Root cause

Den felaktiga vägen var:

`tools/spard_neutral_race.py::load_data()` → bortfiltrering av rader där `target_fwd52w is None` → samma filtrerade frame användes för prediction/ranking och portföljkonstruktion.

Targettillgänglighet är endast känd i efterhand. Filtret gjorde därför framtida utfallsobserverbarhet – i stor utsträckning framtida terminalstatus – till ett investerbarhetsvillkor vid T. På de ursprungliga 20 OOS-paneldatumen fanns 7 016 CORE-rader men bara 6 781 tidigare championpredictions: 235 rader föll bort, varav 231 avsåg 24 verifierade terminalinstrument. Korrekt universum ändrade Top 30 på 7 av de 10 faktiska 8-veckors-rebalancedatumen i den gamla perioden.

## Reparation

Ny gemensam motor: `tools/decision_portfolio_v2.py`.

Den upprätthåller följande gränser:

1. `load_decision(...)` läser endast panel, PIT-filter och features. Funktionen avvisar target-/utfallskolumner.
2. `target_map(...)` läser target separat.
3. `evaluation(...)` skapar endast efteråt den delmängd där target kan observeras.
4. `ic_metrics(...)` använder evaluation-delmängden.
5. `build_portfolio(...)` tar endast targetfria scores/decision rows och avvisar target-/utfallskolumner.
6. Benchmark byggs i samma funktion från exakt samma PIT-korrekta decision universe som strategin, men utan Top-N-urval.
7. Ekonomisk realiserad portföljavkastning hämtas separat efter att holdings redan är låsta. Verifierade terminalhändelser används i avkastningssteget och aldrig i urvalssteget.

Reparationen ändrar inte A, B, C eller targettabellen.

## Terminalinstrument

Alla 24 tidigare felaktigt bortfiltrerade terminalinstrument återfördes till det valbara universumet före sin terminalhändelse. I den korrigerade slutliga F-portföljen förekommer åtta verifierade terminalinstrument: ABLI, CALTX, CCOR-B, CS, DORO, NPAPER, PROB och RESURS.

Manuell kontroll av de begärda fallen:

| Instrument | Korrigerad hantering |
|---|---|
| DORO | Valbart och ägt från 2024-02-23, totalt 15 holdingdatum till 2025-09-05. Försvinner inte på grund av senare avnotering 2025-12-17. |
| CCOR-B | Ägt 2024-01-26; verifierad terminal/last price 2024-02-06; periodavkastning −0,20 %. |
| CALTX | Ägt vid fyra datum, senast 2024-10-04; verifierad terminal/last price 2024-10-10; periodavkastning +0,68 %. |
| ABLI | Ägt vid tre datum, senast 2025-02-21; verifierad terminal 2025-03-17; periodavkastning −1,33 %. |
| PROB | Ägt vid två datum, senast 2025-01-24; verifierad terminal 2025-02-12; periodavkastning −0,29 %. |
| CS | Ägt till 2025-12-26. Terminalhändelsen 2026-04-01 ligger efter experimentets sista avkastningsperiod; decemberinnehavet bokför den observerbara fyraveckorsavkastningen −11,88 %, inte en påhittad terminalavkastning. |

Terminalinstrument kan alltså rankas, väljas och ägas fram till den ekonomiska händelsen. Censurering av 52v-target påverkar endast IC-samplet.

## Benchmark

Tidigare benchmark byggdes från samma felaktigt targetfiltrerade frame. Den korrigerade benchmarken använder nu hela decision universe vid varje T och kräver varken framtida target eller framtida prisobserverbarhet för medlemskap. För D/F:s gemensamma OOS-fönster ändrades benchmark-CAGR från 14,02 % till 10,50 %.

Benchmark och strategi använder identiska datumvisa instrument-/PIT-filter. Skillnaden är endast viktning: benchmark lika vikt över universum, strategin lika vikt över sitt förregistrerade Top-N.

## Korrigerat Spår D

Exakt samma ursprungliga features, splits, embargo, modellfamiljer, parametrar och 20 bp kostnad har använts. IC-resultaten är nästan/oförändrade eftersom IC legitimt beräknas på observerbara targets. Portföljresultaten ändras materiellt.

| Modell | Mean IC gammal → ny | Top-30 IC gammal → ny | CAGR gammal → ny | Sharpe gammal → ny | MaxDD gammal → ny | Turnover gammal → ny | Leave-top-3 excess gammal → ny |
|---|---:|---:|---:|---:|---:|---:|---:|
| 12m momentum | 0,13265 → 0,13261 | −0,04343 → −0,04343 | 15,11 % → 17,29 % | 0,102 → 0,574 | −14,74 % → −13,58 % | 0,323 → 0,297 | −9,33 % → −3,29 % |
| Ridge | −0,00236 → −0,00236 | −0,08409 → −0,08409 | 19,94 % → 16,12 % | 0,362 → 0,344 | −18,76 % → −20,84 % | 0,260 → 0,236 | −10,50 % → −12,80 % |
| ElasticNet | −0,02366 → −0,02366 | −0,10033 → −0,10033 | 17,34 % → 11,32 % | 0,236 → 0,141 | −20,70 % → −23,33 % | 0,225 → 0,213 | −12,68 % → −16,61 % |
| LightGBM | 0,07156 → 0,07156 | −0,21400 → −0,21400 | 40,75 % → 30,88 % | 1,383 → 1,005 | −8,87 % → −15,25 % | 0,398 → 0,379 | +8,08 % → +0,57 % |
| XGBoost | 0,09504 → 0,09504 | −0,18685 → −0,18685 | 38,35 % → 26,14 % | 1,402 → 0,843 | −10,90 % → −15,33 % | 0,408 → 0,381 | +8,66 % → −2,29 % |
| CatBoost | 0,08933 → 0,08933 | −0,11669 → −0,11669 | 42,24 % → 30,09 % | 1,528 → 0,908 | −9,51 % → −16,97 % | 0,422 → 0,410 | +9,01 % → +3,24 % |

Den ursprungliga D-slutsatsen ändras inte: ingen ML-familj kvalificerar robust. Alla har negativ Top-30 IC; de positiva ML-resultaten är fortfarande koncentrationskänsliga. De tidigare mycket höga CAGR-värdena var dessutom materiellt uppblåsta av universumbuggen.

På de 20 gemensamma gamla datumen ändrades holdings för momentum på 14 datum (25 utbytta positioner), Ridge 18 (53), ElasticNet 16 (41), LightGBM 19 (43), XGBoost 16 (35) och CatBoost 16 (41). Den targetfria körningen kan dessutom konstruera portföljer för sex paneldatum augusti–december 2025 som tidigare saknades.

## Korrigerat Spår F

Hela originalsekvensen kördes om sekventiellt med oförändrat preregistrerat kandidatregister och beslutskriterier:

F1 → signalarkitektur → momentumkvalitet → gates → portföljstorlek → rebalance → entry/exit.

Inga nya varianter lades till, inga gamla togs bort och ingen parameter valdes för att rädda den tidigare CAGR:n. Den tidigare exkluderade `trend_consistency` förblev exkluderad av sin redan dokumenterade dataintegritetsorsak.

### F1, ren 12m

| Mått | Gammalt | Korrigerat |
|---|---:|---:|
| Mean IC52 | 0,13265 | 0,13261 |
| Median IC52 | 0,16467 | 0,16471 |
| Top-30 IC | −0,04343 | −0,04343 |
| Positiva IC-datum | 95,0 % | 95,0 % |
| Netto-CAGR | 15,11 % | 17,29 % |
| Benchmark-CAGR | 14,02 % | 10,50 % |
| Sharpe | 0,102 | 0,574 |
| MaxDD | −14,74 % | −13,58 % |
| Turnover | 0,323 | 0,297 |
| Leave-top-3 excess | −9,96 % | −3,29 % |

### Slutlig F-vinnare

| Mått | Gammal preliminär/ogiltig | Korrigerad |
|---|---:|---:|
| Mean IC52 | 0,15550 | 0,15549 |
| Median IC52 | 0,16531 | 0,16576 |
| Top-30 IC | −0,02197 | −0,02503 |
| Positiva IC-datum | 100 % | 100 % |
| Netto-CAGR | 25,43 % | 23,59 % |
| Benchmark-CAGR | 14,02 % | 10,50 % |
| Sharpe | 1,146 | 1,390 |
| MaxDD | −4,33 % | −5,86 % |
| Turnover | 0,210 | 0,196 |
| Leave-top-3 excess | +0,12 % | +2,97 % |

Den korrigerade 8v-varianten behöll originalets beslutskriterium mot den korrigerade 4v-varianten (4v: CAGR 19,69 %, Sharpe 0,974, MaxDD −9,58 %, turnover 0,263 och leave-top-3 excess −0,83 %). Ny klassificering enligt samma förregistrerade F-regel är därför fortfarande **A) ROBUST FÖRBÄTTRING AV MOMENTUM**. Detta är ett historiskt utvecklingsresultat och får inte beskrivas som oberoende forwardvalidering.

På den gamla gemensamma perioden ändrades den slutliga F-portföljen på 14 av 20 paneldatum och 22 tidigare positioner ersattes. Återkommande återförda namn var CCOR-B, DORO, CALTX, ABLI, PROB och CS; dessutom kom ATIC in indirekt genom den korrigerade rankordningen. Sex senare portföljdatum kunde nu konstrueras utan krav på framtida 52v-target.

## Påverkan på Spår E

E1 och E4 importerade samma targetfiltrerade `load_data` och deras portföljmått var därför ogiltiga. Båda har körts om med exakt ursprungliga CatBoost-/XGBoost-konfigurationer och utan tuning.

E1:s slutsats kvarstår: **FUNDAMENTA TILLFÖR INTE ROBUST INFORMATION**.

* CatBoost CORE → FUNDAMENTA: Δ mean IC −0,0564, Δ Top-30 IC +0,0055, Δ CAGR −12,08 procentenheter och Δ Sharpe −0,712.
* XGBoost CORE → FUNDAMENTA: Δ mean IC −0,1173, Δ Top-30 IC −0,1889, Δ CAGR −17,89 procentenheter.

E4:s slutsats kvarstår: **MACRO TILLFÖR INTE ROBUST INFORMATION**.

* CatBoost CORE → MACRO: Δ mean IC +0,0184 och Δ Top-30 IC +0,0392, men bara +0,23 procentenheter CAGR och något sämre leave-top-3 excess. Förbättringen är inte robust.
* XGBoost CORE → MACRO: Δ mean IC −0,0235, Δ Top-30 IC −0,0210 och Δ CAGR −12,29 procentenheter.

IC-delarna på observerbara targetrader var principiellt legitima, men de gamla portföljjämförelserna har ersatts av de korrigerade körningarna.

## Adversarial regressionstester

`tools/test_decision_portfolio_v2.py` kör följande hårda tester och samtliga passerar:

* decision schema får inte innehålla target/utfall;
* portföljmotorn avvisar targetbärande inputs;
* borttagen/ändrad framtida target lämnar tidigare ranking byte-identisk;
* borttagen framtida pris- och terminalinformation lämnar frysta featurebeslut oförändrade;
* ändrad framtida realiserbar avkastning lämnar rankings, holdings och trades byte-identiska;
* DORO, CCOR-B, CALTX, ABLI, PROB och CS finns kvar i decision universe före terminaldatum.

Senaste körning:

```text
PASS test_decision_schema_cannot_contain_target
PASS test_future_price_and_terminal_ablation_cannot_change_frozen_feature_decision
PASS test_future_return_availability_cannot_change_holdings
PASS test_future_target_ablation_cannot_change_prior_ranking
PASS test_known_future_terminal_names_remain_decision_eligible
```

Det byteorienterade beviset och testdefinitionerna finns i `repair_df/regression_results.json`.

## Sökning efter samma felklass

Statisk genomgång av aktiva urvals-/portföljvägar hittade fyra påverkade körningar:

* `tools/spard_neutral_race.py`
* `tools/sparf_systematic_momentum.py`
* E1 FUNDAMENTA-challenger
* E4 MACRO-challenger

Samtliga har ersatts i reparationskörningen. Övriga targetträffar i `spar_c_target.py`, `spar_c_qa.py` och tidigare QA/regressionstest avser targetproduktion eller legitim efterhandsutvärdering, inte ranking eller holdings. Full klassificering finns i `repair_df/static_scope_audit.json`.

Ingen ytterligare aktiv portföljväg hittades där target, framtida avkastning, terminalutfall eller framtida pristillgänglighet används före selection. De dynamiska ablationerna ger samma slutsats för den nya motorn.

## Artefakter och reproducerbarhet

Varje portföljexperiment producerar separata artefakter för rankings/scores, Top-N/holdings, trades, turnover/kostnader i returns och portföljavkastningar. D, F och E kördes två gånger med identiska aggregate SHA256.

| Körning | Aggregate SHA256 | Rankings | Holdings | Trades | Returns |
|---|---|---|---|---|---|
| D V2 PIT | `91ec27de6661b19f3a3d4f897588989614fa2f497f222ee4a5110b7ef7254488` | `bb54dab2…e2889fe76` | `141a877d…0525a677` | `67624258…dd36515` | `0d997d6b…956e6eb` |
| F V2 PIT | `a49c8f5f1d32f46232f36c1a672f379461f7f885eac5ad7d1ce0f98849a5a9d8` | `98ee056d…4e90722` | `509f5a49…07bedaa` | `e547f122…fe305d5` | `b3427f31…f740e72` |
| E V2 PIT | `90438bde6c6d26e9933d610f3d59e90d22c0756a4d53f4bee564ebb10e297cfa` | `55873076…c26730` | `a5fb3134…a0022e2c` | `722f0a07…985b24f` | `7a4d74d9…3fd77d8` |

Fullständiga hashar, filstorlekar och paths finns i respektive `manifest.json`. Artefaktrader:

| Körning | Rankings | Holdings | Trades | Returnperioder |
|---|---:|---:|---:|---:|
| D | 54 648 | 4 680 | 2 810 | 156 |
| F | 264 132 | 21 890 | 11 578 | 754 |
| E | 72 864 | 6 240 | 4 138 | 208 |

De låsta A/B/C-inputarna verifierades separat byte-for-byte: 13 av 13 aktiva artefakter matchar manifest, registry version 1.2.0.

## Historik och status

De gamla resultaten har inte skrivits över. Följande gamla kataloger har en explicit invalidationsmarkör:

* `spard/results/SPARD_CORE_NEUTRAL_RACE_V1/`
* `sparf/results/SPARF_SYSTEMATIC_MOMENTUM_V1/`
* gamla E1- och E4-resultatkataloger

Status för dessa är **INVALIDATED_BY_TARGET_AVAILABILITY_LOOKAHEAD**. De får endast användas som revisionshistorik.

Nya, aktiva reparationsartefakter ligger under `repair_df/results/`. Den övergripande frysningen finns i `repair_df/FREEZE_MANIFEST.json`.

## Slutbesked

* Root cause: **reparerad och regressionstestat**.
* Decision universe: **oberoende av framtida target**.
* Terminalinstrument: **valbara före verifierad terminalhändelse**.
* Benchmark: **ombyggd från samma PIT-universum**.
* Spår D: **ombyggt; ML-slutsatsen kvarstår, gamla portföljmått ogiltiga**.
* Spår F: **helt ombyggt; ny korrigerad champion är samma arkitektur men med nya metrics och nya holdings**.
* Spår E: **påverkat och ombyggt; FUNDAMENTA/MACRO-slutsatserna kvarstår**.
* Spår G: **fortsatt stoppat och inte reparerat/återstartat**.

