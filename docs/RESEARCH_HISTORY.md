# MOMENTUM_V2 RESEARCH HISTORY & KRONOLOGISK UTVECKLINGSLOGG

Datum: 2026-08-18 · **Kronologisk historik över alla större forskningsfaser och rättelser**

---

## CHRONOLOGICAL LOG OF RESEARCH PHASES

### Fas 1: Grundläggande V2-Arkitektur & Universumreparation (2026-08-08 – 2026-08-14)
- Validerade prisryggraden med Skatteverkets avnoteringshistorik (349 avnoterade bolag i H1419, 134 i 2020–2026).
- Låste H0-scannern på 12m/18m relativ momentum-rank.
- Forskning på SPAR A–K visade att fundamenta och volymindikatorer saknade PIT-täckning för delistade bolag $ightarrow$ spärrades under `FORBIDDEN_IN_MODEL_TEST` och `DATA_BLOCKED`.

### Fas 2: Beslutslager & Riskkomponenter (2026-08-15 – 2026-08-16)
- **Hysteres (`rank <= 35`)**: Validerades. Minskar omsättningen med $38{,}5\%$ utan avkastningsförlust.
- **G97-P Volatilitetssvans-exkludering**: Validerades. Sänker 2020–2026 MaxDD från $-24{,}32\%$ till $-19{,}5\%$.
- **Path- och Memory-tester (G-PATH-1, G-PROP-1)**: TIS visade sig vara redundant med H0-rank. Bolagspecifik historisk propensity var kraftigt kollineär med TIS och stängdes.

### Fas 3: Population Heterogeneity & Size-Conditional Audit (2026-08-17 – 2026-08-18)
- **G-HET-1**: Visade att Top-30-kandidater inte är homogena. K1-Sektor och Listsegment predikterar framtida fördelning ($\Delta R^2 = +3{,}03\%	ext{ pp}$).
- **G-SIZE-HET-1 & Reclassification Audit**:
  - Avslöjade ett massivt regimskifte i Small Cap mellan fönstren (nedsidesrisk steg från $15{,}9\%$ till $41{,}7\%$).
  - Förklarade fönsterinstabiliteten i `vol_52w` och avslöjade en dold reproducerad reversal-effekt för `run_return` i Mid Cap ($-0{,}069	ext{ till }-0{,}084$).
  - Bekräftade att **H0 förblir en universell momentum-scanner**, medan heterogeniteten uppstår helt *efter selection*.

### Fas 4: Hierarkiskt Populationsträd & Hold/Replace Feasibility (2026-08-18)
- **G-HIER-1**: Etablerade en obalanserad hierarkisk trädarkitektur (Universe $ightarrow$ Size $ightarrow$ Sector | Size för täta celler, STOPP vid parent för glesa celler) med Empirical Bayes Shrinkage.
- **G-HIER-2**: Bevisade att PIT Population Passports förbättrar prediktionen av framtida Opportunity Cost ($OC = R_{24w,B} - R_{24w,A}$) i A-vs-B replace-beslut OOS ($M3$ riktningsprecision $61{,}3\%$, $r_s = +0{,}246$, OOS $R^2 = 3{,}65\%$).
