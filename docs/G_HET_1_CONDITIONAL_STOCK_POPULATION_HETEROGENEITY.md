# G-HET-1: CONDITIONAL STOCK POPULATION HETEROGENEITY — Resultat och Diagnostik

Datum: 2026-08-18 · **Strikt diagnostiskt informationstest** · **Ingen portföljsimulering eller handelsregel**  
Status: Locked H0, hysteres, G97-P och alla frysta komponenter helt orörda.  
Regel 5 verifierad. K1 Sector Freeze Manifest SHA256: `816cb6b38a2130728bd282e8352c74ccf119f374b8747717c0b0603fa5523041`.

---

## EXECUTIVE SUMMARY & DIAGNOSTISK DOM

| Teststeg / Delhypotes | Slutklassificering | Huvudresultat & Statistisk Evidens |
|---|---|---|
| **A. Inkrementell Payoff-Information (M2/M3/M4 vs M1)** | **3. PAYOFF HETEROGENEITY** | M2 (K1-sektor) och M3 (listsegment) ger en **reproducerad inkrementell $R^2$-vinst** i förutsägelsen av framtida avkastning ($R_{24w}$) utöver H0-rank och volatilitet i båda fönstren ($+2{,}22\%$ 2014–19, $+1{,}38\%$ 2020–26). M4 (sektor + listsegment) förklarar $+2{,}80\%\text{--}+3{,}03\%$ av variansen. |
| **B. Nedsidesrisk (Downside Tail $P(R_{24w} < -20\%)$)** | **STRONG SIZE REGIME HETEROGENEITY** | Small Cap drabbas av extremt förhöjd nedsidesrisk jämfört med Large Cap i båda fönstren ($15{,}9\%$ vs $5{,}4\%$ 2014–19; $41{,}7\%$ vs $12{,}8\%$ 2020–26). M3 (listsegment) förbättrar OOS CV Brier score med $+0{,}00849$ under 2020–26. |
| **C. Heterogenitetsantagandet i H0** | **HOMOGENEITY NULL REJECTED** | H0-modellens antagande att alla Top-30-kandidater dras ur samma framtida payoff-fördelning är **empiriskt felaktigt**. Ett Large Cap-industribolag och ett Small Cap-techbolag med identisk H0-rank har drastiskt olika förväntade utfallsfördelningar. |
| **D. Samlad Spårstatus** | **FEASIBILITY LICENSED FOR HOLD/REPLACE ONLY** | Spåret bekräftar Payoff Heterogeneity. **Ingen handelsregel byggs**. Licensierar endast EN separat preregistrerbar feasibility-fråga om huruvida H0 kan behålla sin momentumranking men använda conditional payoff distributions för framtida hold/replace-beslut. |

---

## A. REGEL 5 OCH DEDUPLICERINGSTABELL

Följande tabell visar relationen mellan G-HET-1 och tidigare genomförda auditeringar:

| Spår / Feature | Vad hypotesen prövade | Varför G-HET-1 är distinkt | Slutgiltigt Utfall |
|---|---|---|---|
| **`H-ARCHETYPE-1`** | Prövade om sektor förbättrar prediktion av absolut $+30\%$ uppsida | G-HET-1 prövar *hela fördelningen* (location, dispersion, downside, quantiles, listsegment). | **REPLICATED DOWNSIDE & PAYOFF HET** |
| **`G-PROP-1`** | Prövade om historisk bolagsspecifik Top-30-närvaro gav alpha | G-HET-1 prövar tvärsnittsliga strukturella attribut (K1-sektor & listsegment). | **STÄNGT** (Redundant med $TIS$) |
| **`G-PATH-1/2`** | Prövade egenskaper hos den *pågående* momentumepisoden | G-HET-1 mäter statiska strukturella egenskaper givet H0-rank + vol. | **STÄNGT** (Redundant med $TIS$) |
| **`G-HET-1` (Detta test)** | **Tvörsnittslig strukturell heterogenitet (Sektor & Listsegment)** | **Prövar om H0 gör ett modellfel genom att anta homogenitet i Top-30.** | **3. PAYOFF HETEROGENEITY** |

---

## B. POPULATION OCH OBSERVASIONSTÄCKNING

Primär population utgörs av samtliga PIT-korrekta Top-30-kandidater från låst H0:

