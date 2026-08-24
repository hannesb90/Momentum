# Verifiering och kontrollerad återbyggnad efter independent second review

Datum: 2026-08-08. All modellträning, tuning, feature selection och targetbaserad optimering var stoppad under arbetet. Fynden verifierades mot faktisk kod och hela aktuella datasetet före patchning.

## Slutbesked

**B) Ytterligare blockerare finns. A/B/C + target är INTE redo för Spår D.**

Blockerarna är:

1. historiskt Nasdaq Stockholm Large/Mid/Small-membership kan inte rekonstrueras fullständigt ur tillgängliga V2-källor;
2. den falsifierande efterkontrollen hittade en ytterligare prisnivå/enhetskonflikt i `fcf_yield_ttm` (och därmed otillräckligt bevisad market-cap-konstruktion);
3. fundamentaldata för 67/68 avnoterade bolag saknas fortfarande strukturellt;
4. buyback/shareholder-yield saknar verifierad FX-, correction- och cashflow-definition;
5. V2 saknar egen gitidentitet och A läser ett externt legacy-arkiv.

`manifest_sparA.json` och `manifest_sparC.json` är uttryckligen markerade EJ FRYST/OGILTIG. `README.md` har en STOPP-banner.

## 1. Target och falsk avnotering

### Verifiering före ändring

Hypotesen var korrekt. `spar_c_target.py` använde `serie_slut < sista_global` som direkt proxy för `genuint_avnoterat`.

- terminaltargets: **893 rader, 73 instrument**;
- med explicit avnoteringsdatum i instrument_master: **828 rader, 68 instrument**;
- enbart kort prisserieslut: **65 rader, 5 instrument**;
- falskt klassade koder: `FLERIE`, `KDEV`, `FPIP`, `MAHA-A`, `NYF` (13 rader vardera);
- horisont: min 0, median 174, max 363 dagar;
- `<30`: 84; `<90`: 236; `<180`: 462; `<364`: 893; `0 dagar`: 11.

Second-review-fyndet är alltså **bekräftat**, inklusive alla fem namngivna instrument.

### Beslut och reparation

Kortare terminalavkastning är **inte jämförbar** med preregistrerad 52v-avkastning: exponeringstid, riskackumulering och uppköps-/konkursmekanik skiljer sig. Targetdefinitionen ändrades därför inte.

- `target_fwd52w` fylls endast vid full 52v-horisont.
- `validated/terminal_events.json` byggs endast från explicit `avnoterad_datum` + evidenstext i instrument_master.
- kort terminalutfall lagras separat som `terminal_return`, `terminal_horisont_dagar`, `terminal_event_type`, `terminal_event_date`.
- prisserieslut infererar aldrig terminalevent.

Efter återbyggnad: 25 026 fulla 52v-targets, 5 344 null p.g.a. ofullständig horisont, 828 separata verifierade terminalutfall och **0** falska terminalutfall för de fem koderna. Full återräkning av 30 370 targetrader gav 0 PIT-, värde- och typfel.

## 2. Pris × volym och övriga prisnivåfeatures

Hypotesen var korrekt och materiell. Före ändring hade 388 139/581 115 rader `|adjusted_close/close-1|>1%`; 47 171 hade faktor `<0,5` eller `>2`.

Drabbade byggda CORE-features:

- `turnover_13w_msek`;
- `illiquidity_amihud_13w`.

`volume_trend_13w` använder endast volym och var inte drabbad. Blueprint-kandidater som inte är byggda påverkar ingen aktuell panel.

Spår A bevarar nu både `adj` (totalavkastning) och QA-filtrerad ojusterad `close` (ekonomisk prisnivå). CORE använder `close×v`; dagsavkastning i Amihuds täljare använder fortsatt `adj`.

Före/efter: 21 180 turnover-observationer och 21 173 Amihud-observationer ändrades; coverage var oförändrad (95,7 % respektive 95,6 %). `volume_trend_13w` ändrade 0 observationer.

