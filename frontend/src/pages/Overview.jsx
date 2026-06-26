import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { ResponsiveContainer, AreaChart, Area, YAxis, Tooltip } from 'recharts'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { SignalBadge } from '../components/SignalBadge'
import { fmtPct, fmtSek, fmtNum } from '../format'

export function OverviewPage() {
  const stats = useApiData(() => api.stats(), [])
  const portfolio = useApiData(() => api.portfolio(), [])
  const signals = useApiData(() => api.latestSignals(), [])
  const sectors = useApiData(() => api.sectorMomentum(), [])

  const series = useMemo(() => {
    if (!portfolio.data) return []
    return portfolio.data.map((r) => ({ date: r.date, value: r.portfolio_value }))
  }, [portfolio.data])

  if (stats.loading || portfolio.loading) return <Loading />
  if (stats.error) return <ErrorBlock error={stats.error} />
  if (portfolio.error) return <ErrorBlock error={portfolio.error} />

  const overall = stats.data.overall ?? {}
  const latestValue = series.length ? series[series.length - 1].value : null
  const totalReturn = overall.total_return
  const positiveReturn = !String(totalReturn ?? '').trim().startsWith('-')

  const topBuys = (signals.data ?? [])
    .filter((s) => s.pred_signal === 1)
    .slice(0, 5)

  const topSectors = (sectors.data ?? []).slice(0, 3)

  return (
    <section className="page">
      {/* Hero – strategins backtestportfölj som "saldo" */}
      <div className={`hero ${positiveReturn ? 'hero--up' : 'hero--down'}`}>
        <div className="hero__label">Strategins portfölj · backtest</div>
        <div className="hero__value">{fmtSek(latestValue)}</div>
        <div className="hero__return">
          <span className={`hero__chip ${positiveReturn ? 'hero__chip--up' : 'hero__chip--down'}`}>
            {positiveReturn ? '▲' : '▼'} {totalReturn ?? '–'}
          </span>
          <span className="hero__period">
            {stats.data.period.start} → {stats.data.period.end ?? 'idag'}
          </span>
        </div>
        {series.length > 0 && (
          <div className="hero__spark">
            <ResponsiveContainer width="100%" height={64}>
              <AreaChart data={series} margin={{ top: 4, bottom: 0, left: 0, right: 0 }}>
                <defs>
                  <linearGradient id="heroFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <YAxis domain={['dataMin', 'dataMax']} hide />
                <Tooltip
                  contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
                  formatter={(v) => [fmtSek(v), 'Värde']}
                  labelFormatter={() => ''}
                />
                <Area type="monotone" dataKey="value" stroke="var(--accent)" strokeWidth={2} fill="url(#heroFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Snabbstatistik */}
      <div className="tile-grid">
        <div className="tile">
          <div className="tile__label">CAGR</div>
          <div className="tile__value">{overall.CAGR ?? '–'}</div>
        </div>
        <div className="tile">
          <div className="tile__label">Sharpe</div>
          <div className={`tile__value ${Number(overall.Sharpe) >= 1 ? 'tile__value--good' : ''}`}>
            {fmtNum(overall.Sharpe)}
          </div>
        </div>
        <div className="tile">
          <div className="tile__label">Max Drawdown</div>
          <div className="tile__value tile__value--bad">{overall['Max Drawdown'] ?? '–'}</div>
        </div>
        <div className="tile">
          <div className="tile__label">Win Rate</div>
          <div className="tile__value">{overall['Win Rate'] ?? '–'}</div>
        </div>
      </div>

      {/* Senaste köpsignaler */}
      <div className="section-head">
        <h2>Senaste köpsignaler</h2>
        <Link to="/signaler" className="section-head__link">Visa alla →</Link>
      </div>
      <div className="list-card">
        {topBuys.length === 0 && <div className="list-card__empty">Inga aktiva köpsignaler just nu.</div>}
        {topBuys.map((s) => (
          <Link to="/signaler" key={s.ticker} className="list-row">
            <div className="list-row__main">
              <span className="list-row__ticker">{s.ticker}</span>
              <span className="list-row__sub">P(upp) {fmtPct(s.prob_up)}</span>
            </div>
            <div className="list-row__side">
              <span className="list-row__num">{fmtPct(s.pred_return)}</span>
              <SignalBadge variant="buy" />
            </div>
          </Link>
        ))}
      </div>

      {/* Heta sektorer */}
      {topSectors.length > 0 && (
        <>
          <div className="section-head">
            <h2>Heta sektorer</h2>
            <Link to="/sektorer" className="section-head__link">Visa alla →</Link>
          </div>
          <div className="list-card">
            {topSectors.map((sec) => (
              <Link to="/sektorer" key={sec.sector} className="list-row">
                <div className="list-row__main">
                  <span className="list-row__ticker">{sec.sector}</span>
                  <span className="list-row__sub">{sec.etf_ticker ?? '–'} · {sec.n_stocks} bolag</span>
                </div>
                <div className="list-row__side">
                  <span className={`list-row__num ${Number(sec.composite_score) >= 0 ? 'pos' : 'neg'}`}>
                    {fmtNum(sec.composite_score, 3)}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
