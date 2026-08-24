# Universumreparation v2 — åtgärd av PREMODEL_AUDIT_2026-08-08

Svar på revisionsfyndet i `PREMODEL_AUDIT_2026-08-08.md`: 7 instrument med felaktigt
trunkerad prishistorik pga aktieslagsförväxling i Skatteverket-parsningen. Åtgärdat
med **generell, korrekt logik** i `tools/instrument_master_v2.py` — ingen
specialregel för de sju kända fallen. Hela universumet (1648 sidor) genomsökt på
nytt.

## Rotorsaker och fixar

**BUG-FIX 1 — Aktieslagskonflation.** Skatteverkets sidor beskriver ofta flera
värdepapper (stamaktie, preferensaktie, C/D-aktie, SDB) för samma bolag i samma
händelsetabell. Gamla koden valde blint senaste "avnoterad"-händelsen oavsett
aktieslag. Fix: varje händelse aktieslagstaggas (regex), och kopplas till ett
specifikt EODHD-instrument endast om taggen är otaggad ELLER matchar
målinstrumentets eget aktieslag (härlett ur kodsuffix -A/-B/-C/-D/-PREF/-SDB).

**BUG-FIX 2 — Byten-alias-felet.** Bytestabellens `fran`-fält (föregångarens namn
i en företagshändelse) användes felaktigt som alternativt namn för SIDANS EGET
bolag i namnmatchningen — lät t.ex. Millicoms sida matcha Kinneviks ISIN via
byten-raden "Kinnevik -> Millicom". Fix: `fran` används aldrig som sökvariant för
sidans egen identitet.

**BUG-FIX 3 — Icke-deterministisk entitetsupplösning.** Ett bolagsnamn kan
legitimt peka på flera olika ISIN (flera noterade aktieslag). Ursprunglig kod
itererade en Python-`set`, hash-ordningsberoende mellan körningar. Fix:
deterministisk sortering + disambiguering mot det etablerade Spår A-universumet
(exakt en klass per bolag är alltid redan medlem), med volym som sistahandsfallback.

**BUG-FIX 4 — Avknoppningskonflation i efterföljarfallbacken.** Byten-tabellens
`till`-fält användes som efterföljarkandidat oavsett anledning. En rad med
anledning "Utdelning" (eller köpoptioner/inköpsrätter/återköp/unit/likvidation/
teckningsoptioner) beskriver INTE att ursprungsbolaget blev målbolaget, utan att
aktieägarna även fick målbolagets aktier utdelade (avknoppning) — ursprungsbolaget
fortsätter existera separat. Gav SCA:s sida fel koppling till ESSITY-B (istället
för SCA:s egen SCA-B) och MTG:s sida fel koppling till NENT-B. Fix: uteslut
avknoppnings-/rättighets-/återköpshändelser som efterföljarkandidat; uteslut även
`fran` som pekar mot flera olika `till`-mål (bevis på en-till-flera-distribution,
t.ex. Kinnevik -> Transcom/Invik/MTG/Netcom/Korsnäs).

**BUG-FIX 5 — Uppköpskonflation i efterföljarfallbacken.** Även en till-synes
kontinuitetsbärande anledning ("Inlösen"/"Uppköp"/"Byte") kan beskriva att ett
REDAN ETABLERAT, separat bolag köpte upp/löste in ursprungsbolaget — inte en
genuin namnbyteskontinuitet. Skillnaden syns i TIDEN: en genuin efterföljare
börjar handlas kring ursprungets sista relevanta år; ett redan etablerat
uppköpande bolag har handlats långt innan. Gav Gambro AB (avnoterad 2006,
uppköpt av ABB via "Inlösen") fel koppling till ABB Ltd (handlats sedan 1999) —
hade fått Gambros datum skriva över ABB:s egen post och felaktigt trunkera
ABB:s fortsatt aktiva prisserie vid 2006. Fix: varje efterföljarkandidat
tidsprövas mot den ENDA aktieslagskompatibla avnoteringshändelsen på
ursprungssidan (samma kompatibilitetslogik som BUG-FIX 1) — kandidatens egen
handelsstart får inte ligga mer än 2 år FÖRE den händelsen. (En första,
grövre version jämförde mot sidans SENASTE händelseår oavsett aktieslag, vilket
felaktigt avvisade VEF Ltd SDB → VEF AB — en genuin, kontinuerlig
redomicilieringsefterföljare sedan 2015 — eftersom sidans enda avnoteringsrad
gällde SDB-omslagets avveckling, inte stamaktiens handel.)

