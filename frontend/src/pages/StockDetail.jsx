import { useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ResponsiveContainer, AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from 'recharts'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { usePortfolio } from '../usePortfolio'
import { useWatchlist } from '../useWatchlist'
import { Loading } from '../components/StatusBlock'
import { SignalBadge } from '../components/SignalBadge'
import { StatCard } from '../components/StatCard'
import { InfoButton } from '../components/InfoButton'
import { EmptyState } from '../components/EmptyState'
import { fmtPct, fmtNum, fmtDate, fmtSek, cleanName } from '../format'

export function StockDetailPage() {
  const { ticker } = useParams()
  const history = useApiData(() => api.signalHistory(ticker), [ticker])
  const prices = useApiData(() => api.prices(ticker), [ticker])
  const stats = useApiData(() => api.stats(), [])
  const { addHolding } = usePortfolio()
  const { addToWatchlist } = useWatchlist()

  const horizon = stats.data?.horizon_weeks ?? 4

  const sigSeries = useMemo(() => {
    if (!history.data) return []
    return history.data.map((r) => ({
      date: r.date,
      prob: r.prob_up != null ? r.prob_up * 100 : null,
      ret: r.pred_return != null ? r.pred_return * 100 : null,
      signal: r.pred_signal,
    }))
  }, [history.data])

  const priceSeries = useMemo(() => {
    if (!prices.data) return []
    return prices.data.map((r) => ({ date: r.date, close: r.close }))
  }, [prices.data])

  const dev = useMemo(() => {
    if (priceSeries.length < 2) return null
    const first = priceSeries[0].close
    const last = priceSeries[priceSeries.length - 1].close
    return first ? last / first - 1 : null
  }, [priceSeries])

  if (history.loading) return <Loading />
  if (history.error) {
    return (
      <section className="page">
        <div className="page-head">
          <Link to="/signaler" className="section-head__link">← Tillbaka</Link>
          <h1>{ticker}</h1>
        </div>
        <EmptyState
          title="Ingen modelldata för denna ticker"
          hint="Aktien ingår inte i modellens universum, eller har ingen genererad signal än."
        />
      </section>
    )
  }

  const latest = history.data[history.data.length - 1] ?? {}
  const isBuy = latest.pred_signal === 1
  const displayName = cleanName(latest.name, ticker)

  return (
    <section className="page">
      <div className="page-head">
        <Link to="/signaler" className="section-head__link">← Tillbaka</Link>
        <h1>
          {displayName} <SignalBadge variant={isBuy ? 'buy' : 'flat'} />
        </h1>
        <p className="page-subtitle">
          {displayName !== ticker && <span className="page-subtitle__ticker">{ticker} · </span>}
          {latest.sector ?? 'Okänd sektor'}
          {stats.data?.last_signal_date && ` · senaste signal ${stats.data.last_signal_date}`}
        </p>
      </div>

      <div className="add-form">
        <button className="btn btn--primary" onClick={() => addHolding({ ticker, shares: null })}>
          + Lägg till i portfölj
        </button>
        <button className="btn" onClick={() => addToWatchlist(ticker)}>
          + Bevaka
        </button>
      </div>

      {/* Nyckeltal från senaste signalen */}
      <div className="stat-grid">
        <StatCard
          label={`P(upp) nästa ${horizon}v`}
          value={fmtPct(latest.prob_up)}
          tone={isBuy ? 'good' : 'neutral'}
          info={`Modellens sannolikhet att aktien stiger mer än tröskeln under de kommande ${horizon} veckorna (en period = ${horizon} veckor, uppdateras varje vecka).`}
        />
        <StatCard
          label={`Förv. avk. ${horizon}v`}
          value={fmtPct(latest.pred_return)}
          info={`Modellens prognos för aktiens prisförändring under de kommande ${horizon} veckorna.`}
        />
        <StatCard
          label="Föreslagen storlek"
          value={fmtPct(latest.position_size)}
          info="Hur stor andel av portföljen modellen föreslår i denna aktie, efter risk-/likviditetshänsyn. 0% = ingen position just nu."
        />
        {isBuy && latest.limit_price != null && (
          <StatCard
            label="Köp upp till (limit)"
            value={fmtSek(latest.limit_price)}
            tone="good"
            info="Lägg en LIMITORDER på max denna kurs. Edgen sitter på kvartalshorisont, så jaga inte en aktie som gapat upp – fyller priset inte ≤ gränsen avstår du (nästa ombalansering fångar den annars)."
          />
        )}
        {latest.ta_score != null && latest.ta_score !== 1 && (
          <StatCard
            label="TA-score"
            value={fmtPct(latest.ta_score, 0)}
            info="Tekniskt analyspoäng – hur starkt aktiens pris-/volymmönster ser ut just nu."
          />
        )}
      </div>

      {/* Kursutveckling */}
      <div className="chart-card">
        <h3>
          Kursutveckling
          {dev != null && (
            <span className={`chart-legend ${dev >= 0 ? 'pos' : 'neg'}`}>
              {' '}— {dev >= 0 ? '+' : ''}{fmtPct(dev)} på perioden
            </span>
          )}
          <InfoButton title="Kursutveckling">
            Aktiens stängningskurs över tid (senaste ~5 åren). Detta är den faktiska priskurvan,
            inte modellens prognos.
          </InfoButton>
        </h3>
        {priceSeries.length < 2 ? (
          <div className="list-card__empty">
            Kursdata genereras vid nästa modellkörning – kom tillbaka efter en uppdatering.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={priceSeries} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="date" tickFormatter={fmtDate} stroke="#64748b" minTickGap={40} />
              <YAxis stroke="#64748b" domain={['auto', 'auto']} tick={{ fontSize: 12 }} />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
                labelFormatter={fmtDate}
                formatter={(v) => [fmtNum(v, 2), 'Kurs']}
              />
              <Area type="monotone" dataKey="close" stroke="var(--accent)" strokeWidth={1.5} fill="url(#priceFill)" />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Signalhistorik (P(upp) över tid) */}
      <div className="chart-card">
        <h3>
          Modellens signalhistorik
          <InfoButton title="Signalhistorik">
            Hur modellens uppgångssannolikhet P(upp) utvecklats över tid. Den streckade linjen är
            köptröskeln – när P(upp) ligger ovanför den ger modellen köpsignal.
          </InfoButton>
        </h3>
        {sigSeries.length < 2 ? (
          <div className="list-card__empty">För lite signalhistorik att visa än.</div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={sigSeries} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="date" tickFormatter={fmtDate} stroke="#64748b" minTickGap={40} />
              <YAxis domain={[0, 100]} stroke="#64748b" tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
                labelFormatter={fmtDate}
                formatter={(v, name) => [`${Number(v).toFixed(1)}%`, name === 'prob' ? 'P(upp)' : 'Förv. avk.']}
              />
              {stats.data?.threshold?.buy_threshold != null && (
                <ReferenceLine
                  y={stats.data.threshold.buy_threshold * 100}
                  stroke="#f59e0b"
                  strokeDasharray="4 4"
                  label={{ value: 'köptröskel', fill: '#f59e0b', fontSize: 11, position: 'insideTopRight' }}
                />
              )}
              <Line type="monotone" dataKey="prob" stroke="#4CAF50" dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  )
}
