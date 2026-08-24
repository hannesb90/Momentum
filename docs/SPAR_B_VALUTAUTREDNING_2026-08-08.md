# Spår B: valutautredning — KRITISKT FYND i redan fryst data

Datum: 2026-08-08. Utredning enligt uttryckligt mandat (löser valutafrågan för
KPI-historiken, utreder ABB-avvikelsen end-to-end, klassificerar samtliga
EBITDA<EBIT-observationer). **Ingen modellträning. Ingen reparation utförd
— endast utredning, dokumentation och rapportering, enligt instruktion.**

## SAMMANFATTNING — KRITISKT FYND

**Den redan frysta, "GODKÄNDA" Spår B-fundamentadatan
(`validated/fundamentals/fundamentals_*_validated.json`, byggd av
`tools/build_validated_fundamentals_final.py`) innehåller en
valutakonverteringsbugg som DUBBELKONVERTERAR samtliga icke-SEK-rapporterande
bolag.** Exempel: AstraZeneca (AZN) 2023 lagras med `revenues: 4 661 989.69`
(miljoner SEK) — det vill säga en påstådd omsättning på **4,66 biljoner
SEK (~462 miljarder USD)**. AstraZenecas verkliga 2023-omsättning var cirka
45,8 miljarder USD. Det lagrade värdet är alltså **~10 100× för stort**.

**Detta är INTE ett ABB-specifikt fel** (uppgift 2) **och rör INTE Spår A
eller PIT-reglerna** (temporal korrekthet) — det är ett generellt
skal-/valutafel i Spår B:s befintliga, redan godkända normaliseringssteg,
som drabbar **40 bolag, 473 bolag-år-rader** i den frysta årsdatan (plus
motsvarande i kvartals-/R12-tabellerna, ej ännu kvantifierat rad för rad).

**Ingen ändring har gjorts.** Rapporteras enligt instruktion innan vidare
arbete.

## 1. Rotorsak

`tools/build_validated_fundamentals_final.py` rad ~90-94:
```python
for kol in GODKANDA:
    v = r.get(kol)
    if v is not None and ratio and kol != "number_Of_Shares":
        v = v * ratio
```
Koden antar att RÅVÄRDET (`r.get(kol)`) är i bolagets rapporteringsvaluta
(t.ex. USD) och att `currency_Ratio` (lokal valuta → SEK) ska MULTIPLICERAS
in för att få SEK.

**Detta antagande är fel.** Börsdatas `/reports`-endpoint returnerar
`revenues`, `operating_Income`, `cash_Flow_From_Investing_Activities` m.fl.
**redan SEK-konverterade**, inte i bolagets rapporteringsvaluta.
`currency_Ratio` är alltså inte "multiplicera för att få SEK" — det tvärtom
möjliggör att gå TILLBAKA till lokal valuta genom DIVISION.

## 2. Bevisföring (uppgift 1 — valutafrågan för KPI-historiken)

### 2.1 Extern verifiering mot kända, offentliga siffror

| bolag | år | KPI-historik (kpiId 53, Omsättning), RAW | reports.revenues, RAW | reports.revenues ÷ ratio | verklig, offentligt känd omsättning |
|---|---|---|---|---|---|
| AstraZeneca (AZN) | 2023 | **45 811** | 462 136,79 (ratio 10,0879) | **45 811** | ~45,8 miljarder USD ✓ EXAKT MATCH |
| Evolution (EVO) | 2023 | **1 798,6** | 20 031,03 (ratio 11,137) | **1 798,6** | ~1,8 miljarder EUR ✓ MATCH |
| Hexagon (HEXA-B) | 2023 | **5 435,2** | 60 531,85 (ratio 11,137) | **5 435,2** | ~5,4 miljarder EUR ✓ MATCH |

**Slutsats: KPI-historikens värden (EBITDA, Capex, Omsättning m.fl.) är i
bolagets EGEN RAPPORTERINGSVALUTA, INTE SEK.** `reports`-endpointens RAW-fält
är TVÄRTOM redan SEK-konverterade.

### 2.2 Populationstest (samtliga icke-SEK-bolag, inte bara stickprov)

