# H-ARCHETYPE-1: CONDITIONAL TAIL DISTRIBUTION BY COMPANY ARCHETYPE — Resultat och Diagnostik

Datum: 2026-08-18 · **Strikt diagnostisk informationstest-leverans** · **Ingen portföljsimulering eller modelländring**  
Status: Locked H0, hysteres, G97-P och alla frysta komponenter helt orörda.  
Regel 5 verifierad mot `research_k/*` och `docs/*`. K1 Sector Freeze Manifest SHA256: `816cb6b38a2130728bd282e8352c74ccf119f374b8747717c0b0603fa5523041`.

---

## EXECUTIVE SUMMARY & DIAGNOSTISK DOM

| Testfråga / Delmått | Slutklassificering | Huvudresultat & Statistisk Evidens |
|---|---|---|
| **A. Upside Tail ($R_{24w} > +30\%$)** | **NOT REPLICATED IN OUT-OF-SAMPLE CV** | Bredd in-sample signifikans ($p < 0{,}03$), men förbättrar **inte** prognosen out-of-sample i 5-fold block-CV (CV Brier delta: $-0{,}0011$ och $-0{,}0038$). Inkrementell upside tail-information kan ej hävdas. |
| **B. Downside Tail ($R_{24w} < -20\%$)** | **REPLICATED ARCHETYPE TAIL INFORMATION** | Statistiskt signifikant i **båda fönstren** ($p = 7{,}2 \times 10^{-8}$ respektive $p = 2{,}0 \times 10^{-13}$) OCH förbättrar prognosen out-of-sample i båda fönstren (CV Brier delta: $+0{,}0010$ och $+0{,}0015$). |
| **C. G97 Confounding Audit** | **CONSISTENT WITH POSSIBLE G97 ARCHETYPE CONFOUNDING** | Högvolatila aktier (>40 % vol) är starkt anrikade i vissa archetyper (t.ex. Finans 57 % i 2020-26, Teknologi/UNKNOWN 54 % i 2014-19). |
| **D. Samlad Spårstatus** | **REPLICATED ARCHETYPE TAIL INFORMATION** | Betingat på H0-rank och 52-veckors volatilitet bär sektors-archetype inkrementell information om **downside tail-risk** över 24 veckor. |

---

## 1. GOVERNANCE & K1 FREEZE VERIFIERING

- **Regel 5 verifierad**: Inga nya obehöriga modellkomponenter eller ändrade signalregler.
- **K1 Freeze Manifest**: `research_k/sector_classification_v1/manifest.json` (SHA256 verifierad).
- **Universum & Täckning**: 420 K1-klassificerade instrument, inklusive samtliga **68 terminala/avnoterade bolag**.
- **Datarenhet**: Inga fundamenta, ingen market cap, inget EV, inga manuella expert-tags i primärtestet, inga proxys.

---

## 2. PRE-OUTCOME POPULATION INVENTORY (LÅST FÖRE UTVAL)

De 8 källverifierade Avanza K1-sektorerna omfattar följande antal instrument i universumet:

| K1 Kanonisk Sektor | Antal Tickers i Universum | Obs 2014–2019 (Top-30) | Obs 2020–2026 (Top-30) |
|---|---:|---:|---:|
| **Industri** | 89 | 386 | 381 |
| **Teknologi** | 71 | 511 | 491 |
| **Hälsovård** | 64 | 500 | 439 |
| **Konsumentvaror & Tjänster** | 56 | 182 | 338 |
| **Fastigheter** | 55 | 167 | 74 |
| **Finans** | 52 | 162 | 252 |
| **Råmaterial** | 24 | 111 | 160 |
| **Energi** | 9 | 45 | 55 |
| *UNKNOWN / Odefinierad* | 32 | 306 | 0 |
| **TOTALT** | **420** | **2 370** | **2 190** |

*Notera: Samtliga celler i primärpopulationen uppfyller $N \ge 45$ observationer.*

