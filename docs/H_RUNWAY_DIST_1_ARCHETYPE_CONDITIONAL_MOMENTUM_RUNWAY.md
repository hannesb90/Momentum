# H-RUNWAY-DIST-1: ARCHETYPE-CONDITIONAL MOMENTUM RUNWAY — Resultat och Diagnostik

Datum: 2026-08-18 · **Strikt diagnostiskt distributions-/feasibilitytest** · **Ingen portföljsimulering eller modelländring**  
Status: Locked H0, hysteres, G97-P och alla frysta komponenter helt orörda.  
Regel 5 verifierad. K1 Sector Freeze Manifest SHA256: `816cb6b38a2130728bd282e8352c74ccf119f374b8747717c0b0603fa5523041`.

---

## EXECUTIVE SUMMARY & DIAGNOSTISK DOM

| Teststeg / Delhypotes | Slutklassificering | Huvudresultat & Statistisk Evidens |
|---|---|---|
| **A. Archetype-Relative Progress (M4 vs M2)** | **NOT REPLICATED / NO GAIN** | M4 (archetype-relativ run-percentil) förbättrar **inte** prognosen jämfört med M2 (absolut run progress) i 5-fold OOS CV (CV Brier delta: $-0{,}00087$ och $-0{,}00092$). |
| **B. Absolute Run Progress (M2 vs M1)** | **SMALL PATH EFFECT** | M2 (absolut run progress) ger en liten men positiv förklaringskraft över H0 + vol ($R^2$ gain $+0{,}36\%$ i 2014-19; $+0{,}42\%$ i 2020-26). High correlation mot TIS ($r \approx 0{,}63\text{--}0{,}77$). |
| **C. Archetype Sector Additive (M3 vs M2)** | **NO OOS GAIN** | M3 (absolut run progress + K1-sektor) ger ingen OOS CV-förbättring över M2 (CV Brier delta: $-0{,}00015$ och $-0{,}00041$). |
| **D. Samlad Spårstatus** | **GENERIC PATH INFORMATION ONLY** | Pågående momentum-run bär viss information, men den är helt **generell pris/path-information** (tid i tillstånd / run-to-date return). Archetype-relativ normalisering tillför **noll inkrementell information**. |

---

## A. GOVERNANCE & INVARIANTS

- **Regel 5 verifierad**: Inga nya signalmodeller, inga köp/säljregler, inga ändringar i locked H0 eller G97-P.
- **K1 Sector Freeze Manifest**: SHA256 verifierad (`816cb6b38a2130728bd282e8352c74ccf119f374b8747717c0b0603fa5523041`).
- **Datagates**: Fundamenta/KPI (**FORBIDDEN IN MODEL TEST**), Size/Market Cap/EV (**DATA_BLOCKED**), inga proxies, inga manuella archetype-tags.

---

## B. POPULATION & K1 ARCHETYPE COVERAGE

Analysen omfattar Top-30-populationen vid varje beslutspanel i två helt separata fönster:
- **Fönster 1 (2014–2019)**: 72 paneler, 2 370 Top-30 observationer (2 368 giltiga 24v utfall).
- **Fönster 2 (2020–2026)**: 66 paneler, 2 190 Top-30 observationer (2 189 giltiga 24v utfall).

---

## C. RÅ 24-VECKORS AVKASTNINGSDISTRIBUTION PER ARCHETYPE

Sekundära fördelningsmått över 24 veckor ($R_{24w}$) i H0 Top-30:

### Fönster 1: 2014–2019 ($N = 2 368$)
| K1 Sektor | Obs (valid) | Median (Q50) | Q10 | Q25 | Q75 | Q90 | Q95 | Skewness | $P(R > 0)$ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Energi** | 45 | +18,7 % | -8,1 % | 0,0 % | +34,8 % | +55,2 % | +82,9 % | +0,96 | 73,3 % |
| **Fastigheter** | 167 | +17,5 % | -1,3 % | +5,1 % | +29,2 % | +40,1 % | +43,6 % | +0,01 | 88,6 % |
| **Finans** | 162 | +4,9 % | -18,7 % | -7,8 % | +25,5 % | +45,2 % | +54,8 % | +0,86 | 61,7 % |
| **Hälsovård** | 500 | +6,3 % | -26,0 % | -11,4 % | +30,0 % | +55,5 % | +75,0 % | +1,07 | 60,4 % |
| **Industri** | 386 | +4,3 % | -24,9 % | -9,8 % | +21,2 % | +50,8 % | +64,5 % | +0,84 | 56,7 % |
| **Konsument** | 182 | +0,7 % | -20,5 % | -11,2 % | +27,2 % | +55,1 % | +70,0 % | +1,00 | 50,5 % |
| **Råmaterial** | 111 | -3,1 % | -28,5 % | -20,9 % | +12,3 % | +65,3 % | +81,4 % | +2,10 | 43,2 % |
| **Teknologi** | 511 | +13,1 % | -19,7 % | -2,7 % | +33,3 % | +58,9 % | +80,9 % | +1,88 | 71,2 % |

