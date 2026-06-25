import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { StatCard } from '../components/StatCard'

function fmtDate(d) {
  return new Date(d).toLocaleDateString('sv-SE', { year: '2-digit', month: 'short' })
}

function PercentileRow({ label, pct, fmt }) {
  return (
    <tr>
      <td>{label}</td>
      <td>{fmt(pct.p5)}</td>
      <td className="cell-strong">{fmt(pct.p50)}</td>
      <td>{fmt(pct.p95)}</td>
    </tr>
  )
}

export function RobustnessPage() {
  const stats = useApiData(() => api.stats(), [])
  const drift = useApiData(() => api.drift(), [])

  if (stats.loading || drift.loading) return <Loading />
  if (stats.error) return <ErrorBlock error={stats.error} />
  if (drift.error) return <ErrorBlock error={drift.error} />

  const { robustness, drift: driftSummary } = stats.data
  const boot = robustness.bootstrap

  return (
    <section>
      <h1>Robusthet & modell-drift</h1>
      <p className="page-subtitle">
        Block bootstrap-konfidensintervall, Probabilistic/Deflated Sharpe Ratio och rullande AUC mot realiserade utfall.
      </p>

      <div className="stat-grid">
        <StatCard label="Probabilistic Sharpe" value={`${(robustness.psr * 100).toFixed(1)}%`} tone={robustness.psr > 0.95 ? 'good' : 'neutral'} />
        <StatCard
          label={`Deflated Sharpe (n=${robustness.n_trials})`}
          value={`${(robustness.dsr * 100).toFixed(1)}%`}
          tone={robustness.dsr > 0.95 ? 'good' : 'neutral'}
        />
        <StatCard label="P(Sharpe ≤ 0)" value={`${(boot.prob_sharpe_below_0 * 100).toFixed(1)}%`} tone="bad" />
      </div>

      <div className="chart-card">
        <h3>Bootstrap-konfidensintervall (p5 / p50 / p95)</h3>
        <table>
          <thead>
            <tr>
              <th>Mått</th>
              <th>p5</th>
              <th>p50</th>
              <th>p95</th>
            </tr>
          </thead>
          <tbody>
            <PercentileRow label="Sharpe" pct={boot.sharpe} fmt={(v) => v.toFixed(2)} />
            <PercentileRow label="CAGR" pct={boot.cagr} fmt={(v) => `${(v * 100).toFixed(1)}%`} />
            <PercentileRow label="Max Drawdown" pct={boot.max_dd} fmt={(v) => `${(v * 100).toFixed(1)}%`} />
          </tbody>
        </table>
      </div>

      {driftSummary && (
        <div className="stat-grid">
          <StatCard label="Senaste rullande AUC" value={driftSummary.auc.toFixed(3)} tone={driftSummary.flagged ? 'bad' : 'good'} />
          <StatCard label="Senaste hit-rate" value={`${(driftSummary.hit_rate * 100).toFixed(1)}%`} />
          <StatCard label="Flaggade perioder" value={`${driftSummary.n_flagged}/${driftSummary.n_periods}`} />
        </div>
      )}

      <div className="chart-card">
        <h3>Rullande AUC mot realiserat utfall</h3>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={drift.data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="date" tickFormatter={fmtDate} stroke="#64748b" minTickGap={40} />
            <YAxis domain={[0.3, 0.8]} stroke="#64748b" />
            <Tooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #1e293b' }}
              labelFormatter={fmtDate}
              formatter={(v) => [Number(v).toFixed(3), 'AUC']}
            />
            {driftSummary && (
              <ReferenceLine y={driftSummary.auc_floor} stroke="#f44336" strokeDasharray="4 4" label="Golv" />
            )}
            <Line type="monotone" dataKey="auc" stroke="#4CAF50" dot={false} strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
