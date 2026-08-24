# Spår K3 — Fundamental förändring inom momentum

Status: **SLUTFÖRD OCH FRYST**  
Run ID: `K3_FUNDAMENTAL_CHANGE_DIAGNOSTIC_V1`  
Preregistrering SHA256: `44f2be7df469f5dd011f056ebe92cd448c3fe6aaa9fd232e911ee45559c4a1cb`

> **NOT SURVIVORSHIP SAFE.** Varje testad population innehåller 0 terminalinstrument. Resultaten kan inte etablera robust fundamental alpha.

## Slutsats

Samtliga fem preregistrerade fundamental-change-mått klassificeras **INGET STÖD**. Alla jämförelser använder featurevis identiska rader för matched H0 och den fasta 50/50-blenden. Ingen jämförelse mot hela H0-populationen används som evidens och ingen challenger skapas.

## Primära resultat

| Feature | Instrument | Evalrader | Terminaler | Matched H0 mean IC | Blend mean IC | Δ mean IC | Δ median IC | Δ Top-30 IC | Klass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Revenue growth YoY | 307 | 5 995 | **0** | 0,1824 | 0,1526 | −0,0299 | −0,0371 | −0,0654 | INGET STÖD |
| Operating-margin expansion YoY | 305 | 5 967 | **0** | 0,1824 | 0,1575 | −0,0250 | −0,0426 | −0,0018 | INGET STÖD |
| EBITDA-margin expansion YoY | 305 | 5 967 | **0** | 0,1824 | 0,1596 | −0,0229 | −0,0296 | −0,0078 | INGET STÖD |
| FCF-margin expansion YoY | 305 | 5 967 | **0** | 0,1824 | 0,0987 | −0,0837 | −0,0968 | −0,0996 | INGET STÖD |
| Lägre share-count dilution YoY | 330 | 6 467 | **0** | 0,1531 | 0,1506 | −0,0026 | −0,0261 | −0,1124 | INGET STÖD |

Positiv IC-andel var redan 100 % för matched H0 och ändrades inte. Detta räddar inte challengers vars mean/median/Top-30 IC försämras.

## Tidsblock

- Revenue growth: Δ mean IC −0,0207 / −0,0390.
- Operating-margin expansion: −0,0228 / −0,0271.
- EBITDA-margin expansion: −0,0212 / −0,0245.
- FCF-margin expansion: −0,0701 / −0,0974.
- Lägre dilution: +0,0208 / −0,0259.

Fyra mått försämras i båda blocken. Dilution byter tecken och är därför inte tidsstabil; dess Top-30-försämring är dessutom −0,1124.

## Sekundära matched-population-portföljer

Portföljresultaten är sekundära och byggda med samma V4 executionregel, Top-30, equal weight, 8v-rebalans och kostnad. De stöder inte någon uppgradering:

| Feature | Matched H0 CAGR | Blend CAGR | Matched H0 Sharpe | Blend Sharpe | Matched H0 MaxDD | Blend MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| Revenue growth | 28,14 % | 16,24 % | 1,856 | 0,893 | −3,02 % | −7,60 % |
| Operating margin change | 28,14 % | 25,43 % | 1,856 | 1,944 | −3,02 % | −5,41 % |
| EBITDA margin change | 28,14 % | 22,14 % | 1,856 | 1,621 | −3,02 % | −6,57 % |
| FCF margin change | 28,14 % | 18,16 % | 1,856 | 0,823 | −3,02 % | −4,12 % |
| Lägre dilution | 27,01 % | 17,01 % | 1,499 | 0,661 | −3,05 % | −8,12 % |

Operating-margin-blenden har något högre Sharpe men sämre primära IC-mått, lägre CAGR och större drawdown. En sekundär portföljdimension får inte övertrumfa den preregistrerade selection-frågan.

## Survivorship

Coverage är hög bland överlevande instrument, 305–330 bolag, men **noll** verifierade terminalinstrument har featurecoverage. Det är den centrala begränsningen, inte en fotnot. Resultaten säger endast att dessa förändringsmått inte förbättrade H0 på den observerbara fundamentalpopulationen; de säger inte hur strategin skulle ha fungerat med komplett avnoterad fundamentahistorik.

## Beslut

- Inkrementellt informationsstöd: **0/5**.
- Svagt stöd: **0/5**.
- Inget stöd: **5/5**.
- Ingen fundamental challenger och ingen ny score skapas.
- Ingen av K3-idéerna rekommenderas för separat forward-preregistrering.

## Artefakter

- `research_k/results/K3_FUNDAMENTAL_CHANGE_DIAGNOSTIC_V1/fundamental_change_results.json`
- separata `rankings`, `holdings`, `trades`, `returns`
- `run_provenance.json`, `manifest.json`

Manifest SHA256: `1129c0b0cb1e5cfb319a7476d1e5c476e821f68998158d09413144d0bfd67030`.