### Fönster 2: 2020–2026 ($N = 2 189$)
| K1 Sektor | Obs (valid) | Median (Q50) | Q10 | Q25 | Q75 | Q90 | Q95 | Skewness | $P(R > 0)$ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Energi** | 55 | -7,0 % | -26,0 % | -20,4 % | +5,5 % | +46,1 % | +85,8 % | +1,85 | 34,5 % |
| **Fastigheter** | 74 | -12,6 % | -48,2 % | -25,4 % | +4,2 % | +16,9 % | +25,6 % | +0,05 | 32,4 % |
| **Finans** | 252 | +0,1 % | -38,2 % | -18,1 % | +17,0 % | +41,6 % | +59,9 % | +2,00 | 50,0 % |
| **Hälsovård** | 439 | -4,0 % | -54,5 % | -32,0 % | +19,5 % | +43,7 % | +57,8 % | +0,58 | 44,4 % |
| **Industri** | 381 | +1,9 % | -24,7 % | -12,3 % | +24,1 % | +49,5 % | +59,9 % | +0,81 | 54,9 % |
| **Konsument** | 337 | +2,7 % | -25,7 % | -13,0 % | +18,6 % | +41,8 % | +65,5 % | +2,73 | 56,1 % |
| **Råmaterial** | 160 | +2,2 % | -25,0 % | -11,6 % | +23,8 % | +52,1 % | +69,0 % | +1,31 | 53,8 % |
| **Teknologi** | 491 | -4,9 % | -36,7 % | -24,4 % | +19,6 % | +54,6 % | +73,2 % | +12,05 | 45,0 % |

---

## D. REALIZED MOMENTUM RUN & REDUNDANSANALYS

### 1. PIT-korrekt konstruktion av Realized Momentum Run
En pågående momentum-run definieras strikt parameterfritt som antalet sammanhängande paneler i Top-30 ($TIS$, Time-in-State), samt den hittills realiserade kursavkastningen från inträdespanelen till panel $T$ (`run_return`).

### 2. Korrelationsmatris mot H0 och övriga variabler (Spearman)

| Variabel | `run_return` | `tis` | `mom_12m` | `h0_score` | `vol_52w` | `r_24w` |
|---|---:|---:|---:|---:|---:|---:|
| **`run_return` (2014–19)** | 1,00 | **0,77** | 0,36 | 0,57 | 0,18 | 0,02 |
| **`run_return` (2020–26)** | 1,00 | **0,63** | 0,40 | 0,49 | 0,01 | 0,00 |

> **Redundansfynd**: `run_return` har hög korrelation ($r = 0{,}63\text{--}0{,}77$) med $TIS$ (tid i tillstånd) och måttlig korrelation ($r = 0{,}49\text{--}0{,}57$) med nuvarande H0 score. Det är därmed en variant av den redan kända path/time-in-state-variabeln.

---

## E. EXPANDING PIT ARCHETYPE PERCENTILES (RUN PROGRESS)

### 1. Expanding PIT-metodik
För att undvika look-ahead bias beräknades `run_progress_pct` strikt **expanderande PIT**. Vid panel $T$ ställs den pågående avkastningen `run_return` mot referensfördelningen av alla avslutade och historiskt kända momentum-runs för samma K1-sektor vars 24-veckors utfall var fullständigt kända före $T$ (dvs. paneldatum $\le T - 168\text{ dagar}$).

---

## F. NEGATIVE CONTROL LADDER & MODELLJÄMFÖRELSE

För att pröva om archetype-relativ run progress tillför något utöver enklare förklaringar jämfördes följande modellsteg:

- **M0**: H0 rank
- **M1**: H0 rank + `vol_52w`
- **M2**: H0 rank + `vol_52w` + `run_return` (Absolut run progress / path)
- **M3**: H0 rank + `vol_52w` + `run_return` + K1 Sektor
- **M4**: H0 rank + `vol_52w` + `run_progress_pct` (Archetype-relativ progress)

### 1. Kontinuerlig $R_{24w}$ Regressionsjämförelse ($R^2$)