Testat mot samtliga 40 bolag med rapporteringsvaluta ≠ SEK i universumet
(EUR 24, USD 11, NOK 3, plus PLN/ISK som framkom vid granskning av den
frysta datan). Ingen bolag med DKK-rapportering finns i universumet
(bekräftat empiriskt, 0 träffar).

**Omsättning** (kpiId 53) mot `reports.revenues`, 18 bolag × flera år:
- Antagande "KPI = reports RAW" (befintlig pipelines implicita antagande):
  kvot varierar 0,08–1,0 beroende på valuta — INGEN konsekvent relation.
- Antagande "KPI = reports RAW ÷ ratio": kvot = 1,000 (±0,0001) för
  SAMTLIGA testade bolag/år, oavsett valuta (EUR/USD/NOK) och oavsett att
  växelkursen (`ratio`) varierar år för år. **Entydigt bevisat.**

**EBITDA vs EBIT-identitet** (EBITDA ≥ EBIT ekonomiskt sett), 40 bolag,
441 bolag-år-observationer:
| tolkning | godkända | andel |
|---|---|---|
| A: EBITDA(kpi) och EBIT(reports) i samma valuta | 94/441 | 21,3 % |
| B: EBIT(reports) redan SEK, EBITDA(kpi) lokal — jämför EBITDA×ratio mot EBIT | **439/441** | **99,5 %** |

**Capex** mot `cash_Flow_From_Investing_Activities` (proxy, 40 bolag,
426 observationer): medianen av \|Capex×ratio ÷ CFI\| = **1,000** (Capex
utgör i praktiken hela investeringskassaflödet, väntat). Medianen av
\|Capex ÷ CFI\| utan konvertering = 0,104 — ingen meningsfull relation.

**Samtliga tre oberoende test (omsättning mot extern fakta, EBITDA mot EBIT,
Capex mot kassaflöde) pekar entydigt åt samma håll.**

### 2.3 Beslut om produktionskonvertering

**KPI-historikens EBITDA/Capex-värden är i bolagets rapporteringsvaluta.**
För att jämföra tvärsnittsmässigt i Spår C måste de multipliceras med
`currency_Ratio` från motsvarande rapportrad (samma (år,period)-koppling som
redan används för PIT-mappning) — INTE lämnas okonverterade. Detta är nu
verifierat, inte ett antagande, och kan implementeras i nästa steg.

## 3. ABB-avvikelsen (uppgift 2) — förklarad, generell, inte ABB-specifik

Ursprungsfyndet (`docs/SPAR_B_KPI_HISTORIK_FULLSKALA.md` §5): ABBs
`operating_Income` (55 794, 2025) verkade ~8× för stort mot KPI-EBITDA
(6 860). Med korrekt valutariktning:
- KPI-EBITDA (lokal, USD) × ratio (9,2268) = **63 296 SEK-ekvivalent**
- `operating_Income` (reports, redan SEK) = **55 794**
- 63 296 ≥ 55 794 ✓ — identiteten håller (implicit D&A ≈ 7 500 SEK-ekv. ≈
  813 MUSD, rimligt för ABB).

**Felet var i min egen jämförelsemetodik i föregående rapport (fel
valutariktning antagen), inte i data.** Sökt efter andra instrument med
samma mönster: samtliga 40 icke-SEK-bolag uppvisade samma "avvikelse" innan
korrigering (21,3 % godkänt) och samma icke-avvikelse efter (99,5 %
godkänt) — **generellt, inte ABB-specifikt**, exakt som misstänkt i
mandatets uppgift 2.

## 4. Samtliga EBITDA<EBIT-observationer, klassificerade (uppgift 3)

Efter korrekt valutahantering (multiplicera EBITDA med `currency_Ratio` för
icke-SEK-bolag före jämförelse):

- **6 841 SEK-bolag-år + 441 icke-SEK-bolag-år = 7 282 testade.**
- **7 271 godkända (99,85 %).**
- **11 kvarstående avvikelser, samtliga individuellt klassificerade, INGEN
  reparerad:**

