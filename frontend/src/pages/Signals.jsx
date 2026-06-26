import { useMemo, useState } from 'react'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { SegmentedControl } from '../components/SegmentedControl'
import { SignalBadge } from '../components/SignalBadge'
import { EmptyState } from '../components/EmptyState'
import { fmtPct } from '../format'

const SIGNAL_FILTERS = [
  { value: 'all', label: 'Alla' },
  { value: 'buy', label: 'Köp' },
  { value: 'flat', label: 'Neutrala' },
]

const SORTS = [
  { value: 'prob_up', label: 'P(upp)' },
  { value: 'pred_return', label: 'Förv. avk.' },
  { value: 'position_size', label: 'Storlek' },
]

export function SignalsPage() {
  const { data, error, loading } = useApiData(() => api.latestSignals(), [])
  const [query, setQuery] = useState('')
  const [signalFilter, setSignalFilter] = useState('all')
  const [sort, setSort] = useState('prob_up')

  const rows = useMemo(() => {
    if (!data) return []
    let r = data
    if (query.trim()) {
      const q = query.trim().toUpperCase()
      r = r.filter((s) => s.ticker.toUpperCase().includes(q))
    }
    if (signalFilter === 'buy') r = r.filter((s) => s.pred_signal === 1)
    if (signalFilter === 'flat') r = r.filter((s) => s.pred_signal !== 1)
    return [...r].sort((a, b) => (Number(b[sort]) || 0) - (Number(a[sort]) || 0))
  }, [data, query, signalFilter, sort])

  if (loading) return <Loading />
  if (error) return <ErrorBlock error={error} />

  const buyCount = data.filter((s) => s.pred_signal === 1).length
  const hasTa = data.some((s) => s.ta_score != null && s.ta_score !== 1)

  return (
    <section className="page">
      <div className="page-head">
        <h1>Signaler</h1>
        <p className="page-subtitle">
          {data.length} bolag · {buyCount} köpsignaler denna vecka
        </p>
      </div>

      <div className="filter-bar">
        <input
          className="search-input"
          type="search"
          placeholder="Sök ticker…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <SegmentedControl options={SIGNAL_FILTERS} value={signalFilter} onChange={setSignalFilter} size="sm" />
      </div>
      <div className="filter-bar filter-bar--secondary">
        <span className="filter-bar__label">Sortera:</span>
        <SegmentedControl options={SORTS} value={sort} onChange={setSort} size="sm" />
      </div>

      {rows.length === 0 ? (
        <EmptyState title="Inga signaler matchar" hint="Justera filtren eller sökningen." />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>P(upp)</th>
                <th>Signal</th>
                <th>Förv. avk.</th>
                {hasTa && <th>TA</th>}
                <th>Storlek</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.ticker}>
                  <td className="ticker-cell">{row.ticker}</td>
                  <td>{fmtPct(row.prob_up)}</td>
                  <td><SignalBadge variant={row.pred_signal === 1 ? 'buy' : 'flat'} /></td>
                  <td>{fmtPct(row.pred_return)}</td>
                  {hasTa && <td>{row.ta_score == null ? '–' : fmtPct(row.ta_score, 0)}</td>}
                  <td>{fmtPct(row.position_size)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
