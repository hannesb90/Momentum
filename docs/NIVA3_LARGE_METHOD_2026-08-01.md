# Large Nivå 3 – metodkontrakt

Nivå 3 är en ny, separat forskningskedja ovanpå den frysta Nivå-2-arkitekturen.
Stage-07-forwardmodellen och dess ledger får inte ändras. Gammal holdout har
noll rösträtt. Varje förbättrad Nivå-3-kandidat får ett eget framtida
forwardstartdatum och ersätter aldrig Stage 07 retroaktivt.

## Tillägg efter full gap-analys

SR-1–SR-44 och samtliga befintliga `tune_*.py` täckte inte följande risker
tillräckligt. De läggs därför till innan Nivå 3 fryses:

1. **N3-SR45 – calendar52-faskänslighet.** Kör samtliga 52 möjliga startveckor
   med frusna scores, utan omträning. Rapportera median, sämsta fas och andel
   faser som slår XACT. Fas får inte väljas som parameter. Det tidigare testet
   använde bara en calendar52-fas; staggered-testet besvarar inte samma fråga.
2. **N3-SR46 – eligibilitygrindens decomposition.** Separera expected-return-
   golv, fond/ETF-exkludering och momentumgrind. Testa momentumtröskelns lokala
   platå med förregistrerade nivåer, år/split-majoritet och random mask-control.
   Detta är obligatoriskt eftersom grinden stod för nästan hela Stage-05-lyftet.
3. **N3-SR47 – seed- och fitdatumsstabilitet.** Minst tre seeds samt 1–4 veckors
   förskjutning av fit-cutoff. Mät topp-15-Jaccard, CAGR-spridning och worst seed.
4. **N3-SR48 – PIT-universum/delistings.** Mät historisk listing/delisting-
   täckning och redovisa en konservativ lower-bound-alpha när prisserier saknas.
   Ett positivt resultat får inte kallas robust på dagens överlevare ensamt.
5. **N3-SR49 – datakälle-/corporate-action-känslighet.** Separera Börsdata,
   verifierad Yahoo-fallback och exklusion av konflikttickers. Resultatet ska
   visa hur mycket alpha som kommer från korrigerade/extrema prisserier.
6. **N3-SR50 – 100 000 kr implementerbarhet.** Heltalsaktier, minimiorder,
   courtage, ofyllda målvikter och tracking error mot idealportföljen. Detta är
   separat från månadsinsättningsregeln.
7. **N3-SR51 – refit-cutoff kring rotation.** Testa datalag på 0/1/2/4 veckor
   före årsrotationen. Stage 06 testade cadence, inte operativ cutoff-lag.
8. **N3-SR52 – temporal och faktorattribuering.** Rullande femårs-/eraresultat,
   sämsta startår och residual alpha efter beta, sektor, size, value, quality
   och momentum. Exponerad 2021–2026-period är diagnostik utan rösträtt.
9. **N3-SR53 – publiceringslagg/missingness i faktiskt urval.** Mät hur många
   topp-15-val som ändras av +1 veckas fundamental lagg och av tekniskt saknade
   värden. Placebo-SR43 täcker läckage generellt men inte selektionskonsekvensen.
10. **N3-SR54 – benchmarkens totalavkastningsparitet.** Kontrollera utdelningar,
    splitar, tracking error och start-/slutkurs för XACT så att alpha inte är en
    pris-/totalavkastningsskillnad.

## Obligatorisk ordning

1. Calendar52-fas, eligibility-decomposition, seeds/fitdatum och PIT-/datakällegater.
2. Featurefamilje-ablation.
3. PIT-fundamenta och ekonomiskt motiverade interaktioner.
4. Risk- och exponeringslager.
5. Entry/exit mellan årsrotationerna.
6. Exekveringsfördröjning, likviditet, kapacitet och 100k-implementerbarhet.
7. Integrerad paritet, benchmark-/faktorattribuering och multipeltestkontroll.

Large/Small-allokering, LSTM och månadsinsättningar är separata mandat och får
inte skapa skenbar Large-alpha i denna kedja.

## Frys- och rollbackregler

- Varje stage hashkedjas rekursivt till sin förälder och alla beslutsartefakter.
- Nästa stage måste verifiera hela kedjan före träning eller backtest.
- `results/niva3_stages/latest_healthy.json` uppdateras först efter full PASS-
  verifiering och är den enda tillåtna rollbackpunkten.
- Ett fel, en krasch eller en muterad artefakt flyttar aldrig pekaren.
- Endast det felaktiga steget och dess eventuella barn görs om; tidigare friska
  stages behålls.
- Nivå-2-kedjan och Stage-07-forwardartefakterna är read-only för Nivå 3.
