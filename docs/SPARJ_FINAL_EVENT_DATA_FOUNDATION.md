# Spår J — slutlig eventdatagrund före alpha

Datum: 2026-08-09. Ingen target, IC, portföljutvärdering eller alphaanalys har körts i detta arbete. H0/H1/H2 och samtliga tidigare frysningar är orörda.

## 1. H0 untouched forward — PASS

`tools/sparh_forward.py verify`, `status` och hela regressionstestet passerar. H0 är fortfarande exakt 50/50 rank(12m)+rank(18m), Top 30, equal weight, 8 veckor och V4:s post-decision execution/kostnads-/terminalregler.

* H0-lock: `93f462fc9d4461c54c277cddada08664c1f7eef30176980b4d879df86d038661`
* V4-freeze: `6716e083c570bcf3b9f86d7583e85ad72e2d00e4089295214a746deb2d7f5c3d`
* V4: 43/43 och A/B/C: 13/13 manifestmatchade.
* Journalen är append-only och innehåller 0 records. Inga gamla paneler har återanvänts som forward.
* Första eligible panel och nästa frysta 8v-rebalance är 2026-09-04.
* H1/H2 har separata manifests/journaler och kan inte skriva i H0:s journal.

Ingen forwardutvärdering är möjlig eller genomförd ännu.

## 2. MFN report foundation — PASS MED BEGRÄNSNING

Immutable källa: `MFN_V2_AUTHOR_20260809T140000Z`, 427 råsidor och 1 454 004 553 mottagna byte. Samtliga råhashar verifierades innan reportlagret byggdes.

Det frysta reportlagret `MFN_REPORT_EVENTS_V1_IMMUTABLE_2026-08-09` innehåller:

* 14 074 reportkandidater före terminalkontroll.
* 13 998 inkluderade pre-terminalevents; 76 efter verifierat terminaldatum exkluderades.
* Exakt identitet, explicit UTC `published_at`, och `market_known_time = published_at`.
* 382/420 instrument med reportevent: 325/352 aktuella och 57/68 terminala.
* För den snävare primära resultatrapportdefinitionen: 6 094 events, 375 instrument, 320 aktuella och 55 terminala.
* Providerklassificering behålls; deterministiska titelregler markeras separat. Ingen LLM- eller targetbaserad klassificering.
* Rättelser/uppdateringar och samma-dagspubliceringar finns kvar explicit; endast tidigaste kvalificerade resultatrelease markeras som primär.

Report reaction, PEAD och report-confirmation conditional on H0 är därför preregistrerbara på explicit eventtäckt, coverage-matchad population. Preregistreringen finns i `research_k/REPORT_PEAD_PREREGISTRATION_BEFORE_ALPHA.json` och har inte körts.

Attention-gap är fortsatt **BLOCKERAD** eftersom verifierad eventrelativ volymdefinition ännu inte är fryst. En dämpad prisreaktion ensam får inte kallas inattention.

## 3. Officiell FI insider foundation — PASS MED BEGRÄNSNING

Godkänd RAW-run: `FI_OFFICIAL_V2_20260809T190500Z`.

* 345/345 disjunkta sjudagarsfönster.
* 120 446 parsade CSV-poster = FI:s officiella globala sökantal 120 446.
* 346 manifesterade requests; mottagna UTF-16LE-byte sparas verbatim.
* RAW-manifest SHA256: `6024a7472dd214d2dc507d0d61a37d5829f88b1626b12fa5c906c89b74f6967a`.
* Ett upptäckt räknarfel rättades före frysning: två radbrytningar inne i citerade CSV-fält fick aldrig längre räknas som poster.

Validerat lager: `VALIDATED_FI_INSIDER_V2_TIMEZONE_SAFE`.

* 41 753 pre-terminalrader med exakt V2-ISIN.
* 405/420 instrument: 342/352 aktuella och 63/68 terminala.
* Saknade terminala: AGRO, AM1S, ENDO, MIC-SDB och SMF.
* 65 publiceringar efter verifierat terminaldatum exkluderades.
* FI:s `Publiceringsdatum` tolkas explicit i `Europe/Stockholm` och normaliseras till UTC. Transaktionsdatum används aldrig som market-known-time.
* Status: 38 645 Aktuell, 2 623 Reviderad, 485 Makulerad.
* FI-exporten saknar stabilt report-ID. `source_status` är retrieval-time state och får därför aldrig användas för att retroaktivt filtrera historisk tillgänglighet.

Konservativ FI↔Börsdata-QA gav 34 256 exakta matchningar på identitet, transaktionsdatum, signerad kvantitet, pris och valuta. Medianen för Börsdata `verificationDate` minus FI-publicering är 0 timmar efter explicit timezone-normalisering. FI är primärkälla; Börsdata är endast QA.

Insider conditional on H0 är preregistrerat i `research_k/INSIDER_CONDITIONAL_H0_PREREGISTRATION_BEFORE_ALPHA.json`, men har inte körts. Huvuddefinitionen använder en fast 28-dagars förekomstsignal för ordinära `Förvärv` respektive `Avyttring`, utan belopps-, person-, ratio- eller klustergrid. Current-status får inte skriva om historiken.

## 4. Status och nästa forskningsgrind

| Steg | Status | Beslut |
|---|---|---|
| H0 forwardjournal | PASS | Lämna orörd; vänta på verkliga paneler |
| MFN RAW/identity/PIT/provenance | PASS MED BEGRÄNSNING | 57/68 terminalcoverage |
| Report/PEAD testbarhet | PASS MED BEGRÄNSNING | Preregistrerad, coverage-matchad test möjlig |
| Attention-gap | BLOCKERAD | Eventvolym-QA saknas |
| FI RAW completeness | PASS | 120 446/120 446 |
| FI identity/PIT/provenance | PASS MED BEGRÄNSNING | 63/68 terminalcoverage; correction-chain saknar stabilt ID |
| Insider testbarhet | PASS MED BEGRÄNSNING | Preregistrerad närvarosignal möjlig; ingen alpha körd |

Nästa tillåtna steg är två separata preregistrerade alphatester: först report/PEAD, därefter insider conditional on H0. De får inte kombineras med varandra innan båda har testats och falsifierats separat. Ett positivt historiskt resultat får endast skapa en separat forward-challenger, aldrig skriva om H0.

## 5. Reproducerbarhet

* MFN manifest SHA256: `5d74ff7188767ec125ddbc5dbc6f317f087f911d4f08e654e1a0046bd7724db5`.
* FI final freeze manifest SHA256: `80fd640c968f6324135ff806673ac92072df074499eb486024272df87e26fbb0`.
* `python3 tools/verify_sparj_event_foundations.py` verifierar paths, bytes, SHA256 och byteantal fail-fast.

Underkända FI-försök är bevarade och explicit märkta `INVALID_*`; inget av dem används av den aktiva frysningen.
