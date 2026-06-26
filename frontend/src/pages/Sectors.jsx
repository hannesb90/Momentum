import { Fragment, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ResponsiveContainer, BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { SegmentedControl } from '../components/SegmentedControl'
import { SignalBadge } from '../components/SignalBadge'
import { EmptyState } from '../components/EmptyState'
import { InfoButton } from '../components/InfoButton'
import { fmtNum, fmtPct } from '../format'

const WINDOWS = [
  { value: 'composite_score', label: 'Sammanvägt' },
  { value: 'momentum_4w', label: '4v' },
  { value: 'momentum_13w', label: '13v' },
  { value: 'momentum_26w', label: '26v' },
  { value: 'momentum_52w', label: '52v' },
]

const FLOW_FILTERS = [
  { value: 'all', label: 'Alla' },
  { value: 'Kapital in', label: 'Kapital in' },
  { value: 'Kapital ut', label: 'Kapital ut' },
]

export function SectorsPage() {
  const { data, error, loading } = useApiData(() => api.sectorMomentum(), [])
  const signals = useApiData(() => api.latestSignals(), [])
  const [metric, setMetric] = useState('composite_score')
  const [query, setQuery] = useState('')
  const [flowFilter, setFlowFilter] = useState('all')
  const [expanded, setExpanded] = useState(null)

  // Bolag per sektor, härlett ur signaldatan (varje signal har en sektor).
  // Låter användaren expandera en sektorrad och se vilka aktier som ingår.
  const bySector = useMemo(() => {
    const map = {}
    for (const s of signals.data ?? []) {
      const sec = s.sector ?? 'Okänd'
      ;(map[sec] = map[sec] ?? []).push(s)
    }
    for (const sec of Object.keys(map)) {
      map[sec].sort((a, b) => (Number(b.prob_up) || 0) - (Number(a.prob_up) || 0))
    }
    return map
  }, [signals.data])

  const rows = useMemo(() => {
    if (!data) return []
    let r = data
    if (query.trim()) {
      const q = query.trim().toLowerCase()
      r = r.filter((s) => (s.sector ?? '').toLowerCase().includes(q))
    }
    if (flowFilter !== 'all') {
      r = r.filter((s) => s.flow === flowFilter)
    }
    return [...r].sort((a, b) => (Number(b[metric]) || 0) - (Number(a[metric]) || 0))
  }, [data, metric, query, flowFilter])

  const hasFlow = data?.some((r) => r.flow != null)

  if (loading) return <Loading />
  if (error) return <ErrorBlock error={error} />

  const chartData = rows.slice(0, 12).map((r) => ({
    label: r.sector,
    value: Number(r[metric]) || 0,
  }))

  const hasMetric = (key) => data.some((r) => r[key] != null)
  const windowOptions = WINDOWS.filter((w) => hasMetric(w.value))

  return (
    <section className="page">
      <div className="page-head">
        <h1>
          Sektorer
          <InfoButton title="Sektorer">
            <p>
              Visar vilka branscher/sektorer som har starkast momentum just nu, beräknat som
              medianen av bolagens kursutveckling (ROC) i varje sektor.
            </p>
            <p>
              Varje sektor är kopplad till en handelsbar ETF om du vill agera på sektornivå istället
              för enskilda aktier.
            </p>
          </InfoButton>
        </h1>
        <p className="page-subtitle">
          Momentum aggregerat per sektor (median av bolagens ROC), mappat mot handelsbar sektor-ETF.
          {hasFlow && ' Rotation visar hur sektorns rank förändrats de senaste 4 veckorna – en proxy för var relativ styrka flyttar, inte faktiska fondflöden.'}
        </p>
      </div>

      <div className="filter-bar">
        <input
          className="search-input"
          type="search"
          placeholder="Sök sektor…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <div className="filter-bar filter-bar--secondary">
        <span className="filter-bar__label">Mått:</span>
        <SegmentedControl options={windowOptions} value={metric} onChange={setMetric} size="sm" />
      </div>
      {hasFlow && (
        <div className="filter-bar filter-bar--secondary">
          <span className="filter-bar__label">Rotation:</span>
          <SegmentedControl options={FLOW_FILTERS} value={flowFilter} onChange={setFlowFilter} size="sm" />
        </div>
      )}

      {rows.length === 0 ? (
        <EmptyState title="Ingen sektordata" hint="Kör pipelinen för att generera sector_momentum.csv." />
      ) : (
        <>
          <div className="chart-card">
            <h3>
              Rankning · {windowOptions.find((w) => w.value === metric)?.label}
              <InfoButton title="Rankningsdiagram">
                <p>
                  Staplarna visar sektorernas momentum-poäng för det valda måttet, sorterade från
                  starkast till svagast. Grönt betyder positivt momentum, rött negativt.
                </p>
                <p>
                  "Sammanvägt" kombinerar flera tidshorisonter (4/13/26/52 veckor) till en enda
                  poäng, medan de andra måtten visar momentum över just den perioden.
                </p>
              </InfoButton>
            </h3>
            <ResponsiveContainer width="100%" height={Math.max(220, chartData.length * 26)}>
              <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                <XAxis type="number" stroke="#64748b" tickFormatter={(v) => fmtNum(v, 2)} />
                <YAxis type="category" dataKey="label" stroke="#94a3b8" width={150} tick={{ fontSize: 12 }} />
                <Tooltip
                  contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
                  formatter={(v) => [fmtNum(v, 3), 'Momentum']}
                />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {chartData.map((row) => (
                    <Cell key={row.label} fill={row.value >= 0 ? 'var(--good)' : 'var(--bad)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Sektor</th>
                  <th>ETF</th>
                  <th>Bolag</th>
                  <th>Värde</th>
                  {hasFlow && (
                    <th>
                      Rotation (4v)
                      <InfoButton title="Rotation (4v)">
                        Hur sektorns rankning bland alla sektorer har förändrats de senaste 4
                        veckorna. "Kapital in" betyder att sektorn klättrat i rank (relativ styrka
                        ökar), "Kapital ut" att den fallit. Detta är en proxy baserad på rankförändring,
                        inte faktiska fondflöden.
                      </InfoButton>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => {
                  const open = expanded === row.sector
                  const members = bySector[row.sector] ?? []
                  const colSpan = hasFlow ? 6 : 5
                  return (
                    <Fragment key={row.sector}>
                      <tr
                        className="sector-row"
                        onClick={() => setExpanded(open ? null : row.sector)}
                      >
                        <td>{i + 1}</td>
                        <td className="ticker-cell">
                          <span className={`sector-caret ${open ? 'sector-caret--open' : ''}`}>▸</span>
                          {row.sector}
                        </td>
                        <td>{row.etf_ticker ?? '–'}</td>
                        <td>{row.n_stocks ?? '–'}</td>
                        <td className={Number(row[metric]) >= 0 ? 'pos' : 'neg'}>{fmtNum(row[metric], 3)}</td>
                        {hasFlow && (
                          <td>
                            <span className={`flow-chip flow-chip--${
                              row.flow === 'Kapital in' ? 'in' : row.flow === 'Kapital ut' ? 'out' : 'flat'
                            }`}>
                              {row.flow === 'Kapital in' && '↑ '}
                              {row.flow === 'Kapital ut' && '↓ '}
                              {row.flow ?? 'Okänd'}
                              {row.rank_change != null && row.rank_change !== 0
                                ? ` (${row.rank_change > 0 ? '+' : ''}${row.rank_change})`
                                : ''}
                            </span>
                          </td>
                        )}
                      </tr>
                      {open && (
                        <tr className="sector-members-row">
                          <td colSpan={colSpan}>
                            {members.length === 0 ? (
                              <div className="sector-members__empty">
                                {signals.loading
                                  ? 'Laddar bolag…'
                                  : 'Inga bolag med signaler i den här sektorn just nu.'}
                              </div>
                            ) : (
                              <div className="sector-members">
                                {members.map((m) => (
                                  <Link
                                    key={m.ticker}
                                    to={`/aktie/${encodeURIComponent(m.ticker)}`}
                                    className="sector-member"
                                  >
                                    <span className="sector-member__ticker">{m.ticker}</span>
                                    <span className="sector-member__prob">P(upp) {fmtPct(m.prob_up)}</span>
                                    <SignalBadge variant={m.pred_signal === 1 ? 'buy' : 'flat'} />
                                  </Link>
                                ))}
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
