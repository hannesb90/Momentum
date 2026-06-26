import { useMemo } from 'react'
import { ResponsiveContainer, AreaChart, Area, YAxis, Tooltip } from 'recharts'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { InfoButton } from './InfoButton'
import { fmtSek, fmtPct } from '../format'

/**
 * Live track record (pappershandel). Visar den framåtblickande, tidsstämplade
 * historiken som byggs upp körning för körning – det enda ärliga måttet på om
 * signalerna fungerar utanför backtesten. Tom tills liggaren börjat fyllas.
 */
export function LiveTrackRecord() {
  const ledger = useApiData(() => api.paperLedger(), [])

  const series = useMemo(() => {
    if (!ledger.data) return []
    return ledger.data.map((r) => ({
      date: r.date,
      value: r.paper_value,
      ret: r.return_since_start,
    }))
  }, [ledger.data])

  // Tyst medan den laddar eller om endpointen saknas (äldre backend).
  if (ledger.loading || ledger.error) return null

  const last = series.length ? series[series.length - 1] : null
  const ret = last?.ret ?? null
  const positive = ret != null && ret >= 0

  return (
    <>
      <div className="section-head">
        <h2>
          Live track record
          <InfoButton title="Live track record (pappershandel)">
            <p>
              En pappersportfölj som följer modellens senaste signaler framåt i tiden – uppdaterad
              vecka för vecka, utan efterhandsjusteringar. Till skillnad från backtesten har
              modellen aldrig sett den här datan.
            </p>
            <p>
              Det här är det ärligaste måttet på om strategin fungerar på riktigt. Den börjar tom
              och blir meningsfull först efter några veckor/månader.
            </p>
          </InfoButton>
        </h2>
      </div>

      {series.length < 2 ? (
        <div className="list-card">
          <div className="list-card__empty">
            Live-historiken byggs upp. Den fylls på varje gång modellen kör – kom tillbaka om
            några veckor för att se hur signalerna presterat i realtid.
          </div>
        </div>
      ) : (
        <div className="hero">
          <div className="hero__label">Pappersportfölj sedan start</div>
          <div className="hero__value">{fmtSek(last.value)}</div>
          <div className="hero__return">
            <span className={`hero__chip ${positive ? 'hero__chip--up' : 'hero__chip--down'}`}>
              {positive ? '▲' : '▼'} {fmtPct(ret)}
            </span>
            <span className="hero__period">
              {series[0].date} → {last.date} · {series.length} veckor
            </span>
          </div>
          <div className="hero__spark">
            <ResponsiveContainer width="100%" height={64}>
              <AreaChart data={series} margin={{ top: 4, bottom: 0, left: 0, right: 0 }}>
                <defs>
                  <linearGradient id="liveFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <YAxis domain={['dataMin', 'dataMax']} hide />
                <Tooltip
                  contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
                  formatter={(v) => [fmtSek(v), 'Pappersvärde']}
                  labelFormatter={() => ''}
                />
                <Area type="monotone" dataKey="value" stroke="var(--accent)" strokeWidth={2} fill="url(#liveFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </>
  )
}
