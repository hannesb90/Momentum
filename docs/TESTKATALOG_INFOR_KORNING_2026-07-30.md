# Momentum – samlad testkatalog inför körning

Datum: 2026-07-30. Denna fil är den enda arbetskön för nya alfa-, risk- och scenariotester.

## Regler

1. Lås hypotes, data, parametrar, mått och beslutsregel före körning.
2. Börja med IC/Q5–Q1 och tidsstabilitet; kör full backtest först efter positiv screening.
3. Kräv point-in-time-data, nästa-bar-exekvering och realistiska kostnader.
4. Nuvarande holdout är diagnostisk, inte tillräcklig för produktion; använd senare orörd period eller paper/live.

## Dubblettkontroll

Kontrollerad mot #1–#164, aktiva testkön, `FEATURE_COLS` och samtliga `tune_*.py`. Kör inte om residualmomentum (#121), riskjusterat momentum som solo-IC (#123), 12-1/skip-month, 52v-high, PEAD, sentiment, sektor-gap, regimfeature, breadth/dispersion, ETF-rotation, vol-target, standard-exits, triple-barrier-pilot, kvalitet×momentum, accruals eller dynamiskt antal positioner.

## Tier A – körbara nu

| ID | Test | Status och beslutskriterium |
|---|---|---|
| A1 | Riskjusterat momentum i LambdaRank | **KLAR 2026-07-30, se UTVECKLINGSLOGG #165. Inkonklusivt** – roc13-varianten vinner på dev-median-IC men blir identisk med baslinjen i holdout-diagnostiken (klassiskt dev/holdout-omvänt varningsmönster); mom_12_1-varianten tvärtom. Ingen adoptionskandidat, ingen ytterligare körning gjord (`tune_riskadj_momentum_ablation.py`). |
| A2 | Modellosäkerhet som filter | **OGILTIGFÖRKLARAT 2026-07-31 – kräver omkörning.** #167/#171 z-normaliserade över modeller *inom varje aktie* och tog sedan std över samma axel, vilket gör oenigheten definitionsmässigt ≈1. Koden är rättad till z-normalisering av varje modell tvärs över aktier följt av std mellan modeller. Tidigare filter/random-control-resultat får inte användas som evidens. Omtag ska använda den efter LambdaRank validerade Large 52v-baslinjen (#124). |
| A3 | Sektorneutral residualmomentum | Residual mot marknad och sektor; jämför rå 12-1 och `resid_mom`. Stabilitet i små sektorer krävs. |
| A4 | Price-delay-interaktion | Hou–Moskowitz delay som interaktion med `resid_mom`/PEAD. Samma riktning i dev och senare period krävs. |
| A5 | Volymfas i momentum | Turnover × vinnare i 2×3-sort över 13/26/52v. Kräver nettoedge efter kostnad/kapacitet. |
| A6 | Amihud/spread-resiliens | Testa residualmomentum efter ex ante illikviditets- och spreadjustering. Rapportera brutto, netto och stressad kostnad. |
| A7 | Koncentrationstak | **KLAR 2026-07-30/31, se UTVECKLINGSLOGG #168+#170+#171 (buggmönster 13+14, nu helt stängda). ROBUST RESULTAT.** `tune_concentration_cap.py` saknade själv `MAX_POSITIONS`/`MARKET_FILTER_EXPOSURE`/`SECTOR_MAP` (buggmönster 14) men INTE `REBALANCE_WEEKS`; omkört med fullt korrekt config – **"0 trimningar vid 20/25%"-resultatet står kvar oförändrat** även under produktionens exakta förutsättningar. Jämförelsen mot #161 (`viktdrift`) är fortfarande INTE explicit kontrollerad – #161:s källskript är inte identifierat, kvarstår som öppen punkt. |
| A8 | Re-entry-tröskel | #149:s 10 pp-resultat replikeras på small eller senare period före produktion. |
| A9 | Individuell −40 %-rotation | **Underlaget slutgiltigt uppdaterat 2026-07-31, se UTVECKLINGSLOGG #171.** #147 omkört med fullt korrekt config (dev CAGR +15,80%/holdout +4,30% baslinje): `rotate_exit` vinner tydligt på DEV (+16,40%) men `cash_exit` är marginellt BÄTTRE än `rotate_exit` på holdout (+4,40% mot +4,20%), samma rangordning som föregående omkörning bara med större tal – kriteriet "rotation måste slå kassa OCH baslinje netto" alltså fortsatt INTE uppfyllt på holdout. Förregistrerad replikering (denna post) fortfarande inte gjord. |

## Tier B – ny daglig-data-/screeningforskning

