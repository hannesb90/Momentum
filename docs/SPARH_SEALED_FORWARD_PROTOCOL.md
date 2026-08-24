# Spår H — förseglad forwardvalidering

## Besked vid H0

Infrastrukturen är byggd och H0 är förseglad. Status kvarstår:

**B — CHAMPION LOVANDE MEN EJ BEKRÄFTAD.**

Ingen forwardobservation har skapats. Per 2026-08-09 finns inget ordinarie
paneldatum strikt efter V4-frysningen. Panelen 2026-08-07 är uttryckligen
pre-freeze och får aldrig märkas om som forward.

* Första forward-eligible paneldatum: **2026-09-04**.
* Nästa fasta 8v-rebalancedatum: **2026-09-04**.
* Forwardobservationer som kan förseglas 2026-08-09: **0**.

H börjar från cash vid denna första forwardrebalans. Det behåller den frysta
8v-fasen och importerar inga pre-V4-innehav som forwardevidens.

## H0-låsning och verifiering

H0-låset är `SPARH_FORWARD_PROTOCOL_V1_IMMUTABLE_2026-08-09`.

* V4 freeze-manifest: `6716e083c570bcf3b9f86d7583e85ad72e2d00e4089295214a746deb2d7f5c3d`.
* Spår G slutrapport: `72927885614af3f0ab65d402b443726ed8ff19fc3ee04ddb4869e972d8cf4cd0`.
* H0-lock: `93f462fc9d4461c54c277cddada08664c1f7eef30176980b4d879df86d038661`.
* V4-kontroll: 43/43 filer PASS.
* Aktiva A/B/C-artefakter: 13/13 PASS.
* Git commit: ej tillgänglig eftersom arbetsytan saknar Git-metadata. Exekverbar
  kod och protokoll låses därför byte-för-byte med SHA256.

Fail-fast körs före varje status-, prediction- och utfallshändelse. Den granskar
H0:s låsta filer, alla 43 V4-filer, alla 13 aktiva A/B/C-artefakter, den
manifesterade externa källan och hela den redan skrivna forwardjournalen.

## Artefakter per prediction

Varje nytt panelpaket bevarar följande före framtida utfall:

1. exakt använd pris-snapshot;
2. exakt använd universum-/membership-snapshot med `known_at`;
3. signalunderlag och faktiska 12m-/18m-lookbackpriser;
4. decision universe med 12m, 18m, ranks och kombinerad score;
5. full championranking;
6. full fryst 12m-ranking;
7. champion Top-30;
8. 12m Top-30;
9. planerade holdings;
10. planerade trades och nästa exekveringsdatum;
11. benchmarkuniversum;
12. inputprovenance och upstream-hashar;
13. prediction-manifest med path, bytes, radantal och SHA256 per fil.

Exekvering, portföljutfall, moget 52v-target och eventuella rättelser blir egna
events. En rättelse kräver ett unikt ID och ersätter aldrig originalpredictionen.

## Append-only-format

`trackh/journal/INDEX.jsonl` har en JSON-post per event med:

`seq`, `event`, `panel_date`, `path`, `artifact_sha256`, `prev_chain_hash`,
`chain_hash`.

Sekvensen är låst och hashkedjad; filskapande använder exclusive-create och
seglade filer görs read-only. Samtidiga append-operationer serialiseras med
fillås. Detta är en teknisk append-only-kontroll i den lokala arbetsytan, inte en
extern betrodd tidsstämpling eller hårdvarubaserad WORM-lagring.

## Fail-fast-regler

Körningen stoppas bland annat om:

* ett låst path, byteantal eller SHA256 avviker;
* inbox saknas för ett förfallet paneldatum;
* `data_as_of_timestamp` eller membership-`known_at` ligger efter decision time;
* pris-snapshot innehåller datum efter paneldatum;
* decision-universum innehåller target, future return eller terminal outcome;
* ett upstream-manifest saknas, avviker eller har framtida `as_of`;
* en prediction redan finns;
* journalens sekvens, hashkedja eller refererade artefakter avviker;
* en normal exekvering har `execution_price_date <= decision_date`;
* obligatoriska portfölj- eller targetutfall saknas.

Regressionstesten bekräftar kalenderfas, no-overwrite, byte-identiska beslut när
orefererad framtidsdata ändras, avvisning av framtida pris, avvisning av target i
decision-input och fail-fast efter artefaktmanipulation.

## Drift och checkpoints

`tools/sparh_forward.py run-due` är den enda schemalagda prediction-ingången.
Den verifierar hela kedjan och stoppar om ett komplett hashmatchat inboxpaket
saknas. Predictioner förseglas först; exekveringspriser registreras därefter på
första faktiska handelsdag strikt efter beslutet. Mogen portfölj- och targetdata
kopplas senare till predictionens oförändrade manifesthash.

Checkpoints utlöses endast av informationsmängd:

* efter 3, 6 och 12 fullbordade 8v-perioder;
* efter 5, 10 och 20 mogna IC52-paneler.

Resultatkvalitet får varken tidigarelägga en checkpoint eller ändra championen.
Endast fryst champion, fryst ren 12m och fryst benchmark följs.

## Slutlig avgränsning

Ingen modell-, signal-, Top-N-, rebalance-, execution-, gate-, exit-, universum-
eller targetändring har gjorts. Ingen syntetisk forwarddata och ingen pre-V4-data
har återanvänts som forward. Nästa faktiska handling är därför först möjlig när
2026-09-04-paketet finns med data som var tillgänglig vid beslutstid.
