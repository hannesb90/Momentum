# H-ORIGIN-1: MOMENTUM ORIGIN — RECOVERY VS EXPANSION PAYOFF — Resultat och Diagnostik

Datum: 2026-08-18 · **Strikt diagnostiskt informationstest** · **Ingen portföljsimulering eller handelsregel**  
Status: Locked H0, hysteres, G97-P och alla frysta komponenter helt orörda.  
Regel 5 verifierad. K1 Sector Freeze Manifest SHA256: `816cb6b38a2130728bd282e8352c74ccf119f374b8747717c0b0603fa5523041`.

---

## EXECUTIVE SUMMARY & DIAGNOSTISK DOM

| Teststeg / Delhypotes | Slutklassificering | Huvudresultat & Statistisk Evidens |
|---|---|---|
| **A. Inkrementell Origin-Information (M2 vs M1)** | **NOT REPLICATED IN OOS CV** | M2 (Momentum Origin: RECOVERY vs EXPANSION) ger en OOS CV-förbättring i 2014–2019 (Brier delta $+0{,}00209$, $R^2$-vinst $+0{,}69\%$), men **kollapsar helt i 2020–2026** (Brier delta $-0{,}00042$, $R^2$-vinst $+0{,}0000\%$). |
| **B. Negativ Kontroll & Redundans (M1 vs M0)** | **PATH CONTROL SUBSUMES ORIGIN** | Då H0-rank, `vol_52w` och generell path (`run_return` / $TIS$) beaktats har uppgångens ursprung (RECOVERY vs EXPANSION) **ingen stabil inkrementell förklaringskraft** över 24 veckors horisont. |
| **C. Episod-/Klusteranalys** | **EPISODE-LEVEL VERIFIED** | Observationerna driver från 475 unika episoder (194 bolag) i 2014–19 och 592 unika episoder (260 bolag) i 2020–26. Medianlängden är 2 paneler ($4\text{ veckor}$). Koncentrationen till topp-5 bolag är låg ($< 9,7\%$). |
| **D. Samlad Spårstatus** | **PROMISING-BUT-UNSTABLE MOMENTUM-ORIGIN INFORMATION** | Hypotesen om att momentumets ursprung (återhämtning efter ras vs ren expansion) tillför oberoende information över H0 + vol + path **falleer på replikationskravet**. Spåret stängs utan handelsregler. |

---

## A. DEDUPLICERINGSREVISION & TIDIGARE TESTER

Följande relaterade variabler och hypoteser har tidigare auditerats i projektet:
1. **Kortsiktig reversal / överextension**: Feature #44 (`ret_4w_rel`). Auditerad i G-PATH-1 och G97. Förkastad som signalmodifierare.
2. **Drawdown / Pullback**: Feature #36 (`max_drawdown_52w`), #66 (`pullback_ratio`). Auditerad i G-PATH-1 och H-ARCHETYPE-1.
3. **Trend age & Time-in-State ($TIS$)**: Feature #64 (`trend_age_weeks`), $TIS$ i G-PATH-1. Visat ha stark korrelation ($r = 0{,}63\text{--}0{,}77$) med pågående run-avkastning (`run_return`).
4. **Archetype-relativ runway**: Auditerades i **`H-RUNWAY-DIST-1`** och klassificerades som **`GENERIC PATH INFORMATION ONLY`**. Archetype-relativ normalisering tillförde noll utöver M2 (`run_return` + H0 + vol).
5. **Momentum Origin (Detta test)**: Testar om huruvida den pågående momentum-episoden inleddes efter ett större kursfall ($\ge 30\%$ ras från tidigare 2-årstopp) vs en obrutning expansion tillför inkrementell information **utöver M1** (H0 + vol + `run_return`). Detta är ett nytt och icke-tidigare utfört strukturellt informationstest.

---

## B. ANALYSENHET: CONTINUOUS EPISODES / RUNS

Överlappande panelobservationer har samlats i sammanhängande oavbrutna Top-30-episoder (State-S runs) för att undvika överdriven statistisk inferens från beroende panel-N.

| Parameter / Mått | Fönster 1: 2014–2019 | Fönster 2: 2020–2026 | Totalt / Samlat |
|---|---:|---:|---:|
| **Giltiga Panelobs ($N$)** | 2 368 | 2 189 | 4 557 |
| **Unika Episoder ($N_{\text{episodes}}$)** | 475 | 592 | 1 067 |
| **Unika Tickers ($N_{\text{tickers}}$)** | 194 | 260 | 368 |
| **Episoder per Ticker** | 2,45 | 2,28 | 2,90 |
| **Median Episodlängd (Paneler / Veckor)** | 2 paneler (4 v) | 2 paneler (4 v) | 2 paneler (4 v) |
| **Topp-5 Ticker Koncentration (% av obs)** | 9,63 % | 8,09 % | 8,86 % |

