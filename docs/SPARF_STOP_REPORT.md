# Spår F — STOPP vid dataintegritetsfel

Status: **STOPPED_DATA_INTEGRITY_ERROR**  
Spår D och E: oförändrade  
A/B/C: inte ändrade

## Blockerare

`trend_consistency_52w` är inte den feature som blueprint och registry beskriver.

- Dokumenterad definition: andel positiva **veckor** under trailing 52 veckor (`tools/spar_c_blueprint.py`).
- Aktiv implementation: `win52.pct_change()` direkt på den dagliga adjusted-close-serien (`tools/spar_c_features_core_v2.py:252`), alltså andel positiva **handelsdagar**.
- Spår F:s preliminära F3-vinnare var detta fält. Resultatet får därför inte godkännas, kallas alpha eller frysas som ny champion.

Detta är en faktisk blueprint/implementation-avvikelse i fryst C. En automatisk ändring är förbjuden av uppdraget; Spår F stoppas därför.

## Resultat som får behållas som diagnostik

F1 reproducerade Spår D:s 12m-champion exakt:

- OOS mean IC52 0,1327
- median IC52 0,1647
- top-30 IC52 -0,0434
- CAGR netto 15,1 %
- MaxDD -14,7 %
- mean turnover 0,323

F2:s preregistrerade `combo_12m_18m` passerade den registrerade robusthetsregeln före F3:

- mean IC52 0,1555
- median IC52 0,1653
- top-30 IC52 -0,0220
- positiv IC-andel 100 %
- CAGR netto 20,2 %
- MaxDD -8,7 %
- leave-top-3 excess -4,3 %, jämfört med -9,1 % för F1

Detta är **preliminärt och inte en slutlig Spår F-champion**, eftersom den föreskrivna sekventiella kedjan stoppades vid F3.

## Krävt beslut före fortsatt arbete

Välj uttryckligen ett av följande utanför det frysta Spår F:

1. redefiniera den befintliga C-featuren sanningsenligt som daglig trendkonsistens och därefter preregistrera om F3, eller
2. reparera C till verklig veckokonsistens, återbygg berörda C-/manifestartefakter och starta om F3 från den låsta F2-vinnaren.

Ingen av åtgärderna har utförts här.
