# Uppföljande blocker-audit av V2 A/B/C/target — 2026-08-08

Ingen modellträning, feature selection, tuning eller targetbaserad design har utförts.

## Verifierade fynd och åtgärder

### CRITICAL — 52v-datumtolerans: bekräftad och reparerad

`spar_c_target.py:närmast_handelsdag` returnerade tidigare `bäst` även när
toleransvillkoret var falskt. Före reparation: 24 890 forward-labels, faktisk horisont
min/median/max 7/364/721 dagar; 13 var <350 och 29 >370. Alla 42 utanför 350–370
hörde till NEOBO (26), CARA (9) eller RIZZO-B (7).

Grundorsaken fanns även i CORE-panelens as-of-val: paneldatum under långa prisgap
använde godtyckligt gammalt pris. En fast, targetoberoende tolerans på 8 kalenderdagar
är nu gemensam för CORE och target. Utanför toleransen returneras `None`; inga
instrumentspecialregler finns.

Efter: 24 845 forward-labels, min/median/max 357/364/371 dagar. 0 är <350; 3 är
371 dagar (CARA). Dessa tre är giltiga: startpriset ligger före paneldatum medan
slutpriset ligger inom den separata fasta 8-dagarsgränsen. Regressionen kontrollerar
den faktiska slutprislaggen (0–8 dagar), vilket är den preregistrerade regeln.
NEOBO och RIZZO-B har inga avvikande forwardhorisonter kvar. 15 labels sattes null
för saknat slutpris inom tolerans och 30 stale CORE/target-panelrader togs bort.
Terminalutfall är fortsatt separata och kräver explicit event i
`validated/terminal_events.json`.

### HIGH — membership: bekräftad, fortfarande blockerande

`membership_main_list_pit.json` har 420 instrument: 7 med daterad Nasdaq-admission
och 413 med `BASELINE_MEMBER_AT_STUDY_START`. Efter ledgerfiltret finns 0 panelrader
före ledgerns datum, men detta bevisar inte baseline-antagandet.

Källor som kan användas är Nasdaqs årsvisa `Changes to the list` (admission,
transfer, delisting), Nasdaq market notices/welcome notices, en auktoritativ roster
per 2020-01-01 samt årliga `Market Cap Segment Review`. Segment-review visar bara
förändringar, inte hela rosters. Skatteverkets aktiehistorik kan korroborera
bolagshändelser men är inte en komplett membershipkälla. Prisexistens och dagens
Börsdata `marketId` är uttryckligen otillräckliga.

Full rekonstruktion kräver antingen: (A) Nasdaq-roster 2020-01-01 + samtliga
liständringar med ISIN/aktieslagsintervall; (B) licensierad historisk
instrument-/membershipfil; eller (C) ett dokumenterat beslut att ändra universumet
till en annan, observerbar definition. Alternativ C är en ekonomisk designändring
och har inte gjorts. V2 får därför inte beskrivas som full PIT-membership.

### HIGH — blueprint ≠ implementation: bekräftad och reparerad

De fyra 0 %-fälten stod felaktigt som IMPLEMENTERAD/NY_BYGGD i blueprinten trots
att aktiv kod skrev null. Blueprinten har nu en enda statusvokabulär. De fyra är
`BLOCKERAD/SAKNAR DATA` och räknas inte i användbar featurebas:

- turnover_13w_msek
- illiquidity_amihud_13w
- dividend_yield_ttm
- fcf_yield_ttm

Aktuell användbar panelbas är 29 CORE + 17 FUNDAMENTA-features. Provenancekolumner
och de fyra blockerade kolumnerna räknas inte som modellfeatures.

### B-extra → C

