# G-PROP-1: STOCK-SPECIFIC MOMENTUM PROPENSITY — Resultat och Diagnostik

Datum: 2026-08-18 · **Strikt diagnostiskt informationstest** · **Ingen portföljsimulering eller handelsregel**  
Status: Locked H0, hysteres, G97-P och alla frysta komponenter helt orörda.  
Regel 5 verifierad. K1 Sector Freeze Manifest SHA256: `816cb6b38a2130728bd282e8352c74ccf119f374b8747717c0b0603fa5523041`.

---

## EXECUTIVE SUMMARY & DIAGNOSTISK DOM

| Teststeg / Delhypotes | Slutklassificering | Huvudresultat & Statistisk Evidens |
|---|---|---|
| **A. Inkrementell Propensity-Information (M2 vs M1)** | **NO INCREMENTAL PROPENSITY INFORMATION** | M2 (historisk propensity utöver H0 + vol + $TIS$) misslyckas i 5-fold OOS CV i båda fönstren (Brier delta $-0{,}00018$ 2014–19, $-0{,}00022$ 2020–26). Ett bolags historiska benägenhet att vara i Top-30 tillför **noll inkrementell prediktionskraft**. |
| **B. Kollinearitet & Redundans (Negativ Kontroll)** | **HIGHLY COLLINEAR WITH TIS / H0** | Expanderande PIT-propensity ($\tilde{P}_{\text{propensity\_eb}}$) korrelerar starkt med aktuell $TIS$ ($r = 0{,}598\text{--}0{,}661$) och `run_return` ($r = 0{,}473\text{--}0{,}517$). Måttet mäter i praktiken bara om aktien redan befinner sig i en lång pågående episod. |
| **C. Residualiserad Kvintilanalys** | **NON-MONOTONIC / REVERSAL RISK** | I fönster 2 (2020–2026) har aktier med högst residual propensity (Q5) en **negativ medianavkastning** ($-3{,}31\%$) och högre nedsidesrisk ($28{,}5\%$) än mellan-kvintilerna Q2/Q3 ($20{,}8\%\text{--}21{,}5\%$). |
| **D. Samlad Spårstatus** | **DEFINTIVELY CLOSED** | Spåret `G-PROP-1` stängs definitivt. Hypotesen att bolag besitter en persistent oberoende "momentum-kompatibilitet" som H0 saknar är **empiriskt falsifierad**. |

---

## A. REGEL 5 OCH DEDUPLICERINGSTABELL

Följande tabell sammanfattar tidigare relaterade auditeringar och förklarar varför G-PROP-1 utgjorde en distinkt hypotes:

| Feature / Spår | Vad variabeln mäter | Varför G-PROP-1 var distinkt | Slutgiltigt Utfall |
|---|---|---|---|
| **`G-MEM`** | Återupprepade episoder med krav på $\ge 2$ episoder före $T-20$ | G-PROP-1 använde kontinuerlig expanderande PIT-skattning utan $T-20$-spärr. | **FÖRKASTAD** (Sparsity & noll inkrementellt värde) |
| **`G-PATH-1 / G-PATH-2`** | Egenskaper ($TIS$, `run_return`) hos den *aktuella* pågående episoden | G-PROP-1 mätte endast historik *före* den aktuella panelen $T$. | **FÖRKASTAD** (`run_return` redundant med $TIS$) |
| **`H-ARCHETYPE-1`** | Sektor/K1-bunden svansfördelning | G-PROP-1 undersökte bolagsidentitet och empirisk bayes-shrinkage. | **FÖRKASTAD** (Ingen uppsides-skill) |
| **`H-ORIGIN-1`** | Återhämtning efter ras vs strukturell expansion | G-PROP-1 var oberoende av tidigare drawdown-djup. | **FÖRKASTAD** (Instabil i OOS CV) |
| **`G-PROP-1` (Detta test)** | Exponeringsnormaliserad historisk Top-30-benägenhet ($\tilde{P}_{\text{eb}}$) | Prövar om bolag har en persistent individuell benägenhet att generera momentum. | **NO INCREMENTAL PROPENSITY INFORMATION** |