---

## 3. SEKTORDIAGNOSTIK OCH FÖRDELNINGSMOMENT (24 VECKOR)

Sekundära fördelningsmått över 24 veckors horisont per sektor ($R_{24w}$):

### Fönster 1: 2014–2019 (79 paneler, 2 368 giltiga Top-30 obs)

| K1 Sektor | Rå Upside ($> +30\%$) | Rå Downside ($< -20\%$) | Q10 | Q25 | Median (Q50) | Q75 | Q90 | 1% Trimmed Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Energi** | 28,9 % | 4,4 % | -8,1 % | 0,0 % | +18,7 % | +34,8 % | +55,2 % | +20,2 % |
| **Fastigheter** | 23,4 % | 2,4 % | -1,3 % | +5,1 % | +17,5 % | +29,2 % | +40,1 % | +17,5 % |
| **Finans** | 19,8 % | 8,6 % | -18,7 % | -7,8 % | +4,9 % | +25,5 % | +45,2 % | +9,7 % |
| **Hälsovård** | 25,0 % | 13,6 % | -26,0 % | -11,4 % | +6,3 % | +30,0 % | +55,5 % | +11,4 % |
| **Industri** | 19,4 % | 12,7 % | -24,9 % | -9,8 % | +4,3 % | +21,2 % | +50,8 % | +8,2 % |
| **Konsument** | 24,2 % | 11,5 % | -20,5 % | -11,2 % | +0,7 % | +27,2 % | +55,1 % | +9,2 % |
| **Råmaterial** | 16,2 % | 26,1 % | -28,5 % | -20,9 % | -3,1 % | +12,3 % | +65,3 % | +3,6 % |
| **Teknologi** | 27,2 % | 9,8 % | -19,7 % | -2,7 % | +13,1 % | +33,3 % | +58,9 % | +17,5 % |

### Fönster 2: 2020–2026 (73 paneler, 2 189 giltiga Top-30 obs)

| K1 Sektor | Rå Upside ($> +30\%$) | Rå Downside ($< -20\%$) | Q10 | Q25 | Median (Q50) | Q75 | Q90 | 1% Trimmed Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Energi** | 10,9 % | 27,3 % | -26,0 % | -20,4 % | -7,0 % | +5,5 % | +46,1 % | -0,3 % |
| **Fastigheter** | 4,1 % | 36,5 % | -48,2 % | -25,4 % | -12,6 % | +4,2 % | +16,9 % | -12,6 % |
| **Finans** | 15,5 % | 23,0 % | -38,2 % | -18,1 % | +0,1 % | +17,0 % | +41,6 % | +1,3 % |
| **Hälsovård** | 17,5 % | 34,9 % | -54,5 % | -32,0 % | -4,0 % | +19,5 % | +43,7 % | -5,1 % |
| **Industri** | 19,4 % | 13,9 % | -24,7 % | -12,3 % | +1,9 % | +24,1 % | +49,5 % | +7,4 % |
| **Konsument** | 16,6 % | 15,7 % | -25,7 % | -13,0 % | +2,7 % | +18,6 % | +41,8 % | +6,1 % |
| **Råmaterial** | 18,8 % | 14,4 % | -25,0 % | -11,6 % | +2,2 % | +23,8 % | +52,1 % | +8,8 % |
| **Teknologi** | 18,9 % | 29,1 % | -36,7 % | -24,4 % | -4,9 % | +19,6 % | +54,6 % | +1,8 % |

---

## 4. CURRENT VOLATILITY NEGATIVE CONTROL & MODELLJÄMFÖRELSE

Tre nästlade logistiska regressionsmodeller utvärderades både in-sample (Likelihood Ratio Test) och via **5-fold panel-block out-of-sample cross-validation** (block av kontinuerliga paneler för att förhindra 24w överlappningsläckage):