### Episodfördelning per Listkategori
- **2014–2019**: Large Cap 138, Mid Cap 109, Small Cap 92, Terminala 59, Övriga 77 episoder.
- **2020–2026**: Large Cap 181, Mid Cap 222, Small Cap 145, Terminala 44 episoder.

---

## C. PIT-KORREKT DEFINITION AV MOMENTUM ORIGIN

Strikt PIT vid paneldatum $T$ med historik $\le T$:
- **`RECOVERY`**: Startkursen för 1-årseffekten ($P(T-52\text{w})$) låg $\ge 30\%$ under sin högsta kurs under föregående 2-årsperiod ($[T-156\text{w}, T-52\text{w}]$). Aktien återtar tidigare förlorad mark.
- **`EXPANSION`**: Startkursen låg $< 30\%$ från sin tidigare 2-årstopp (mindre skadad historisk bana). Aktien bryter upp i ny expansion utan föregående ras.

---

## D. NEGATIV KONTROLLBASE & PRE-CHECK

Fördelning av kontrollvariabler mellan `RECOVERY` och `EXPANSION` vid beslutstillfället $T$:

| Kontrollvariabel | 2014–2019 RECOVERY | 2014–2019 EXPANSION | 2020–2026 RECOVERY | 2020–2026 EXPANSION |
|---|---:|---:|---:|---:|
| **Antal Panelobs ($N$)** | 334 (14,1 %) | 2 034 (85,9 %) | 946 (43,2 %) | 1 243 (56,8 %) |
| **Medel H0-rank (1..30)** | 14,5 | 15,7 | 14,6 | 16,2 |
| **Medel Volatilitet (`vol_52w`)** | 1,92 * | 0,19 | 0,10 | 0,07 |
| **Medel Run Return (`run_return`)** | +24,1 % | +49,6 % | +16,3 % | +39,7 % |
| **Medel Tid i Tillstånd ($TIS$)** | 3,9 paneler | 6,9 paneler | 3,6 paneler | 5,8 paneler |

*\*Not: I 2014-19 innehåller RECOVERY-gruppen ett fåtal extremt höga vol-värden bland terminala/avnoterade aktier, vilket beaktats via rank- och logit-kontroller.*

> **Slutsats från Pre-Check**: EXPANSION-aktier har i genomsnitt längre varaktighet i Top-30 ($TIS$) och högre hittillsvarande run-avkastning (`run_return`), medan RECOVERY-aktier har högre volatilitet. Detta understryker varför kontroll för `vol_52w` och `run_return` (M1) är helt nödvändig innan någon origin-effekt kan hävdas.

---

## E. FRAMTIDA AVKASTNINGSDISTRIBUTION (24 VECKOR)

Ojusterade 24-veckors utfallsfördelningar ($R_{24w}$) för Top-30 observationer:

### Fönster 1: 2014–2019
- **RECOVERY ($N = 334$)**: Median $+0,46\%$, Q10 $-36,6\%$, Q25 $-19,4\%$, Q75 $+21,6\%$, Q90 $+47,5\%$.  
  $P(R_{24w} > +30\%) = 17,4\%$, $P(R_{24w} < -20\%) = 23,7\%$.
- **EXPANSION ($N = 2 034$)**: Median $+8,35\%$, Q10 $-19,7\%$, Q25 $-6,8\%$, Q75 $+27,9\%$, Q90 $+50,2\%$.  
  $P(R_{24w} > +30\%) = 23,1\%$, $P(R_{24w} < -20\%) = 9,6\%$.

### Fönster 2: 2020–2026
- **RECOVERY ($N = 946$)**: Median $-0,92\%$, Q10 $-40,4\%$, Q25 $-20,2\%$, Q75 $+20,1\%$, Q90 $+45,6\%$.  
  $P(R_{24w} > +30\%) = 17,5\%$, $P(R_{24w} < -20\%) = 25,3\%$.
- **EXPANSION ($N = 1 243$)**: Median $+0,00\%$, Q10 $-33,9\%$, Q25 $-18,3\%$, Q75 $+18,9\%$, Q90 $+45,7\%$.  
  $P(R_{24w} > +30\%) = 17,1\%$, $P(R_{24w} < -20\%) = 23,0\%$.

---

## F. MODELLSTADIEJÄMFÖRELSE & OOS CV BRIER SCORE

Vi jämför tre förklaringssteg:
- **M0**: H0 rank + `vol_52w`
- **M1**: M0 + `run_return` (Generell path)
- **M2**: M1 + `is_recovery_30` (Momentum Origin)

### 1. In-Sample Regressionsförklaring ($R^2$ för kontinuerlig $R_{24w}$)

