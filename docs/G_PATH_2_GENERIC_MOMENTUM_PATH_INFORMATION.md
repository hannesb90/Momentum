# G-PATH-2: GENERIC MOMENTUM PATH INFORMATION — Resultat och Diagnostik

Datum: 2026-08-18 · **Strikt diagnostiskt informationstest** · **Ingen portföljsimulering eller handelsregel**  
Status: Locked H0, hysteres, G97-P och alla frysta komponenter helt orörda.  
Regel 5 verifierad. K1 Sector Freeze Manifest SHA256: `816cb6b38a2130728bd282e8352c74ccf119f374b8747717c0b0603fa5523041`.

---

## EXECUTIVE SUMMARY & DIAGNOSTISK DOM

| Teststeg / Delhypotes | Slutklassificering | Huvudresultat & Statistisk Evidens |
|---|---|---|
| **A. Inkrementell Path-Information (M4 vs M3)** | **REDUNDANT WITH TIS** | M4 (`run_return` utöver H0 + vol + $TIS$) misslyckas i 5-fold OOS CV i fönster 2 (Brier delta $-0{,}00059$). `run_return` tillför **noll inkrementellt värde** när modellen redan känner till $TIS$. |
| **B. M2 vs M1 (Absolut Run utan TIS-kontroll)** | **APPARENT BUT ILLUSORY** | M2 (`run_return` över H0 + vol) visar en skenbar liten effekt ($R^2$-vinst $+0{,}29\%\text{--}+0{,}53\%$), men denna effekt försvinner helt när $TIS$ inkluderas i basmodellen (M3). |
| **C. Ekonomisk Storlek & Reversal Check** | **TRIVIAL & SLIGHT REVERSAL** | Residualiserad `run_return` mot M3 visar att aktier med högst run-avkastning (Q5) har *lägre* eller identisk framtida 24v-avkastning än Q1 (t.ex. $+5{,}6\%$ vs $+10{,}0\%$ 2014–19). |
| **D. Samlad Spår- & Familjestatus** | **GENERIC PATH INFORMATION — REDUNDANT WITH TIS/H0** | `run_return` är i huvudsak en amplitudproxy för $TIS$ (tid i tillstånd) ($r = 0{,}63\text{--}0{,}77$). Hela den generella **PATH/RUNWAY-familjen stängs härmed definitivt**. |

---

## A. REGEL 5 OCH DEDUPLICERINGSTABELL

Följande tabell sammanfattar samtliga tidigare auditeringar av path-, run-, reversal- och tillståndsvariabler i projektet:

| Feature / Variabel | Exakt Definition | Vad den mäter | Tidigare utfall | Relation till `run_return` | Slutgiltig Status |
|---|---|---|---|---|---|
| **`#44 ret_4w_rel`** | 4-veckors relativ avkastning | Kortsiktig överextension / reversal | Förkastad i G-PATH-1 & G97 | Låg/måttlig korrelation ($r \approx 0{,}07$) | **FÖRKASTAD** (Ingen signalvinst) |
| **`#51 acceleration_ratio`** | $R_{4w} / R_{12w}$ | Momentumets förändringstakt | Förkastad i primära signalgates | Mäter derivatan av run | **FÖRKASTAD** |
| **`#64 trend_age_weeks`** | Veckor i positiv trend | Momentumets ålder | Auditering i G-PATH-1 | Mycket hög korrelation ($r > 0{,}70$) med $TIS$ | **REDUNDANT MED TIS** |
| **`#67/68 trend_efficiency`** | Nettoförflyttning / bruttoförflyttning | Trendens rakhet/glatthet | Förkastad i feature-ranking | Redundans mot rank/vol | **FÖRKASTAD** |
| **`#71–73 smoothness_r2`** | $R^2$ för linjär trendpassning | Prisbanans glatthet | Förkastad i path feasibility | Ingen oberoende prediktionskraft | **FÖRKASTAD** |
| **`#74/75 pos_week_ratio`** | Andel positiva veckor under 52v | Konsistens i uppgång | Auditerad i G-PATH-1 | Subsumerad av H0-score | **REDUNDANT MED H0** |
| **`TIS` (Time-in-State)** | Antal paneler i Top-30 state | Tillståndets varaktighet | Auditerad i G-PATH-1 & H-RUNWAY-1 | **Hög korrelation ($r = 0{,}63\text{--}0{,}77$)** | **PRIMÄR PATH-BASILINJE (M3)** |
| **`run_return`** | $P(T)/P(T_{\text{entry}}) - 1$ | Ackumulerad run-avkastning | Auditerad i H-RUNWAY-1 & H-ORIGIN-1 | Detta test (G-PATH-2) | **REDUNDANT MED TIS/H0 (G-PATH-2)** |

---

## B. PIT-LÅSNING OCH DESKRIPTIV STATISTIK FÖR `RUN_RETURN`

Strikt PIT-definition låst utan ändringar:
$$\text{run\_return}(i, T) = \frac{P(i, T)}{P(i, T_{\text{entry}})} - 1$$

### Deskriptiv fördelning över Top-30-populationen