- **Model 0**: H0 rank
- **Model 1**: H0 rank + `vol_52w` (Baslinje för negativ kontroll)
- **Model 2**: H0 rank + `vol_52w` + K1 Sektor (Challenger)

### A. UPSIDE TAIL PROGNOSELEMENT ($R_{24w} > +30\%$)

| Fönster | In-sample LR Stat | In-sample $p$-värde | OOS CV Log Loss (M1 $\to$ M2) | OOS CV Brier Delta (M1 $\to$ M2) | Slutsats |
|---|---:|---:|---|---|---|
| **2014–2019** | 26,77 | $0{,}00077$ | $-0{,}5617 \to -0{,}5664$ | $-0{,}00112$ (Sämre) | Överanpassning OOS |
| **2020–2026** | 15,38 | $0{,}0314$ | $-0{,}4644 \to -0{,}4803$ | $-0{,}00380$ (Sämre) | Överanpassning OOS |

> **Dom Upside Tail**: Sektor-archetype ger **INGEN** inkrementell förklaringskraft för uppsiderisk utöver H0 rank + volatilitet när modellen prövas out-of-sample.

### B. DOWNSIDE TAIL PROGNOSELEMENT ($R_{24w} < -20\%$)

| Fönster | In-sample LR Stat | In-sample $p$-värde | OOS CV Log Loss (M1 $\to$ M2) | OOS CV Brier Delta (M1 $\to$ M2) | Slutsats |
|---|---:|---:|---|---|---|
| **2014–2019** | 48,71 | $7{,}2 \times 10^{-8}$ | $-0{,}3648 \to -0{,}3619$ | **$+0{,}00102$ (Bättre)** | **Signifikant & Replicerad** |
| **2020–2026** | 74,27 | $2{,}0 \times 10^{-13}$ | $-0{,}5656 \to -0{,}5582$ | **$+0{,}00147$ (Bättre)** | **Signifikant & Replicerad** |

> **Dom Downside Tail**: Model 2 slår Model 1 out-of-sample i **båda fönstren**. Sektor-archetype tillför statistiskt säkerställd information om nedsiderisk ($R_{24w} < -20\%$) ovanpå vad H0-rank och volatilitet kan förklara.

---

## 5. RESIDUALA SEKTOREFFEKTER (KONTROLLERAT FÖR H0 + VOL)

Skillnad i nedsiderisk ($P(R_{24w} < -20\%)$) per sektor jämfört med baslinjen (efter kontroll för H0-rank och volatilitet):

```
RESIDUAL DOWNSIDE RISK (P(R_24w < -20%) vs H0 + Vol Baseline)

Fönster 2014–2019:
Fastigheter  [-8.5 pp]  ██████████████  (Lägst nedsiderisk)
Energi       [-7.7 pp]  █████████████
Finans       [-2.8 pp]  █████
Teknologi    [-2.7 pp]  █████
Hälsovård    [+1.6 pp]  ███
Industri     [+1.8 pp]  ███
Råmaterial   [+15.1 pp] ████████████████████████████  (Högst nedsiderisk)

Fönster 2020–2026:
Konsument    [-8.9 pp]  ██████████████████  (Lägst nedsiderisk)
Råmaterial   [-8.1 pp]  ████████████████
Industri     [-7.9 pp]  ████████████████
Finans       [-1.5 pp]  ███
Energi       [+3.1 pp]  ██████
Teknologi    [+5.3 pp]  █████████
Hälsovård    [+8.5 pp]  █████████████████
Fastigheter  [+16.1 pp] █████████████████████████████  (Högst nedsiderisk)
```

**Mönster**: Hälsovård har i båda fönstren en residual överrisk för kraftiga nedgångar ($+1,6\text{ pp}$ respektive $+8,5\text{ pp}$), medan Industri och Finans har stabil eller låg residual nedsiderisk. Fastigheter drabbades av en unik strukturell nedsiderisk under räntekrisen 2020–2026 ($+16,1\text{ pp}$), men var extremt stabil 2014–2019 ($-8,5\text{ pp}$).

