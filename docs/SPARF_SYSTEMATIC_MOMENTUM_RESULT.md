# Spår F — systematisk utveckling av momentumstrategin

Status: **SLUTFÖRD OCH REPRODUCERAD**  
Klassificering: **A) ROBUST FÖRBÄTTRING AV MOMENTUM**  
Ny champion: **lika viktad kombination av 12m- och 18m-momentum, 30 aktier, 8 veckors rebalance**

Spår D/E och A/B/C har inte ändrats. Ingen ML-tuning, extern data, targetändring eller kontinuerlig parametersökning har utförts.

## Championdefinition

Signal per instrument och paneldatum:

1. `mom_12m = adj[T] / adj[T-52v] - 1`
2. `mom_18m = adj[T] / adj[T-78v] - 1`
3. Beräkna respektive signals percentilrang inom samma paneldatum.
4. Slutscore = `0,5 × rank(mom_12m) + 0,5 × rank(mom_18m)`.

Övrig konfiguration:

- Ingen skip-period.
- Top 30, lika viktade.
- Rebalance var åttonde vecka; signalen utvärderas fortsatt på alla frysta fyraveckorspaneler.
- 20 bp kostnad per registrerad ensidig turnover enligt Spår D:s kostnadslogik.
- Samma investerbarhetsuniversum, target, OOS-period och prisavkastningar som Spår D.
- Ingen gate och ingen separat entry/exit-regel.

Tvåveckorsrebalance testades inte: den frysta C-panelen har endast fyraveckorsvisa PIT-observationer. Ingen approximation gjordes.

## F1 — reproducerad referenschampion

Spår D:s 12m momentum reproducerades exakt.

| Mått | F1 12m |
|---|---:|
| Mean IC52 | 0,1327 |
| Median IC52 | 0,1647 |
| Positiva IC-datum | 95 % |
| Top-30 IC52 | -0,0434 |
| CAGR brutto | 16,1 % |
| CAGR netto | 15,1 % |
| Benchmark CAGR | 14,0 % |
| Excess CAGR | 1,1 pp |
| Sharpe på excess | 0,102 |
| MaxDD | -14,7 % |
| Mean turnover | 0,323 |
| Leave-top-3 CAGR | 4,1 % |

Top-3 bidrag: `ATIC`, `NELLY`, `LUG`. Att ta bort dessa sänker CAGR under benchmark; F1:s portföljresultat är koncentrationskänsligt trots den starka tvärsnittssignalen.

## F2 — signalarkitektur

Elva preregistrerade signalchallengers testades. `combo_12m_18m` var den enda som passerade hela ersättningsregeln.

| Mått | F1 12m | 12m+18m | Förändring |
|---|---:|---:|---:|
| Mean IC52 | 0,1327 | 0,1555 | +0,0228 |
| Median IC52 | 0,1647 | 0,1653 | +0,0006 |
| Positiva IC-datum | 95 % | 100 % | +5 pp |
| Top-30 IC52 | -0,0434 | -0,0220 | +0,0215 |
| CAGR netto, 4v | 15,1 % | 20,2 % | +5,1 pp |
| Sharpe | 0,102 | 0,610 | +0,509 |
| MaxDD | -14,7 % | -8,7 % | +6,1 pp |
| Turnover | 0,323 | 0,282 | -0,042 |
| Leave-top-3 excess | -10,0 pp | -5,1 pp | +4,9 pp |

Årsvis mean IC är 0,1603 år 2024 och 0,1466 år 2025; samtliga 20 OOS-paneldatum har positiv IC.

Top-30 IC förbättras men är fortfarande negativ. Förbättringen drivs därför främst av bättre bred tvärsnittsranking och robustare portföljutfall, inte av demonstrerat positiv rangordning inom de trettio högst rankade aktierna.

### 18m-täckningskänslighet

Kombinationen har som mest 19,4 % ties när saknad 18m-historik medianersätts enligt den låsta baselineprincipen; minst 274 distinkta scores återstår per datum. På endast de 6 646 OOS-observationer där 18m faktiskt finns:

- 12m mean IC 0,1330; 12m+18m 0,1569.
- Positiv IC-andel 90 % respektive 100 %.
- Top-30 IC -0,0519 respektive -0,0220.
- Median IC 0,1679 respektive 0,1676 — i praktiken oförändrad och marginellt lägre för kombinationen.

Känsligheten stödjer mean IC och stabilitet men visar att förbättringen i median IC är obetydlig.

## F3 — momentumkvalitet och stoppfynd

`trend_consistency_52w` vann först preliminärt, men adversarial QA visade att blueprinten säger andel positiva veckor medan aktiv C-kod beräknar andel positiva handelsdagar. Spår F stoppades, resultatet ogiltigförklarades och C ändrades inte.