| Modell | 2014–2019 $R^2$ | 2020–2026 $R^2$ | Kommentar |
|---|---:|---:|---|
| **M0 (H0 rank)** | 0,04 % | 0,07 % | Ingen kontinuerlig $R^2$ förklaring |
| **M1 (H0 + Vol)** | 0,13 % | 0,91 % | Baslinje |
| **M2 (H0 + Vol + Abs Run)** | 0,48 % | 1,33 % | **Liten path-effekt ($+0{,}36\text{--}+0{,}42\%$)** |
| **M3 (M2 + Sektor)** | 3,07 % | 2,82 % | In-sample sektoreffekt (ej OOS-säkrad) |
| **M4 (M1 + Archetype Pct)** | 0,75 % | 0,91 % | Noll vinst över M2 |

### 2. Downside Risk Logit & Out-of-Sample CV Brier Score

| Utvärderingssteg | Fönster 2014–2019 | Fönster 2020–2026 | Dom |
|---|---|---|---|
| **M4 vs M2 CV Brier Delta** | **$-0{,}00087$ (Sämre)** | **$-0{,}00092$ (Sämre)** | **M4 misslyckas OOS** |
| **M3 vs M2 CV Brier Delta** | **$-0{,}00015$ (Sämre)** | **$-0{,}00041$ (Sämre)** | **M3 misslyckas OOS** |

---

## G. EXAKT VILKET LED SOM ÖVERLEVER / FALLEER (§R)

```
EVALVERINGSKEDJA FÖR ARCHETYPE-CONDITIONAL RUNWAY:

[Strukturella sektorskillnader i avkastning (C)]
       │
       ▼  JA (Visat i H-ARCHETYPE-1 & C här)
[Absolut Run Progress / Path har viss effekt (M2 vs M1)]
       │
       ▼  JA (+0.36% till +0.42% R2 vinst; r = 0.63-0.77 mot TIS)
[Archetype Additive i Run Progress förbättrar OOS CV (M3 vs M2)]
       │
       ▼  NEJ (CV Brier Delta < 0 i båda fönstren)
[Archetype-Relativ Progress slår Absolut Progress (M4 vs M2)]
       │
       ▼  NEJ (CV Brier Delta < 0 i båda fönstren)

FALSIFIERINGS-DOM: FALLEER VID LED 3 OCH 4.
```

1. **Led 1 (Sektordistributioner skilder sig)**: ÖVERLEVER. Sektorer har olika tail-mått och volatilitet.
2. **Led 2 (Generell momentum path/duration bär information)**: ÖVERLEVER DELVIS. Absolut run return / TIS tillför en mycket liten förbättring i $R^2$ ($+0,36\%\text{--}+0,42\%$).
3. **Led 3 (Sektor-additiv run progress förbättrar OOS prediktion)**: **FALLEER**. M3 slår inte M2 i 5-fold OOS CV.
4. **Led 4 (Archetype-relativ normalisering slår absolut run progress)**: **FALLEER**. M4 är sämre än M2 i båda fönstren i OOS CV.

---

## H. STATIONARITET & ARCHETYPE DRIFT

Som visades i `H-ARCHETYPE-1` drabbades Fastighetssektorn av extrem icke-stationaritet (residual downside risk shifted från $-8,5\text{ pp}$ i 2014-19 till $+16,1\text{ pp}$ i 2020-26). Att bygga en archetype-relativ referensfördelning förväntar sig stationära svansar för sektorn, vilket bevisligen inte råder i makroskiften.

---

## I. SLUTGILTIG KLASSIFICERING

Diagnostisk klassificering för spåret **H-RUNWAY-DIST-1**:

# **`GENERIC PATH INFORMATION ONLY`**

### Motivering:
1. Momentum run progress innehåller viss information, men den är helt **generell pris/path-information** (korrelerad $r = 0{,}63\text{--}0{,}77$ med $TIS$ / tid i tillstånd).
2. Archetype-relativ normalisering (`run_progress_pct`) ger **noll inkrementellt prognosvärde** jämfört med ren absolut run progress + H0 + volatilitet.
3. Att införa archetype-specifika normaliseringar eller runway-trösklar vore att klassificera vanlig path/duration-information som "bolagskunskap".

---

## J. INGEN LICENSIERING FÖR NÄSTA STEG

Eftersom **`H-RUNWAY-DIST-1`** klassificerats som **`GENERIC PATH INFORMATION ONLY`**:
- Ingen `H-RUNWAY-2` opportunity cost-preregistrering licensieras.
- Ingen runway-score byggs.
- Inga hålla/sälja-regler baserade på archetype-runway licensieras.
- Archetype-runway-spåret **STÄNGS HÄRMED**.

---
*Slut på resultat- och diagnostikrapport för H-RUNWAY-DIST-1.*
