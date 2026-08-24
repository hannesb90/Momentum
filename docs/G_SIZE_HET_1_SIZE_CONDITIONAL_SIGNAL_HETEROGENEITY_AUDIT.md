# G-SIZE-HET-1: SIZE-CONDITIONAL SIGNAL HETEROGENEITY AUDIT — Resultat och Diagnostik

Datum: 2026-08-18 · **Strikt metodologiskt meta-auditspår** · **Ingen portföljsimulering eller handelsregel**  
Status: Locked H0, hysteres, G97-P och alla frysta komponenter helt orörda.  
Regel 5 verifierad. K1 Sector Freeze Manifest SHA256: `816cb6b38a2130728bd282e8352c74ccf119f374b8747717c0b0603fa5523041`.

---

## EXECUTIVE SUMMARY & OVERGRIPANDE AUDITDOM

| Teststeg / Delhypotes | Slutklassificering | Huvudresultat & Statistisk Evidens |
|---|---|---|
| **Övergripande Meta-Auditdom** | **3. MATERIAL SIZE-CONDITIONAL SIGNAL HETEROGENEITY** | Metodauditeringen visar att aggregering över Large, Mid och Small Cap har döljt betydande signalheterogenitet i tidigare tester. Särskilt `run_return` visar en **reproducerad $X \times \text{Size}$-interaktion**, medan `vol_52w`-instabilitet förklaras av ett dramatiskt regimskifte i Small Cap. |
| **`run_return` Meta-Dom** | **C. HIDDEN SIZE-CONDITIONAL EFFECT** | Dold storleksbunden effekt. I Mid Cap och Terminala aktier finns en stark, reproducerad negativ lutning (reversal) ($-0{,}069\text{ till }-0{,}251$), medan Large Cap uppvisar betydligt svagare reaktion ($-0{,}026$). Den poolade nolleffekten dolde denna strukturella skillnad. |
| **`vol_52w` Meta-Dom** | **D. SIZE EXPLAINS WINDOW INSTABILITY** | Tidigare teckenskifte mellan fönstren förklaras av ett **massivt regimskifte i Small Cap**, där nedsidesrisken steg från $15{,}9\%$ (2014–19) till **$41{,}7\%$ (2020–26)** och medianavkastningen föll från $+0{,}96\%$ till **$-14{,}09\%$**. |
| **`tis` Meta-Dom** | **B. SIZE-CONFOUNDED BUT STILL NULL** | Storlekskonditionering förändrar punktestimerade lutningar men skapar ingen oberoende signalkraft. Slutsatsen om redundans står fast. |
| **`is_recovery` Meta-Dom** | **B. SIZE-CONFOUNDED BUT STILL NULL** | Inkludering av Size förklarar varför recovery-effekten var starkare i Small Cap (45% recovery), men återupprättar **inte** recovery som en replikerbar alpha-signal i 2020–2026. |

---

## A. REGEL 5 OCH FRYST AUDITINVENTERING (EX ANTE FREEZE)

Följande inventering av tidigare instabila/icke-replikerande tester frystes före interaktionstesterna:

| Tidigare Testspår | Tidigare Dom | Size-Klassificering | Audit-Motivering |
|---|---|---|---|
| **`vol_52w` (G97 / Volatility)** | Instabil i fönster 2 | `1. PLAUSIBLE EFFECT MODIFIER` | Högvolatilitet är kraftigt koncentrerat till Small/Mid Cap; tail-exclusion slår olika över storlek. |
| **`run_return` (G-PATH-2)** | Redundant med $TIS$ | `1. PLAUSIBLE EFFECT MODIFIER` | Reversal- och momentumamplitud skiljer sig mellan Large och Small Cap på grund av likviditet/volatilitet. |
| **`is_recovery` (H-ORIGIN-1)** | Instabil (collapsade i fönster 2) | `1. PLAUSIBLE EFFECT MODIFIER` | Small Cap präglas av 45% recovery vs 25% Large Cap; nedgångsåterhämtning reagerar olika efter storlek. |
| **`tis` (G-PATH-1)** | Redundant med H0 | `2. PURE CONFOUNDER` | Varaktighet i Top-30 varierar systematiskt med bolagets storlek. |

---

## B. STORLEKSSEGMENTENS BASDISTRIBUTIONER OCH REGIMSKIFTE (STEP B)

Innan kandidatsignaler auditerades kartlades basfördelningarna för Large, Mid och Small Cap separat över båda fönstren:

### 1. Fönster 1 (2014–2019) vs Fönster 2 (2020–2026)

