# Spår G – oberoende falsifiering av korrigerad F-champion

Datum: 2026-08-09  
Slutklassificering: **D — DATA-/IMPLEMENTATIONSBLOCKERARE**

## Sammanfattning

G0 passerade efter att D/F-frysningen reparerats och reproducerats byte-identiskt.
G2–G13 kördes enligt preregistreringen utan parameterändring. G14 upptäckte
emellertid en ny exekveringstidsbugg som gör de historiska portföljmåtten
icke-exekverbara. Spår G stoppar därför med D. Ingen reparation har gjorts i G.

Den tidigare target-availability-buggen är fortsatt borta. Den nya blockeraren är
en annan felklass.

## G0 – reparationsgate

* Ny freeze `DF_LOOKAHEAD_REPAIR_V3_IMMUTABLE_2026-08-09`: 40/40 filer PASS.
* Freeze-manifest SHA256: `d25bbbad934c88ee6631926e5011cae244e1bb02b7cfe5ec0ba0005526f7763a`.
* D: 8/8 outputfiler byte-identiska efter full rebuild.
* F: 15/15 outputfiler byte-identiska efter full F1–F7-rebuild.
* Framtidsablation/schema: 5/5 PASS.
* A/B/C: 13/13 aktiva artefakter byte-identiska mot manifest.
* Den aktiva reparationsvägen använder target endast i separat efterhands-evaluation för IC.

## G14-blockerare – samma stängning och historiskt entrypris

CORE-features använder `adjusted_close` på `price_date`. För 720 av championens
780 holdingrader är `price_date == panel_date`: momentumrankingen känner alltså
stängningspriset T. `tools/decision_portfolio_v2.py::price_returns()` börjar
samtidigt portföljavkastningen från exakt samma stängningspris.

Dokumentationen säger att rebalansering sker efter stängning. Då är close T känt,
men det går inte längre att köpa retroaktivt till den avslutade stängningen T.
Portföljen behöver en explicit, preregistrerad första exekverbar pris-/laggregel.

För ytterligare 60 holdingrader infaller paneldatum när marknaden är stängd:

* 30 rader använder ett pris en kalenderdag före beslutet;
* 30 rader använder ett pris tre kalenderdagar före beslutet.

Motorn räknar ändå avkastning från det historiska priset. Alla 780 holdingrader
har ett senare faktiskt handelspris i den validerade prisserien. Detta är därför
inte bara en konservativ saknad-dataregel utan en faktisk exekveringstidsdefekt.

Konsekvens: korrigerade F:s ranking och IC kan granskas vidare, men 23,59 % CAGR,
Sharpe 1,390, MaxDD −5,86 % och alla portföljbaserade robusthetsmått får inte
användas som exekverbar alpha-evidens innan D/F-portföljutvärderingen reparerats
och återfrysts. G väljer ingen ny exekveringsregel.

## Historisk diagnostik före blockeraren

Följande resultat redovisas transparent men kan inte upphäva D-klassificeringen.

### Tidsblock

| Block | Mean IC | Top-30 IC | Portfölj-excess CAGR | Andel av absolut block-excess |
|---|---:|---:|---:|---:|
| 2024 H1 | 0,226 | +0,026 | +13,33 % | 18,2 % |
| 2024 H2 | 0,104 | −0,123 | +2,24 % | 5,2 % |
| 2025 H1 | 0,139 | +0,028 | +8,02 % | 13,4 % |
| 2025 H2 | 0,188, endast 1 observerbar IC-dag | +0,034 | +28,99 % | 63,1 % |

Portföljexcess är alltså starkt koncentrerad till 2025 H2, medan targetbaserad
evidens där i praktiken bara omfattar ett paneldatum.

### Rebalancefas

| 8v-fas | CAGR | Excess CAGR | Sharpe | MaxDD | Leave-top-3 excess |
|---|---:|---:|---:|---:|---:|
| Fryst fas 0 | 23,59 % | 13,09 % | 1,390 | −5,86 % | +2,97 % |
| Fas 1 | 19,91 % | 9,41 % | 1,063 | −12,88 % | −0,19 % |

Championfasen är bäst av de två möjliga faserna. Alternativfasen kollapsar inte i
absolut CAGR men tappar hela leave-top-3-excessen och mer än fördubblar MaxDD.

### Tickerkoncentration

* Top 1: NELLY; borttagning lämnar 8,55 % excess CAGR.
* Top 3: NELLY, LUG, ATIC; 77,5 % av aritmetisk excess. Leave-top-3 excess CAGR är verifierat +2,97 %.
* Top 5: plus SANION och OVZON; 111,1 % av aritmetisk excess. Leave-top-5 excess CAGR blir −1,18 %.
* Top 10: 172,1 % av aritmetisk excess. Leave-top-10 excess CAGR blir −8,24 %.

