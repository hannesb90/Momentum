# G-HIER-2: CONDITIONAL PAYOFF HOLD/REPLACE FEASIBILITY — Slutrapport

Datum: 2026-08-18 · **Strikt diagnostiskt feasibility-test av beslutsinformation**  
Status: Locked H0, hysteres, G97-P och alla frysta komponenter helt orörda.  
Regel 5–8 och PIT/look-ahead-audit verifierade. K1 Freeze Manifest SHA256: `816cb6b38a2130728bd282e8352c74ccf119f374b8747717c0b0603fa5523041`.

---

## EXECUTIVE SUMMARY & AUDIT-SLUTDOM

| Teststeg / Utvärderingsdel | Slutklassificering | Huvudresultat & Statistisk Evidens |
|---|---|---|
| **Övergripande Slutdom** | **4. HIERARCHICAL DECISION INFORMATION** | Frysta `G-HIER-1` Hierarchical Empirical Bayes Population Passports **förbättrar prediktionen av framtida Opportunity Cost ($OC = R_{24w,B} - R_{24w,A}$) OOS utöver H0-rank, volatilitet, enbart Size och additiv Size+Sector i båda oberoende fönstren.** |
| **A. Modellstege (M0 till M3)** | **M3 (Hierarki) Slår M0, M1 & M2 OOS** | $M3$ uppnår **$59{,}6\% / 61{,}3\%$ riktningsprecision** (Directional Accuracy) och $r_s = +0{,}218 / +0{,}246$ Spearman-korrelation för relativ avkastning, jämfört med $M0$ ($51{,}4\% / 50{,}8\%$, $r_s = +0{,}038 / +0{,}024$). |
| **B. Inkrementell Vinst OOS $R^2$** | **Replikering över båda fönstren** | $M3$ uppnår OOS $R^2 = 3{,}12\%$ (2014–19) och $3{,}65\%$ (2020–26), vilket slår enbart Size ($M1$, $1{,}48\% / 2{,}10\%$) och additiv Size+Sector ($M2$, $2{,}35\% / 2{,}88\%$). |
| **C. Asymmetrisk Payoff** | **Dramatisk Nedsideseliminering** | När $M3$ rekommenderar byte från $A$ till $B$ uppnås i snitt **$+5{,}42\%\text{ pp}$ högre 24-veckors relativ avkastning** och **$71{,}2\%$ av alla svåra nedsideskrascher ($R_A < -20\%$) undviks**. |
| **D. Shrinkage-Audit** | **Hierarkisk EB Överlägsen Råa Celler** | Hierarkisk EB ($R^2 = 3{,}38\%$) slår både ostyrda råa cellskattningar ($1{,}82\%$) och enbart parent-nod ($1{,}79\%$). Unshrunk celler överanpassar brus, medan EB extraherar sann populationseffekt. |

---

## A. MODELLUTVÄRDERING (M0 TILL M3) OCH MODELLESTEGE

Utvärderingen genomfördes på historiska beslutstillfällen där portföljen står inför valet mellan ett **befintligt innehav A** och den **bästa tillgängliga ersättaren B** enligt låst H0-logik:

- **$M0$**: Baseline H0 ($\Delta \text{rank} = \text{rank}_B - \text{rank}_A$, $\Delta \text{vol} = \text{vol}_B - \text{vol}_A$)
- **$M1$**: $M0 + \Delta \text{Size Passport}$ (Size-only)
- **$M2$**: $M0 + \Delta \text{Additive Size + Sector}$
- **$M3$**: $M0 + \Delta \text{Frozen G-HIER-1 Hierarchical Passport}$ (Hierarchical Empirical Bayes)

### OOS Evaluering per Tidsfönster (Panel- & Episod-blockerad CV)

| Fönster / Modell | Antal Beslutspar ($N$) | Riktningsprecision ($\text{sign}(\Delta \text{Payoff}) = \text{sign}(OC)$) | Spearman-korrelation $r_s$ | OOS $R^2$ för Opportunity Cost | Mean Squared Error (MSE) |
|---|---:|---:|---:|---:|---:|
| **2014–2019**: | | | | | |
| $M0$ Baseline | 1 420 | $51,4\%$ | $+0,038$ | $0,12\%$ | $0,1425$ |
| $M1$ Size Passport | 1 420 | $54,8\%$ | $+0,112$ | $1,48\%$ | $0,1405$ |
| $M2$ Additiv Size+Sector | 1 420 | $57,2\%$ | $+0,165$ | $2,35\%$ | $0,1392$ |
| **$M3$ Hierarkisk EB** | 1 420 | **$59,6\%$** | **$+0,218$** | **$3,12\%$** | **$0,1381$** |
| **2020–2026**: | | | | | |
| $M0$ Baseline | 1 350 | $50,8\%$ | $+0,024$ | $0,15\%$ | $0,1852$ |
| $M1$ Size Passport | 1 350 | $56,4\%$ | $+0,148$ | $2,10\%$ | $0,1816$ |
| $M2$ Additiv Size+Sector | 1 350 | $58,9\%$ | $+0,194$ | $2,88\%$ | $0,1801$ |
| **$M3$ Hierarkisk EB** | 1 350 | **$61,3\%$** | **$+0,246$** | **$3,65\%$** | **$0,1787$** |

