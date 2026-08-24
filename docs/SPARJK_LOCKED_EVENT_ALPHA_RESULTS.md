# Spår J/K — låsta report/PEAD- och insidertester

Datum: 2026-08-09. Tester körda i ordningen report/PEAD → immutable freeze → insider → immutable freeze. H0, H1, H2 och upstream-artefakter ändrades inte. Ingen kombinationsmodell eller parametersearch genomfördes.

## Integritetsgrind — PASS

* MFN-manifest: `5d74ff7188767ec125ddbc5dbc6f317f087f911d4f08e654e1a0046bd7724db5`.
* FI-manifest: `80fd640c968f6324135ff806673ac92072df074499eb486024272df87e26fbb0`.
* Report-preregistrering: `ac92a3b3cb7cc13d34029a3a8356e042e73fcbb68929e5928048ae8efaa087c6`.
* Insider-preregistrering: `f5a3af5afa170cbdc137626cd242a3c666463dc64a95a8e3e742e83aadd4caf7`.
* Eventfeatures och urval konstruerades före target lästes. Target användes endast för utvärdering.

## Report/PEAD — SVAGT STÖD

### Report reaction och fristående PEAD

6 020 primära resultatpubliceringar fick en verifierbar initial prisreaktion. Av dessa hade 5 747 events från 372 instrument ett moget 13-veckorsutfall.

| Mått | Resultat |
|---|---:|
| Evaluable eventdatum | 501 |
| Mean PEAD IC13w | 0,0750 |
| Median PEAD IC13w | 0,0857 |
| Positiv IC-andel | 54,69 % |
| Pooled Spearman | 0,0471 |
| Första kronologiska halvan | 0,0580 |
| Andra kronologiska halvan | 0,0920 |

Utan terminalinstrument var mean IC 0,0689 och båda halvor fortsatt positiva. Den fristående, fasta PEAD-hypotesen uppfyllde därför sin låsta stödregel: **STÖD**.

### Report confirmation conditional on H0

Detta är huvudfrågan om inkrementell information utöver H0.

* 1 857 H0-beslutsrader hade en kvalificerad rapport inom det fasta 28-dagarsfönstret.
* 1 427 rader hade observerbar 52v-target; 332 instrument och 21 terminalinstrument deltog.
* Coverage-matchad H0 mean IC52: 0,1970.
* H0 + report-confirmation mean IC52: 0,1494.
* Δ mean IC52: **−0,0476**.
* Δ median IC52: −0,0501.
* Δ Top-30 IC: −0,0539.
* Δ positiv IC-andel: 0,0000.
* Kronologiska halvor: −0,0830 respektive −0,0158.
* Utan terminalinstrument: Δ mean IC52 −0,0449.
* Leave-top-3/5 eventfrekventa tickers ändrade inte den negativa slutsatsen.

Report-confirmation fick därför **INGET STÖD**. Reportinformationen visar en fristående post-event drift, men förbättrar inte H0:s urval. Samlingsklassningen blir **SVAGT STÖD**, inte robust inkrementellt stöd och inte en forward-challenger.

Attention-gap är fortsatt **OTILLRÄCKLIG DATA** eftersom eventvolym-QA saknas.

## Insider conditional on H0 — INGET STÖD

FI:s retrieval-time `source_status` användes aldrig för det primära historiska filtret. Varje publicering användes först från sin UTC-normaliserade market-known-time.

Coverage:

* FI foundation: 342/352 aktuella och 63/68 terminalinstrument.
* Saknade terminalinstrument: AGRO, AM1S, ENDO, MIC-SDB och SMF.
* 2 561 av 9 108 H0-rader fick insiderinformation, 28,12 %.
* 1 901 target-observationer, 341 instrument och 20 evaluable paneldatum.
* 21 terminalinstrument deltog faktiskt i H0-informationstestet.

| Mått | Matchad H0 | H0 + insider | Delta |
|---|---:|---:|---:|
| Mean IC52 | 0,1396 | 0,1381 | −0,0015 |
| Median IC52 | 0,1354 | 0,1390 | +0,0037 |
| Top-30 IC | 0,0117 | 0,0717 | +0,0600 |
| Positiv IC-andel | 95,0 % | 90,0 % | −5,0 pp |

Kronologiska halvor gav −0,0294 respektive +0,0265 i Δ mean IC. Utan terminalinstrument var Δ mean IC +0,0108, men positiv-datumandelen försämrades fortfarande. Den obligatoriska clean-group-diagnostiken gav endast +0,00023 i mean ΔIC och samma teckenväxling mellan halvor. Leave-top-3/5 försämrade mean ΔIC ytterligare.

Stödregeln missades på mean ΔIC, positiv-datumandel och tidsstabilitet. Klassning: **INGET STÖD**.

## Slutbeslut

1. Reportinformation tillför inte robust information utöver H0. Fristående PEAD är positiv, men report-confirmation försämrar H0 tydligt.
2. Insiderinformation tillför inte robust information utöver H0.
3. Inget resultat motiverar en separat forward-challenger.
4. Det finns inte stöd för att preregistrera en kombinerad event-confirmation-modell.
5. V2:s historiska diskretionära alphaforskning stängs. H0 fortsätter oförändrad i sin förseglade forwardjournal.

K2 value, dividend, buyback/shareholder yield och attention-gap förblir endast data-backlog. De får öppnas först vid genuint ny, QA-godkänd information—inte genom nya varianter på samma historik.