---

## B. PIT-KONSTRUKTION OCH EXPOSURE-NORMALISERING

För varje ticker $i$ vid beslutspanel $T$ beräknades propensity strikt PIT med data *före* $T$:

$$P_{\text{propensity\_raw}}(i, T) = \frac{N_{\text{top30\_hist}}(i, T)}{\max(1, N_{\text{eligible\_hist}}(i, T))}$$

För att förhindra att unga bolag med få historiska paneler genererade brusiga extrema värden tillämpades en förregistrerad **Empirical Bayes Shrinkage** med populationsprior $\bar{P}_{\text{pop}}(T)$ och krympningsvikt $M = 15$:

$$\tilde{P}_{\text{propensity\_eb}}(i, T) = \frac{N_{\text{top30\_hist}}(i, T) + 15 \cdot \bar{P}_{\text{pop}}(T)}{N_{\text{eligible\_hist}}(i, T) + 15}$$

### Deskriptiv fördelning över Top-30-populationen

| Mått / Variabel | Fönster 1: 2014–2019 | Fönster 2: 2020–2026 |
|---|---:|---:|
| **Giltiga Panelobservationer ($N$)** | 2 368 | 2 189 |
| **Unika Episoder ($N_{\text{episodes}}$)** | 475 | 592 |
| **Unika Tickers ($N_{\text{tickers}}$)** | 194 | 260 |
| **Medelvärde $\tilde{P}_{\text{propensity\_eb}}$** | $23{,}21\%$ | $17{,}93\%$ |
| **Median $\tilde{P}_{\text{propensity\_eb}}$** | $18{,}27\%$ | $13{,}77\%$ |
| **Q10 / Q25 / Q75 / Q90** | $10{,}0\% / 11{,}8\% / 30{,}8\% / 44{,}5\%$ | $9{,}4\% / 11{,}2\% / 21{,}5\% / 33{,}9\%$ |

---

## C. NEGATIV KONTROLL OCH SPEARMAN-KORRELATIONER ($r$)

| Variabelpar | 2014–2019 Korrelation ($r$) | 2020–2026 Korrelation ($r$) | Diagnostisk Slutsats |
|---|---:|---:|---|
| **$\tilde{P}_{\text{propensity\_eb}}$ vs `tis`** | **$+0{,}598$** | **$+0{,}661$** | **Stark kollinearitet med nuvarande episodlängd** |
| **$\tilde{P}_{\text{propensity\_eb}}$ vs `run_return`** | **$+0{,}517$** | **$+0{,}473$** | **Hög korrelation med pågående run-avkastning** |
| **$\tilde{P}_{\text{propensity\_eb}}$ vs `h0_score`** | $+0{,}323$ | $+0{,}293$ | Måttlig korrelation med H0-score |
| **$\tilde{P}_{\text{propensity\_eb}}$ vs `vol_52w`** | $+0{,}290$ | $+0{,}144$ | Svag/måttlig korrelation med volatilitet |
| **$\tilde{P}_{\text{propensity\_eb}}$ vs `n_elig_hist`** | $-0{,}238$ | $-0{,}119$ | Yngre bolag med färre paneler krymps mot prior |
| **$\tilde{P}_{\text{propensity\_eb}}$ vs `r_24w` (Utfall)** | **$+0{,}028$** | **$-0{,}025$** | **Nära noll oberoende samband med framtida avkastning** |

---

## D. PRIMÄR HYPOTESEVALVERING (M0 vs M1 vs M2)

- **M0**: `h0_rank` (Enkel rankkontroll)
- **M1**: `h0_rank` + `vol_52w` + `tis` (Fullständig basmodells-kontroll)
- **M2**: M1 + $\tilde{P}_{\text{propensity\_eb}}$ (Inklusive historisk stock propensity)