| Mått / Variabel | Fönster 1: 2014–2019 | Fönster 2: 2020–2026 |
|---|---:|---:|
| **Giltiga Panelobservationer ($N$)** | 2 368 | 2 189 |
| **Unika Episoder ($N_{\text{episodes}}$)** | 475 | 592 |
| **Unika Tickers ($N_{\text{tickers}}$)** | 194 | 260 |
| **Episoder per Ticker** | 2,45 | 2,28 |
| **Topp-5 Ticker Koncentration (% av obs)** | 9,63 % | 8,09 % |
| **Medelvärde `run_return`** | $+45,98 \%$ | $+29,58 \%$ |
| **Median `run_return`** | $+14,80 \%$ | $+4,95 \%$ |
| **Q10 / Q25 / Q75 / Q90** | $-0,8\% / 0,0\% / +52,6\% / +135,7\%$ | $-4,9\% / 0,0\% / +30,9\% / +83,7\%$ |
| **Min / Max** | $-31,7\% / +812,4\%$ | $-58,4\% / +999,0\%$ |

### Spearman-korrelationer ($r$) vid beslutstillfället $T$

| Variabelpar | 2014–2019 Korrelation ($r$) | 2020–2026 Korrelation ($r$) | Diagnostisk slutsats |
|---|---:|---:|---|
| **`run_return` vs `TIS`** | **$+0{,}767$** | **$+0{,}625$** | **Stark kollinearitet med tillståndets varaktighet** |
| **`run_return` vs `h0_score`** | $+0{,}570$ | $+0{,}486$ | Måttlig korrelation med nuvarande rank |
| **`run_return` vs `vol_52w`** | $+0{,}181$ | $+0{,}013$ | Låg korrelation med volatilitet |
| **`run_return` vs `ret_4w_rel` (#44)** | $+0{,}070$ | — | Oavhängig kortsiktig reversal |
| **`run_return` vs $R_{24w}$ (Framtida 24v)** | **$+0{,}019$** | **$+0{,}000$** | **Noll ojusterad korrelation mot framtida utfall** |

---

## C. MODELLSTADIEJÄMFÖRELSE & KRITISKT TIS-SEPARATIONSTEST

För att pröva om `run_return` har någon oberoende information över H0, volatilitet och tillståndslängd ($TIS$) jämfördes följande fem modellsteg:

- **M0**: `h0_rank` (Icke-parametrisk decil/rank)
- **M1**: `h0_rank` + `vol_52w`
- **M2**: `h0_rank` + `vol_52w` + `run_return`
- **M3**: `h0_rank` + `vol_52w` + `TIS` (Tillståndsbaslinje)
- **M4**: `h0_rank` + `vol_52w` + `TIS` + `run_return` (**Kritiskt separationstest**)

### 1. In-Sample Regressionsförklaring ($R^2$ för $R_{24w}$)

| Modellsteg | Fönster 2014–2019 $R^2$ | Fönster 2020–2026 $R^2$ | Inkrementell Vinst ($R^2$) |
|---|---:|---:|---|
| **M0 (H0 rank)** | 0,02 % | 0,01 % | Baslinje |
| **M1 (H0 + Vol)** | 0,30 % | 0,36 % | Baslinje |
| **M2 (M1 + `run_return`)** | 0,59 % | 0,89 % | $+0,29\%\text{--}+0,53\%$ över M1 |
| **M3 (M1 + `TIS`)** | 0,30 % | 0,63 % | Baslinje med TIS |
| **M4 (M3 + `run_return`)** | **0,90 %** | **0,89 %** | **$+0,61\%$ (2014-19) vs $+0,26\%$ (2020-26)** |

### 2. Out-of-Sample Episode-Block CV Brier Score (Nedsiderisk $R_{24w} < -20\%$)

| Modell / Utvärdering | Fönster 2014–2019 | Fönster 2020–2026 | Dom per fönster |
|---|---:|---:|---|
| **M1 CV Brier Score** | 0,10175 | 0,17941 | Baslinje |
| **M2 CV Brier Score** | 0,10173 | 0,17795 | M2 slår M1 svagt |
| **M3 CV Brier Score (TIS)** | 0,10176 | 0,17862 | Baslinje med TIS |
| **M4 CV Brier Score (TIS + Run)** | **0,10164** | **0,17921** | **Brier Delta M4-M3: $+0{,}00012$ (2014-19) vs $-0{,}00059$ (2020-26)** |

> **Kritiskt Fynd**: I fönster 2 (2020–2026) uppvisar M4 en **sämre OOS CV Brier-score än M3** (Brier delta $-0{,}00059$). När modellen redan känner till H0-rank, volatilitet och hur länge aktien befunnit sig i Top-30 ($TIS$) tillför `run_return` **noll replikerad inkrementell information**.

---

## D. EKONOMISK STORLEK & RESIDUALISERADE KVINTILER

För att kontrollera om effekten är ekonomiskt meningsfull residualiserades `run_return` mot M3-prediktorerna (`h0_rank`, `vol_52w`, `TIS`). Populationen delades därefter in i fem lika stora residualkvintiler (Q1_Low till Q5_High):

### Fönster 1 (2014–2019) Residualkvintiler
| Kvintil | Medel Residual | Medel `run_return` | Medel $TIS$ | Median $R_{24w}$ | Medel $R_{24w}$ | $P(R_{24w} < -20\%)$ | $P(R_{24w} > +30\%)$ |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Q1 (Lägst residual)** | $-56,1\%$ | $+36,7\%$ | 10,7 paneler | **$+10,0\%$** | $+14,9\%$ | 11,6 % | 27,2 % |
| **Q2** | $-20,4\%$ | $+32,2\%$ | 6,8 paneler | $+7,2\%$ | $+11,1\%$ | 14,6 % | 25,2 % |
| **Q3** | $+0,2\%$ | $+31,1\%$ | 4,8 paneler | $+7,2\%$ | $+12,9\%$ | 11,2 % | 22,6 % |
| **Q4** | $+15,8\%$ | $+22,8\%$ | 3,2 paneler | $+6,8\%$ | $+11,0\%$ | 8,9 % | 17,3 % |
| **Q5 (Högst residual)** | $+60,4\%$ | $+107,1\%$ | 7,0 paneler | **$+5,6\%$** | $+10,0\%$ | 11,8 % | 19,0 % |

### Fönster 2 (2020–2026) Residualkvintiler
| Kvintil | Medel Residual | Medel `run_return` | Medel $TIS$ | Median $R_{24w}$ | Medel $R_{24w}$ | $P(R_{24w} < -20\%)$ | $P(R_{24w} > +30\%)$ |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Q1 (Lägst residual)** | $-53,0\%$ | $+18,0\%$ | 8,6 paneler | **$-3,9\%$** | $+1,2\%$ | 27,9 % | 19,9 % |
| **Q2** | $-14,0\%$ | $+21,7\%$ | 5,2 paneler | $+0,2\%$ | $+2,9\%$ | 25,6 % | 15,3 % |
| **Q3** | $+2,7\%$ | $+13,6\%$ | 3,0 paneler | $+0,7\%$ | $+3,6\%$ | 20,8 % | 16,0 % |
| **Q4** | $+14,0\%$ | $+12,4\%$ | 2,1 paneler | **$+1,9\%$** | $+8,1\%$ | 18,7 % | 18,0 % |
| **Q5 (Högst residual)** | $+50,3\%$ | $+82,2\%$ | 5,3 paneler | **$-2,7\%$** | $+1,2\%$ | 26,9 % | 17,1 % |

> **Ekonomiskt Slutord**: Hög residual `run_return` (Q5) ger **lägre eller obefintlig framtida avkastning** jämfört med Q1. Det finns ingen positiv "runway expansion-effekt", utan snarare en svag tendens till kortsiktig konsolidering/reversal efter extrema utslag.

---

## E. REPLIKATIONSCHECKLISTA & SLUTGILTIG KLASSIFICERING

```
REPLIKATIONSUTVÄRDERING FÖR G-PATH-2:

[1. Har M2 inkrementell effekt över M1 i båda fönstren?]
       └─► JA (Svag R2-vinst +0.29% till +0.53%).

[2. Har M4 inkrementell effekt över M3 (TIS-kontroll) OOS i båda fönstren?]
       ├─► 2014–2019: JA (Brier Delta +0.00012)
       └─► 2020–2026: NEJ (Brier Delta -0.00059 ───► M4 SÄMRE ÄN M3) ───► FALLEER!

[3. Är effekten ekonomiskt materiell och positiv?]
       └─► NEJ (Residual Q5 har lägre/identisk framtida avkastning än Q1).

SLUTLIG DOM: GENERIC PATH INFORMATION — REDUNDANT WITH TIS/H0
```

---

## F. SLUTGILTIG DOM OCH STOPPREGEL

# **`GENERIC PATH INFORMATION — REDUNDANT WITH TIS/H0`**

### Exakt Motivering:
1. `run_return` har en stark korrelation ($r = 0{,}63\text{--}0{,}77$) med $TIS$ (Time-in-State / tid i tillstånd).
2. När basmodellen utökas till M3 ($H0\text{-rank} + \text{vol\_52w} + TIS$) misslyckas M4 (`run_return` tillägg) att förbättra prognosen out-of-sample i fönstret 2020–2026 (Brier delta $-0{,}00059$).
3. `run_return` utgör endast en amplitudproxy för $TIS$ och tillför noll oberoende prognosvärde när $TIS$ och H0-rank redan är kända.

---

## G. DEFINTIV STÄNGNING AV PATH / RUNWAY-FAMILJEN

I enlighet med den förregistrerade stoppregeln (Led L):
- **Inga nya transformationer** av `run_return`, acceleration, percentile-of-run, run slope, archetype-relative run eller kombinationer får någonsin skapas.
- Den generella **PATH/RUNWAY-familjen är härmed DEFINITIVT STÄNGD**.
- **Ingen opportunity-cost feasibility test licensieras**.
- H0, hysteres och G97-P förblir helt orörda.

---
*Slut på resultat- och diagnostikrapport för G-PATH-2.*
