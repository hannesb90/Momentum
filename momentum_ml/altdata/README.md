# altdata/ — MFN-pressmeddelanden + LLM-sentiment (validate-first)

Detta är **validerings­experimentet** för alt-data-spåret. Hypotesen: ren
pris-momentum har tappat sin edge i algo-eran (se `era_analysis.py` – försprånget
mot OMXS30 var en uppvärmnings­artefakt). En durabel edge kräver något algon inte
trivialt arbitrerar bort: **tonen i bolagens egna regulatoriska pressmeddelanden**
(PEAD-anda – marknaden under-reagerar på nyhetston, driften håller i sig veckor
framåt).

Vi **bevisar edgen först**, billigt, innan något byggs in i modellen.

## Varför MFN

MFN.se (Modular Finance) distribuerar nordiska regulatoriska PM och har ett
**arkiv med publiceringstidsstämpel** → point-in-time text utan look-ahead. Det är
förutsättningen för en ärlig backtest av en textsignal.

## Tre steg (körs på Pi:n)

> **Måste köras på Pi:n.** Molncontainern där koden utvecklas når varken mfn.se
> eller Yahoo (egress-spärr).

### 0. API-nyckel (engång)

1. Skapa konto på **console.anthropic.com**, fyll på t.ex. $25 (pay-as-you-go,
   ingen prenumeration) och sätt en **spend limit**.
2. Skapa en API-nyckel.
3. Lägg den som miljövariabel – **aldrig i repot**:

   ```bash
   echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.momentum.env
   source ~/.momentum.env
   ```

### 1. Hämta MFN-arkivet

MFN:s exakta endpoint/JSON-form är inte hårdkodad på tro. **Proba först** ett
bolag och titta på råsvaret:

```bash
cd /opt/momentum/momentum_ml
/opt/momentum/venv/bin/python altdata/mfn_fetch.py probe "Saab"
```

Det skriver `cache/mfn/_probe_*.txt`. Titta på filen med flest tolkade PM –
stämmer fälten (id / published / title / text)? Då är parsern rätt. Annars:
skicka tillbaka en `_probe_*.txt` så låser jag parsern mot den faktiska formen
(ev. fyll även i `altdata/mfn_map.csv` med `ticker,mfn_query` för bolag vars namn
inte matchar i MFN:s sök).

När proben ser bra ut, hämta hela segmentet (inkrementellt, cachas per ticker):

```bash
/opt/momentum/venv/bin/python altdata/mfn_fetch.py fetch large
```

### 2. Poängsätt med Claude (Haiku 4.5, Batch-API −50%)

```bash
/opt/momentum/venv/bin/python altdata/sentiment.py one  AAA.ST   # snabb rimlighetskoll på 5 PM
/opt/momentum/venv/bin/python altdata/sentiment.py score large   # hela segmentet (batch)
```

Varje PM poängsätts på `sentiment` (−2..+2), `materiality` (0..3), `category` och
en mening motivering. Poäng cachas per PM-id → samma PM betalas aldrig om.

### 3. OOS-backtest av signalen

```bash
/opt/momentum/venv/bin/python altdata/backtest_sentiment.py large
```

Två test på rent OOS-fönster (2016+):
- **Event-studie**: framåtavkastning efter positiva vs negativa PM (störst för
  materiella PM om edgen är äkta).
- **Tvärsnitt**: veckovis ton-rank vs framåtavkastning, capture-spread topp- vs
  botten-tercil (samma mått som `capture_analysis.py`).

**Beslutsregel:** är båda spreadarna tydligt positiva (och störst för materiella
PM) → äkta edge värd att bygga in som modell-feature. Är de nära noll/negativa →
pris-only-modellen har redan allt, spara pengarna. Samma hederliga regel som
gällde feature-experimenten v2/PEAD (som båda föll och revertades).

## Kostnad

| Steg | Volym | Kostnad |
|---|---|---|
| Rimlighetskoll (`one`) | 5 PM | ~ören |
| Backtest, smal (Large/Mid, ~10 år) | ~10 000 PM | ~$40 → batchat **~$20** |
| Backtest, brett (hela universum) | ~50 000 PM | ~$200 → batchat **~$100** |
| Live-drift (innehavens PM) | ~5–15 PM/vecka | ~ören/vecka |

Engångskostnad på ~en hundralapp för att bevisa idén — mot Börsdatas 599 kr/mån
*för evigt*. Det är hela poängen med alt-data-spåret vid ditt kapital.

## Filer

- `mfn_fetch.py` — hämtar + cachar PM (probe / fetch / one)
- `sentiment.py` — Claude-poängsättning (score / one), batch + cache
- `backtest_sentiment.py` — OOS event-studie + tvärsnitts-capture-spread
- `mfn_map.csv` *(valfri)* — `ticker,mfn_query` för bolag med svårmatchat namn
- konfig i `../config.py` under "Alt-data: MFN…"
