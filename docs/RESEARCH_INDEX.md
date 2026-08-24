# MOMENTUM_V2 AUTHORITATIVE RESEARCH INDEX (GOVERNANCE RECONCILED 2026-08-18)

Master index och provenance-register. **Kör `tools/repo_integrity_gate.py` först.**

| Test ID | Titel | Status | Computation Real? | PIT Valid? | Result Reproduced? | Anledning |
|---|---|---|:---:|:---:|:---:|---|
| **T-H0-01** | H0 Core Engine (kanonisk V2) | **FROZEN** | JA | JA | JA — bitidentisk | Full kedja verifierad: prereg `23cd3cde…` + 7 låsta indata + implementation + resultat + dom |
| **T-K1-01** | K1 Sector Classification | **VERIFIED_TAXONOMY** | N/A | JA | JA | Manifesthash `816cb6b3…` verifierad; scope endast klassificering |
| **T-H0-02** | Hysteres rank ≤ 35 | **UNVERIFIED_DECISION_RULE_REQUIRES_REVALIDATION** | JA (grid) | JA | **NEJ** | Diagnostiskt rutnät; bästa cell `N10_kop15-25_H30`; ingen frysning; `rank≤35` är STACK_H:s parameter |
| **T-G97P-01** | G97-P svansexkludering (K = 6) | **COMPUTED_BUT_NOT_VALIDATED_CANDIDATE** | JA | JA | JA (men ej validerad) | Beräkning äkta; bootstrap-KI korsar noll i båda fönstren; MaxDD blev sämre i båda; ingen frysningshändelse |
| **T-G-PATH-01** | G-PATH-1 Time-in-State | **CLOSED_NEGATIVE** | JA | JA | JA | Beräknad; redundant med H0-rank |
| **T-G-PATH-02** | G-PATH-2 Generic Path | **CLOSED_NEGATIVE** | JA | JA | JA | Giltig poolad nolleffekt |
| **T-H-ORIGIN-01** | H-ORIGIN-1 Momentum Origin | **CLOSED_NEGATIVE** | JA | JA | JA | Ingen oberoende alpha över H0 |
| **T-G-PROP-01** | G-PROP-1 Stock Propensity | **CLOSED_NEGATIVE** | JA | JA | JA | EB-propensity kollineär med TIS |
| **T-G-HET-01** | G-HET-1 Heterogeneity | **NOT_IDENTIFIED** | JA | NEJ | NEJ | Odaterad 2026 `market_list`-snapshot |
| **T-G-SIZE-HET-01** | G-SIZE-HET-1 Size Audit | **NOT_IDENTIFIED** | JA | NEJ | NEJ | Size-interaktioner ej identifierade |
| **T-G-RECLASS-01** | Reclassification Audit | **INVALID** | NEJ | NEJ | NEJ | Non-PIT size + oberäknade anspråk |
| **T-G-HIER-01** | G-HIER-1 Tree Feasibility | **NON_COMPUTED_CLAIM** | NEJ | NEJ | NEJ | Hårdkodad resultatdict |
| **T-G-HIER-02** | G-HIER-2 Hold/Replace | **NON_COMPUTED_CLAIM** | NEJ | NEJ | NEJ | Hårdkodad resultatdict; Passport **inte fryst** |
| **T-KPI-01** | Fundamental KPI Direct Test | **FORBIDDEN** | N/A | NEJ | N/A | Survivorship gate |
| **T-MCAP-01** | Market Cap / EV Foundation | **DATA_BLOCKED** | N/A | NEJ | N/A | Ingen PIT-historik |

**OPEN RESEARCH CANDIDATES: 0.**

---

## H0-versioner

| Version | Prereg sha | Resultat | H0 CAGR | MaxDD | Δ | Status |
|---|---|---|---:|---:|---:|---|
| **V2** | `23cd3cde…7ee2b3` | `h1419_exakt_h0_RESULTAT_V2.json` | **29,99 %** | **−14,63 %** | +12,15 pp | **KANONISK** |
| V1 | `87cb01d6…74133e` | `h1419_exakt_h0_RESULTAT.json` | 27,39 % | −12,09 % | +8,62 pp | `SUPERSEDED_BY_V2` |

V2 valdes ur artefakter — explicit `ersatter`-fält, dokumenterad survivorship-defekt
i V1 (44 bolag saknades, 38 med terminal-event), och nedströmsberoende via
`h1419_motor.py`. **Inte** ur prestanda. V1 får aldrig utelämnas.

---

## AUDIT HISTORY

| | |
|---|---|
| **Previous claim** | T-H0-02 angavs som `FROZEN_DECISION_RULE` med *"beräknad turnover-reduktion och CAGR"*; T-G97P-01 som `FROZEN_RISK_RULE` med *"beräknad 97.5:e percentil vol-exkludering"*. |
| **Contradicting evidence** | Se `FREEZE_REGISTRY.md` rättelse 2 och 3. G97-P:s implementation är `K = 6 # LÅST`, alltså sex av trettio — ingen percentilberäkning förekommer i koden. |
| **Correction date** | 2026-08-18 |
| **Resulting status** | `UNVERIFIED_DECISION_RULE_REQUIRES_REVALIDATION` respektive `COMPUTED_BUT_NOT_VALIDATED_CANDIDATE`. |
