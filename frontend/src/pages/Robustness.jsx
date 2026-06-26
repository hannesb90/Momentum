import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  Cell,
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
import { InfoButton } from '../components/InfoButton'

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

  // Köptröskel (data-driven). Saknas i äldre stats.json – rendera bara om den finns.
  const threshold = stats.data.threshold
  const OBJ_LABEL = { sharpe: 'Sharpe', cagr: 'CAGR', calmar: 'Calmar' }
  const gridData = (threshold?.grid ?? []).map((g) => ({
    threshold: Number(g.threshold).toFixed(2),
    score: g.score,
    invested: Math.round((g.invested ?? 0) * 100),
    chosen: Number(g.threshold) === Number(threshold?.buy_threshold),
  }))

  return (
    <section>
      <h1>Robusthet & modell-drift</h1>
      <p className="page-subtitle">
        Block bootstrap-konfidensintervall, Probabilistic/Deflated Sharpe Ratio och rullande AUC mot realiserade utfall.
      </p>

      {threshold && (
        <div className="chart-card">
          <h3>
            Köptröskel (data-driven)
            <InfoButton title="Köptröskel (data-driven)">
              <p>
                Modellen köper en aktie när dess P(upp) överstiger en tröskel. I stället för en
                fast gräns söks den fram på dev-perioden (in-sample) och valideras på den frusna
                holdouten – som aldrig används i sökningen.
              </p>
              <p>
                Varje testad nivå räknas som ett "trial" och deflaterar Deflated Sharpe-måttet
                ovan, så vi inte lurar oss själva genom att prova många gränser. En lägre tröskel
                = portföljen är investerad oftare (mindre kontant-drag), men kan ta fler svaga
                affärer.
              </p>
            </InfoButton>
          </h3>

          <div className="stat-grid">
            <StatCard
              label="Vald köptröskel"
              value={`P(upp) > ${(Number(threshold.buy_threshold) * 100).toFixed(0)}%`}
              tone="good"
              info="Den gräns för uppgångssannolikhet som måste passeras för att modellen ska ta en köpposition. Lägre gräns = oftare investerad."
            />
            <StatCard
              label="Optimeringsmål"
              value={threshold.optimized ? (OBJ_LABEL[threshold.objective] ?? threshold.objective) : 'Fast (ingen sökning)'}
              info={threshold.optimized
                ? 'Måttet som maximerades när tröskeln söktes fram på dev-perioden. Sharpe = riskjusterat (default), CAGR = rå avkastning, Calmar = avkastning per drawdown.'
                : 'Tröskeln är fast inställd (--no-optimize-threshold eller --buy-threshold), ingen datadriven sökning gjordes.'}
            />
          </div>

          {gridData.length > 0 && (
            <>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={gridData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="threshold" stroke="#64748b" tick={{ fontSize: 12 }} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
                    formatter={(v, name) =>
                      name === 'score'
                        ? [v == null ? '–' : Number(v).toFixed(3), `${OBJ_LABEL[threshold.objective] ?? threshold.objective}`]
                        : [`${v}%`, 'Investerad']
                    }
                    labelFormatter={(t) => `Tröskel P(upp) > ${(Number(t) * 100).toFixed(0)}%`}
                  />
                  <Bar dataKey="score" radius={[4, 4, 0, 0]}>
                    {gridData.map((row) => (
                      <Cell key={row.threshold} fill={row.chosen ? 'var(--accent)' : '#334155'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="footnote">
                Staplarna visar {OBJ_LABEL[threshold.objective] ?? threshold.objective} per testad
                tröskel på dev-perioden. Den markerade (blå) stapeln är den valda nivån. Jämför med
                holdout-statistiken nedan för att se om valet höll out-of-sample.
              </p>
            </>
          )}
        </div>
      )}

      <div className="stat-grid">
        <StatCard
          label="Probabilistic Sharpe"
          value={`${(robustness.psr * 100).toFixed(1)}%`}
          tone={robustness.psr > 0.95 ? 'good' : 'neutral'}
          info="Probabilistic Sharpe Ratio (PSR) – sannolikheten att den uppmätta Sharpe-kvoten verkligen är högre än noll, med hänsyn till mätosäkerhet. Över 95% indikerar att resultatet sannolikt inte är slumpmässigt."
        />
        <StatCard
          label={`Deflated Sharpe (n=${robustness.n_trials})`}
          value={`${(robustness.dsr * 100).toFixed(1)}%`}
          tone={robustness.dsr > 0.95 ? 'good' : 'neutral'}
          info={`Deflated Sharpe Ratio (DSR) – som PSR, men justerar även för att ${robustness.n_trials} olika strategivarianter testats, vilket ökar risken att hitta ett resultat som ser bra ut av slump. Ett strängare och mer pålitligt mått än PSR.`}
        />
        <StatCard
          label="P(Sharpe ≤ 0)"
          value={`${(boot.prob_sharpe_below_0 * 100).toFixed(1)}%`}
          tone="bad"
          info="Sannolikheten, baserat på bootstrap-simuleringar, att strategins verkliga Sharpe-kvot egentligen är noll eller negativ. Lägre är bättre."
        />
      </div>

      <div className="chart-card">
        <h3>
          Bootstrap-konfidensintervall (p5 / p50 / p95)
          <InfoButton title="Bootstrap-konfidensintervall">
            <p>
              Genom att slumpmässigt omsampla historiska block av avkastningar tusentals gånger får
              man ett spann av troliga utfall för varje mått, istället för bara ett enda historiskt
              värde.
            </p>
            <p>
              p5/p50/p95 visar den 5:e, 50:e (median) och 95:e percentilen – dvs. ett pessimistiskt,
              typiskt och optimistiskt scenario. Ett brett spann betyder större osäkerhet.
            </p>
          </InfoButton>
        </h3>
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
          <StatCard
            label="Senaste rullande AUC"
            value={driftSummary.auc.toFixed(3)}
            tone={driftSummary.flagged ? 'bad' : 'good'}
            info="AUC (Area Under Curve) mäter hur bra modellen är på att skilja aktier som gick upp från de som gick ner, beräknat på de senaste periodernas faktiska utfall. 0.5 = ren slump, 1.0 = perfekt. Ett fallande AUC över tid kan tyda på att modellen tappar i precision (drift)."
          />
          <StatCard
            label="Senaste hit-rate"
            value={`${(driftSummary.hit_rate * 100).toFixed(1)}%`}
            info="Andelen senaste förutsägelser som faktiskt slog rätt på riktning (upp/ner)."
          />
          <StatCard
            label="Flaggade perioder"
            value={`${driftSummary.n_flagged}/${driftSummary.n_periods}`}
            info="Antal perioder där modellens AUC fallit under det förinställda golvet, vilket flaggar att modellen kan behöva tränas om."
          />
        </div>
      )}

      <div className="chart-card">
        <h3>
          Rullande AUC mot realiserat utfall
          <InfoButton title="Rullande AUC mot realiserat utfall">
            <p>
              Visar hur väl modellen löpande lyckats förutsäga riktningen på faktiska utfall, mätt
              som AUC över en rullande tidsperiod.
            </p>
            <p>
              Den röda streckade linjen ("Golv") markerar en lägstanivå – om AUC dyker under den
              flaggas perioden som ett tecken på att modellens prestanda försämrats (drift).
            </p>
          </InfoButton>
        </h3>
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