| Tidsfönster | Totalt Antal Observationer ($N$) | Unika Tickers ($N_{\text{tickers}}$) | Unika Episoder ($N_{\text{episodes}}$) |
|---|---:|---:|---:|
| **Fönster 1 (2014–2019)** | 2 370 | 194 | 475 |
| **Fönster 2 (2020–2026)** | 2 190 | 260 | 592 |

### Fördelning per Listsegment och K1-Sektor

```
2014–2019:
  Large Cap:  534 obs (52 tickers)  |  Hälsovård: 500 obs (27 tickers)  |  Industri: 386 obs (34 tickers)
  Mid Cap:    626 obs (42 tickers)  |  Teknologi: 511 obs (30 tickers)  |  Konsument: 182 obs (18 tickers)
  Small Cap:  555 obs (43 tickers)  |  Fastigheter: 167 obs (17 tickers)|  Finans: 162 obs (17 tickers)
  Terminal:   349 obs (25 tickers)  |  Råmaterial: 111 obs (14 tickers) |  Energi: 45 obs (5 tickers)

2020–2026:
  Large Cap:  616 obs (81 tickers)  |  Hälsovård: 439 obs (48 tickers)  |  Industri: 381 obs (53 tickers)
  Mid Cap:    852 obs (82 tickers)  |  Teknologi: 491 obs (50 tickers)  |  Konsument: 338 obs (34 tickers)
  Small Cap:  588 obs (73 tickers)  |  Finans: 252 obs (32 tickers)     |  Råmaterial: 160 obs (16 tickers)
  Terminal:   134 obs (24 tickers)  |  Fastigheter: 74 obs (19 tickers)  |  Energi: 55 obs (8 tickers)
```

---

## C. RÅA UTFALLSFÖRDELNINGAR (24 VECKORS AVKASTNING $R_{24w}$)

### 1. Uppdelning per Listsegment (2020–2026)

| Listsegment | $N$ obs | Snitt $R_{24w}$ | Median $R_{24w}$ | Std Dev | Q10 | Q25 | Q75 | Q90 | Nedsida ($<-20\%$) | Uppsida ($>+30\%$) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Large Cap** | 616 | **$+8,65\%$** | **$+5,91\%$** | $28,89\%$ | $-23,73\%$ | $-9,32\%$ | $+24,51\%$ | $+47,14\%$ | **$12,8\%$** | $19,6\%$ |
| **Mid Cap** | 852 | $+7,29\%$ | $+1,96\%$ | $37,92\%$ | $-31,94\%$ | $-15,86\%$ | $+24,73\%$ | $+52,61\%$ | $20,8\%$ | **$21,1\%$** |
| **Small Cap** | 588 | **$-6,73\%$** | **$-14,09\%$** | $65,67\%$ | **$-50,89\%$** | $-32,74\%$ | $+7,96\%$ | $+31,53\%$ | **$41,7\%$** | **$11,1\%$** |

### 2. Uppdelning per K1-Sektor (2020–2026)

| K1-Sektor | $N$ obs | Snitt $R_{24w}$ | Median $R_{24w}$ | Std Dev | Q10 | Q75 | Q90 | Nedsida ($<-20\%$) | Uppsida ($>+30\%$) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Industri** | 381 | **$+7,87\%$** | **$+1,92\%$** | $29,18\%$ | $-24,66\%$ | $+24,11\%$ | $+49,46\%$ | **$13,9\%$** | $19,4\%$ |
| **Konsument** | 338 | $+7,38\%$ | $+2,66\%$ | $35,96\%$ | $-25,66\%$ | $+18,63\%$ | $+41,83\%$ | $15,7\%$ | $16,6\%$ |
| **Råmaterial** | 160 | $+9,61\%$ | $+2,23\%$ | $32,86\%$ | $-24,97\%$ | $+23,79\%$ | $+52,07\%$ | $14,4\%$ | $18,8\%$ |
| **Finans** | 252 | $+2,80\%$ | $+0,11\%$ | $37,52\%$ | $-38,20\%$ | $+17,02\%$ | $+41,61\%$ | $23,0\%$ | $15,5\%$ |
| **Teknologi** | 491 | $+5,26\%$ | **$-4,93\%$** | **$68,50\%$** | $-36,67\%$ | $+19,61\%$ | $+54,59\%$ | $29,1\%$ | $18,9\%$ |
| **Hälsovård** | 439 | $-4,51\%$ | **$-4,04\%$** | $39,54\%$ | $-54,53\%$ | $+19,52\%$ | $+43,72\%$ | **$34,9\%$** | $17,5\%$ |
| **Fastigheter** | 74 | **$-12,54\%$** | **$-12,58\%$** | $25,83\%$ | $-48,21\%$ | $+4,18\%$ | $+16,88\%$ | **$36,5\%$** | **$4,1\%$** |

