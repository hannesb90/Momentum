import { useMemo, useState } from 'react'
import { ResponsiveContainer, BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { SegmentedControl } from '../components/SegmentedControl'
import { EmptyState } from '../components/EmptyState'
import { fmtNum } from '../format'

const WINDOWS = [
  { value: 'composite_score', label: 'Sammanvägt' },
  { value: 'momentum_4w', label: '4v' },
  { value: 'momentum_13w', label: '13v' },
  { value: 'momentum_26w', label: '26v' },
  { value: 'momentum_52w', label: '52v' },
]

export function SectorsPage() {
  const { data, error, loading } = useApiData(() => api.sectorMomentum(), [])
  const [metric, setMetric] = useState('composite_score')
  const [query, setQuery] = useState('')

  const rows = useMemo(() => {
    if (!data) return []
    let r = data
    if (query.trim()) {
      const q = query.trim().toLowerCase()
      r = r.filter((s) => (s.sector ?? '').toLowerCase().includes(q))
    }
    return [...r].sort((a, b) => (Number(b[metric]) || 0) - (Number(a[metric]) || 0))
  }, [data, metric, query])

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
        <h1>Sektorer</h1>
        <p className="page-subtitle">
          Momentum aggregerat per sektor (median av bolagens ROC), mappat mot handelsbar sektor-ETF.
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

      {rows.length === 0 ? (
        <EmptyState title="Ingen sektordata" hint="Kör pipelinen för att generera sector_momentum.csv." />
      ) : (
        <>
          <div className="chart-card">
            <h3>Rankning · {windowOptions.find((w) => w.value === metric)?.label}</h3>
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
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={row.sector}>
                    <td>{i + 1}</td>
                    <td className="ticker-cell">{row.sector}</td>
                    <td>{row.etf_ticker ?? '–'}</td>
                    <td>{row.n_stocks ?? '–'}</td>
                    <td className={Number(row[metric]) >= 0 ? 'pos' : 'neg'}>{fmtNum(row[metric], 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
