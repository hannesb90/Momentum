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
          info="Andelen av de veckor portföljen faktiskt var investerad som gav positiv avkastning. Kontantveckor räknas inte (varken vinst eller förlust)."
        />
        {stats.Invested && (
          <StatCard
            label="Investerad andel"
            value={stats.Invested}
            info="Hur stor del av tiden portföljen var i marknaden (inte kontanter). Låg andel = kontant-drag som tynger CAGR. I den alltid-investerade designen ska denna vara hög utom i kriser, då marknadsfiltret drar ner exponeringen."
          />
        )}
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
      benchmark: row.benchmark_value ?? null,
      omxs30: row.omxs30_value ?? null,
      drawdown: row.drawdown * 100,
    }))
  }, [portfolio.data])

  const hasBenchmark = useMemo(
    () => chartData.some((d) => d.benchmark != null),
    [chartData],
  )
  const hasOmxs30 = useMemo(
    () => chartData.some((d) => d.omxs30 != null),
    [chartData],
  )

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
          Portföljvärde {hasBenchmark && <span className="chart-legend">— blå: strategi · grå: likaviktat universum{hasOmxs30 && ' · gul: OMXS30'}</span>}
          <InfoButton title="Portföljvärde vs benchmark">
            <p>
              Blå linje: hur en tänkt portfölj skulle ha utvecklats om man följt modellens
              köp/sälj-signaler historiskt. Grå linje: ett passivt likaviktat köp-och-behåll av
              samma universum. Gul linje: OMXS30 (XACT-ETF) – det en bred publik annars köper
              passivt (kap-viktat, 30 största).
            </p>
            <p>
              Om den blå inte ligger över den grå tillför strategin inget jämfört med att bara äga
              allt – det är själva testet på om modellen har en edge. Detta är en backtest, inte
              dina egna pengar.
            </p>
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
              formatter={(v, name) => [
                `${Number(v).toLocaleString('sv-SE')} SEK`,
                name === 'benchmark'
                  ? 'Likaviktat universum'
                  : name === 'omxs30'
                    ? 'OMXS30'
                    : 'Strategi',
              ]}
            />
            {hasBenchmark && (
              <Line type="monotone" dataKey="benchmark" stroke="#64748b" dot={false} strokeWidth={1.5} strokeDasharray="4 4" />
            )}
            {hasOmxs30 && (
              <Line type="monotone" dataKey="omxs30" stroke="#f59e0b" dot={false} strokeWidth={1.5} strokeDasharray="2 3" />
            )}
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

      {stats.data.benchmark && (
        <div className="stats-block">
          <h3>
            Strategi vs index
            <InfoButton title="Strategi vs index (alfa/beta)">
              <p>
                Jämför strategin mot ett passivt likaviktat köp-och-behåll av samma universum.
                Alfa = strategins årsavkastning minus indexets. Positiv alfa = strategin tillför
                värde; negativ = du hade tjänat mer på att bara äga allt.
              </p>
              <p>
                Beta = hur mycket strategin följer marknaden. Eftersom strategin är long-only bär
                den marknadsrisk – en beta nära 1 betyder att den i stort sett rör sig med index.
              </p>
            </InfoButton>
          </h3>
          <div className="stat-grid">
            <StatCard
              label="Alfa (vs index)"
              value={`${stats.data.benchmark.alpha_cagr >= 0 ? '+' : ''}${(stats.data.benchmark.alpha_cagr * 100).toFixed(1)}%`}
              tone={stats.data.benchmark.alpha_cagr >= 0 ? 'good' : 'bad'}
              info="Strategins CAGR minus indexets CAGR. Detta är kärnfrågan: tillför modellen något jämfört med att passivt äga hela universumet? Negativt = nej."
            />
            <StatCard
              label="Beta (marknad)"
              value={Number.isFinite(stats.data.benchmark.beta) ? stats.data.benchmark.beta.toFixed(2) : '–'}
              info="Marknadskänslighet. ~1 = rör sig med index, <1 = mindre svängigt än marknaden, >1 = mer. Long-only momentum har typiskt positiv beta och bär alltså marknadsrisk."
            />
            <StatCard
              label="Index CAGR"
              value={stats.data.benchmark.overall.CAGR}
              info={`Årlig avkastning för jämförelsen: ${stats.data.benchmark.label}.`}
            />
            <StatCard
              label="Index Sharpe"
              value={stats.data.benchmark.overall.Sharpe}
              info="Indexets riskjusterade avkastning – jämför med strategins Sharpe ovan."
            />
          </div>
        </div>
      )}

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