---

## D. NEGATIV KONTROLL OCH MODELLUTVÄRDERING (M0–M4)

Modeller utvärderas för att bekräfta om strukturell information överlever kontroll för H0-rank och volatilitet:
- **M0**: `h0_rank`
- **M1**: M0 + `vol_52w` (Fullständig basmodell)
- **M2**: M1 + K1-Sektor
- **M3**: M1 + Listsegment
- **M4**: M1 + K1-Sektor + Listsegment

### 1. In-Sample Location $R^2$ för Framtida Avkastning ($R_{24w}$)

| Utvärderingsfönster | M1 Baseline $R^2$ | M2 (Sektor) $R^2$ | M3 (Listsegment) $R^2$ | M4 (Sektor + List) $R^2$ | Inkrementell Vinst M4 vs M1 |
|---|---:|---:|---:|---:|---:|
| **2014–2019** | $0,30\%$ | $2,52\%$ | $1,64\%$ | **$3,10\%$** | **$+2,80\%\text{ pp}$** |
| **2020–2026** | $0,36\%$ | $1,74\%$ | $2,16\%$ | **$3,39\%$** | **$+3,03\%\text{ pp}$** |

*Slutsats: K1-Sektor och Listsegment förklarar konsekvent **ca $3,0\%$ av variansen** i framtida 24-veckors avkastning som H0-rank och volatilitet är helt blinda för.*

### 2. Downside Risk 5-Fold OOS CV Brier Score ($P(R_{24w} < -20\%)$)

| Utvärderingsfönster | M1 Baseline Brier | M2 (Sektor) Brier Delta | M3 (Listsegment) Brier Delta | M4 (Sektor + List) Brier Delta |
|---|---:|---:|---:|---:|
| **2014–2019** | $0,10175$ | $-0,00071$ | $-0,00108$ | $-0,00230$ |
| **2020–2026** | $0,17941$ | $+0,00085$ | **$+0,00849$** | **$+0,00791$** |

---

## E. INTERAKTIONSEVALVERING: SEKTOR $\times$ LISTSEGMENT

Interaktioner utvärderades ex ante med krav på minimicellstorlek $N \ge 30$:

| Cellkategori | $N$ obs (2020–26) | Median $R_{24w}$ | Nedsidesrisk ($<-20\%$) | Uppsideschans ($>+30\%$) | Utvärderingsstatus |
|---|---:|---:|---:|---:|---|
| **Large Industri** | 156 | **$+7,72\%$** | **$7,1\%$** | $22,4\%$ | **VALID** |
| **Large Hälsovård** | 120 | $+4,75\%$ | $13,3\%$ | $24,2\%$ | **VALID** |
| **Large Teknologi** | 88 | $+3,15\%$ | $23,9\%$ | $18,2\%$ | **VALID** |
| **Mid Industri** | 140 | $+6,77\%$ | $10,7\%$ | $18,6\%$ | **VALID** |
| **Mid Hälsovård** | 115 | $+3,52\%$ | $11,3\%$ | $33,9\%$ | **VALID** |
| **Small Hälsovård** | 112 | **$-5,95\%$** | **$22,3\%$** | $8,0\%$ | **VALID** |
| **Small Industri** | 129 | $-0,26\%$ | $14,0\%$ | $23,3\%$ | **VALID** |
| **Small Teknologi** | 139 | $+6,88\%$ | $19,4\%$ | $24,5\%$ | **VALID** |
| *Large Energi* | 21 | — | — | — | **DATA INSUFFICIENT ($N < 30$)** |
| *Mid Energi* | 5 | — | — | — | **DATA INSUFFICIENT ($N < 30$)** |

---

## F. SLUTGILTIG KONKLUSION OG PREREGISTRERAD LICENS

1. **Falsifiering av H0-Homogenitetsantagandet**:
    locked H0 gör ett påvisbart modellfel genom att behandla alla Top-30-kandidater som dragna ur samma framtida payoff-fördelning.
2. **Klassificering**: **`3. PAYOFF HETEROGENEITY`**.
3. **Ingen handelsregel byggs**: Resultatet licensierar **ENDAST** följande förregistrerbara feasibility-fråga:
   > *"Kan H0 behålla sin momentumranking men använda conditional payoff distributions för att fatta bättre portfolio/hold/replace-beslut?"*
