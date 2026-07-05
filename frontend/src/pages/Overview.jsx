import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ResponsiveContainer, AreaChart, Area, YAxis, Tooltip } from 'recharts'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { SignalBadge } from '../components/SignalBadge'
import { InfoButton } from '../components/InfoButton'
import { LiveTrackRecord } from '../components/LiveTrackRecord'
import { SegmentedControl } from '../components/SegmentedControl'
import { fmtPct, fmtSek, fmtNum, cleanName } from '../format'

const NEXTBUY_AMOUNTS = [
  { value: '1000', label: '1 000 kr' },
  { value: '5000', label: '5 000 kr' },
  { value: '10000', label: '10 000 kr' },
]

export function OverviewPage() {
  const stats = useApiData(() => api.stats(), [])
  const portfolio = useApiData(() => api.portfolio(), [])
  const signals = useApiData(() => api.latestSignals(), [])
  const sectors = useApiData(() => api.sectorMomentum(), [])
  const myLog = useApiData(() => api.portfolioLog(), [])
  const [buyAmount, setBuyAmount] = useState('5000')
  const nextBuy = useApiData(() => api.nextBuy(buyAmount), [buyAmount])

  const mySeries = useMemo(
    () => (myLog.data ?? []).map((r) => ({ date: r.date, value: r.value })),
    [myLog.data],
  )
  const myNow = mySeries.length ? mySeries[mySeries.length - 1].value : null
  const myChange = mySeries.length >= 2 ? mySeries[mySeries.length - 1].value / mySeries[0].value - 1 : null

  const series = useMemo(() => {
    if (!portfolio.data) return []
    return portfolio.data.map((r) => ({
      date: r.date,
      value: r.portfolio_value,
      idx: r.omxs30_value,         // riktigt, ägbart segment-index (XACT total-avk.)
    }))
  }, [portfolio.data])
  const hasIdx = series.some((r) => r.idx != null)

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
      {/* CORE – Nästa köp: ETT rangordnat svar på "var ska nästa krona in?" */}
      <div className="section-head">
        <h2>
          Nästa köp
          <InfoButton title="Nästa köp – modellens Core">
            <p>
              Det här är appens huvudsvar: <b>hit går nästa krona</b>, givet dina sparade innehav
              och målfördelningen (fyll-mot-mål – ingen försäljning, ingen timing).
            </p>
            <p>
              Ordningen är evidensordningen från våra egna tester: <b>bred global kärna först</b>
              (slog varje aktiv variant netto), därefter Sverige-modellen och rotationens tema som
              små satelliter – ärligt stämplade som obevisade aktiva vad.
            </p>
          </InfoButton>
        </h2>
        <SegmentedControl options={NEXTBUY_AMOUNTS} value={buyAmount} onChange={setBuyAmount} size="sm" />
      </div>
      <div className="list-card">
        {nextBuy.loading && <div className="list-card__empty">Räknar…</div>}
        {nextBuy.error && <div className="list-card__empty">Kunde inte hämta planen.</div>}
        {(nextBuy.data?.rows ?? []).map((r) => (
          <div key={`${r.order}-${r.ticker}`} className="list-row">
            <div className="list-row__main">
              <span className="list-row__ticker">
                {r.order}. {r.name}{' '}
                <span className={r.evidence === 'kärna' ? 'pos' : ''} style={{ fontSize: '0.78em' }}>
                  {r.evidence === 'kärna' ? '● kärna' : '○ satellit'}
                </span>
              </span>
              <span className="list-row__sub">{r.ticker} · {r.why}</span>
            </div>
            <div className="list-row__side">
              <span className="list-row__num">{fmtSek(r.kr)}</span>
            </div>
          </div>
        ))}
        {(nextBuy.data?.skipped ?? []).map((s) => (
          <div key={s.bucket} className="list-row" style={{ opacity: 0.6 }}>
            <div className="list-row__main">
              <span className="list-row__sub">{s.reason}</span>
            </div>
          </div>
        ))}
        {nextBuy.data && !nextBuy.data.has_holdings && (
          <div className="list-card__empty">
            <Link to="/innehav">Spara dina innehav</Link> så anpassas planen efter vad du redan äger.
          </div>
        )}
      </div>
      {nextBuy.data?.note && <p className="footnote">{nextBuy.data.note}</p>}

      {/* Backtest – simulering, nedgraderad under Coret */}
      <div className={`hero ${positiveReturn ? 'hero--up' : 'hero--down'}`}>
        <div className="hero__label">
          Backtest · simulering – inte dina pengar
          <InfoButton title="Backtest · simulering">
            <p>
              Det här är INTE dina egna pengar – det är hur en tänkt portfölj skulle ha utvecklats om
              man hade följt modellens köp/sälj-signaler historiskt, med start på en fast summa.
            </p>
            <p>
              <b>OBS survivorship:</b> simuleringen körs på dagens överlevande bolag – döda/avnoterade
              saknas – så kurvan är systematiskt för optimistisk. Det ärliga måttet är holdouten
              (aldrig sedd data) som visas nedan, och din egen framåt-loggade portfölj.
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
        {stats.data.index_benchmark && (
          <div className="hero__bench">
            {stats.data.index_benchmark.label}: {stats.data.index_benchmark.CAGR}/år ·{' '}
            <span className={stats.data.index_benchmark.alpha_cagr >= 0 ? 'pos' : 'neg'}>
              vs index {stats.data.index_benchmark.alpha_cagr >= 0 ? '+' : ''}
              {(stats.data.index_benchmark.alpha_cagr * 100).toFixed(1)}%/år
            </span>
            <InfoButton title="Strategi vs riktigt index">
              <p>
                Jämför strategin mot det <b>riktiga, ägbara</b> segment-indexet (XACT total-
                avkastning){stats.data.index_benchmark.window ? ` över ${stats.data.index_benchmark.window}` : ''}.
                Positivt = strategin slog en indexfond, negativt = du hade tjänat mer på att bara
                köpa indexet.
              </p>
              <p>
                <b>OBS survivorship:</b> backtesten körs på dagens överlevande bolag – döda/av-
                noterade saknas – så marginalen är optimistisk. Lita på holdouten och live-liggaren.
              </p>
            </InfoButton>
          </div>
        )}
        {stats.data.holdout?.CAGR && (
          <div className="hero__bench">
            Holdout (ärligaste måttet, aldrig sedd data): CAGR{' '}
            <span className={String(stats.data.holdout.CAGR).trim().startsWith('-') ? 'neg' : 'pos'}>
              {stats.data.holdout.CAGR}
            </span>
            <InfoButton title="Holdout – det ärliga måttet">
              <p>
                De senaste två åren är <b>frusna</b>: modellen tränas aldrig på dem. Siffran här är
                därför den enda historiska mätning som liknar verkligheten – till skillnad från
                15-årskurvan ovan, som är survivorship-uppblåst.
              </p>
              <p>Är holdouten svag ska du lita mer på den breda kärnan än på strategins signaler.</p>
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
                  formatter={(v, name) => [fmtSek(v), name === 'idx' ? 'Index (XACT)' : 'Strategi']}
                  labelFormatter={() => ''}
                />
                {hasIdx && (
                  <Area type="monotone" dataKey="idx" stroke="var(--good)" strokeWidth={1.6}
                    fill="none" dot={false} connectNulls />
                )}
                <Area type="monotone" dataKey="value" stroke="var(--accent)" strokeWidth={2} fill="url(#heroFill)" />
              </AreaChart>
            </ResponsiveContainer>
            {hasIdx && (
              <div className="hero__legend">
                <span><i className="dot dot--accent" />Strategi</span>
                <span><i className="dot dot--good" />Index (XACT total-avk.)</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Min egen portfölj – framåt-logg (byggs upp från och med första sparningen) */}
      {myLog.data && (
        <section className="myportf">
          <div className="myportf__head">
            <h3 className="section-title" style={{ margin: 0 }}>
              Min portfölj
              <InfoButton title="Din faktiska portfölj">
                <p>
                  Din egen portföljs totalvärde loggas varje gång du sparar innehav (en punkt
                  per dag). Kurvan byggs upp <b>framåt</b> härifrån – det finns ingen historik
                  bakåt eftersom värdet matas in manuellt.
                </p>
              </InfoButton>
            </h3>
            {myNow != null && <span className="myportf__val">{fmtSek(myNow)}</span>}
            {myChange != null && (
              <span className={myChange >= 0 ? 'pos' : 'neg'}>{fmtPct(myChange)}</span>
            )}
          </div>
          {mySeries.length >= 2 ? (
            <ResponsiveContainer width="100%" height={56}>
              <AreaChart data={mySeries} margin={{ top: 4, bottom: 0, left: 0, right: 0 }}>
                <defs>
                  <linearGradient id="myFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--good)" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="var(--good)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <YAxis domain={['dataMin', 'dataMax']} hide />
                <Tooltip
                  contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
                  formatter={(v) => [fmtSek(v), 'Min portfölj']}
                  labelFormatter={(l) => l}
                />
                <Area type="monotone" dataKey="value" stroke="var(--good)" strokeWidth={2} fill="url(#myFill)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <p className="footnote" style={{ marginTop: 4 }}>
              {myNow != null
                ? 'Kurvan börjar byggas – spara innehav igen framöver så växer historiken.'
                : 'Spara dina innehav i Innehav-fliken så börjar din portfölj-kurva byggas här.'}
            </p>
          )}
        </section>
      )}

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
