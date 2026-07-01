import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { ResponsiveContainer, AreaChart, Area, YAxis, Tooltip } from 'recharts'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { SignalBadge } from '../components/SignalBadge'
import { InfoButton } from '../components/InfoButton'
import { LiveTrackRecord } from '../components/LiveTrackRecord'
import { fmtPct, fmtSek, fmtNum, cleanName } from '../format'

export function OverviewPage() {
  const stats = useApiData(() => api.stats(), [])
  const portfolio = useApiData(() => api.portfolio(), [])
  const signals = useApiData(() => api.latestSignals(), [])
  const sectors = useApiData(() => api.sectorMomentum(), [])

  const series = useMemo(() => {
    if (!portfolio.data) return []
    return portfolio.data.map((r) => ({
      date: r.date, value: r.portfolio_value, index: r.benchmark_value,
    }))
  }, [portfolio.data])
  const hasIndex = series.some((r) => r.index != null)

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
        <div className="hero__label">
          Strategins portfölj · backtest
          <InfoButton title="Strategins portfölj · backtest">
            <p>
              Det här är INTE dina egna pengar – det är hur en tänkt portfölj skulle ha utvecklats om
              man hade följt modellens köp/sälj-signaler historiskt, med start på en fast summa.
            </p>
            <p>
              Syftet är att visa hur strategin presterat över tid innan du litar på den med riktiga
              pengar. Se fliken Portfölj för dina egna, faktiska innehav.
            </p>
          </InfoButton>
        </div>
        <div className="hero__value">{fmtSek(latestValue)}</div>
        <div className="hero__return">
          <span className={`hero__chip ${positiveReturn ? 'hero__chip--up' : 'hero__chip--down'}`}>
            {positiveReturn ? '▲' : '▼'} {totalReturn ?? '–'}
          </span>
          <span className="hero__period">
            {stats.data.period.start} → {stats.data.period.end ?? 'idag'}
          </span>
        </div>
        {stats.data.market?.enabled && stats.data.market.regime && (
          <div className="hero__bench">
            Marknadsläge:{' '}
            {{ bull: 'Bull (full exponering)', bear: 'Bear (defensiv)', sideways: 'Sidledes (nedskalad)' }[
              stats.data.market.regime
            ] ?? stats.data.market.regime}{' '}
            · rekommenderad exponering {Math.round(stats.data.market.exposure * 100)}%
            <InfoButton title="Marknadsfilter (long-only)">
              <p>
                Strategin blankar aldrig. I stället drar den ner andelen som är investerad mot
                kontanter när den breda marknaden är svag (bear), och kör fullt i stark trend
                (bull). Detta sänker marknadsrisken och nedgångarna utan blankning.
              </p>
              <p>Rekommenderad exponering visar hur stor del av portföljen som bör vara investerad nu.</p>
            </InfoButton>
          </div>
        )}
        {stats.data.benchmark && (
          <div className="hero__bench">
            Index (köp-och-behåll): {stats.data.benchmark.overall.CAGR}/år ·{' '}
            <span className={stats.data.benchmark.alpha_cagr >= 0 ? 'pos' : 'neg'}>
              alfa {stats.data.benchmark.alpha_cagr >= 0 ? '+' : ''}
              {(stats.data.benchmark.alpha_cagr * 100).toFixed(1)}%
            </span>
            <InfoButton title="Alfa mot index">
              <p>
                Jämför strategin mot ett passivt likaviktat köp-och-behåll av samma universum. Alfa
                = strategins årsavkastning minus indexets.
              </p>
              <p>
                Positiv alfa = strategin tillför värde. Negativ = du hade tjänat mer på att bara äga
                allt. Se fliken Analys → Backtest för full jämförelse.
              </p>
            </InfoButton>
          </div>
        )}
        {series.length > 0 && (
          <div className="hero__spark">
            <ResponsiveContainer width="100%" height={72}>
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
                  formatter={(v, name) => [fmtSek(v), name === 'index' ? 'Index' : 'Strategi']}
                  labelFormatter={() => ''}
                />
                {hasIndex && (
                  <Area type="monotone" dataKey="index" stroke="var(--text-muted)" strokeWidth={1.5}
                    strokeDasharray="4 3" fill="none" dot={false} />
                )}
                <Area type="monotone" dataKey="value" stroke="var(--accent)" strokeWidth={2} fill="url(#heroFill)" />
              </AreaChart>
            </ResponsiveContainer>
            {hasIndex && (
              <div className="hero__legend">
                <span><i className="dot dot--accent" />Strategins portfölj</span>
                <span><i className="dot dot--muted" />Index (köp-och-behåll)</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Snabbstatistik */}
      <div className="tile-grid">
        <div className="tile">
          <div className="tile__label">
            CAGR
            <InfoButton title="CAGR">
              <p>
                Compound Annual Growth Rate – den genomsnittliga årliga tillväxttakten för
                backtestportföljen, omräknad som om värdeökningen hade skett jämnt år för år.
              </p>
              <p>Ju högre, desto bättre – men jämför alltid med risken (se Sharpe och Max Drawdown).</p>
            </InfoButton>
          </div>
          <div className="tile__value">{overall.CAGR ?? '–'}</div>
        </div>
        <div className="tile">
          <div className="tile__label">
            Sharpe
            <InfoButton title="Sharpe-kvot">
              <p>
                Mäter avkastning i förhållande till hur mycket portföljvärdet svänger (risken). Ett
                högre tal betyder bättre avkastning per enhet risk som tagits.
              </p>
              <p>Som riktmärke: under 1 är svagt, 1–2 är bra, över 2 är mycket starkt.</p>
            </InfoButton>
          </div>
          <div className={`tile__value ${Number(overall.Sharpe) >= 1 ? 'tile__value--good' : ''}`}>
            {fmtNum(overall.Sharpe)}
          </div>
        </div>
        <div className="tile">
          <div className="tile__label">
            Max Drawdown
            <InfoButton title="Max Drawdown">
              <p>
                Den största nedgången portföljen haft från en topp till en efterföljande botten,
                innan den hämtade sig igen. Visar hur illa det kunde gå att hålla strategin under
                den sämsta perioden i backtesten.
              </p>
              <p>Ett stort (negativt) tal betyder att man behöver kunna stå ut med stora nedgångar.</p>
            </InfoButton>
          </div>
          <div className="tile__value tile__value--bad">{overall['Max Drawdown'] ?? '–'}</div>
        </div>
        <div className="tile">
          <div className="tile__label">
            Win Rate
            <InfoButton title="Win Rate">
              <p>
                Andelen av de veckor då portföljen <strong>faktiskt var investerad</strong> som gav
                positiv avkastning. Kontantveckor räknas inte (de är varken vinst eller förlust).
              </p>
              <p>
                En hög win rate är inte allt – några stora vinster kan väga upp många små förluster,
                och vice versa.
              </p>
            </InfoButton>
          </div>
          <div className="tile__value">{overall['Win Rate'] ?? '–'}</div>
        </div>
      </div>

      {/* Live track record (pappershandel) */}
      <LiveTrackRecord />

      {/* Senaste köpsignaler */}
      <div className="section-head">
        <h2>
          Senaste köpsignaler
          <InfoButton title="Senaste köpsignaler">
            <p>
              De aktier modellen senast bedömt ha störst sannolikhet att gå upp (P(upp)) och därför
              fått en köpsignal. Listan visar bara köpsignaler, sorterade efter förväntad avkastning.
            </p>
            <p>Klicka på en rad för att se alla signaler i detalj på fliken Signaler.</p>
          </InfoButton>
        </h2>
        <Link to="/signaler" className="section-head__link">Visa alla →</Link>
      </div>
      <div className="list-card">
        {topBuys.length === 0 && <div className="list-card__empty">Inga aktiva köpsignaler just nu.</div>}
        {topBuys.map((s) => (
          <Link to={`/aktie/${encodeURIComponent(s.ticker)}`} key={s.ticker} className="list-row">
            <div className="list-row__main">
              <span className="list-row__ticker">{cleanName(s.name, s.ticker)}</span>
              <span className="list-row__sub">{s.ticker} · P(upp) {fmtPct(s.prob_up)}</span>
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
            <h2>
              Heta sektorer
              <InfoButton title="Heta sektorer">
                <p>
                  Sektorer som modellen just nu bedömer ha starkast momentum, baserat på en
                  sammanvägd poäng (composite score) av flera tekniska faktorer för bolagen i
                  sektorn.
                </p>
                <p>Ett högre (mer positivt) värde betyder starkare uppåttrend i sektorn som helhet.</p>
              </InfoButton>
            </h2>
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
