# Samtida/bakåtblickande dispersionsproxyer för signalstyrka

Date: 2026-07-26

Uppföljning på `abstention_gate_full_backtest_2026-07-26.md`. `val_auc_best`
är en MODELL-signal, bara känd vid omträning (var 13:e vecka). Kan en
DATA-proxy - beräkningsbar varje vecka, ingen omträning behövd - fånga
samma "är detta en låg-signal-period?"-information, samtidigt eller tätare?
Skript: `tune_dispersion_proxy.py`.

## Metod

Sex kandidatproxyer beräknade vid VARJE splits träningsfönsterslut (bara
information tillgänglig innan testfönstret):

- `dispersion_ret_4w`/`dispersion_ret_12w` - tvärsnittsdispersion (std) i
  trailing 4-/12-veckors avkastning
- `dispersion_mom12_1` - tvärsnittsdispersion i `mom_12_1`-featuren
- `dispersion_prob_raw` - dispersion i splittens EGNA råa modellscore,
  mätt på valideringsfönstret (känt innan test)
- `pct_positive_trend` - andel bolag med `roc_13w > 0` (marknadsbredd)
- `avg_pairwise_corr` - genomsnittlig parvis korrelation, trailing 26v

Mot två mål per split (testfönstret): `test_ic` (Spearman rå-score mot
target_return) och `test_top_decile_edge` (medel-topp-decil minus
medel-alla). `val_auc_best` inkluderad som referenspunkt.

Samma full-universum-datakälla som `abstention_gate`-backtesten (174
tickers, färsk data, riktig `fit_walk_forward`).

## Resultat: Spearman-korrelation + leave-one-split-out (n=31)

| Proxy | vs test_ic | LOO-tecken­byten (IC) | vs edge | LOO-tecken­byten (edge) |
|---|---:|---:|---:|---:|
| **pct_positive_trend** | +0,081 | 0/31 | **+0,479** | 0/31 |
| **dispersion_ret_4w** | **-0,394** | 0/31 | -0,187 | 0/31 |
| dispersion_mom12_1 | -0,448 | 0/31 | -0,062 | **3/31** |
| dispersion_prob_raw | -0,043 | **3/31** | **+0,369** | 0/31 |
| avg_pairwise_corr | -0,271 | 0/31 | +0,165 | 0/31 |
| dispersion_ret_12w | -0,198 | 0/31 | +0,049 | 3/31 |
| val_auc_best (referens) | +0,054 | 2/31 | +0,223 | 0/31 |

("Teckenbyten" = hur många av de 31 leave-one-out-körningarna som ändrar
korrelationens tecken jämfört med hela stickprovet - 0 betyder att INGEN
enskild split ensam avgör riktningen, dvs robust; jämför med
abstention-gatets holdout-resultat som visade sig vara EN splits
tröskelpassage.)

## Slutsats per proxy

**`pct_positive_trend` (marknadsbredd) är den klart starkaste kandidaten.**
Robust på BÅDA målen (0/31 teckenbyten vardera), starkast korrelation mot
den praktiskt relevanta metriken (topp-decil-edge, +0,48), och enklast att
tolka: när fler bolag trendar uppåt samtidigt fungerar momentum-urvalet
bättre. Beräkningsbar varje vecka utan någon modell alls.

**`dispersion_ret_4w` är en robust tvåa**, men med en genuint
kontraintuitiv riktning: HÖG nyligen (4v) tvärsnittsdispersion föregår
SÄMRE både IC och edge, inte bättre. Tolkning: en plötslig spik i
avkastningsspridning ser ut att spegla marknadsstress/instabilitet
(oftast åtföljd av att korrelationer stiger samtidigt - `avg_pairwise_corr`
visar exakt samma riktning mot IC, -0,27, konsekvent med "korrelationer
går mot 1 i kris") snarare än sund, uthållig differentiering att utnyttja.

**`dispersion_mom12_1` och `dispersion_prob_raw` är HALVT validerade** -
robusta mot ETT mål men inte det andra (3/31 teckenbyten). Kvintiltabellen
för `dispersion_mom12_1` visar dessutom en extremt skev fördelning
(sista kvintilens std = 21,4 mot första kvintilens 0,32) - sannolikt
driven av enstaka extremvärden i featuren, inte ett rent
dispersionsmått. Otillräckligt underbyggda för att stå på egen hand.

**`avg_pairwise_corr` är robust på båda måtten men med MOTSATT tecken**
(-0,27 mot IC, +0,17 mot edge) - inget entydigt "bra/dåligt"-svar, mindre
användbar som ensam signal trots att den klarar LOO-kontrollen separat på
vardera målet.

## Rekommendation

`pct_positive_trend` (marknadsbredd) är mogen att läggas till som en
kompletterande, VECKOVIS beräkningsbar tidig varningssignal i
`pipeline_health.json` - till skillnad från `val_auc_best`-trenden (som
bara uppdateras var 13:e vecka vid omträning) skulle den ge en tätare
puls på samma underliggande fråga. `dispersion_ret_4w` är värd att logga
som sekundär signal (samma robusthetsnivå, motsatt håll: hög nyligen-
dispersion = varningstecken, inte allt-klart-tecken).

Innan detta kodas in: samma disciplin som resten av sessionen - inget
kodas in i `ensemble.py`/live-signallogiken utan en fullständig
CAGR/Sharpe/MaxDD-backtest (samma mönster som
`abstention_gate_full_backtest_2026-07-26.md`), och helst en körning på
VECKOVIS (inte bara per-split) upplösning för att verkligen dra nytta av
att proxyn inte kräver omträning - det är den poäng med den här hela
undersökningen.

Rådata: `results/dispersion_proxy_analysis.csv`,
`results/dispersion_proxy_correlations.csv` (genererade av
`tune_dispersion_proxy.py`, ej incheckade).