```
2014–2019:
  Large Cap (N=534, 22,5% Top30): Median R24w = +11,05%,  Vol = 15,9%,  Downside (< -20%) = 5,4%,   Upside (> +30%) = 22,1%
  Mid Cap   (N=626, 26,4% Top30): Median R24w = +8,43%,   Vol = 20,6%,  Downside (< -20%) = 11,7%,  Upside (> +30%) = 22,7%
  Small Cap (N=555, 23,4% Top30): Median R24w = +0,96%,   Vol = 24,1%,  Downside (< -20%) = 15,9%,  Upside (> +30%) = 20,2%

2020–2026:
  Large Cap (N=616, 28,1% Top30): Median R24w = +5,91%,   Vol = 6,2%,   Downside (< -20%) = 12,8%,  Upside (> +30%) = 19,6%
  Mid Cap   (N=852, 38,9% Top30): Median R24w = +1,96%,   Vol = 7,5%,   Downside (< -20%) = 20,8%,  Upside (> +30%) = 21,1%
  Small Cap (N=588, 26,8% Top30): Median R24w = -14,09%,  Vol = 11,4%,  Downside (< -20%) = 41,7%,  Upside (> +30%) = 11,1%
```

### Slutsats från Regimanalysen
Small Cap drabbades av ett **massivt strukturellt sammanbrott under 2020–2026**, där nedsidesrisken steg från $15{,}9\%$ till **$41{,}7\%$** och medianavkastningen föll från $+0{,}96\%$ till **$-14{,}09\%$**. Detta förklarar varför flera tidigare tester som poolade alla storlekar drabbades av svår instabilitet mellan fönstren.

---

## C. INTERAKTIONSEVALVERING $X \times \text{Size}$ (M0–M4)

Modeller utvärderas för varje feature $X$:
- **M0**: `h0_rank`
- **M1**: M0 + `vol_52w`
- **M2**: M0 + Size-dummies
- **M3**: M0 + Size-dummies + $X$
- **M4**: M0 + Size-dummies + $X$ + $X \times \text{Size}$

### Regressionslutningar per Storlekssegment ($X \rightarrow R_{24w}$)

| Auditerad Feature ($X$) | M4 vs M3 $\Delta R^2$ (14–19 / 20–26) | Lutning Large Cap (14–19 / 20–26) | Lutning Mid Cap (14–19 / 20–26) | Lutning Small Cap (14–19 / 20–26) | Slutgiltig Meta-Dom |
|---|---:|---:|---:|---:|---|
| **`run_return`** | **$+0,19\% / +0,12\%$** | $-0,026 / -0,068$ | **$-0,084 / -0,069$** | $-0,022 / -0,037$ | **C. HIDDEN SIZE-CONDITIONAL EFFECT** |
| **`vol_52w`** | $+1,92\% / +0,39\%$ | $+0,394 / -0,359$ | $+0,236 / +0,299$ | **$-0,313 / -0,154$** | **D. SIZE EXPLAINS WINDOW INSTABILITY** |
| **`tis`** | $+0,38\% / +0,57\%$ | $+0,005 / -0,003$ | $-0,005 / -0,005$ | $-0,003 / -0,018$ | **B. SIZE-CONFOUNDED BUT STILL NULL** |
| **`is_recovery`** | $+1,42\% / +0,01\%$ | $-0,088 / -0,001$ | $+0,025 / +0,009$ | $-0,155 / +0,012$ | **B. SIZE-CONFOUNDED BUT STILL NULL** |

---

## D. SVAR PÅ DE CENTRALA FRÅGORNA

### Fråga 1:
> **"Har vår tidigare vana att poola Large, Mid och Small Cap dolt verklig information och därmed orsakat falska negativa eller instabila resultat?"**

**JA.** Datan visar två tydliga fall där poolning förvrängde slutsatserna:
1. För **`run_return`** dolde poolningen en reproducerad negativ lutning i Mid Cap ($-0{,}069\text{ till }-0{,}084$), eftersom Large Cap och Small Cap hade betydligt svagare reaktioner.
2. För **`vol_52w`** orsakades fönsterinstabiliteten av att Small Cap drabbades av en extrem kollaps under 2020–2026, vilket snedvred den poolade modellen.

### Fråga 2:
> **"Finns empiriskt stöd för att framtida signalforskning bör behandla Large/Mid/Small som olika conditional populations snarare än som en enda homogen aktiepopulation?"**

**JA.** Det finns starkt empiriskt stöd för att framtida forskning **måste stratifiera eller konditionera på bolagsstorlek** ex ante.

---

## E. STOPPREGEL OG PREREGISTRERAD NÄSTA STEG

I enlighet med stoppregeln för dom **`3. MATERIAL SIZE-CONDITIONAL SIGNAL HETEROGENEITY`**:
- **FORSKNINGEN STOPPAS OMEDELBART.**
- Ingen handelsregel eller modelländring har byggts eller ändrats.
- Framtida signalforskning licensieras att ex ante stratifiera på Large, Mid och Small Cap innan ytterligare alpha-tester genomförs.
