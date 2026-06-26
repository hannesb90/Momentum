import { ResponsiveContainer, BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { InfoButton } from '../components/InfoButton'

const REGIME_LABELS = { bull: 'Bull', bear: 'Bear', sideways: 'Sidledes' }
const REGIME_COLORS = { bull: '#4CAF50', bear: '#f44336', sideways: '#64748b' }

export function RegimesPage() {
  const { data, error, loading } = useApiData(() => api.regime(), [])

  if (loading) return <Loading />
  if (error) return <ErrorBlock error={error} />

  const chartData = data.map((row) => ({
    ...row,
    label: REGIME_LABELS[row.regime] ?? row.regime,
  }))

  return (
    <section>
      <h1>
        Marknadsregimer
        <InfoButton title="Marknadsregimer">
          <p>
            Marknaden klassificeras löpande som "Bull" (uppåttrend), "Bear" (nedåttrend) eller
            "Sidledes" baserat på det allmänna marknadsklimatet. Detta visar hur strategin presterat
            i varje typ av regim.
          </p>
          <p>
            Måtten är inte "path-dependent" – eftersom regimperioderna hoppar i tiden (diskontinuerliga)
            går det inte att räkna en sammanhängande CAGR eller Max Drawdown för en regim, bara
            genomsnitt och Sharpe per vecka inom regimen.
          </p>
        </InfoButton>
      </h1>
      <p className="page-subtitle">
        Strategins prestanda nedbruten per bull/bear/sidledes-regim. OBS: inte path-dependent CAGR/Max
        Drawdown – regimperioderna är diskontinuerliga i tid.
      </p>

      <div className="chart-card">
        <h3>
          Sharpe per regim
          <InfoButton title="Sharpe per regim">
            Visar strategins riskjusterade avkastning (Sharpe-kvot) separat för varje marknadsregim.
            Det visar om strategin presterar bäst i uppåttrender, nedåttrender eller sidledes
            marknader.
          </InfoButton>
        </h3>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="label" stroke="#64748b" />
            <YAxis stroke="#64748b" />
            <Tooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #1e293b' }}
              formatter={(v) => [Number(v).toFixed(2), 'Sharpe']}
            />
            <Bar dataKey="sharpe">
              {chartData.map((row) => (
                <Cell key={row.regime} fill={REGIME_COLORS[row.regime] ?? '#2196F3'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Regim</th>
              <th>Veckor</th>
              <th>
                Avg avkastning/v
                <InfoButton title="Avg avkastning/v">
                  Genomsnittlig veckoavkastning för strategin under veckor klassificerade i denna
                  regim.
                </InfoButton>
              </th>
              <th>Sharpe</th>
              <th>
                Win Rate
                <InfoButton title="Win Rate">
                  Andelen veckor inom regimen som hade positiv avkastning.
                </InfoButton>
              </th>
            </tr>
          </thead>
          <tbody>
            {chartData.map((row) => (
              <tr key={row.regime}>
                <td>{row.label}</td>
                <td>{row.n_weeks}</td>
                <td>{(row.avg_return * 100).toFixed(2)}%</td>
                <td>{row.sharpe.toFixed(2)}</td>
                <td>{(row.win_rate * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