| bolag | år | valuta | ebitda (lokal/SEK-konv.) | ebit (SEK) | klassificering |
|---|---|---|---|---|---|
| KAR | 2024 | SEK | −239,5 | 146,0 | Oförklarad, EBITDA negativ men EBIT positiv — flaggad |
| KAR | 2025 | SEK | 709,9 | 1123,0 | Oförklarad, ~37 % gap — flaggad |
| MSAB-B | 2008–2010 | SEK | −(~2 %) | — | Litet, systematiskt gap 3 år i rad — sannolik definitionsskillnad, ej utredd djupare |
| VISC | 2022 | SEK | −25,66 | −20,24 | Implicit negativ avskrivning — omöjligt, flaggad |
| CCC (Cavotec) | 2017 | EUR | −331,3 (SEK-konv.) | −177,1 | Implicit negativ avskrivning efter korrekt konvertering — flaggad |
| IPCO | 2024 | USD | 1494 (SEK-konv.) | 2152,0 | ~31 % gap efter korrekt konvertering — flaggad, ej utredd djupare (olje-/gasbolag, kan bero på engångsposter) |

**Ingen av dessa 11 har reparerats.** De ska exkluderas från okritisk
användning i Spår C och flaggas per bolag/år, i enlighet med instruktionen
"ändra inga värden utan verifierad orsak."

## 5. Omfattning av den frysta datans dubbelkonverteringsbugg

Kontrollerat direkt mot `validated/fundamentals/fundamentals_year_validated.json`:

- **40 unika bolag, 473 bolag-år-rader** i årsdatan har `currency ≠ SEK` OCH
  `currency_ratio ≠ 1.0` — samtliga dessa rader är dubbelkonverterade
  (inflaterade med en faktor ≈ `currency_ratio`, dvs. ~9–11× för
  EUR/USD-bolag).
- Valutor berörda: EUR (285 rader), USD (158), PLN (16), NOK (14), ISK (8).
- Bolag berörda inkluderar flera stora, likvida Nasdaq Stockholm-bolag:
  **AstraZeneca, ABB, Evolution, Hexagon, Nordea (NDA-SE), EQT, Betsson,
  Troax, Tietoevry, Sampo** m.fl. — inte perifera småbolag.
- Kvartals- och R12-tabellerna (`fundamentals_quarter_validated.json`,
  `fundamentals_r12_validated.json`) byggs av SAMMA kodsnutt och är
  sannolikt lika drabbade — inte radräknat än, men bedöms strukturellt
  identiskt.

**Detta är ett fel i redan fryst, tidigare godkänd Spår B-data — inte i
Spår A och inte i PIT-tidsreglerna.** Ingen ändring har gjorts i väntan på
instruktion.

## 6. Vad som INTE är ändrat

- Spår A: orört.
- PIT-reglerna (R1–R4, tidsmässig giltighet av `report_Date`): orörda —
  detta är ett SKALNINGS-/valutafel, inte ett tidsfel.
- `validated/fundamentals/*.json` (den frysta, "GODKÄNDA" datan): orörd.
- `tools/build_validated_fundamentals_final.py`: orörd.
- Den nya KPI-historik-datan (`validated/fundamenta_extra/`): orörd sedan
  föregående rapport — dess RAW-värden är (nu verifierat) redan korrekta i
  sin egen rapporteringsvaluta; det som saknas är själva
  SEK-konverteringssteget, inte en reparation av data.

## 7. Rekommendation (för beslut, inte utfört)

1. **`build_validated_fundamentals_final.py` behöver en riktningskorrigering**
   för `GODKANDA`-fälten: dividera med `currency_Ratio` (eller helt enkelt
   inte multiplicera alls, om målet är SEK och råvärdet redan är SEK) —
   kräver ett uttryckligt beslut och en fullständig ombyggnad av den frysta
   Spår B-datan, med ny SHA256 och nytt manifest.
2. Kvartals-/R12-tabellerna bör kontrolleras med samma metodik innan någon
   ombyggnad.
3. De 11 flaggade EBITDA/EBIT-avvikelserna (§4) bör förbli exkluderade tills
   vidare, oavsett hur valutafrågan löses.
4. Detta bör sannolikt hanteras som en EGEN, uttrycklig uppgift givet
   omfattningen (påverkar redan fryst, "GODKÄND" data — inte bara den nya
   KPI-utökningen) — inte antas ingå automatiskt i shareholder_yield-/
   ROIC-arbetet.

**Stoppar här enligt instruktion. Väntar på besked innan fortsatt arbete.**
