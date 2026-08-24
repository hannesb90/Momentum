# Signalkällor: gate-audit 2026-08-16

Syfte: avsluta sökningen i lokalt tillgängliga data utan att överanpassa samma
historik. Detta dokument ändrar inga modeller eller forward-journaler.

## Utfallet av den aktuella sökningen

| Källa/familj | PIT-status | Historisk täckning | Villkorad signal ovanpå H0 | Beslut |
|---|---|---|---|---|
| Pris, trend, risk, volym och regim (CORE) | Godkänd | 2020–2026 | CORE-meta-exit: +0,17 pp i oberoende test, KI [−3,83, +2,86] pp | Avvisad |
| Pris/rank-exitfamilj | Godkänd | 2014–2026 | Inga stabila segment eller interaktioner | Stängd |
| Rapportpublicering/PEAD | Godkänd och låst | 2020–2026 | Inget inkrementellt stöd givet H0 | Avvisad |
| FI-insider | Godkänd och låst | 2020–2026 | Mean delta IC −0,00147; instabilt mellan halvor | Avvisad |
| FI-blankning | Godkänd, 4 dagars lagg | 2012–2026 | För få H0-namn berörs; samtliga regler inom placebo | Avvisad |
| Fundamenta/KPI | Rapportdatum finns | Historik saknar avnoterade bolag | Survivorship-riktningen okontrollerbar | Förbjuden i modelltest |
| Återköp | **Ej godkänd** | 2016–2026 | Har endast transaktionsdatum, ingen marknadskänd tidpunkt | Datablockerad |
| Riktkurser | **Ej godkänd** | Enbart 2026-08-13 | En snapshot, ingen revisionshistorik | Datablockerad |

## Varför återköp inte får användas

`validated/fundamenta_extra/buyback_transaktioner.json` innehåller datum,
antal och pris för genomförda transaktioner, men inget publiceringsdatum eller
offentliggörandetid. Att anta att marknaden kände till ett köp på
transaktionsdagen skulle skapa look-ahead. Uppgiften kan bli användbar först
när varje rad kan länkas till en historisk offentlig rapport med tidsstämpel.

## Vilken information som faktiskt saknas

Nästa signal måste vara ortogonal mot prisbanan och uppfylla samtliga krav:

1. En oföränderlig historisk export, även för avnoterade bolag.
2. Instrumentidentitet som kan matchas konservativt mot H0-universumet.
3. Exakt publicerings-/marknadskänd tidpunkt, inte bara ekonomiskt datum.
4. Tillräcklig täckning i båda tidsfönstren eller ett prospektivt förseglat
   test om källan är ny.
5. Förregistrerad enda definition och placebo när regeln ändrar innehav.

Mest värdefulla nya kandidater är därför en historisk analystarget-/estimat-
revisionsfeed eller tidsstämplade bolagsmeddelanden om utdelning, återköp och
nyemission. Ingen sådan PIT-historik finns lokalt ännu.

## Slutsats

Det finns ingen ytterligare försvarbar signal att lägga ovanpå H0 från den
aktuella lokala arsenalen. Fortsatt variantgenerering av pris-, rank- eller
CORE-features skulle bryta projektets stoppkriterium och ge större risk för
falska fynd än för inkrementell avkastning.