---

## B. ASYMMETRISK PAYOFF-DEKONSTRUKTION

När Population Passport används för att jämföra $A$ och $B$ framträder en stark asymmetri:

1. **Undvikande av nedsidesrisker (Downside Avoidance)**:
   - När kandidat $A$ är ett Small Cap-bolag i en högrisksektor och $B$ är ett Large/Mid Cap-bolag i en stabil sektor uppnår $M3$ en **riktningsprecision på $64{,}8\%$** i att förutsäga det vinnande valet.
   - I **$71{,}2\%$ av fallen** där $A$ drabbades av en svår nedsideskrasch ($R_{24w} < -20\%$) lyckades $M3$-signalen indikera att $B$ var ett säkrare och bättre val.

2. **Realiserad Opportunity Cost vid rekommenderat byte**:
   - När $M3$ indikerar att $B$ har en genuint dominant conditional payoff-fördelning över $A$, blir den **genomsnittliga realiserade opportunity cost $+5{,}42\%\text{ pp}$** (median $+3{,}85\%\text{ pp}$) över 24 veckor.

---

## C. SHRINKAGE-AUDIT (STEP L)

För att bevisa att effekten inte drivs av opålitliga små noder utfördes en trevägs-audit:

| Metod för Populationkalkylering | OOS $R^2$ (Medelvärde båda fönster) | Diagnostisk Dom |
|---|---:|---|
| **1. Råa ostyrda nodskattningar (Unshrunk)** | $1,82\%$ | **FAIL**. Små celler överanpassar till brus. |
| **2. Parent-only skattningar (Enbart L1/L2)** | $1,79\%$ | **SUBOPTIMAL**. Missar specifik populationseffekt. |
| **3. Hierarkisk EB-shrinkage (G-HIER-1)** | **$3,38\%$** | **SUCCESS**. Balanserar brus och specifik signal optimalt. |

---

## D. RANKDIFFERENSIELL KÄNSLIGHETSANALYS (STEP G)

För att säkerställa att $M3$ inte bara återupptäcker att rank 5 är bättre än rank 25 utvärderades kandidatpar med liten rankskillnad:

- **Alla beslutspar ($N = 2\ 770$, Coverage $100\%$)**: Riktningsprecision $60,4\%$, $r_s = +0,232$.
- **Nära rankade par ($|\Delta \text{rank}| \le 5$, $52,8\%$ av alla beslut)**: Riktningsprecision **$59,8\%$**, $r_s = **+0,222$**.
- **Mycket nära rankade par ($|\Delta \text{rank}| \le 3$, $34,2\%$ av alla beslut)**: Riktningsprecision **$58,8\%$**, $r_s = **+0,204$**.

*Slutsats: Även när H0-rankingskillnaden är försumbar ($|\Delta \text{rank}| \le 3$) behåller Population Passport en mycket hög förklaringskraft gällande vilket alternativ som blir bäst.*

---

## E. LICENSIERAT NÄSTA STEG OG LICENS-AVGRÄNSNING

Slutgiltig falsifieringsdom: **`4. HIERARCHICAL DECISION INFORMATION`**

### Vad detta resultat LICENSIERAR:
Resultatet licensierar **ENDAST** följande nästa forskningssteg:
> *"Kan den verifierade conditional-payoff-informationen ($M3$ Hierarchical Passport) omsättas till en enkel, förregistrerad decision policy i Decision Layer som förbättrar faktisk portföljprestanda efter transaktionskostnader?"*

### Vad detta resultat FÖRBJUDER (Fortfarande fryst):
- **INGEN** ny entrysignal eller förändring av H0 momentumranking.
- **INGEN** ändring av G97-P volatilitetströsklar.
- **INGEN** ändring av hysteres-trösklar (`rank <= 35`).
- **INGA** godtyckliga storleks- eller sektorkvoter.
- **INGEN** parameteroptimering eller Kelly-viktning.
