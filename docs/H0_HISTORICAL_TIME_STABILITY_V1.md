# H0 Historical Time Stability V1

Status: **HISTORICAL ROBUSTNESS — NOT UNTOUCHED FORWARD**

Slutklassificering: **BLANDAD TIDSSTABILITET**

H0 har inte ändrats. Forwardprotokollet har inte lästs om eller ändrats. Första eligible untouched-forwardpanel är fortsatt 2026-09-04.

## Låsning och historik

- Preregistrering: `research_k/H0_HISTORICAL_TIME_STABILITY_PREREGISTRATION.json`
- Preregistrering SHA256: `e231f8e4e5010ba1ac7dcdf2cd46c08ecc47d6ebb067c9f5f0a352f49c9cf485`
- Validerad prisstart: 2020-01-02.
- Första panel där en verklig 18m-lookback kan finnas: 2021-07-16. Då hade 325/352 rader äkta 18m; den frysta median-/tie-regeln hanterade resterande 27/28 kombinationsmissing.
- Den frysta 8v-fasen är förankrad i 2024-01-26. Första fas-kompatibla historiska rebalance är därför 2021-08-13.
- Sista historiska decision panel: 2026-07-10.
- Sista panel med utvärderbar post-decision 4v-portföljavkastning: 2026-06-12.
- Sista panel med observerbar 52v-target: 2025-07-11.
- Totalt: 32 faktiska 8v-rebalanseringar.

## Forskningsutsatta perioder

- 2020–2022/2023 användes i D:s walk-forward-träning, beroende på split och 52v-embargo.
- Kalenderåret 2023 var explicit validation och påverkade forskningsbeslut.
- 2024-01-26–2025-07-11 var target-observerbar historisk OOS; portföljutfall till 2025-12-26 påverkade F/G/K och championvalet.
- Data-, QA- och forskningsarbete fram till V4-frysningen har exponerat den övriga historiken. Ingen del av analysen ska kallas untouched forward.

## Fasta fönster

| Fönster | IC-paneler | Mean IC52 | Median IC52 | Top-30 IC | Positiv IC | CAGR | Benchmark | Excess CAGR | Sharpe excess | MaxDD | Turnover | 8v reb. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Pre-2024 | 33 | 0,0811 | 0,0775 | −0,0521 | 72,7 % | −2,35 % | −7,15 % | +4,80 pp | 0,45 | −33,81 % | 0,177 | 16 |
| Full historik | 53 | 0,1091 | 0,1108 | −0,0419 | 83,0 % | 6,08 % | 0,21 % | +5,87 pp | 0,54 | −33,81 % | 0,171 | 32 |
| Championperiod 2024–2025, fristående fryst referens | 20 | 0,1555 | 0,1658 | −0,0250 | 100,0 % | 25,29 % | 10,07 % | +15,21 pp | 1,38 | −4,43 % | 0,196 | 13 |
| 2021, partiellt | 7 | −0,0764 | −0,0572 | −0,0383 | 0,0 % | 11,78 % | −6,97 % | +18,75 pp | 1,02 | −15,58 % | 0,267 | 3 |
| 2022 | 13 | 0,1537 | 0,1700 | −0,0430 | 100,0 % | −5,78 % | −12,06 % | +6,28 pp | 0,63 | −18,44 % | 0,156 | 7 |
| 2023 | 13 | 0,0932 | 0,0775 | −0,0686 | 84,6 % | −4,91 % | −2,05 % | −2,86 pp | −0,35 | −17,12 % | 0,156 | 6 |
| 2024 | 13 | 0,1604 | 0,1679 | −0,0540 | 100,0 % | 27,48 % | 17,45 % | +10,03 pp | 0,71 | −2,62 % | 0,182 | 7 |
| 2025, IC partiellt | 7 | 0,1464 | 0,1636 | 0,0289 | 100,0 % | 23,29 % | 3,16 % | +20,14 pp | 2,69 | −2,92 % | 0,156 | 6 |
| 2026, partiellt | 0 | — | — | — | — | −20,01 % | 0,22 % | −20,23 pp | −3,97 | −7,66 % | 0,144 | 3 |

2021 och 2026 har färre än fem faktiska 8v-rebalanseringar och är uttryckligen låg statistisk styrka. 2026 saknar ännu mogna IC52-observationer.

## Rullande fönster

- 52 förregistrerade rullande 12m-fönster: median excess CAGR +6,86 pp; 80,8 % positiva. Spann −5,65 till +20,14 pp. Alla fönster med observerbar IC hade positiv mean IC.
- 39 förregistrerade rullande 24m-fönster: median excess CAGR +4,15 pp; 97,4 % positiva. Spann −1,26 till +15,30 pp. Alla hade positiv mean IC.
- Svagaste 12m-fönstret var 2022-12-30–2023-12-01: excess −5,65 pp.
- Starkaste kontinuerliga 24m-fönstret var 2024-01-26–2025-12-26: excess +15,30 pp. Den frysta fristående championreferensen är +15,21 pp; skillnaden är enbart initial turnover (1,00 fristående mot 0,30 i den redan pågående historiska portföljen).

## Koncentration

- Pre-2024 stod Top-5 för cirka 100,4 % av aritmetisk excess. Leave-top-5 CAGR var −7,37 %.
- Full historik stod Top-1/Top-3/Top-5 för 27,2 % / 60,3 % / 92,3 % av aritmetisk excess.
- Fullhistorisk CAGR föll från 6,08 % till 0,27 % leave-top-5, nästan samma som benchmark 0,21 %.
- Championperiodens Top-5 stod för 96,3 % av aritmetisk excess, i linje med tidigare G-fynd.
- 2024–2025 skapade 83,9 % av fullhistoriens positiva aritmetiska excess. Pre-2024 bidrog 48,6 %, medan den partiella 2026-perioden drog bort 32,4 %.

## Marknadsmiljöer

Historiken innehåller flera distinkta miljöer: stark marknad 2021, börsnedgång/hög volatilitet och inledd ränteuppgång 2022, fortsatt högt/rising ränteläge och svag svensk 12m-marknad 2023, starkare marknad 2024, räntenedgång 2025 och en ännu kort/svag H0-period 2026. Detta är en beskrivning, inte en gate eller allokeringsregel.

## Tolkning

H0:s tvärsnittsranking visar signal även före 2024: pre-2024 mean IC52 är positiv och 2022–2023 är IC positivt. Portföljen slog också en fallande benchmark pre-2024. Därför är H0 inte rent ett 2024–2025-fenomen.

Evidensen är ändå inte bred nog för klassificeringen BRED HISTORISK TIDSSTABILITET. Absolut CAGR före 2024 var negativ, 2023 gav negativ excess, 2026 är hittills kraftigt negativt och Top-30 IC är negativt över nästan alla längre perioder. Framför allt försvinner praktiskt taget hela fullhistoriens excess när de fem största tickerbidragen tas bort.

Slutsatsen är därför **BLANDAD TIDSSTABILITET**: en generell rankningsedge är synlig i flera marknadsmiljöer, men den starka portföljprofilen och låga drawdownen är tydligt koncentrerade till 2024–2025 och ett fåtal vinnare. Detta ändrar tilltron till H0, inte H0.

## Reproducerbarhet

- Resultatmanifest SHA256: `c163c3a365d62435b7f8b36f188c6dd446f3e2cc9293378b4bc5689ae83b959c`
- Två konsekutiva körningar gav byte-identiskt manifest och outputs.
- Maskinläsbara resultat finns i `research_k/h0_historical_time_stability_v1/`.
