# Research I Batch 2 — legacy exits/holding på V2

## Slutsats

Ingen av de fem korrekt replikerbara mekanismerna förtjänar en separat forward-challenger. DD20, 13v/26v-milstolparna och re-entry-blocket får **INGET STÖD**. Det sammansatta 8v-tidsstoppet får **SVAGT STÖD** som riskhypotes: MaxDD förbättras, men avkastning, excess och transaktionseffektivitet försämras för mycket för `STÖD — RISK`.

H0, H1 och H2 påverkas inte. Inga mekanismer kombinerades med varandra eller med H1/H2.

## Låst testdesign

Alla körbara armar använde fryst H0-ranking, Top 30, equal weight, original 8v-fas, targetfritt PIT-universum, V4:s första exekverbara close efter beslut/trigger och 20 bp per registrerad ensidig köpturnover. Endast exit-/holdingmekanismen varierade. Två möjliga 8v-startfaser kördes diagnostiskt; ingen fas valdes efter resultat.

H0-kontrollen reproducerades period för period och gav CAGR-differens `4.44e-16` mot den frysta artefakten.

## Resultat — primär fryst fas

| Mekanism | Klass | CAGR | Excess CAGR | Sharpe excess | MaxDD | Turnover | Events | Förlorare undvikna | Framtida vinnare kapade | Leave-3 | Leave-5 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H0 | GODKÄND REFERENS | 25,29 % | 15,21 % | 1,379 | −4,43 % | 19,62 % | 0 | 0 | 0 | 14,65 % | 14,69 %* |
| DD20 | INGET STÖD | 23,84 % | 13,77 % | 1,263 | −6,29 % | 33,33 % | 114 | 49 | 61 | 17,12 % | 14,14 % |
| Milestone 13v abs | INGET STÖD | 23,74 % | 13,66 % | 1,231 | −5,67 % | 21,54 % | 23 | 12 | 11 | 16,08 % | 12,88 % |
| Milestone 26v abs | INGET STÖD | 24,41 % | 14,34 % | 1,298 | −5,14 % | 20,13 % | 3 | 1 | 2 | 16,91 % | 13,73 % |
| Time stop 8v | SVAGT STÖD | 22,79 % | 12,72 % | 1,292 | −3,59 % | 92,95 % | 672 | 373 | 284 | 15,76 % | 12,21 % |
| Re-entry block | INGET STÖD | 24,60 % | 14,52 % | 1,310 | −5,41 % | 33,46 % | 113 | 49 | 60 | 17,93 % | 14,85 % |

\* H0 leave-5 är samma diagnostiska contributionsmetod som Batch 2; fryst V4 levererar byte-auktoritativ H0 för övriga nyckeltal och leave-3.

Time stop förbättrar MaxDD med cirka 0,84 procentenheter, alltså mindre än den preregistrerade 1 pp-gränsen, samtidigt som CAGR faller cirka 2,50 pp och turnover nästan femdubblas. Regeln kapade 284 framtida vinnare och undvek 373 förlorare; riskeffekten köps med för stor avkastnings- och handelskostnad.

Resultaten är inte startfasrobusta nog för promotion. Alternativfasens excess var cirka 2,51 % (DD20), 6,50 % (13v), 5,46 % (26v), 0,14 % (time stop) och 5,21 % (re-entry). Kalenderblocken visar också tydlig periodvariation, särskilt för DD20/re-entry.

## Legacy mot V2

Legacytal är endast bakgrund, inte evidens. Den äldre kedjan hade fel universum, survivorship/look-ahead, exekverings- och prisproblem och är inte numeriskt jämförbar med V2.

| Mekanism | Legacybakgrund | Ny V2-slutsats |
|---|---|---|
| DD20 | Legacy medel: cirka 10,05 % holdout och 6,57 % framåt; beskriven som stödd | INGET STÖD |
| Re-entry block | 10,03 % / 6,73 %, praktiskt oskiljbar från DD20 | INGET STÖD; fortsatt ingen inkrementell nytta |
| Time stop 8v | 9,35 % / 5,47 %, fler byten och sämre än DD20 | SVAGT STÖD, men ingen promotion |
| Milestone 13v abs | 8,42 % / 2,79 %, föll i legacy | INGET STÖD |
| Milestone 26v abs | 7,65 % / 2,17 %, föll i legacy | INGET STÖD |

Slutsatsen står alltså kvar för milstolpar och re-entry/time-stop-komplexitet, men DD20:s gamla positiva slutsats överlever inte V2.

## Ej korrekt replikerbara

- **Streak/uthållighet — KAN INTE TESTAS KORREKT.** Originalet kräver veckovisa köpsignaler och 5/10/20 veckors följd. V2-panelen är fyraveckorsvis; panelapproximation vore ett nytt forskarbeslut.
- **Rank-exit — KAN INTE TESTAS KORREKT som en unik legacyhypotes.** Legacy innehåller flera oförenliga definitioner. Rank 45 är dessutom redan testad i fryst Spår F; ingen definition valdes om här.
- **ATR — KAN INTE TESTAS KORREKT.** QA-godkänd high/low-kedja saknas.

## Separat dat back-log

Report/attention/PEAD, dividend-gap och insider-gap är fortsatt **OTESTADE**, inte falsifierade. Exakta krav på ny rådata och QA finns i `research_i/docs/UNTESTED_DATA_BACKLOG.md`.

## Definitionsfynd

`trend_consistency_52w` i aktiv panel är andel positiva handelsdagar medan registry/spec anger andel positiva veckor. Ingen fryst C/H-fil ändrades. Framtida veckohypoteser får endast använda den oberoende veckorekonstruktionen; eventuell C-rättning kräver separat versionsbeslut.

## Rekommendation

**Ingen Batch 2-mekanism ska frysas som forward-challenger.** H0 fortsätter oförändrad och H1/H2 samlar var sin separat forwardevidens från sina freeze timestamps. Batch 2 stoppas här.
