import { useMemo, useState } from 'react'
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { StatCard } from '../components/StatCard'
import { SegmentedControl } from '../components/SegmentedControl'
import { InfoButton } from '../components/InfoButton'
import { fmtDate } from '../format'

const PERIODS = [
  { value: 'overall', label: 'Hela perioden' },
  { value: 'dev', label: 'Dev' },
  { value: 'holdout', label: 'Holdout' },
]

function StatsRow({ title, stats }) {
  if (!stats) return null
  return (
    <div className="stats-block">
      <h3>{title}</h3>
      <div className="stat-grid">
        <StatCard
          label="Total avkastning"
          value={stats.total_return}
          info="Den totala procentuella förändringen av portföljvärdet från start till slut av perioden."
        />
        <StatCard
          label="CAGR"
          value={stats.CAGR}
          info="Compound Annual Growth Rate – den genomsnittliga årliga tillväxttakten, som om avkastningen skett jämnt fördelat över åren."
        />
        <StatCard
          label="Sharpe"
          value={stats.Sharpe}
          tone={Number(stats.Sharpe) >= 1 ? 'good' : 'neutral'}
          info="Avkastning i förhållande till risk (volatilitet). Över 1 är bra, över 2 är mycket starkt."
        />
        <StatCard
          label="Sortino"
          value={stats.Sortino}
          info="Liknar Sharpe men straffar bara nedåtrisk (förluster) – uppåtrörelser räknas inte som 'risk'. Ofta mer relevant än Sharpe för strategier med skev avkastningsfördelning."
        />
        <StatCard
          label="Max Drawdown"
          value={stats['Max Drawdown']}
          tone="bad"
          info="Den största nedgången från en topp till en efterföljande botten under perioden – det värsta scenariot man hade behövt stå ut med."
        />
        <StatCard
          label="Win Rate"
          value={stats['Win Rate']}
          info="Andelen perioder/affärer med positiv avkastning. Säger inget om hur stora vinsterna respektive förlusterna var."
        />
      </div>
    </div>
  )
}

export function BacktestPage() {
  const portfolio = useApiData(() => api.portfolio(), [])
  const stats = useApiData(() => api.stats(), [])
  const [period, setPeriod] = useState('overall')

  const chartData = useMemo(() => {
    if (!portfolio.data) return []
    return portfolio.data.map((row) => ({
      date: row.date,
      value: row.portfolio_value,
      drawdown: row.drawdown * 100,
    }))
  }, [portfolio.data])

  if (portfolio.loading || stats.loading) return <Loading />
  if (portfolio.error) return <ErrorBlock error={portfolio.error} />
  if (stats.error) return <ErrorBlock error={stats.error} />

  return (
    <section>
      <h1>Backtest</h1>
      <p className="page-subtitle">
        {stats.data.period.start} → {stats.data.period.end ?? 'idag'} · {stats.data.tickers.join(', ')}
      </p>

      <div className="chart-card">
        <h3>
          Portföljvärde
          <InfoButton title="Portföljvärde">
            <p>
              Hur en tänkt portfölj skulle ha utvecklats över tid om man följt modellens
              köp/sälj-signaler historiskt, med start på en fast summa.
            </p>
            <p>Detta är en backtest, inte dina egna pengar – se fliken Portfölj för dina innehav.</p>
          </InfoButton>
        </h3>
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="date" tickFormatter={fmtDate} stroke="#64748b" minTickGap={40} />
            <YAxis stroke="#64748b" tickFormatter={(v) => `${(v / 1e6).toFixed(1)}M`} />
            <Tooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #1e293b' }}
              labelFormatter={fmtDate}
              formatter={(v) => [`${Number(v).toLocaleString('sv-SE')} SEK`, 'Portföljvärde']}
            />
            <Line type="monotone" dataKey="value" stroke="#2196F3" dot={false} strokeWidth={1.5} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-card">
        <h3>
          Drawdown
          <InfoButton title="Drawdown">
            Hur många procent portföljvärdet legat under sin senaste topp vid varje tidpunkt. Visar
            hur djupa och långvariga nedgångarna varit under backtestperioden.
          </InfoButton>
        </h3>
        <ResponsiveContainer width="100%" height={160}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="date" tickFormatter={fmtDate} stroke="#64748b" minTickGap={40} />
            <YAxis stroke="#64748b" tickFormatter={(v) => `${v}%`} />
            <Tooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #1e293b' }}
              labelFormatter={fmtDate}
              formatter={(v) => [`${Number(v).toFixed(1)}%`, 'Drawdown']}
            />
            <Area type="monotone" dataKey="drawdown" stroke="#f44336" fill="#f44336" fillOpacity={0.25} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="filter-bar filter-bar--secondary">
        <span className="filter-bar__label">Period:</span>
        <SegmentedControl options={PERIODS} value={period} onChange={setPeriod} size="sm" />
      </div>
      {period === 'overall' && <StatsRow title="Hela perioden" stats={stats.data.overall} />}
      {period === 'dev' && <StatsRow title="Dev-period (tränad på)" stats={stats.data.dev} />}
      {period === 'holdout' && <StatsRow title="Holdout (frusen, aldrig sedd)" stats={stats.data.holdout} />}
    </section>
  )
}
