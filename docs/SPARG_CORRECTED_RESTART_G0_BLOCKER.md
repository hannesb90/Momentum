# Spår G – korrigerad omstart stoppad vid G0

Datum: 2026-08-09  
Slutklassificering: **D — DATA-/IMPLEMENTATIONSBLOCKERARE**

## Besked

Spår G stoppades vid reparations-gaten. Inga G1–G14-resultat, robusthetstest, nya championval eller parameterändringar har producerats.

## Blockerare

Den auktoritativa reparationsfrysningen `repair_df/FREEZE_MANIFEST.json` beskriver inte de faktiska inputbytes som D/F-körningen använder. Samtliga sex deklarerade inputhashar avviker från SHA256 beräknad direkt från filerna. Manifestet saknar dessutom filväg för feature-registret och den naturliga deklarerade vägen `panels/feature_registry.json` finns inte.

| Input | SHA256 i FREEZE_MANIFEST | Faktisk SHA256 | Status |
|---|---|---|---|
| `panels/core_panel.json` | `220e258d89a02a285c88402390cdbb2d5a33b33528b06b742e6a94e96c3b1f4f` | `220e258669b1eed774e533065dec5ed8e5780edc0e31ec4eb3e841c128a1c974` | MISMATCH |
| `panels/core_fundamenta_panel.json` | `117ac68c330510f9ac94c6be56e399cf2c922cbaf0ca25910e1268051acac931` | `117ac6e811ff62ea62168fea2f55a6da430c43774794bed8733573dc4dd1eaaa` | MISMATCH |
| `panels/target_table.json` | `6c2b87c42841bd7cf8a8cdcc40287a83c97708894f1617912e860650733954a5` | `6c2b87aad0e1853837b8d60a3b11e100bca781486b7c12966a27b9a8bd671d21` | MISMATCH |
| feature registry | `391a365cc06e61c327d836f61dd187d207cf1bf868814040439a99ca8422cc5e` | `391a365fd73f981d682ed756deacb94d921f14d61a47628eb16ac1de9eb65f05` (`docs/probes/feature_registry.json`) | MISMATCH + saknad manifestpath |
| `validated/prices/prices_validated.json` | `e3ed38276700070200b8a2c8db387a04b22e009f427893bd0c71dd15be22eb38` | `e3ed38b8e89a25149e61b71c8e0c91b8adbd2dab22b282bc156b1214987f17b4` | MISMATCH |
| `validated/terminal_events.json` | `f43765042f944e212ea5045116b289474d86ab2ceffbcf439d18c56e9290cb37` | `f437650e06e7a4405a922725d8415dc5b55fdca4df511aa72cc31bf6e47c7a8a` | MISMATCH |

De faktiska hashvärdena överensstämmer med den tidigare `repair_df/repair_preregistration.json`. Problemet är alltså inte bevis för att A/B/C-filerna ändrats; det är en faktisk integritetsdefekt i den senare fil som påstås vara den auktoritativa frysningen. G0 kräver att de nya D/F-resultaten kan reproduceras från entydigt frysta inputs. Det kravet kan inte godkännas när frysningsmanifestet anger andra bytes och inte explicit anger korrekt registry-path.

## Kodspårning före stopp

Den nya reparationsvägen använder `tools/decision_portfolio_v2.py` och de nya rebuild-scripten. Den gamla, invaliderade `tools/spard_neutral_race.py` innehåller fortfarande den historiska `target_fwd52w is None`-filtreringen, men de nya rebuild-scripten importerar inte dess `load_data`. Detta är dokumenterad historik och inte orsaken till det aktuella stoppet.

Inga G1+-tester kördes efter att manifestdefekten bekräftats.

## Vad som måste göras innan G kan startas om

Detta ska göras i reparationsspåret, inte tyst inne i G:

1. generera om D/F:s övergripande frysningsmanifest direkt från faktiska filbytes;
2. ange explicit path och SHA256 för varje input, inklusive `docs/probes/feature_registry.json`;
3. verifiera manifestet med en automatisk kontroll som misslyckas på ändrad, saknad eller flyttad input;
4. reproducera D och hela F från just de hashverifierade filerna;
5. verifiera identiska resultat- och aggregate-hashar;
6. utfärda en ny immutable D/F-frysning;
7. starta därefter om G från G0.

Den gamla 25,43-procents-CAGR:n förblir `INVALIDATED_BY_TARGET_AVAILABILITY_LOOKAHEAD`. Den korrigerade 23,59-procentsuppgiften har inte använts som evidens i denna avbrutna G-körning.
