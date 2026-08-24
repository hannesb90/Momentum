# Spår J1B — ATR/ADX legacy-replikation på V2

Status: **SLUTFÖRD OCH FRYST**  
Run ID: `SPARJ_J1B_ATR_ADX_V1`  
Ingen parametersearch: ja  
H0/H1/H2 ändrade: nej  
Ny challenger: nej

## Preregistrerad design

Tre familjer låstes före resultatgranskning:

1. `atr_normalized_risk`: 14 veckors Wilder-ATR dividerad med justerad veckostängning; lägre risk rankas högre. Solo samt fast 50/50 rankblend med H0.
2. `adx_trend_strength`: standardiserad osignerad Wilder-ADX med 14 veckor; högre trendstyrka rankas högre. Solo samt fast 50/50 rankblend med H0.
3. `atr_trailing_stop`: separat risk/holding-test med 10 veckors enkelt TR-medel och fast legacy-default 2,5× ATR under högsta avslut sedan köp. Veckovis trigger efter stängning, exekvering första observerade close strikt efter trigger och kontant till nästa frysta 8v-rebalans.

Ingen annan period, multipel, kombination eller TA-feature testades.

## Referens H0

| Mått | H0 |
|---|---:|
| Mean IC52 | 0,1555 |
| Median IC52 | 0,1658 |
| Top-30 IC52 | −0,0250 |
| Positiva IC-datum | 100 % |
| Netto-CAGR | 25,29 % |
| Excess-Sharpe | 1,379 |
| MaxDD | −4,43 % |
| Leave-top-3 CAGR | 14,65 % |
| Leave-top-5 CAGR | 10,56 % |

## ATR-normaliserad risk

### Solo

Mean IC52 0,1836, median IC52 0,1942, Top-30 IC52 +0,1518 och positiva IC-datum 100 %. Däremot blev netto-CAGR 15,23 %, Sharpe 0,529 och MaxDD −6,72 %.

### Fast 50/50 blend med H0

| Mått | H0 | ATR-blend |
|---|---:|---:|
| Mean IC52 | 0,1555 | 0,2030 |
| Median IC52 | 0,1658 | 0,2072 |
| Top-30 IC52 | −0,0250 | +0,0969 |
| Positiva IC-datum | 100 % | 100 % |
| Netto-CAGR | 25,29 % | 18,05 % |
| Excess-Sharpe | 1,379 | 0,892 |
| MaxDD | −4,43 % | −6,34 % |
| Leave-top-3 CAGR | 14,65 % | 14,55 % |
| Leave-top-5 CAGR | 10,56 % | 12,54 % |

Klassificering: **SVAGT STÖD**. Tvärsnittssignalen är tydligt positiv men den fulla låsta stödregeln missas eftersom leave-top-3 försämras marginellt och portföljegenskaperna försämras materiellt. Ingen challenger skapas.

## ADX / trendstyrka

ADX solo är svag och periodinstabil: mean IC52 0,0361, Top-30 IC −0,0176 och endast 55 % positiva IC-datum. Mean IC är −0,0369 under 2025.

Den fasta blenden ger Top-30 IC +0,0115, netto-CAGR 25,57 %, Sharpe 1,409 och MaxDD −3,52 %, men total mean IC faller till 0,1132 och median IC till 0,1011.

Klassificering: **SVAGT STÖD**. Förbättrad topp-rankning och historiska portföljmått väger inte upp försämrad total IC och tidsstabilitet. Ingen challenger skapas.

## ATR trailing-stop

Stopregeln ändrade aldrig H0:s schemalagda ranking eller selection. Den utlöste 55 exits.

| Mått | H0 | ATR-stop |
|---|---:|---:|
| Netto-CAGR | 25,29 % | 25,65 % |
| Excess CAGR | 15,21 % | 15,58 % |
| Excess-Sharpe | 1,379 | 1,450 |
| MaxDD | −4,43 % | −3,59 % |
| Mean turnover | 0,196 | 0,291 |
| Leave-top-3 CAGR | 14,65 % | 15,33 % |
| Leave-top-5 CAGR | 10,56 % | 11,16 % |

Klassificering: **SVAGT STÖD**. Resultatet är positivt i flera dimensioner, men MaxDD förbättras med 0,84 procentenheter och når därmed inte den preregistrerade gränsen 1,0 procentenhet för `STÖD — RISK`. Omsättningen och kostnaden ökar dessutom. Ingen separat forward-challenger skapas.

## Integritet och korrigering under körning

En första stopkörning tappade sista OOS-perioden genom att nästa gräns hämtades ur OOS-listan. Den bevaras separat som `SPARJ_J1B_ATR_ADX_V1_INVALID_MISSING_FINAL_BOUNDARY` och är uttryckligen ogiltig. Den godkända körningen använder den frysta globala nästa-panelgränsen och benchmark-CAGR matchar H0 exakt, 10,07 %.

Regressionstester verifierar fasta parametrar, kausal featurekonstruktion och att target inte förekommer i besluts-/indikatorfunktionerna. Protected-scope-audit omfattar 308 filer och visar noll förändringar i A–I/H0/H1/H2.

## Stopp

J1B är avslutad. MFN- och FI-arbetet har inte startats i detta steg, i enlighet med den föreskrivna ordningen.
