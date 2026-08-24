# MOMENTUM_V2 DATA GOVERNANCE REGISTRY

Datum: 2026-08-18 · **Auktoritativt Datagovernance- & Variabelregister**  
Ingen variabel får användas i modelltester utan uttryckligt godkännande i detta register.

---

## AUDITERADE VARIABLER OCH ANVÄNDNINGSTILLÅTELSER

| Variabelnamn | Datakälla | PIT-Semantik | Overlevnads- & Avnoteringsstatus | Tillåtelse i Modelltest |
|---|---|---|---|---|
| **`mom_52w` / `mom_78w`** | Validerad prisryggrad (EODHD + Skatteverket) | Strikt T-1 stängningspris tillgängligt före öppning | **349 avnoterade bolag i 14–19, 134 i 20–26** inkluderade | **TILLÅTEN FÖR ALLA MODELLER (Core Momentum)** |
| **`vol_52w`** | 52-veckors rullande dagsavkastning std dev | Strikt T-1 rullande fönster | Inkluderar alla avnoterade aktier | **TILLÅTEN FÖR RISK- OCH KONTROLLMODELLER** |
| **`list_segment`** (Large/Mid/Small) | Avanza-skrapning 2026-08-09 (EJ ett PIT-arkiv) | **INGEN — inget datumfält, ett värde per instrument** | `Terminal/Avnoterad` ur `terminal_events.json` = avnoterade någon gång, tilldelas även år före händelsen | **STRIKT FÖRBJUDEN (FORBIDDEN_IN_MODEL_TEST)** |
| **`nasdaq_market_cap_segment_pit`** | Nasdaq Nordic månadsrapporter, 201 filer 2009-08…2026-07 | **Månadssnapshot; uppslag använder strikt föregående månad** | Avnoterade inkluderade — exposure-täckning 100,0 % mot aktiva 94,0 % | **ENDAST POPULATIONSSTRATIFIERING (Ej poängtilt)** |
| **`canonical_sector`** (K1) | Avanza / NACE PIT Sektor-intervall | Låst manifest SHA256 `816cb6b3...` | PIT interval-lookup vid beslutspanel | **ENDAST POPULATIONSSTRATIFIERING (Ej poängtilt)** |
| **`fundamental_kpis`** (P/E, ROE, etc) | Börsdata Finansiella Rapporter | Saknar fullständig PIT-rapportdatum | **Missar historik för avnoterade/konkursade aktier** | **STRIKT FÖRBJUDEN (FORBIDDEN_IN_MODEL_TEST)** |
| **`market_cap` / `enterprise_value`** | Börsdata Market Cap Snapshot | Ojusterad ögonblicksbild saknar PIT-historik | **Överlevnadsbias identifierad** | **STRIKT BLOCKERAD (DATA_BLOCKED_GOVERNANCE)** |


---

## RÄTTELSE 2026-08-18 — `list_segment`

Raden angav tidigare källan som *"Avanza Stockholm Market List PIT"* med *"Expanderande PIT listmedlemskap"* och tillåtelse för populationsstratifiering. Verifiering mot `qa_identity_sector_evidence.json` visar att filen saknar datumfält helt och har ett `market_list`-värde per instrument. Raden motsade `CURRENT_RESEARCH_STATE.md` §3, `INVALIDATED_AND_SUPERSEDED_RESULTS.md` punkt 2 och `RESEARCH_INDEX.md`, och licensierade den variabel som gjorde G-HET-1 och G-SIZE-HET-1 `NOT_IDENTIFIED`.

Underlag: [`PROVENANCE_DISCREPANCY_AUDIT_2026-08-18.md`](PROVENANCE_DISCREPANCY_AUDIT_2026-08-18.md)


---

## TILLÄGG 2026-08-18 — `nasdaq_market_cap_segment_pit`

Ny PIT-korrekt storleksvariabel, registrerad efter `PIT_SIZE_FOUNDATION_VALID` (14 av 14 gate-kriterier).

**Detta är en datavariabel, inte en validerad alfafeature.** Ingen size-effekt är visad. `G-HET-1`/`G-SIZE-HET-1` förblir `NOT_IDENTIFIED`, `G-HIER-1`/`G-HIER-2` förblir `NON_COMPUTED_CLAIM`, och OPEN RESEARCH CANDIDATES förblir 0.

Underlag: [`NASDAQ_PIT_SIZE_FOUNDATION_FINAL.md`](NASDAQ_PIT_SIZE_FOUNDATION_FINAL.md) · hashmanifest `research_k/nasdaq_segment_foundation/manifest.json`
