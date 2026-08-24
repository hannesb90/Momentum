# Spår B: reparation av valutakonverteringsfelet (2026-08-08)

Uppföljning av `docs/SPAR_B_VALUTAUTREDNING_2026-08-08.md`. Detta dokument
täcker reparation, ombyggnad, full diff, QA och downstream-konsekvensanalys.
**Ingen modellträning. Ingen utveckling av shareholder_yield/ROIC/Spår C.**

## A. Root cause

`tools/build_validated_fundamentals_final.py` multiplicerade samtliga
monetära `GODKANDA`-fält (22 fält, se §B) med `currency_Ratio` för att
"konvertera till SEK". Men Börsdatas `/reports`-endpoint returnerar dessa
fält **redan SEK-konverterade** (verifierat i föregående utredning mot
externt kända siffror — AstraZenecas 2023-omsättning, Evolutions, Hexagons —
samt mot Capex/kassaflödesidentiteter över samtliga 40 icke-SEK-bolag).
Resultatet var en dubbelkonvertering: redan-SEK-värden multiplicerades med
`currency_Ratio` en gång till.

**Fix:** multiplikationen borttagen. Radvärdet används oförändrat
(`rad[kol] = r.get(kol)`). Ingen annan logik ändrad.

## B. Exakt omfattning — fält och tabeller

**Samtliga tre tabeller** byggs av samma funktion (`bygg()`) med samma
`GODKANDA`-lista, och var alla drabbade identiskt:
- `fundamentals_year_validated.json` (år)
- `fundamentals_quarter_validated.json` (kvartal)
- `fundamentals_r12_validated.json` (R12/TTM)

**22 monetära fält** (samtliga `GODKANDA` utom `number_Of_Shares`, som
aldrig multiplicerades och alltså aldrig var fel):
`revenues, gross_Income, operating_Income, profit_Before_Tax,
profit_To_Equity_Holders, total_Assets, total_Equity,
total_Liabilities_And_Equity, current_Assets, current_Liabilities,
non_Current_Assets, non_Current_Liabilities, cash_And_Equivalents,
net_Debt, tangible_Assets, intangible_Assets, financial_Assets,
cash_Flow_From_Operating_Activities, cash_Flow_From_Investing_Activities,
cash_Flow_From_Financing_Activities, cash_Flow_For_The_Year,
free_Cash_Flow, earnings_Per_Share, dividend`.

**Ett tidigare, redan överskrivet skript** (`tools/build_validated_fundamentals.py`,
icke-slutlig version, mtime 02:48 — överskriven av `_final.py` mtime 02:59)
hade samma buggmönster men producerade aldrig den nu gällande frysta datan;
ingen åtgärd behövs där.

**Den nya KPI-utökningen** (`validated/fundamenta_extra/`, EBITDA/Capex från
KPI-historik-endpointen) var INTE drabbad — den byggs av ett separat skript
(`build_validated_kpi_extra.py`) som aldrig applicerade någon
valutakonvertering (dokumenterat som öppen fråga i föregående rapport, nu
löst genom denna utredning: KPI-historikens värden är i lokal
rapporteringsvaluta och kan nu, med bekräftad riktning, multipliceras med
`currency_Ratio` vid behov i Spår C).

## C. Före/efter-resultat

Fullständig diff: `docs/probes/sparB_valutafix_diff.json`. Sammanfattning:

| tabell | rader totalt | instrument berörda | SEK-rader testade | SEK-rader oväntat ändrade |
|---|---|---|---|---|
| år | 4 847 | 40 | 104 784 | **0** |
| kvartal | 12 280 | 41 | 264 000 | **0** |
| R12 | 12 269 | 41 | 263 712 | **0** |

- **Radnycklar (insid,year,period) identiska** före/efter i alla tre
  tabeller (verifierat via assert) — inga rader tillagda/borttagna, bara
  värden korrigerade.
- **Förändringsfaktor per fält:** median ×9,6–10,4 (EUR/USD/PLN, som
  tidigare var uppräknade för högt) ner till ×0,064 (ISK, som tidigare var
  nerräknat, eftersom 1 ISK ≈ 0,06–0,08 SEK). Konsekvent med respektive
  valutas verkliga `currency_Ratio` — exakt den dubbelkonvertering som
  förväntades, i båda riktningar.
- **Valutor berörda:** EUR, USD, NOK, PLN, ISK. Inga DKK-bolag i
  universumet (bekräftat, 0 träffar).
- **PIT-regelutfall (R1–R5) identiskt** i alla tre tabeller före/efter —
  exakt samma antal uteslutna rader per regel, exakt samma slutgiltiga
  radantal (4 847/12 280/12 269 — matchar det tidigare frysta antalet).
  **PIT-reglerna är inte rörda.**
- **Inga nya `null`-värden, inga `null`→värde-flippar, `number_Of_Shares`
  helt oförändrat** (0 avvikelser, kontrollerat rad för rad).

## D. QA efter ombyggnad

- **PIT/look-ahead:** identiskt regelutfall som §C — R1–R5 opåverkade.
- **EBITDA ≥ EBIT** (mot den REPARERADE `operating_Income`, EBITDA
  SEK-konverterad för icke-SEK-bolag): **4 542/4 551 (99,80 %)**. Samma
  klassificerade avvikelser som i föregående utredning (KAR×2, MSAB-B×3,
  VISC, CCC, IPCO) plus **en ny, marginell** (EVO 2024, 16 161 mot 16 262 —
  0,6 % gap, samma kategori som MSAB-B:s små systematiska gap). Ingen
  reparerad, samtliga klassificerade som bolagsspecifika avvikelser.
