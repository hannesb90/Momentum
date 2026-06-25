import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'

function fmtPct(v) {
  return v == null ? '–' : `${(v * 100).toFixed(1)}%`
}

export function SignalsPage() {
  const { data, error, loading } = useApiData(() => api.latestSignals(), [])

  if (loading) return <Loading />
  if (error) return <ErrorBlock error={error} />

  return (
    <section>
      <h1>Aktuella signaler</h1>
      <p className="page-subtitle">Senaste veckans modellsignal per ticker, sorterat efter sannolikhet för uppgång.</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>P(upp)</th>
              <th>Signal</th>
              <th>Förv. avkastning</th>
              <th>Positionsstorlek</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.ticker}>
                <td className="ticker-cell">{row.ticker}</td>
                <td>{fmtPct(row.prob_up)}</td>
                <td>
                  <span className={`badge ${row.pred_signal === 1 ? 'badge--up' : 'badge--flat'}`}>
                    {row.pred_signal === 1 ? 'KÖP' : '–'}
                  </span>
                </td>
                <td>{fmtPct(row.pred_return)}</td>
                <td>{fmtPct(row.position_size)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
