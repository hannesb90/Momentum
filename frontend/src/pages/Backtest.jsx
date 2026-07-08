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
import { fmtDate, fmtSek, fmtPct } from '../format'

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
  const nextBuyBt = useApiData(() => api.portfolioBacktest(), [])
  const [period, setPeriod] = useState('overall')

  const chartData = useMemo(() => {
    if (!portfolio.data) return []
    return portfolio.data.map((row) => ({
      date: row.date,
      value: row.portfolio_value,
      omxs30: row.omxs30_value ?? null,
      drawdown: row.drawdown * 100,
    }))
  }, [portfolio.data])

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
        {stats.data.period.start} → {stats.data.period.end ?? 'idag'} ·{' '}
        {(stats.data.tickers ?? []).length} bolag
      </p>

      <div className="chart-card">
        <h3>
          Portföljvärde {hasOmxs30 && <span className="chart-legend">— blå: strategi · gul: index (XACT)</span>}
          <InfoButton title="Portföljvärde vs index">
            <p>
              Blå linje: hur en tänkt portfölj skulle ha utvecklats om man följt modellens
              köp/sälj-signaler historiskt. Gul linje: det <b>riktiga, ägbara</b> segment-indexet
              (XACT total-avkastning) – det du annars köper passivt.
            </p>
            <p>
              <b>OBS survivorship:</b> backtesten körs på dagens överlevande bolag; döda/av-
              noterade saknas, så strategins marginal är optimistisk. Det ärliga måttet är
              holdouten och live-liggaren – inte den här 15-åriga kurvan. Detta är en backtest,
              inte dina egna pengar.
            </p>
          </InfoButton>
        </h3>
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e1e8e3" />
            <XAxis dataKey="date" tickFormatter={fmtDate} stroke="#8aa094" minTickGap={40} />
            <YAxis stroke="#8aa094" tickFormatter={(v) => `${(v / 1e6).toFixed(1)}M`} />
            <Tooltip
              contentStyle={{ background: '#16241d', border: '1px solid #e1e8e3' }}
              labelFormatter={fmtDate}
              formatter={(v, name) => [
                `${Number(v).toLocaleString('sv-SE')} SEK`,
                name === 'omxs30' ? 'Index (XACT)' : 'Strategi',
              ]}
            />
            {hasOmxs30 && (
              <Line type="monotone" dataKey="omxs30" stroke="#f59e0b" dot={false} strokeWidth={1.5} strokeDasharray="2 3" />
            )}
            <Line type="monotone" dataKey="value" stroke="var(--accent)" dot={false} strokeWidth={1.5} />
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
            <CartesianGrid strokeDasharray="3 3" stroke="#e1e8e3" />
            <XAxis dataKey="date" tickFormatter={fmtDate} stroke="#8aa094" minTickGap={40} />
            <YAxis stroke="#8aa094" tickFormatter={(v) => `${v}%`} />
            <Tooltip
              contentStyle={{ background: '#16241d', border: '1px solid #e1e8e3' }}
              labelFormatter={fmtDate}
              formatter={(v) => [`${Number(v).toFixed(1)}%`, 'Drawdown']}
            />
            <Area type="monotone" dataKey="drawdown" stroke="#f44336" fill="#f44336" fillOpacity={0.25} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {stats.data.index_benchmark && (
        <div className="stats-block">
          <h3>
            Strategi vs index
            <InfoButton title="Strategi vs riktigt index">
              <p>
                Jämför strategin mot det <b>riktiga, ägbara</b> segment-indexet (XACT total-
                avkastning){stats.data.index_benchmark.window ? ` över ${stats.data.index_benchmark.window}` : ''}.
                Skillnaden = strategins CAGR minus indexets. Positivt = strategin slog en
                indexfond; negativt = du hade tjänat mer på att bara köpa indexet.
              </p>
              <p>
                <b>OBS survivorship:</b> backtesten körs på dagens överlevande bolag; döda/av-
                noterade saknas, så marginalen är optimistisk. Det ärliga måttet är holdouten och
                live-liggaren, inte den här kurvan.
              </p>
            </InfoButton>
          </h3>
          <div className="stat-grid">
            <StatCard
              label="Vs index (CAGR/år)"
              value={`${stats.data.index_benchmark.alpha_cagr >= 0 ? '+' : ''}${(stats.data.index_benchmark.alpha_cagr * 100).toFixed(1)}%`}
              tone={stats.data.index_benchmark.alpha_cagr >= 0 ? 'good' : 'bad'}
              info="Strategins CAGR minus det riktiga indexets CAGR, över det gemensamma fönstret. Optimistiskt pga survivorship – lita på holdout + live."
            />
            <StatCard
              label="Index CAGR"
              value={stats.data.index_benchmark.CAGR}
              info={`Årlig avkastning för ${stats.data.index_benchmark.label} (ägbar total-avkastnings-ETF).`}
            />
          </div>
        </div>
      )}

      <div className="stats-block">
        <h3>
          Nästa köp vs index
          <InfoButton title="'Nästa köp'-allokeringen mot index">
            <p>
              Isolerar precis det som "Nästa köp" faktiskt styr: <b>vart nytt kapital går</b> –
              köp-och-behåll-boken säljs aldrig. Samma startbok, tre öden för varje ny krona
              framåt:
            </p>
            <p>
              <b>A) Fyll mot mål</b> – nya insättningar riktas mot underviktade hinkar (appens
              logik). <b>B) Allt i index</b> – samma startbok, men alla nya kronor i en global
              indexfond i stället. <b>C) Sälj allt → index idag</b> – aggressiv referens: hela
              boken omvandlad till index just nu.
            </p>
            <p>
              A − B är hela svaret på frågan: <b>tjänar fyll-mot-mål-logiken sin plats</b>, eller
              hade en ren indexinsättning varit lika bra? Hinkarna proxas av ETF-korgar (bred
              kärna/Sverige-småbolag/tema), inte de enskilda aktierekommendationerna.
            </p>
          </InfoButton>
        </h3>
        {nextBuyBt.data ? (
          <>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Strategi</th><th>Slutvärde</th><th>IRR/år</th><th>Max DD</th></tr></thead>
                <tbody>
                  <tr>
                    <td>A) Fyll mot mål</td>
                    <td>{fmtSek(nextBuyBt.data.A.final)}</td>
                    <td className={nextBuyBt.data.A.irr_year >= 0 ? 'pos' : 'neg'}>{fmtPct(nextBuyBt.data.A.irr_year)}</td>
                    <td className="neg">{fmtPct(nextBuyBt.data.A.maxdd)}</td>
                  </tr>
                  <tr>
                    <td>B) Allt i index</td>
                    <td>{fmtSek(nextBuyBt.data.B.final)}</td>
                    <td className={nextBuyBt.data.B.irr_year >= 0 ? 'pos' : 'neg'}>{fmtPct(nextBuyBt.data.B.irr_year)}</td>
                    <td className="neg">{fmtPct(nextBuyBt.data.B.maxdd)}</td>
                  </tr>
                  <tr>
                    <td>C) Sälj allt → index idag</td>
                    <td>{fmtSek(nextBuyBt.data.C.final)}</td>
                    <td className={nextBuyBt.data.C.irr_year >= 0 ? 'pos' : 'neg'}>{fmtPct(nextBuyBt.data.C.irr_year)}</td>
                    <td className="neg">{fmtPct(nextBuyBt.data.C.maxdd)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="footnote">
              Startbok {fmtSek(nextBuyBt.data.start_value)} · {fmtSek(nextBuyBt.data.monthly)}/mån ·{' '}
              {nextBuyBt.data.months} insättningar · {nextBuyBt.data.years} år · A − B:{' '}
              <span className={nextBuyBt.data.A.final - nextBuyBt.data.B.final >= 0 ? 'pos' : 'neg'}>
                {fmtSek(nextBuyBt.data.A.final - nextBuyBt.data.B.final)}
              </span>
              {nextBuyBt.data.generated && ` · beräknat ${String(nextBuyBt.data.generated).slice(0, 16).replace('T', ' ')}`}
            </p>
          </>
        ) : (
          <p className="footnote">
            Inte beräknat än. Kör <code>python portfolio.py backtest 5000</code> på Pi:n
            (kräver nät för ETF-prispanelen) – resultatet cachas och visas här.
          </p>
        )}
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