Efter explicit fortsättningsprotokoll uteslöts kandidaten som `EXCLUDED_DATA_INTEGRITY`. De fyra övriga ursprungligen preregistrerade kvalitetsmåtten kördes om från den låsta F2-vinnaren. Ingen passerade den ursprungliga ersättningsregeln. Ingen kvalitetsfeature lades till.

Historiken över stoppet finns kvar i `docs/SPARF_STOP_REPORT.md`; den har inte raderats.

## F4 — gates

Ingen gate passerade den preregistrerade riskkontrollregeln.

- Positivt 12m-momentum förändrade inte den valda top-30-portföljen.
- Pris över SMA52 förbättrade vissa portföljmått men nådde inte det förregistrerade kravet på minst två procentenheters MaxDD-förbättring.
- Bred positiv marknadstrend gav 75 % genomsnittlig exponering men sänkte CAGR och Sharpe kraftigt. Det är cash timing/riskkontroll, inte förbättrad stock-selection-alpha.

## F5 — portföljstorlek

N=10/20/30/40 testades med faktisk top-N IC.

- N=10 hade hög historisk CAGR men negativ top-10 IC och sämre tickerrobusthet.
- N=20 hade negativ top-20 IC och klart sämre drawdown.
- N=40 hade positiv top-40 IC och något bättre drawdown, men klarade inte den låsta Sharpe-toleransen relativt N=30.
- N=30 behölls.

Ingen portföljstorlek valdes enbart på högst CAGR.

## F6 — rebalance

8 veckor ersatte 4 veckor enligt den preregistrerade regeln.

| Mått | 4 veckor | 8 veckor |
|---|---:|---:|
| CAGR brutto | 21,0 % | 26,1 % |
| CAGR netto | 20,2 % | 25,4 % |
| Sharpe | 0,610 | 1,146 |
| MaxDD | -8,7 % | -4,3 % |
| Mean turnover | 0,282 | 0,210 |
| Leave-top-3 excess | -5,1 pp | +0,1 pp |

Nettoavkastningen för de observerade panelperioderna var 26,5 % under 2024 och 12,0 % under den tillgängliga delen av 2025. Dessa är korta historiska OOS-resultat och ska inte extrapoleras som en framtida avkastningsprognos.

## F7 — entry/exit

Rank-exit, momentumförlust, absolut trendbrott och drawdown-exit testades isolerat. Ingen passerade den preregistrerade riskkontrollregeln. Slutlig champion har därför inget separat entry/exit-lager.

## Robusthet och koncentration

Slutlig 8v-champion:

- Top-3 tickers: `NELLY`, `ATIC`, `LUG`.
- CAGR efter att top-3 tas bort: 14,14 %, mot benchmark 14,02 %.
- Sämsta leave-one-ticker-out CAGR är 20,71 % när `NELLY` tas bort.
- Största sektorandel är sektor 5 med 26 %, följd av sektor 4 med 22 % och sektor 6 med 20 %.
- Median adjacent-rank stability är 0,937.
- Minst 274 distinkta scores per OOS-datum; ingen degenererad ranking, men den dokumenterade 18m-täckningens tie-reservation kvarstår.

Resultatet kollapsar därmed inte längre när de tre största tickerbidragen tas bort. Detta var den viktigaste förbättringen jämfört med F1.

## Multiple testing

Totalt 30 utfall finns kvar i experimentregistret, inklusive misslyckade kandidater och den dataintegritetsuteslutna trendkonsistensen. Stegen kördes sekventiellt: signal → kvalitet → gate → portföljstorlek → rebalance → entry/exit.

## Slutbedömning

**A) ROBUST FÖRBÄTTRING AV MOMENTUM.**

12m+18m förbättrar mean IC, positiv datumandel, top-30 IC, drawdown, turnover och tickerrobusthet. Åttaveckorsrebalance förbättrar därefter nettoresultat och koncentrationsrobusthet utan ny signal eller targetanpassning.

Reservationer:

1. OOS-underlaget omfattar endast 20 paneldatum under 2024–juli 2025.
2. Top-30 IC är fortfarande negativ.
3. Median IC förbättras endast marginellt och är marginellt sämre i complete-18m-subsetet.
4. Historisk CAGR är inte bevis för framtida alpha.
5. `trend_consistency_52w` är fortsatt felmärkt i fryst C och får inte användas innan ett separat C-beslut fattas.

## Låsning

- Predictions/rankings SHA256: `5db11f465dcb1d2c651faaf3063cfc1c2cfac626fa38bb5d9cd8053c58845c89`
- Final decision SHA256: `a949144a888a6c0f3a5bf73132dc223efc48816a50b50c3413c3d9a3104eeaf5`
- Result aggregate SHA256: `fdb93e23140e2e28d0242a97987e11cfe08e1eb1b87c0e3c855731b6d9402a72`

En full identisk omkörning gav samma tre hashar. A/B/C-manifestkontrollen passerade samtidigt 13/13 aktiva artefakter byte-för-byte.