Den bredare inventeringen hittade dessutom `dividend_yield_ttm` och `fcf_yield_ttm` med `adj` som prisnivå. De ändrades till `close`, vilket ändrade 14 350 respektive 19 483 observationer. Detta blottlade i efterauditen extremt orimliga FCF-yields (t.ex. `FLERIE` ned till −576 742), alltså en olöst konflikt mellan prisserie, antal aktier, ekonomisk identitet och/eller enhet. **C stoppas därför trots passerad strukturell QA.** Ingen approximation infördes.

## 3. Spår B completeness

### EBITDA och Capex

- 61 874 inputvärden; 56 874 PIT-godkända outputvärden.
- 346/353 live-Börsdata-instrument har data för respektive KPI; median 16 år.
- KPI-värdena är i lokal rapporteringsvaluta. Oberoende Capex/CFI-test gav före konvertering median 0,093 EUR, 0,107 USD, 0,418 PLN och 13,15 ISK; efter `×currency_ratio` ≈1,000 i alla grupper.
- Finalen har nu `value_local` och `value_sek=value_local×currency_ratio` exakt en gång.
- EBITDA/Capex: **GODKÄNDA OCH MANIFESTERADE** i `manifest_sparB_extra.json`, hash `f7d6d99cebd9358f9af587e9827723b19ab3f5c9f15b121e2f8b4a39c33db846`.

### Buybacks, KPI 213–215 och shareholder yield

- fullskalan hämtade transaktionsendpointen, inte KPI 213–215; KPI:erna fanns endast i sample;
- 42 802 transaktioner och 146 verifierade noll-svar;
- valutor inkluderar SEK/EUR/NOK/ISK/DKK/CHF; `change` har både positiva och negativa poster och `shares_proc` har extrema värden.

Klassning:

- transaktionstabell: godkänd som rå/PIT-daterad tabell;
- KPI 213–215: **UTESLUTNA**, inte fullskalehämtade och kalenderaggregat;
- shareholder yield: **UTESLUTEN**, ingen verifierad FX/correction/cashflow-definition;
- `roic_proxy_ttm`: befintlig före-skatt-proxy, inte sann ROIC och inte ersatt av extra-data.

EBITDA/Capex ligger ännu inte i C-panelen. Blueprint/C måste kompletteras först efter att membership och FCF/mcap-blockeraren lösts; featuredesign får inte fortsätta innan dess.

## 4. Historiskt universum/PIT-membership

Fyndet är bekräftat. `build_validated_prices.py` väljer live-ISIN vars nutida Börsdata `marketId` är 1/2/3 och applicerar dem bakåt över prisserien. Prisexistens bevisar varken huvudlistenotering eller investerbar membership.

`docs/probes/membership_pit_audit.json` använder endast explicit destination till Nasdaq Stockholm/Nordiska listan/O-/A-listan som entryevidens:

- panelkoder: 420;
- koder med explicit identifierbar huvudliste-entry: 77;
- koder utan komplett explicit entrysignal: 343;
- verifierad lägstanivå före entry: **254 panelrader, 8 instrument**.

De åtta är `CCC` (72), `AJA-B` (59), `FNOX` (30), `MANG` (28), `CS` (23), `CIBUS` (19), `TRIAN-B` (13), `OX2` (10). Detta är en säker lower bound, inte en uppskattning av hela felet. Ett exakt totalantal kan inte ärligt anges med nuvarande källor; därför markeras kedjan blockerad i stället för att okända intervall fylls med dagens status.

## 5. Entity resolution/dubbla koder

Instrument_master har 24 EODHD-koder med flera poster; 15 ingår i aktuell A och 9 ligger utanför A. A-buildern konsoliderar nu kodgruppen explicit och stoppar vid motstridigt ISIN, active/delisted-status eller terminaldatum. Kanoniskt namn väljs deterministiskt mot EODHD-namnet; ekonomiska attribut är gruppvaliderade. Faktisk vald slug och samtliga alias finns i `manifest_sparA.json.entity_resolution`.