- **Capex mot kassaflöde:** 4 453 observationer, median \|Capex/CFI\| = 1,000
  efter korrekt SEK-konvertering, 100 % inom rimligt intervall [0,5, 1,5].
- **Representativa stickprov** (SEK: SWED-A/ALLIGO-B, EUR: EVO/HEXA-B, USD:
  AZN/ABB, NOK: SMCRT/MORROW) — samtliga värden nu i rimlig, verifierbar
  SEK-skala. Exempel: AZN 2023 `revenues=462 136,79` MSEK (≈458 mdr SEK,
  matchar ~45,8 mdr USD × ratio 10,09).
- **Extremvärden:** 0 kvarstående observationer med `revenues` > 1,5
  biljoner SEK (fanns tidigare, bl.a. AZN:s 4,66 biljoner SEK).
- **Dubbletter:** 0 (radnycklar unika, verifierat).

## E. Downstream-påverkan — vad måste köras om

**Direkt beroende av den nu ombyggda `validated/fundamentals/*.json`:**

1. **`panels/core_fundamenta_panel.json`** (Spår C, CORE+FUNDAMENTA-panelen,
   byggd av `tools/spar_c_features_fundamenta_v2.py` från
   `fundamentals_r12_validated.json`). **UGILTIG** — byggd på buggig data.
   **36 av de 40 valutadrabbade bolagen finns i panelen, 2 413/28 539
   panelrader (8,5 %) tillhör dem.** Samtliga fundamenta-features som
   involverar en absolut monetär storhet (inte en ren kvot inom samma
   bolag/period) är påverkade: `net_debt_to_equity`, `equity_ratio_ttm`,
   `asset_turnover_ttm`, `revenue_growth_yoy`, `dividend_yield_ttm` m.fl. —
   se `docs/SPAR_C_BLUEPRINT_OCH_CLOSURE.md` för fullständig fältlista.
   **Måste byggas om helt från den reparerade datan.**
2. **`validated/manifest_sparC.json`** — dokumenterar den ogiltiga panelen.
   Måste skrivas om vid ombyggnad.
3. **`docs/probes/spar_c_qa.json`** (Spår C:s PIT-/leakage-/coverage-QA) —
   kördes mot den ogiltiga panelen. Måste köras om.
4. **`docs/probes/fundamenta_panel_build_v2.json`** och feature-registret
   — byggda från ogiltig data, måste byggas om.
5. **`tools/fund_split_verify.py`** — läste `fundamentals_year_validated.json`
   (buggig) för EPS-baserad splitverifiering. De **tio namngivna, specifikt
   kontrollerade bolagen** (Humana, Holmen, Carasent, Paradox Interactive,
   Hufvudstaden, Avarda Bank, Volati, NAXS, NCC, New Wave Group) är
   SEK-rapporterande och alltså INTE bland de 40 valutadrabbade bolagen —
   dessa specifika slutsatser kvarstår giltiga. Men **aggregatstatistiken**
   i manifestet (`eps_konsistens_generellt_under_10pct: 0.973`,
   `eps_konsistens_kring_split_under_10pct: 0.899`) beräknades över HELA
   populationen inklusive de 40 buggiga bolagen och **bör räknas om**, även
   om den sannolikt inte ändras dramatiskt (40/353 ≈ 11 % av populationen).
6. **`docs/FUNDAMENTAL_QA.md`** — dokumenterar fältklassificering och
   splitverifiering baserat på den nu ersatta datan. Bör uppdateras med en
   hänvisning till valutabuggen och detta dokument.

**INTE påverkat** (verifierat, ingen ombyggnad behövs):
- Spår A (priser) — helt oberoende, aldrig läst fundamentadata.
- `panels/target_table.json` — pris-/targetbaserad, ingen
  fundamentadata-koppling.
- `panels/core_panel.json` (rena momentum-/prisfeatures) — ingen
  fundamentadata-koppling.
- `validated/fundamenta_extra/` (KPI-utökningen) — byggd av separat skript,
  aldrig applicerat felaktig konvertering.

## F. Kan Spår B frysas på nytt?

**Strukturellt: ja** — ombyggnaden är komplett, PIT-reglerna är verifierat
oförändrade, SEK-bolag är verifierat oförändrade, samtliga QA-kontroller
(identitet, kassaflöde, extremvärden, dubbletter, nulls) passerar rent, och
root cause är entydigt fastställd och åtgärdad (inga bolagsspecifika
specialfall).

**Formellt: inte förrän explicit godkänt**, i enlighet med instruktionen att
inte tyst skriva över den gamla frysningen. Nuvarande status i
`validated/manifest_sparB.json`: `"SPÅR B OMBYGGD ... EJ ÄNNU SLUTGILTIGT
FRYST"`.

**Gammal (ogiltig) data bevarad, inte tyst överskriven:**
`validated/_SUPERSEDED_2026-08-08_valutabugg/` innehåller de tre gamla
tabellfilerna och `manifest_sparB_INVALID.json` (gammal kombinerad sha256:
`9da73a883721b9cb77d67570d17821e4d20903a491e190adb0ec990cddf368c8`).
Ny kombinerad sha256 (ombyggd, ej ännu formellt fryst):
`93b0e884c58fe8076b852248711b04fb69dad59303655dd877cc20a241ae7f97`.

**Rekommendation:** godkänn Spår B-ombyggnaden formellt, uppdatera
`README.md`-statustabellen (redan gjort, se nedan), markera
`panels/core_fundamenta_panel.json` och `validated/manifest_sparC.json`
som ogiltiga i väntan på ombyggnad, och invänta uttrycklig instruktion
innan Spår C, shareholder_yield eller ROIC-arbetet återupptas.

**Stoppar här enligt instruktion.**