### 1. Nedsidesrisk Out-of-Sample CV Brier Score ($P(R_{24w} < -20\%)$)
*5-faldig episod-blockerad korsvalidering. Ett positivt delta innebär att M2 slår basmodellen M1.*

- **2014–2019**: M1 Brier = $0{,}10176$ vs M2 Brier = $0{,}10194$ $\rightarrow$ **Delta = $-0{,}00018$** (M2 sämre än M1).
- **2020–2026**: M1 Brier = $0{,}17862$ vs M2 Brier = $0{,}17884$ $\rightarrow$ **Delta = $-0{,}00022$** (M2 sämre än M1).

### 2. Framtida 24-veckors Avkastning ($R^2$ vinst)
- **2014–2019**: M1 $R^2 = 0{,}30\%$ vs M2 $R^2 = 0{,}54\%$ $\rightarrow$ **$R^2$-vinst = $+0{,}24\%$**.
- **2020–2026**: M1 $R^2 = 0{,}63\%$ vs M2 $R^2 = 0{,}70\%$ $\rightarrow$ **$R^2$-vinst = $+0{,}066\%$**.

---

## E. RESIDUALISERAD KVINTILANALYS (2020–2026)

För att isolera den oberoende effekten av historisk propensity neutraliserades $\tilde{P}_{\text{propensity\_eb}}$ mot basmodellen M1 via linjär regression. Observationerna delades därefter i 5 kvintiler:

| Residualkvintil | Snitt $\tilde{P}_{\text{propensity\_eb}}$ | Median $R_{24w}$ | Snitt $R_{24w}$ | Nedsidesrisk ($R_{24w} < -20\%$) | Uppsideschans ($R_{24w} > +30\%$) | Continuation Rate (Nästa panel) |
|---|---:|---:|---:|---:|---:|---:|
| **Q1 (Lägst propensity)** | $9,40\%$ | $-4,32\%$ | $-2,07\%$ | $27,6\%$ | $11,2\%$ | $70,8\%$ |
| **Q2** | $11,19\%$ | **$+1,85\%$** | $+4,26\%$ | $21,5\%$ | $18,7\%$ | $73,3\%$ |
| **Q3** | $13,77\%$ | **$+1,62\%$** | **$+9,74\%$** | **$20,8\%$** | **$22,4\%$** | $71,6\%$ |
| **Q4** | $21,45\%$ | $+1,07\%$ | $+6,80\%$ | $21,5\%$ | $20,3\%$ | $74,9\%$ |
| **Q5 (Högst propensity)** | $33,86\%$ | **$-3,31\%$** | **$-1,69\%$** | **$28,5\%$** | $13,7\%$ | $74,4\%$ |

### Slutsats från Kvintilanalysen
Det finns **inget monotont eller positivt samband** mellan historisk propensity och framtida avkastning efter kontroll för H0, volatilitet och TIS. Tvärtom drabbas aktierna i Q5 (de med allra högst historisk närvaro i Top-30) av **negativ medianavkastning** och **högst nedsidesrisk ($28,5\%$)**, vilket indikerar en utmattnings- eller reversal-effekt hos aktier som legat i Top-30 under extremt lång samlad historisk tid.

---

## F. SLUTGILTIG KONKLUSION OG SPÅRSTATUS

1. Hypotesen att enskilda bolag har en persistent "momentum-kompatibilitet" eller propensity som tillför inkrementell prediktionskraft utöver låst H0-rank, 52-veckors volatilitet och Time-in-State ($TIS$) **falsifieras av datan**.
2. Variabeln $\tilde{P}_{\text{propensity\_eb}}$ uppvisar stark kollinearitet med $TIS$ och tillför noll out-of-sample prediktionsvinst i 5-faldig CV Brier score i båda testfönstren.
3. **Spåret `G-PROP-1` förklaras HÄRMED STÄNGT.** Samtliga frysta modellkomponenter förblir oförändrade.