| ID | Test | Status och beslutskriterium |
|---|---|---|
| B1 | Intradag vs overnight | Separera 12-1 i open-to-close och close-to-open. IC/Q5–Q1 i två perioder före ablation. |
| B2 | Frog-in-the-pan | Gradvisa små rörelser kontra få hopp, som interaktion med residualmomentum. Isolerad screening först. |
| B3 | Jump-clustering | Klustrade extrema dagliga hopp som villkor för momentum/SUE. Tröskel/fönster förregistreras. |
| B4 | IVOL och lotterisvans | Residual-IVOL och max daglig avkastning som topp-N-veto; måste höja nedsidesprecision. |
| B5 | Kalendermånads-säsong | Samma akties marknadsjusterade månadseffekt över 5/10 år; avfärda om den drivs av en månad/microcaps. |
| B6 | Systemisk co-crash | Vänstersvansbredd + korrelationsspik som nyköpsfilter; block-bootstrap och varje trigger redovisas. |
| B7 | Rapportkalender-premium | Tidigare vinnare i [−5,+5] dagar kring faktiska rapporter; aldrig uppskattade datum. |

## Tier C – point-in-time-fundamenta eller ny data

| ID | Test | Status och beslutskriterium |
|---|---|---|
| C1 | Nedsidesmodell | **DEV-diagnostik KLAR 2026-07-30, se UTVECKLINGSLOGG #166, HOLDOUT MEDVETET INTE ÖPPNAD.** Modellen slår naiv trailing-rvol på PR-AUC (60% av 25 splits) men inte på ROC-AUC; kraschar till nästan slumpmässig ROC-AUC (0,52-0,62) i just krisperioderna – sämst när den behövs mest. Väntar på beslut om att spendera holdout-öppningen (`tune_downside_veto_model.py`). |
| C2 | SUE | Standardiserad kvartalsöverraskning med publiceringstid. Testa solo och med residualmomentum. |
| C3 | Earnings seasonality | Resultat relativt tidigare samma fiskala kvartal; kräver historiska vintages. |
| C4 | Analytikerrevideringar | Befintlig logg testas först med minst 13 mogna datum; topquartile netto och inkrementellt mot rank. |
| C5 | Analytikertäckning | Residual analystäckning × momentum; replikeringsfråga med blandad extern evidens. |
| C6 | Nettoemission/shareholder yield | PIT-aktieantal, återköp och utdelning som riskfilter. Nutida antal aktier är förbjudet historiskt. |
| C7 | Asset growth/investment | Tillgångs-, PP&E- och lagertillväxt med rapportlagg; separat från accruals/F-score. |
| C8 | Distress/failure probability | Transparant distress-score som extra källa till C1:s nedsidesprecision. |
| C9 | Kund/leverantörs-ledlag | Tidsstämplad nordisk relationsgraf; panel- och permutationstest före feature. |

## Genomförda scenariotester: om X, gör Y

| X | Y | Facit hittills |
|---|---|---|
| Enskilt innehav ≤−40 % | Kassa eller direkt rotation | Rotation vinner tydligt på dev, men kassa marginellt bättre på holdout (#147, korrigerat i #170) – tunt n, inget entydigt facit. |
| Trendbrott mellan rebalanseringar | SMA-exit eller ATR-stop | Negativt netto: whipsaw och cash-drag (#115/#130). |
| Björnmarknad | Bear-ETF i stället för kassa | Kontanter vann (#131). |
| Bullregim | +1,5x eller +2x Bull-ETF | +1,5x bäst, men ej produktionssatt p.g.a. hävstång/decay (#131/#133). |
| Återköp efter exit | Kräv 5/10 pp rankförbättring | 10 pp bäst (#149); replikation återstår. |
| Grind blockerar vändare | Mjuka/sänk/stäng av grind | Sämre än hård 0,10-grind (#62). |
| Korrelationsfilter minskar antal namn | Fyll på med nästa kandidat | Inte värt: filtret band aldrig relevant portfölj (#125). |
| Årsvis viktglidning | Ingen lösning testad | #161 är problemdiagnos; A7 är lösningstestet. |

## Saknade stresstester – separat scenarioharness

1. V-formad krasch: marknad −20 % på en vecka, sedan snabb återhämtning.
2. Gap/likviditet: största innehavet −30 % och 5–10× spread/impact vid sälj.
3. Korrelationschock: alla innehav blir ett tema.
4. Signalhaveri: topp-N har negativ IC under 12 månader.
5. Databrott: försenad rapport/fundamenta eller 8 veckors prisstopp.

För varje scenario jämförs baslinje med fördefinierad Y: ingen förändring, färre nyköp, koncentrationstrimning och rotation. Rapportera slutvärde, MaxDD, CVaR, återhämtningstid, turnover, kostnad och felaktiga ingripanden.

## Forskningsankare

- [Price Momentum and Trading Volume](https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00280)
- [Market Frictions, Price Delay, and the Cross-Section of Expected Returns](https://academic.oup.com/rfs/article-abstract/18/3/981/1617714)
- [Momentum Crashes](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2490306)
- [Mispricing Factors](https://academic.oup.com/rfs/article/30/4/1270/2965095)
