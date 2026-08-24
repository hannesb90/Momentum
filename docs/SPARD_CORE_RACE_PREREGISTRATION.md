# Spår D — preregistrerat neutralt CORE-race

Kontraktet i `spard/core_race_preregistration.json` skrevs innan första modell-fit.
Validering är kalenderåret 2023. Orörda OOS-fönster är 2024 och tillgänglig del av
2025. Varje årsmodell tränas expanderande endast på paneldatum senast 52 veckor före
utvärderingsperiodens första datum. Random CV och early stopping används inte.

Alla fem familjer använder samma 29 CORE-features, observationsnycklar och råa
`target_fwd52w`. Terminalutfall är inte modelltarget. Train-fold medianimputering är
gemensam; linjära modeller standardiseras med train-fold-parametrar. Inga features
klipps, väljs bort eller skapas.

Sekundär portfölj är lika viktad top-30, ombalanserad på varje fyraveckors paneldatum,
med 20 bp kostnad per one-way turnover. Benchmark är samma dags observerbara universum
likaviktat. Primärt modellval sker på tvärsnitts-IC, inte CAGR.