| Kod | ISIN | poster/alias (giltighetsindikator = första notering) | används i A |
|---|---|---|---|
| ACAD | SE0007897079 | AcadeMedia 2016 / gamla 1998 | ja |
| BESQAB | SE0010547786 | Besqab 2018 / Besqab Bostadsutveckling 2014 | ja |
| CAPIO | SE0007185681 | Capio 2015 / gamla 2000; avnot. 2018-11-28 | nej |
| CCC | SE0025010887 | Cavotec SA 2011 / Cavotec Group 2025 | ja |
| WISE | SE0007277876 | Dagon 2000 / Wise 2007 | ja |
| DMYD-B | SE0005162880 | Diamyd 2013 / Mertiva 1997 | nej |
| FABG | SE0011166974 | Drott 1998 / Fabege 1990 | ja |
| TESSIN | SE0009522451 | Effnetplattformen 2021 / Tessin 2017 | nej |
| FOI-B | CH0242214887 | Fenix Outdoor / International 2014 | ja |
| GRNG | SE0006288015 | Gränges 2014 / Sapa 1997 | ja |
| IAR-B | SE0005851706 | IAR 2000 / IAR Group 1999; terminal 2025-11-03 | ja |
| SAFETY-B | SE0010769182 | Ledstiernan 1995 / mySafety 1998 | ja |
| LARK | SE0016101935 | Lärkberget 2015 / Novakand 2011 | nej |
| NEO-B | SE0016830038 | Mashup 2019 / Neovici 2024 | nej |
| MCOV-B | SE0009778848 | Medicover AB 2017 / Holding S.A 1997 | ja |
| MTRS | SE0009806607 | Munters 1997 / Munters Group 2017 | ja |
| NDA-SE | FI4000297767 | Nordea Bank AB 1997 / Abp 2018 | ja |
| NWG | DK0060738409 | Nordic Waterproofing AB 2020 / A/S 2016; terminal 2025-03-24 | ja |
| SAVE | SE0015192067 | Nordnet gamla 2000 / Nordnet 2020 | ja |
| ORI | saknas | Oriflame Cosmetics 2004 / Holding 2015; terminal 2019-07-17 | nej |
| PFE | US7170811035 | Pfizer 2003 / Pharmacia 2000 | nej |
| TWW-SDB-B | saknas | Transcom AB 2014 / S.A 2001; terminal 2014-11-24 | nej |
| VEFAB | SE0016128151 | VEF AB 2021 / VEF Ltd SDB 2015 | ja |
| VNIL-SDB | saknas | VNV Global 2007 / Vostok Gas 1997 | nej |

Detta eliminerar implicit last-one-wins i A-bygget, men tabellen visar samtidigt varför fulla tidsintervall och predecessor/successor fortfarande behövs för membership och fundamental attribution.

## 6. Återbyggnad och före/efter

Ordning: A → B-extra (B-main oförändrad) → C CORE → C FUND → target. Ingen modellkod kördes.

| Artefakt | före | efter |
|---|---:|---:|
| A instrument/rader | 420 / 581 115 | 420 / 581 115 |
| C instrument/rader | 420 / 30 370 | 420 / 30 370 |
| fulla 52v-targets | 25 026 | 25 026 |
| terminal i canonical target | 893 | 0 |
| separata verifierade terminalutfall | 0 | 828 |
| paneldatum | 86 | 86 |
| has_fundamenta | 27 121 / 30 370 (89,3 %) | oförändrat |

SHA256 efter:

