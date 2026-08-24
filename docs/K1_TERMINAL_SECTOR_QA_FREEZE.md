# K1 terminal sector classification QA + freeze

## Beslut

Den breda sektordatan är **DATA REDO MED BEGRÄNSNING**. Den omfattar 420/420 instrument och 68/68 terminalinstrument. Detta stänger den mekaniska survivorship-luckan, men 420 etiketter betyder inte 420 historiskt källverifierade etiketter.

Ingen target, framtida avkastning, IC eller portföljutvärdering har lästs eller beräknats.

## QA-resultat

De 68 manuella klassificeringarna har lagrats oförändrade som kandidatinput och har inte automatiskt blivit `PIT_VERIFIED`. Crosswalken låser exakt en bred Avanza-sektor per instrument; dubbla primärsektorer är förbjudna. En fin industry sätts endast när en exakt canonical Avanza-leaf kan försvaras, annars `UNKNOWN`.

- Totalt: 420; aktuella: 352; terminala: 68.
- Bred sektoretikett: 420/420; terminala: 68/68.
- Exakt canonical industry: 352/420.
- `SOURCE_VERIFIED`: 4.
- `STABLE_CLASSIFICATION_SUPPORTED`: 410.
- `MANUAL_EXPERT_CLASSIFICATION`: 6.
- Verifierad eller stabilt understödd: 414/420; terminala 62/68.

Panelårs- och terminalårscoverage finns maskinläsbart i `research_k/sector_classification_v1/qa/coverage.json`.

Statusuppgraderingar kräver identitets- och källstöd. Exact-ISIN Avanza, tre tidigare snapshots och immutable MFN issuer-events används där de finns. Primärkällor används explicit för Klövern, Adapteo, Collector och Endomines. Sex poster är fortfarande synligt manuellt expertklassificerade och måste ingå i framtida känslighetsredovisning.

## KLOV-PREF

KLOV-PREF är Klövern AB:s preferensaktie, ISIN `SE0006593927`, fram till avnoteringen 2021-07-20. [Nasdaq](https://view.news.eu.nasdaq.com/view?id=be51019e28103754e27ce7659d5103d9b&lang=en) identifierar short name och ISIN; [Corems erbjudandesida](https://www.corem.se/en/investor-relations/offer-for-klovern/) beskriver transaktionen och [Klöverns årsredovisning 2020](https://kelly.corem.se/app/uploads/2021/03/klovern__arsredovsning_2020.pdf) beskriver verksamheten. Corem Kelly är senare namn på emittenten och har inte klassificerats bakåt som en ny ekonomisk verksamhet.

## Giltighet och begränsningar

Intervallen börjar vid första observerade V2-pris och slutar vid verifierat terminaldatum; aktuella instrument har öppet slut. Klassificeringen behandlas som stabil entity classification, inte som rapporterad finansiell PIT-data. Historiska sektorbyten mellan snapshots kan inte observeras fullständigt.

Framtida K1-test måste därför redovisa både alla transparent märkta etiketter och en känslighet utan `MANUAL_EXPERT_CLASSIFICATION`. Terminalstatus eller etikettstatus får aldrig påverka decision universe.

## K1 usability

- Sector momentum: **DATA REDO MED BEGRÄNSNING**.
- Sector-relative momentum: **DATA REDO MED BEGRÄNSNING**.
- Sector breadth: **DATA REDO MED BEGRÄNSNING**.
- Industry-relative momentum: **DELVIS TESTBAR**.
- Sector diversification/tie-break: **DATA REDO MED BEGRÄNSNING**, men endast efter separat preregistrering.

Diversifieringshypotesen är dokumenterad men inte aktiverad. H0 ska fortsatt bestämma alpha-rankingen. Ingen tie-tröskel, sektorpenalty eller regel har valts eller testats.

## Immutable freeze

Version: `K1_SECTOR_CLASSIFICATION_V1_IMMUTABLE_2026-08-09`.

Freeze ligger under `research_k/sector_classification_v1/`. Manifestet omfattar inputkällor, kandidater, Avanza-taxonomi, crosswalk, identitets-/evidensfält, validity intervals, coverage, usability och den ej testade diversifieringshypotesen. `tools/verify_spark_sector_freeze.py` gör fail-fast på path, existens, bytes och SHA256.

## Slutsvar

Ja: den breda sektorklassificeringen är nu tillräckligt dokumenterad för att preregistrera K1 utan att terminalinstrumenten försvinner och utan dold survivorship-bias. Begränsningen är explicit: sex instrument saknar starkare historiskt källstöd och fin industry-täckning är ofullständig. Därför är breda sektortester redo med obligatorisk känslighet, medan full industry-relative analys fortfarande bara är delvis testbar.