EBITDA och Capex är formellt länkade från `manifest_sparB.json` till
`manifest_sparB_extra.json`, med bytehash och radantal. EBITDA-marginal är bedömd
`KAN BYGGAS MEN UPPSKJUTEN`: definition och täckning är tillräckliga, men ingen ny
feature införs medan membership är blockerad. Capex-intensitet är blockerad eftersom
R12-Capex har blandad teckensemantik (10 557 negativa, 1 077 positiva, 271 nollor)
och ingen generell cash-out/correction-definition är godkänd.

KPI 213–215 och shareholder yield förblir blockerade/uteslutna: ingen fullskale-KPI,
ingen verifierad FX/correction/cashflow-logik och ingen PIT-mcap-denominator.
`roic_proxy_ttm` behålls endast som uttryckligt före-skatt-mått
`operating_Income/(total_Equity+net_Debt)`, aldrig beskrivet som sann NOPAT/ROIC.

### Manifest och externa beroenden

C-manifestet genereras från färdiga artefakter och matchar nu byte-för-byte. A, B
och C är explicit `EJ FRYST`. B-extra har egna käll- och artefakthashar. Aktivt
externt produktionsberoende är EODHD-arkivet för A; ingen legacy-kod/config importeras.
`validated/external_dependencies_manifest.json` registrerar sökväg, konsument,
420 källfilshashar och aggregathash. Övriga legacy-läsare är diagnostiska och inte
aktiva builders.

## Före → efter

| Mått | Före | Efter |
|---|---:|---:|
| A instrument/rader | 420 / 581 115 | 420 / 581 115 |
| B år/kvartal/R12 | 4 847 / 12 280 / 12 269 | oförändrat |
| B-extra KPI-rader | 56 874 | 56 874 |
| C panelrader | 30 234 | 30 204 |
| användbara CORE/FUND | felaktigt 31/19 | 29/17 |
| forward 52v | 24 890 | 24 845 |
| separata terminalutfall | 828 | 828 |
| högercensurerade/incomplete | 5 344 | 5 344 + 15 tolerans-null |
| membership-instrument | 420 (7 explicit/413 baseline) | oförändrat |

Aktuella SHA256: A prices `e3ed38b8e89a25149e61b71c8e0c91b8adbd2dab22b282bc156b1214987f17b4`;
B year `7cead0b764c81e7d0bb6cb758c40a66ec1379b9f97d090b483732ce46d4e7d6b`;
B quarter `e7c6ec8a1096189ab2bd20ad959f7c37ab94be38e378668f6cbac7bedc17e932`;
B R12 `487f212237f9bdd48d159eeddd8a2da30e342c01bfb05ff8d6a0a061f391bbfd`;
B-extra KPI `48a10a53c17cbb7a2a385f2ccc36cabb28a9bdcf82c7236ccc8c7b108ad8ad0a`;
CORE `350c4a1950bf618a8ae4650169ccd4e0081e4a99e743a61811cba3f417175c42`;
CORE+FUND `e0508aab9b53a45eb8986b0369619b9d67205619fc47bd1a3fbb2c0cdb2c1d27`;
target `566b83d01512206816ef6867b704f0dd4078fb1442c0931db31da35348b185b1`;
terminal events `f437650e06e7a4405a922725d8415dc5b55fdca4df511aa72cc31bf6e47c7a8a`.

## Adversarial slutbedömning

Nya regressioner passerar för fast targettolerans, explicit terminalevidens,
membership-ledgerdatum, blockerade 0 %-features, B-extra-valuta samt entitygrupper.
Full C-QA återräknade 30 204 targets med 0 PIT-/värde-/typfel. Tidigare
currency-dubbelkonvertering, adjusted-close×volume, last-one-wins och falska
terminalevents har inte återkommit.

Kvarvarande blockerare är (1) 413 baseline-antagna membership entries, (2) fundamental
survivorship: 67/68 avnoterade saknar fundamenta, och (3) externt EODHD-underlag är
hashlåst men inte kopierat till en självständig V2 RAW-snapshot. Därför:

**B) EJ REDO FÖR SPÅR D.**