En enskild ticker förstör inte resultatet, men fem tickers räcker för att göra
excess negativ. Koncentrationen är materiell.

### Terminaler

24 verifierade terminalinstrument förekommer i ranking och åtta ägs: ABLI,
CALTX, CCOR-B, CS, DORO, NPAPER, PROB och RESURS. Deras periodavkastningar finns
explicit i `G7_terminal.json`. Diagnostiskt utan samtliga terminalinstrument är
CAGR 23,03 % mot 23,59 % inklusive dem. Terminaler skapar alltså inte den
observerade överavkastningen och terminalförluster försvinner inte genom
targetcensurering i den granskade kedjan.

### 18m missing och ties

* 215 av 9 108 beslutsposter saknar äkta 18m-historik: 2,36 %.
* 0 av 780 Top-30 holdingrader saknar 18m.
* Inga missing-18m-namn finns inom rank 25–35.
* Cutoff har en ensam score på 25/26 datum och två lika scores på ett datum.

Den frysta medianregeln ger alltså ingen observerad Top-30-fördel åt missing-18m.

### Kostnad och benchmark

| Ensidig kostnad | Diagnostisk CAGR | Excess CAGR |
|---|---:|---:|
| 0 bp | 24,20 % | 13,71 % |
| 20 bp | 23,59 % | 13,09 % |
| 40 bp | 22,97 % | 12,47 % |
| 60 bp | 22,36 % | 11,86 % |
| 100 bp | 21,14 % | 10,64 % |

Beräknad break-even är cirka 464 bp per registrerad ensidig turnover. Benchmark
reproduceras till högst `1,39e-17` periodfel, använder samma targetfria
decision universe och har 10,50 % CAGR. Benchmarken debiteras ingen omsättningskostnad,
vilket gör den starkare snarare än artificiellt svagare.

### Membership och sektor

98,2 % av holdingraderna har `membership_verified=False`; 1,8 % är verifierade.
Nästan hela resultatet ligger därför i den dokumenterat osäkra membershipdelen.
Detta är inte bevis för fel medlemskap men hindrar en stark Nasdaq-main-market-
tolkning. Large/Mid/Small- och likviditetssegment kan inte testas PIT med fryst data.

Historiskt PIT-versionerad sektorinformation finns inte. Sektortestet har därför
inte genomförts genom att backcasta dagens `sectorId`.

### Tidsblock-bootstrap

10 000 moving-block-drag, blocklängd tre paneldatum:

* mean IC 95 % intervall: 0,127–0,183;
* ΔIC mot 12m: 0,005–0,041; sannolikhet positiv 99,5 %;
* genomsnittlig period-excess: −0,12 % till +1,38 %; sannolikhet positiv 94,9 %;
* Sharpe: −0,205 till 2,624;
* leave-top-3-excess: −0,84 % till +0,68 % per period; sannolikhet positiv 42,7 %.

IC-förbättringen har historiskt stöd, men portföljexcess och koncentrationsrensad
excess har bred osäkerhet. Endast 20 targetobserverbara IC-datum och 26
portföljperioder finns.

## 12m-jämförelse

Historiskt förbättras mean IC med +0,0229 och Top-30 IC med +0,0184 jämfört med
ren 12m. Top-30 IC är ändå negativ (−0,0250). De laggade portföljmåtten måste
byggas om innan den portföljmässiga förbättringen kan bedömas.

## Untouched forward

Ett permanent schema och protokoll har skapats under `sparg/forward_protocol/`,
men är blockerat tills exekveringstidpunkten reparerats. Ingen tillräcklig ny
panel efter frysningen finns.

**CHAMPION HAR INTE ÄNNU VERIFIERATS PÅ TILLRÄCKLIG UNTOUCHED FORWARD-DATA.**

## Vad som måste öppnas

Spår G får inte reparera fyndet. D/F-portföljlagret måste öppnas för ett
förregistrerat beslut om beslutstid, ordertid och första exekverbara pris. Därefter
måste D och hela F byggas om, resultaten frysas på nytt och G startas om från G0.
A/B/C och signaldefinitionen behöver inte automatiskt öppnas av detta fynd.

## Slutbesked

**D — DATA-/IMPLEMENTATIONSBLOCKERARE**

Ingen ny champion har valts. Ingen parameter, feature, Top-N, rebalancefrekvens,
gate eller exitregel har ändrats.