| Modellsteg | Fönster 2014–2019 $R^2$ | Fönster 2020–2026 $R^2$ | $R^2$-vinst M2 vs M1 |
|---|---:|---:|---:|
| **M0 (H0 + Vol)** | 0,30 % | 0,36 % | — |
| **M1 (M0 + Path)** | 0,59 % | 0,89 % | $+0,29\%\text{--}+0,53\%$ |
| **M2 (M1 + Origin)** | **1,28 %** | **0,89 %** | **+0,69 % (2014-19) vs +0,0000 % (2020-26)** |

### 2. Episod-Block Out-of-Sample CV Brier Score (Nedsiderisk $R_{24w} < -20\%$)

| Utvärderingsmått | Fönster 2014–2019 | Fönster 2020–2026 | Dom per fönster |
|---|---:|---:|---|
| **M0 CV Brier Score** | 0,10175 | 0,17941 | Baslinje |
| **M1 CV Brier Score** | 0,10173 | 0,17795 | Förbättring över M0 |
| **M2 CV Brier Score** | **0,09964** | **0,17837** | **Förbättring i 2014-19; SÄMRE i 2020-26** |
| **M2 vs M1 Brier Delta** | **$+0{,}00209$ (Positiv)** | **$-0{,}00042$ (Negativ)** | **EJ REPLIKERAD** |

---

## G. REPLIKATIONSUTVÄRDERING & REKLASSIFICERING

```
REPLIKATIONS-CHECKLISTA FÖR MOMENTUM ORIGIN:

[1. Har M2 positiv in-sample effekt i båda fönstren?]
       ├─► 2014–2019: JA (+0.69% R2 vinst)
       └─► 2020–2026: NEJ (+0.0000% R2 vinst) ───► FALLEER

[2. Förbättrar M2 prognosen OOS i 5-fold episode-block CV?]
       ├─► 2014–2019: JA (Brier Delta +0.00209)
       └─► 2020–2026: NEJ (Brier Delta -0.00042) ───► FALLEER

[3. Överlever effekten efter kontroll för rank + vol + path (M1)?]
       └─► NEJ: I 2020–2026 förklaras avkastningsskillnaden helt av H0+vol+path.

SLUTLIG DOM: PROMISING-BUT-UNSTABLE MOMENTUM-ORIGIN INFORMATION
```

---

## H. KÄNSLIGHETSANALYS FÖR RECOVERY-DEFINITION

Även när tröskeln för recovery ändrades till $\ge 40\%$ ras (`is_recovery_40`) eller $\ge 50\%$ ras (`is_recovery_50`) förblev mönstret detsamma: M2 gav en liten in-sample vinst i 2014–2019 men **noll eller negativ OOS CV-vinst i 2020–2026**. Resultatet väljs inte post-hoc.

---

## I. SEKUNDÄRA FRÅGOR (LISTSEGMENT OCH REGIM)

Eftersom huvudeffekten M2 vs M1 **misslyckades på replikationskravet** (falleerade i fönster 2), aktiveras **inga sekundära tester** för segment-interaktioner (Large/Mid/Small × recovery) som självständig prognosfaktor. 

Skillnaden i återhämtningsandel mellan fönstren ($25,0\%$ 2014–19 vs $43,2\%$ 2020–26) visar att återhämtningsavtrycket är **regimberoende**. I stället för att införa godtyckliga regim-gates registreras effekten strikt som instabil.

---

## J. SLUTGILTIG KLASSIFICERING

# **`PROMISING-BUT-UNSTABLE MOMENTUM-ORIGIN INFORMATION`**

### Exakt Motivering:
1. Givet aktuell H0-rank, 52-veckors volatilitet och generell path-information (`run_return` / $TIS$) tillför momentumets ursprung (RECOVERY vs EXPANSION) en mätbar OOS-förbättring under fönstret 2014–2019.
2. Denna effekt **kollapsar helt och hållet under fönstret 2020–2026**, där M2 inte uppvisar någon inkrementell förklaringskraft ($R^2$ gain $= +0{,}0000\%$) och presterar sämre än M1 i out-of-sample block-CV.
3. Effekten uppfyller inte kraven för en replikerad signalmodifikator och kan därmed inte hävdas som en stabil egenskapsdimension utöver H0 + vol + generell prisbana.

---

## K. SPÅRSTÄNGNING & DIREKTIV

1. **Ingen handelsregel eller score-ändring**: Ingen exit-regel, company score, rankingförstärkning eller portföljsimulering licensieras.
2. **H0, G97-P och hysteres förblir låsta**: Inga komponenter muteras.
3. **Spåret stängs härmed**: Spåret *MOMENTUM ORIGIN / RECOVERY VS EXPANSION* är fullständigt utfört, levererat och stängt.

---
*Slut på resultat- och diagnostikrapport för H-ORIGIN-1.*