- A prices: `e3ed38b8e89a25149e61b71c8e0c91b8adbd2dab22b282bc156b1214987f17b4`;
- B main combined: `725b9db6c25a4b92e08fd990976b326463c0983c0836229d67e9b7711415b4be`;
- B-extra: `f7d6d99cebd9358f9af587e9827723b19ab3f5c9f15b121e2f8b4a39c33db846`;
- CORE: `0b169a56a9f832c9e9bf26c57d1e675156362bb3564f7144fa6c57568e6be6b7` (före `14b44f11…`);
- CORE+FUND: `80f0915821d1c2354c9b381571c87386905e01cba2924b1c98b0c8036e2862e6` (före `757acc41…`);
- target: `517859f4942303de5483de1d55745393a2c4c37224ebc6b0508cba7b73bbef28` (före `492c2a5d…`);
- terminal events: `f437650e06e7a4405a922725d8415dc5b55fdca4df511aa72cc31bf6e47c7a8a`.

Exakta ändringsmängder: turnover 21 180; Amihud 21 173; dividend yield 14 350; FCF yield 19 483; canonical target 893. Nycklar/radantal ändrades inte.

## 7. Regression och ny pre-model falsifiering

- `tools/regression_second_review.py`: PASS (581 115 priser, 30 370 CORE/target, 68 A-terminalevents, 828 separata terminalutfall, 56 874 extra-KPI-rader).
- `tools/spar_c_qa.py`: 30 370 targetrader återräknade, 0 PIT-/värde-/typfel; CORE/FUND-nycklar identiska; 0 fundamenta-look-ahead.
- `tools/audit_membership_pit.py`: BLOCKERAD, 254 verifierade pre-entry-rader och 343 koder utan komplett explicit entrysignal.
- Ny ekonomisk extremvärdesfalsifiering: `fcf_yield_ttm` misslyckades (se §2). Strukturell QA är alltså nödvändig men inte tillräcklig.

## 8. Fynd som var falska eller behövde nyanseras

- De fem namngivna terminalfallen var inte genuina avnoteringar: reviewern hade rätt.
- Alla korta prisserier var däremot inte falska: 68/73 hade explicit terminalevidens. Felet var inferensregeln, inte att samtliga terminaler saknade stöd.
- `volume_trend_13w` delar inte pris×volymfelet; den använder bara volym.
- KPI 213–215 ligger inte i fullskaleextra trots att sample-kod känner till dem; fullskalan använder en separat transaktionsendpoint.
- EBITDA/Capex är inte redan SEK-normaliserade; här är `currency_ratio`-multiplikation korrekt exakt en gång, till skillnad från `/reports`-fälten.

## 9. Krav innan ny omkörning/frysning

1. Skaffa/verifiera daterade huvudliste-membershipintervall för samtliga 420 instrument, inklusive transfers, re-IPO, redomiciliering och aktieslagsperioder.
2. Lös `fcf_yield_ttm` genom verifierad tidsdaterad shares outstanding/enhet och economic-entity-kontinuitet; inga justeringsfaktorsapproximationer.
3. Besluta om EBITDA/Capex ska integreras i en ny, preregistrerad C-version.
4. Låt buyback/shareholder yield förbli exkluderad eller bygg verifierad FX/correction/cashflow-logik.
5. Återbygg därefter A → B → C → target, kör full QA/regression och skapa ett nytt C-manifest; nuvarande C-manifest är avsiktligt ogiltigt.

**Arbetet stoppades vid de nya strukturella blockerarna. Ingen modellering utfördes.**

## 10. Uppföljande åtgärd 2026-08-08 — Nasdaq membership och monetär prisbasis

