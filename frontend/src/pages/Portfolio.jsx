import { useMemo, useState } from 'react'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { usePortfolio } from '../usePortfolio'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { SegmentedControl } from '../components/SegmentedControl'
import { SignalBadge } from '../components/SignalBadge'
import { holdingSignal } from '../signalLogic'
import { EmptyState } from '../components/EmptyState'
import { fmtPct } from '../format'

const STATUS_FILTERS = [
  { value: 'all', label: 'Alla' },
  { value: 'action', label: 'Åtgärd' },
  { value: 'sell', label: 'Sälj' },
  { value: 'unknown', label: 'Utan data' },
]

export function PortfolioPage() {
  const { holdings, addHolding, removeHolding } = usePortfolio()
  const signals = useApiData(() => api.latestSignals(), [])
  const [ticker, setTicker] = useState('')
  const [shares, setShares] = useState('')
  const [filter, setFilter] = useState('all')

  const sigByTicker = useMemo(() => {
    const map = {}
    for (const s of signals.data ?? []) map[s.ticker.toUpperCase()] = s
    return map
  }, [signals.data])

  const enriched = useMemo(() => {
    return holdings.map((h) => {
      const sig = sigByTicker[h.ticker.toUpperCase()] ?? null
      return { ...h, sig, variant: holdingSignal(true, sig) }
    })
  }, [holdings, sigByTicker])

  // Sektorexponering över de egna innehaven – ren signalmatchning per ticker
  // säger inget om koncentrationsrisk om flera innehav råkar ligga i samma
  // sektor. Räknar per innehav (inte kronor) eftersom andelen användare
  // inte fyller i "Antal" – en grov men ärlig approximation.
  const sectorExposure = useMemo(() => {
    if (enriched.length === 0) return []
    const counts = {}
    for (const h of enriched) {
      const sector = h.sig?.sector ?? 'Okänd/utan data'
      counts[sector] = (counts[sector] ?? 0) + 1
    }
    return Object.entries(counts)
      .map(([sector, n]) => ({ sector, n, share: n / enriched.length }))
      .sort((a, b) => b.share - a.share)
  }, [enriched])

  const topSectorShare = sectorExposure[0]?.share ?? 0
  const sectorConcentrated = sectorExposure.length > 1 && topSectorShare >= 0.5

  const rows = useMemo(() => {
    if (filter === 'all') return enriched
    if (filter === 'sell') return enriched.filter((h) => h.variant === 'sell')
    if (filter === 'unknown') return enriched.filter((h) => h.variant === 'unknown')
    if (filter === 'action') return enriched.filter((h) => h.variant === 'sell' || h.variant === 'buy')
    return enriched
  }, [enriched, filter])

  function onSubmit(e) {
    e.preventDefault()
    if (!ticker.trim()) return
    addHolding({
      ticker,
      shares: shares ? Number(shares) : null,
    })
    setTicker('')
    setShares('')
  }

  const sellCount = enriched.filter((h) => h.variant === 'sell').length
  const holdCount = enriched.filter((h) => h.variant === 'hold').length

  return (
    <section className="page">
      <div className="page-head">
        <h1>Min portfölj</h1>
        <p className="page-subtitle">
          Följ modellens köp/sälj-signal på dina egna innehav. Sparas lokalt på den här enheten.
        </p>
      </div>

      {signals.error && <ErrorBlock error={signals.error} />}

      {/* Lägg till innehav */}
      <form className="add-form" onSubmit={onSubmit}>
        <input
          className="search-input"
          placeholder="Ticker (t.ex. VOLV-B.ST)"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          aria-label="Ticker"
        />
        <input
          className="search-input search-input--narrow"
          placeholder="Antal"
          type="number"
          min="0"
          step="any"
          value={shares}
          onChange={(e) => setShares(e.target.value)}
          aria-label="Antal aktier"
        />
        <button type="submit" className="btn btn--primary">Lägg till</button>
      </form>

      {holdings.length === 0 ? (
        <EmptyState
          title="Inga innehav ännu"
          hint="Lägg till dina aktier ovan så matchar vi dem mot modellens senaste signaler."
        />
      ) : (
        <>
          {/* Sammanfattning */}
          <div className="tile-grid">
            <div className="tile">
              <div className="tile__label">Innehav</div>
              <div className="tile__value">{holdings.length}</div>
            </div>
            <div className="tile">
              <div className="tile__label">Behåll</div>
              <div className="tile__value tile__value--good">{holdCount}</div>
            </div>
            <div className="tile">
              <div className="tile__label">Sälj-signal</div>
              <div className="tile__value tile__value--bad">{sellCount}</div>
            </div>
          </div>

          {sectorExposure.length > 1 && (
            <div className="risk-card">
              <div className="risk-card__head">
                <h2>Sektorexponering</h2>
                {sectorConcentrated && (
                  <span className="risk-chip risk-chip--warn">
                    Hög koncentration ({fmtPct(topSectorShare)} i en sektor)
                  </span>
                )}
              </div>
              <div className="risk-card__bars">
                {sectorExposure.map(({ sector, n, share }) => (
                  <div key={sector} className="risk-bar">
                    <div className="risk-bar__label">
                      <span>{sector}</span>
                      <span>{n} st · {fmtPct(share)}</span>
                    </div>
                    <div className="risk-bar__track">
                      <div
                        className={`risk-bar__fill${share >= 0.5 ? ' risk-bar__fill--warn' : ''}`}
                        style={{ width: `${Math.max(share * 100, 2)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <p className="footnote">
                Räknat per innehav (inte kronor). Säger inget om korrelation mellan dina innehav
                inom samma sektor – bara hur många som delar sektor.
              </p>
            </div>
          )}

          <div className="filter-bar">
            <SegmentedControl options={STATUS_FILTERS} value={filter} onChange={setFilter} size="sm" />
          </div>

          {signals.loading ? (
            <Loading />
          ) : rows.length === 0 ? (
            <EmptyState title="Inga innehav matchar filtret" />
          ) : (
            <div className="list-card">
              {rows.map((h) => (
                <div key={h.ticker} className="holding-row">
                  <div className="holding-row__main">
                    <span className="list-row__ticker">{h.ticker}</span>
                    <span className="list-row__sub">
                      {h.shares ? `${h.shares} st · ` : ''}
                      {h.sig ? `P(upp) ${fmtPct(h.sig.prob_up)}` : 'ingen modelltäckning'}
                    </span>
                  </div>
                  <div className="holding-row__side">
                    {h.sig && <span className="list-row__num">{fmtPct(h.sig.pred_return)}</span>}
                    <SignalBadge variant={h.variant} />
                    <button
                      className="icon-btn"
                      onClick={() => removeHolding(h.ticker)}
                      aria-label={`Ta bort ${h.ticker}`}
                      title="Ta bort"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <p className="footnote">
            Signal per innehav: <strong>BEHÅLL</strong> = modellen har fortsatt köpsignal,{' '}
            <strong>SÄLJ</strong> = köpsignalen har försvunnit, <strong>INGEN DATA</strong> = tickern
            ingår inte i modellens universum.
          </p>
        </>
      )}
    </section>
  )
}