**BUG-FIX 6 — Kodåteranvändningsdisambiguering.** När flera Skatteverket-sidor
pekar mot SAMMA EODHD-kod (äkta kodåteranvändning eller kvarvarande
matchningskonflikt) avgjorde nedströms kod tidigare ARBITRÄRT vilken sidas
avnoteringsdatum som vann (sist i listan skrev över, oavsett om det stämde) —
gav bl.a. Gränges (GRNG, fortsatt noterat) och AcadeMedia (ACAD, fortsatt
noterat) fel trunkeringsdatum från en annan, äldre post med samma kod. Fix:
samtliga rader med samma kod delar per definition samma prisserie; är
EODHD:s egen klassificering "active" vinner alltid "fortsatt noterad"
(oavsett vad en enskild gammal sida påstår), annars vinner den rad vars datum
ligger närmast seriens faktiska sista handelsdag. Ingen trolig kandidat
(>400 dagars avstånd, t.ex. Pfizer/Pharmacia där 2003-uppköpet inte är samma
händelse som Pfizers egen senare avnotering ~2023) ger hellre `None`
(dokumenterad lucka) än ett sannolikt felaktigt datum.

**Mindre generella parsningsfixar (upptäckta vid cross-check mot EODHD:s
delisted-katalog):**
- Elidat sammansatt uttryck "Stam- och Preferensaktie" (stamaktiens "aktie"-led
  utelämnat) taggades enbart PREF — tystade en KORREKT avnoteringssignal för
  stamaktien (Oscar Properties, Svenska Nyttobostäder).
- Käll-HTML tappar ibland mellanslag efter "den" (t.ex. "den11 augusti", 5
  förekomster i hela korpusen) vilket fick datumregexet att missa träffen helt
  (Collector AB m.fl.).

## Verifiering

- **Samtliga 7 kända regressionsfall** (SBB-B, Hufvudstaden, Sagax, Kinnevik,
  VEF, FastPartner, Stenhus Fastigheter) bekräftat korrekta: rätt EODHD-kod, rätt
  aktieslag, `avnoterad_datum: null` (samtliga fortfarande noterade).
- **Cross-check mot EODHD:s delisted-katalog:** av 68 universummedlemmar som
  finns i katalogen saknar endast 1 (KDEV/KDventures) avnoteringsdatum — och det
  är korrekt (bolaget är enligt Skatteverket fortsatt noterat under nytt namn
  efter namnbyte 2026-02-10; sannolikt en EODHD-sidans kodåteranvändning, inte ett
  fel i denna parsning).
- **0 kvarstående kodkonflikter:** samtliga EODHD-koder som matchas av mer än en
  Skatteverket-sida har nu ett internt konsistent avnoteringsdatum (verifierat
  mot koden delade prisserie).
- **Diff v1 (bugg) → v2 (reparerad), hela universumet (1648 sidor):**
  - 42 avnoteringar borttagna (var fel pga aktieslags-/avknoppnings-/uppköps-/
    kodåteranvändningskonflation)
  - 1 avnotering tillagd (Collector AB, saknades pga datumparsningsglitch)
  - 5 avnoteringsdatum korrigerade till rätt datum (kodåteranvändning: Capio,
    I.A.R Systems, Nordic Waterproofing, Oriflame, Transcom WorldWide — samtliga
    verifierade exakt mot respektive prisseries faktiska sista handelsdag)
  - 51 EODHD-kodmappningar ändrade (bl.a. Ratos RATO-A→RATO-B, SEB SEB-C→SEB-A,
    Handelsbanken SHB-B→SHB-A, SCA ESSITY-B→SCA-B, Gambro AB förlorade sin
    felaktiga koppling till ABB Ltd — samtliga verifierade mot
    universummedlemskap/orgnr/prisseriens starttid)
  - Fullständig lista: `docs/probes/instrument_master_v1_vs_v2_final_diff.json`

Ingen manuell specialregel för de sju kända fallen. Samtliga fixar är generella
och verifierade mot hela 1648-sidorskorpusen, inte enbart de kända fallen.

## Nästa steg

Spår A byggs om från RAW med den reparerade `docs/probes/instrument_master.json`
(se `docs/PIS_QA_...` för R1–R8-regeltillämpning). Manifest och SHA256 fryses
först när hela kedjan (A+B+C) passerat slutlig audit.
