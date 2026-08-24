# Spår B: fullskale-resultat, KPI-utökning (EBITDA, Capex, återköp)

Datum: 2026-08-08. Fortsättning på `docs/SPAR_B_KPI_HISTORIK_SAMPLE.md` efter
godkänd sample-validering (inga blockerande problem). Full hämtning +
PIT-mappning + QA nu genomförd för hela Spår A-universumet (353 instrument
som matchar Börsdatas live-API).

**Ingen modellträning. Detta är datainsamling och datakvalitet, inget annat.**

## 1. Hämtning

- 2118/2118 KPI-historik-anrop (EBITDA + Capex × year/quarter/r12 × 353
  instrument) — 0 fel.
- 8/8 återköps-batchar (`/v1/holdings/buyback`, 50 instrument/batch) — 0 fel.
- RAW sparat verbatim under `raw/borsdata/kpi_history/` och
  `raw/borsdata/buyback/`, orört av byggsteget.

## 2. PIT-mappning och regelutfall

Samma R1–R5-regler som redan gäller `reports`-fälten (report_Date krävs,
epok-, look-ahead-, eftersläpnings- och valutakvot-uteslutning) återanvänds
för join-målets giltighet:

| kategori | antal |
|---|---|
| KPI-värden in | 61 874 |
| → PIT-mappade och godkända | **56 874** |
| uteslutet: partiellt (innevarande) räkenskapsår | 704 |
| uteslutet: perioden finns inte i reports-datan | 962 |
| uteslutet: saknar report_Date | 2 914 |
| uteslutet: look-ahead | 358 |
| uteslutet: epok (< 1990) | 20 |
| uteslutet: orimlig eftersläpning | 24 |
| uteslutet: valutakvot uppenbart fel | 18 |

## 3. Coverage

- **EBITDA:** 346/353 instrument (98,0 %), median 16 år/instrument.
- **Capex:** 346/353 instrument (98,0 %), median 16 år/instrument.
- 7 instrument helt utan data — troligen mycket nya noteringar eller
  instrument utan fullständig rapporthistorik hos Börsdata; inte djupare
  undersökt än (låg prioritet, < 2 % av universumet).

## 4. Återköp — nolla vs. saknas (mandatets punkt 12)

- 42 802 enskilda återköpstransaktioner hämtade (transaktionsnivå, eget
  `date`-fält per rad — se §6 för embargo-hantering).
- 146 instrument gav **verifierat noll** transaktioner (HTTP 200, `error:
  null`, tom `values`-lista) — sparas explicit som "0 återköp, bekräftat",
  INTE som saknad data.
- 0 instrument saknades helt i svaren (samtliga 353 dök upp i något batch-
  svar). Denna åtskillnad (bekräftad nolla vs. instrument som aldrig svarar)
  bevaras i `buyback_transaktioner.json` genom att en instrument-rad helt
  enkelt inte förekommer alls om den aldrig rapporterat återköp — kod som
  konsumerar datan måste slå upp mot hela instrumentlistan (inte bara denna
  fil) för att skilja "0 bekräftat" från "okänt".

## 5. Ekonomisk identitetskontroll (mandatets punkt 8)

EBITDA ≥ EBIT (operating_Income), endast SEK-rapporterande bolag och endast
helårsgranularitet (year p=5 / r12 p=4 — jämförbar periodgranularitet):

- **6 841 testade, 6 832 godkända (99,87 %), 9 avvikelser.**
- Tolerans: max(0,05 MCURR, 0,1 % av EBIT) för att inte falsklarma på
  float32-brus i källan (t.ex. lagrat -5.454999923706055 för -5,4545).
- **Kvarstående, klassificerade avvikelser (3 bolag, inte reparerade):**
  - **KAR** 2024/2025 — EBITDA betydligt lägre än EBIT (2024: EBITDA −239,5
    mot EBIT 146,0 — negativ EBITDA men positiv EBIT, ej förklarat).
  - **MSAB-B** 2008–2010 — konsekvent ~2 % gap (EBITDA något lägre än EBIT),
    litet men systematiskt över tre år; sannolikt en definitionsskillnad
    (poster som räknas i EBIT men inte EBITDA hos Börsdata), inte utredd
    djupare.
  - **VISC** 2022 — EBITDA (−25,66) mer negativ än EBIT (−20,24), implicit
    negativ avskrivning, ekonomiskt omöjligt om siffrorna är direkt
    jämförbara.
  - **Rekommendation:** flagga dessa 3 bolag/år som `identitet_avvikelse` i
    Spår C-panelen, exkludera inte automatiskt men använd inte okritiskt.