Efter användarens uppföljning verifierades den tidigare Nasdaq-koden i
`momentum_prod_work`. Den hämtade dagens Nasdaq-marknader och en separat OMXS30-fil;
den var inte en komplett huvudliste-ledger. Däremot publicerar Nasdaq officiella
"Changes to the list"-arkiv och daterade admission notices. Dessa verifierade följande
post-start-inträden i V2-universumet: `MAHA-A` 2020-12-16, `TRIAN-B` 2020-12-17,
`CIBUS` 2021-06-01, `MANG` 2022-02-24, `OX2` 2022-04-06, `FNOX` 2022-04-13 och
`CS` 2022-12-19. `CCC` och `AJA-B` var falska positiva i den första
Skatteverket-lägregränsen: senare namn-/domicilhändelse får inte tolkas som första
huvudlisteinträde.

Ny källbunden artefakt: `validated/membership_main_list_pit.json`, byggd av
`tools/build_membership_main_list_pit.py`. CORE-index, CORE-panel och target läser nu
samma ledger. **136 pre-entry-panelrader togs bort**: MAHA-A 13, TRIAN-B 13, CIBUS 19,
MANG 28, OX2 10, FNOX 30 och CS 23. Efter ombyggnad finns 0 rader före ledger-entry.
För övriga koder är medlemskap vid studiestart 2020-01-01 en explicit baseline-
antagandepunkt, inte en inferens från prisexistens.

Den ekonomiska falsifieringen av `fcf_yield_ttm` visade en bredare felklass än först
antaget. För FLERIE ger EODHD `close=0,0003` medan Börsdatas samtida rapportprisintervall
är hundratals SEK; samma fundamentarad uppfyller samtidigt EPS-identiteten. EODHD:s
historiska `close` kan därför inte generellt bevisas vara faktiskt ojusterat handelspris
på en per-aktie-basis kompatibel med Börsdata. Ingen splitapproximation infördes.
Följande features är nu explicit **UTESLUTNA och alltid null**:

- `turnover_13w_msek` och `illiquidity_amihud_13w` (kräver QA-godkänt ojusterat pris×volym),
- `dividend_yield_ttm` och `fcf_yield_ttm` (kräver QA-godkänd per-aktie/PIT-mcap-basis).

`volume_trend_13w` påverkas inte och behålls. Registry markerar de fyra fälten som
UTESLUTNA; regressionen kräver nu att de förblir null.

### Ny ombyggnad/QA

- CORE/FUND/target: 420 instrument, **30 234 rader** (före 30 370).
- Fulla 52v-targets: **24 890** (före 25 026).
- Verifierade separata terminalutfall: 828; terminalevents: 68; paneldatum: 86.
- `has_fundamenta`: 27 048/30 234 (89,5 %).
- Full targetåterräkning: 30 234 rader, 0 PIT-/värde-/typfel.
- Membership-regression: 0 observationer före ledger-entry.
- `tools/regression_second_review.py`: PASS.

SHA256 (filbytes): membership `1135a3fd5d48f423c9882083d3bc7c2af2dc6b9d705cb29a5aba07d2f9b162ee`;
CORE `5685390f341b7efaf91385ca9d1ca2f2980f5018c244a869f5c979a3d3cd05fd`;
CORE+FUND `371787f7a0ee1e0164fbcc4e308c9b628d68e081b261fdc4938d7008968332dc`;
target `246574240f0d4a967e640f6420a4dd1a6fb23b2b3049f1445a11072e784c3e3e`;
QA `9c488e55119c98cf13ced5306b54d239632e303f6feceeeb3ff500ff8625f662`.

### Uppdaterat beslut

**B) Ytterligare blockerare finns.** Kedjan är inte redo för Spår D. Kvar är främst
att göra baseline-membership vid 2020-01-01 fullständigt auktoritativ för samtliga
ekonomiska enheter/aktieslag och att lösa Spår B:s dokumenterade survivorship-gap
(67/68 avnoterade saknar fundamenta) eller fatta ett uttryckligt exklusionsbeslut för
fundamentala modeller. De fyra monetära features som saknar verifierbar prisbasis är
inte längre blockerande fel i panelen eftersom de är explicit uteslutna; de får inte
återaktiveras utan ny råkälla och QA.