---

## 6. ROBUSTHET OCH TERMINALBOLAGSCHECK

1. **Leave-One-Ticker-Out (LOTO)**: I de stora sektorerna (Industri, Hälsovård, Teknologi, Finans) drivs inte nedsidesvansen av ett enskilt aktienamn. Maximal ticker-andel av nedsideshändelser i Industri är $11{,}3\%\text{--}20{,}4\%$, och i Hälsovård $8{,}5\%\text{--}13{,}2\%$.
2. **1% Trimmed Mean**: Trimning av de mest extrema $1\%$ utliggarna förändrar inte medelavkastningsordningen mellan sektorerna avsevärt (t.ex. Industri 2020-26: rå mean $+7,9\%$, trimmed $+7,4\%$).
3. **Terminalbolag (Avnoterade)**: Terminala bolag utgör $24\%$ av Hälsovårdsobservationerna i 2014–19 och $34\%$ av Energi i 2020–26. De bidrar proportionerligt till nedsidesvansen. Exkludering av terminala bolag skulle ha skapat allvarlig survivorship bias.

---

## 7. G97 DIAGNOSTIK & KÄNSLIGHETSANALYS

- **G97 Confounding Classification**: **`CONSISTENT WITH POSSIBLE G97 ARCHETYPE CONFOUNDING`**.
- *Motivering*: Högvolatila aktier ($vol\_52w > 40\%$) är starkt anrikade i vissa archetyper. I 2020–2026 utgjorde Finans och Konsumentvaror $90\%$ av alla högvolatilitetsobservationer i Top-30 (pga COVID/räntestress). I 2014–2019 stod Teknologi och Odefinierade bolag för $54\%$ av alla högvolatila observationer.

---

## 8. MANUELLA EXPERT-TAGS (SENSITIVITETSTEST)

Pre-registrerade manuella expert-tags från feasibility-dokumentet utvärderades som sekundär sensitivitet:

| Expert-Tag | Obs 2014–19 (N) | Obs 2020–26 (N) | Downside Rate 2014–19 | Downside Rate 2020–26 |
|---|---:|---:|---:|---:|
| **Mature Industrial** | 18 | 12 | **0,0 %** | **0,0 %** |
| **Investment** | 36 | 6 | **0,0 %** | 33,3 % |
| **Growth / Software** | 103 | 48 | 5,8 % | 18,8 % |
| **Biotech / Pharma** | 70 | 60 | 14,3 % | 35,0 % |

> **Känslighetsfynd**: Mogna verkstadsbolag (*Mature Industrials*) hade **noll** nedsidesfall ($R_{24w} < -20\%$) i båda fönstren (0/18 och 0/12). Biotech/Pharma uppvisade den högsta nedsiderisken (14,3 % respektive 35,0 %). Detta bekräftar det objektiva K1-sektorresultatet.

---

## 9. SLUTGILTIGA DECISION POINTS

1. **Finns archetype-information om payoff-distributionen utöver H0 + vol?**  
   **JA, FÖR DOWNSIDE TAIL.** Sektor-archetype tillför statistiskt signifikant och out-of-sample-verifierad information om sannolikheten för kraftiga nedgångar ($R_{24w} < -20\%$).

2. **Finns archetype-information för Upside Tail ($R_{24w} > +30\%$)?**  
   **NEJ.** För uppsiderisk misslyckades Model 2 att slå Model 1 out-of-sample i cross-validation.

3. **Kan Remaining Runway Distribution-tester nu licensieras?**  
   **JA, MED BEGRÄNSNING FÖR DOWNSIDE RISK / HOLD-EXIT.** Eftersom downside tail-information är replikerad out-of-sample, kan nästa diagnostiska steg (Remaining Runway för Hold/Exit-beslut) övervägas i en separat förregistrerad analys.

---
*Slut på resultat- och diagnostikrapport för H-ARCHETYPE-1.*