**ABB (och sannolikt andra USD-/utlandsrapporterande dubbelnoterade bolag)
testades INTE** i identitetskontrollen (valuta ≠ SEK, exkluderat by design).
Manuell kontroll av ABB visar `operating_Income` (efter currency_Ratio-
konvertering, som är en rimlig, verifierad kurs ~9,2 för 2025 — INTE
`R5`-buggen med kvot=1,0) ändå ~8× större än KPI-EBITDA, vilket INTE
reconcilierar i någon riktning (varken i USD eller efter SEK-konvertering).
**Detta är en oförklarad avvikelse specifikt i den REDAN GODKÄNDA
`reports`-datans `operating_Income`/`gross_Income` för ABB** — inte i den nya
KPI-historik-datan (vars interna konsistens, year(p=5)==r12(p=4), höll
perfekt även för ABB). Flaggas för separat granskning, rör inte befintlig
Spår B utan vidare utredning.

**INVE-A (Investor AB) och sannolikt andra investmentbolag** visar EBITDA
runt 210 000–270 000 MSEK för enskilda år — extremt högt jämfört med
operativa bolag, men EKONOMISKT FÖRVÄNTAT för investmentbolag vars
resultaträkning domineras av orealiserade/realiserade värdeförändringar i
portföljen (Investor ABs totala portföljvärde överstiger 1 000 miljarder
SEK). Klassificerat som en sektorsspecifik egenskap, inte ett datafel — bör
hanteras särskilt (t.ex. separat behandling eller exkludering av
investmentbolag) i Spår C, inte i denna datalager.

## 6. Restatement-/revisionsrisk

Oförändrat sedan sample-fasen (§6 i sample-dokumentet): INTE verifierbar
utan ett verkligt point-in-time-arkiv. Dokumenterad, accepterad begränsning,
identisk med den som redan gäller för `reports`-endpointen.

## 7. Nytt (ej åtgärdat) Spår A-fynd: EMPIR-B / SAFETY-B delar insId

Två Spår A-universumkoder (`EMPIR-B` "Ledstiernan AB" och `SAFETY-B`
"mySafety Group AB") delar SAMMA ISIN (SE0010769182) och Börsdata-insId
(147) — sannolikt samma instrument som bytt namn flera gånger utan att
kollapsas till en identitet i `instrument_master`. Konsekvens: all
KPI-/återköpsdata för detta instrument hamnade under `SAFETY-B` (198 rader),
`EMPIR-B` fick 0 rader (täckningslucka, inte korrupt data — byggskriptet
deduplicerar nu korrekt till senaste RAW-fil, se commit-historik i
`tools/build_validated_kpi_extra.py`). **Rör INTE Spår A nu** — dokumenterat
för framtida Spår A-uppföljning, i linje med instruktionen att inte ändra
Spår A utan uttryckligt nytt, dokumenterat fel.

## 8. Duplicering, negativa/ovanliga värden, strukturella brott

- **Dubbletter:** 198 exakta dubbletter hittades initialt (samma
  `(kod,kpi,report_type,year,period)` flera gånger) — samtliga spårade till
  §7:s insId-kollision (samma RAW-data hämtad två gånger under olika
  tidsstämplar). Byggskriptet uppdaterat att deduplicera till senaste
  RAW-fil per `(insId,kpi,reportType)`. **0 dubbletter kvar.**
- **Negativ EBITDA:** 688/4 585 helårsobservationer (15,0 %) — förväntat och
  ekonomiskt rimligt (förlustbolag, särskilt bland mindre/tidiga bolag i
  universumet), inte i sig ett fel.
- **Extremvärden (>200 000 MCURR):** 4 observationer, samtliga INVE-A
  (Investor AB) — se §5, klassificerat som sektorskaraktäristik.

## 9. Valuta (mandatets punkt 7, olöst öppen fråga)

KPI-historikens `{y,p,v}`-svar saknar eget `currency`-fält. `currency` och
`currency_Ratio` bärs med per datapunkt FRÅN DEN MATCHADE rapportraden
(samma period), men **appliceras inte automatiskt** på KPI-värdet — det är
okänt om Börsdatas KPI-system redan returnerar SEK-konverterade värden eller
råvärden i bolagets rapporteringsvaluta. Detta MÅSTE beslutas explicit innan
Spår C jämför EBITDA/Capex mellan instrument i olika valutor (se §5:s
ABB-exempel som antydan om att en enkel `×currency_Ratio`-applicering inte
uppenbart löser saken för alla bolag). Kvarstående, dokumenterad
öppen fråga — INTE löst i detta steg.

## 10. Sammanfattning

Ingen blockerande upptäckt. Datalagret (`validated/fundamenta_extra/`) är
byggt med tydlig RAW → PIT-mappning → QA-separation, alla avvikelser
klassificerade (inte tyst reparerade), och samtliga punkter i mandatets
checklista (PIT, coverage, definition, valuta [öppen fråga dokumenterad],
missingness, dubbletter, fiskalperiod-mappning, year/quarter/r12-konsistens,
negativa/ovanliga värden, strukturella brott, ekonomiska identitetskontroller)
är genomförda eller explicit dokumenterade som öppna frågor.

**Kvarstår innan Spår C kan använda dessa fält:** valutabeslutet (§9),
hantering av de 3+1 flaggade bolagen (§5), samt beslut om investmentbolag
som egen kategori.
