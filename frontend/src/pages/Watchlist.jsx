import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { useWatchlist } from '../useWatchlist'
import { usePortfolio } from '../usePortfolio'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { SegmentedControl } from '../components/SegmentedControl'
import { SignalBadge } from '../components/SignalBadge'
import { holdingSignal } from '../signalLogic'
import { EmptyState } from '../components/EmptyState'
import { InfoButton } from '../components/InfoButton'
import { fmtPct } from '../format'

const STATUS_FILTERS = [
  { value: 'all', label: 'Alla' },
  { value: 'buy', label: 'Köp' },
  { value: 'unknown', label: 'Utan data' },
]

export function WatchlistPage() {
  const { tickers, addToWatchlist, removeFromWatchlist } = useWatchlist()
  const { addHolding } = usePortfolio()
  const signals = useApiData(() => api.latestSignals(), [])
  const [ticker, setTicker] = useState('')
  const [filter, setFilter] = useState('all')

  const sigByTicker = useMemo(() => {
    const map = {}
    for (const s of signals.data ?? []) map[s.ticker.toUpperCase()] = s
    return map
  }, [signals.data])

  const enriched = useMemo(() => {
    return tickers.map((t) => {
      const sig = sigByTicker[t] ?? null
      return { ticker: t, sig, variant: holdingSignal(false, sig) }
    })
  }, [tickers, sigByTicker])

  const rows = useMemo(() => {
    if (filter === 'all') return enriched
    if (filter === 'buy') return enriched.filter((h) => h.variant === 'buy')
    if (filter === 'unknown') return enriched.filter((h) => h.variant === 'unknown')
    return enriched
  }, [enriched, filter])

  const sorted = useMemo(
    () => [...rows].sort((a, b) => (b.sig?.prob_up ?? -1) - (a.sig?.prob_up ?? -1)),
    [rows],
  )

  function onSubmit(e) {
    e.preventDefault()
    if (!ticker.trim()) return
    addToWatchlist(ticker)
    setTicker('')
  }

  function promote(t) {
    addHolding({ ticker: t, shares: null })
    removeFromWatchlist(t)
  }

  const buyCount = enriched.filter((h) => h.variant === 'buy').length

  return (
    <section className="page">
      <div className="page-head">
        <h1>Bevakningslista</h1>
        <p className="page-subtitle">
          Följ bolag du inte äger men vill hålla ögonen på. Sparas lokalt på den här enheten.
        </p>
      </div>

      {signals.error && <ErrorBlock error={signals.error} />}

      <form className="add-form" onSubmit={onSubmit}>
        <input
          className="search-input"
          placeholder="Ticker (t.ex. ERIC-B.ST)"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          aria-label="Ticker"
        />
        <button type="submit" className="btn btn--primary">Bevaka</button>
      </form>

      {tickers.length === 0 ? (
        <EmptyState
          title="Inga bevakade bolag ännu"
          hint="Lägg till tickers ovan för att följa dem utan att äga dem."
        />
      ) : (
        <>
          <div className="tile-grid">
            <div className="tile">
              <div className="tile__label">
                Bevakade
                <InfoButton title="Bevakade">
                  Antal bolag du valt att hålla ögonen på utan att du äger dem.
                </InfoButton>
              </div>
              <div className="tile__value">{tickers.length}</div>
            </div>
            <div className="tile">
              <div className="tile__label">
                Köpsignal
                <InfoButton title="Köpsignal">
                  Antal bevakade bolag som just nu har en aktiv köpsignal från modellen – en
                  möjlighet att flytta dem till din portfölj.
                </InfoButton>
              </div>
              <div className="tile__value tile__value--good">{buyCount}</div>
            </div>
          </div>

          <div className="filter-bar">
            <SegmentedControl options={STATUS_FILTERS} value={filter} onChange={setFilter} size="sm" />
          </div>

          {signals.loading ? (
            <Loading />
          ) : sorted.length === 0 ? (
            <EmptyState title="Inga bevakade bolag matchar filtret" />
          ) : (
            <div className="list-card">
              {sorted.map((h) => (
                <div key={h.ticker} className="holding-row">
                  <div className="holding-row__main">
                    <Link to={`/aktie/${encodeURIComponent(h.ticker)}`} className="list-row__ticker ticker-link">
                      {h.ticker}
                    </Link>
                    <span className="list-row__sub">
                      {h.sig ? `P(upp) ${fmtPct(h.sig.prob_up)}` : 'ingen modelltäckning'}
                    </span>
                  </div>
                  <div className="holding-row__side">
                    {h.sig && <span className="list-row__num">{fmtPct(h.sig.pred_return)}</span>}
                    <SignalBadge variant={h.variant} />
                    {h.variant === 'buy' && (
                      <button
                        className="icon-btn"
                        onClick={() => promote(h.ticker)}
                        aria-label={`Flytta ${h.ticker} till portföljen`}
                        title="Flytta till portfölj"
                      >
                        →
                      </button>
                    )}
                    <button
                      className="icon-btn"
                      onClick={() => removeFromWatchlist(h.ticker)}
                      aria-label={`Sluta bevaka ${h.ticker}`}
                      title="Sluta bevaka"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <p className="footnote">
            <strong>KÖP</strong> = modellen har köpsignal just nu, <strong>NEUTRAL</strong> = ingen
            köpsignal, <strong>INGEN DATA</strong> = tickern ingår inte i modellens universum.
          </p>
        </>
      )}
    </section>
  )
}
