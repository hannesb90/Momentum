import { useMemo, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { SegmentedControl } from '../components/SegmentedControl'
import { SignalBadge } from '../components/SignalBadge'
import { EmptyState } from '../components/EmptyState'
import { InfoButton } from '../components/InfoButton'
import { fmtPct, cleanName } from '../format'

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
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState(searchParams.get('q') ?? '')
  const [signalFilter, setSignalFilter] = useState('all')
  const [sort, setSort] = useState('prob_up')

  const rows = useMemo(() => {
    if (!data) return []
    let r = data
    if (query.trim()) {
      const q = query.trim().toUpperCase()
      r = r.filter(
        (s) =>
          s.ticker.toUpperCase().includes(q) ||
          (s.name && String(s.name).toUpperCase().includes(q)),
      )
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
        <h1>
          Signaler
          <InfoButton title="Signaler">
            <p>
              Modellens senaste bedömning av varje bolag, uppdaterad vecka för vecka. En köpsignal
              betyder att modellen bedömer sannolikheten för uppgång som tillräckligt hög för att
              ta en position.
            </p>
            <p>
              Detta är modellens rekommendationer, inte en garanti – använd informationen som ett
              av flera beslutsunderlag.
            </p>
          </InfoButton>
        </h1>
        <p className="page-subtitle">
          {data.length} bolag · {buyCount} köpsignaler denna vecka
        </p>
      </div>

      <div className="filter-bar">
        <input
          className="search-input"
          type="search"
          placeholder="Sök ticker eller bolagsnamn…"
          value={query}
          onChange={(e) => {
            const v = e.target.value
            setQuery(v)
            setSearchParams(v ? { q: v } : {}, { replace: true })
          }}
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
                <th>Bolag</th>
                <th>
                  P(upp)
                  <InfoButton title="P(upp) – nästa 4 veckor">
                    Modellens beräknade sannolikhet att aktien stiger i värde under de kommande
                    4 veckorna. En "period" = 4 veckor (modellens prognoshorisont), och signalerna
                    uppdateras varje vecka utifrån den senaste datan. Högre procent = modellen är
                    mer säker på en uppgång.
                  </InfoButton>
                </th>
                <th>
                  Signal
                  <InfoButton title="Signal">
                    Köp betyder att P(upp) och förväntad avkastning är höga nog för att modellen ska
                    föreslå en position. Neutral betyder att aktien inte uppfyller kraven just nu.
                  </InfoButton>
                </th>
                <th>
                  Förv. avk.
                  <InfoButton title="Förväntad avkastning (4 veckor)">
                    Modellens prognos för hur mycket aktien kommer förändras i pris under de
                    kommande 4 veckorna, baserat på historiska mönster och tekniska faktorer.
                  </InfoButton>
                </th>
                {hasTa && (
                  <th className="col-ta">
                    TA
                    <InfoButton title="TA-score">
                      Ett kompletterande tekniskt analyspoäng (0–100%) som visar hur starkt aktiens
                      pris-/volymmönster ser ut just nu, oberoende av modellens huvudprognos.
                    </InfoButton>
                  </th>
                )}
                <th>
                  Storlek
                  <InfoButton title="Positionsstorlek">
                    Hur stor andel av portföljen modellen föreslår att placera i just denna aktie,
                    baserat på signalstyrka och riskhantering (t.ex. begränsad sektorexponering).
                  </InfoButton>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.ticker}>
                  <td className="ticker-cell">
                    <Link to={`/aktie/${encodeURIComponent(row.ticker)}`} className="ticker-link">
                      <span className="ticker-link__name">{cleanName(row.name, row.ticker)}</span>
                      <span className="ticker-link__ticker">{row.ticker}</span>
                    </Link>
                  </td>
                  <td>{fmtPct(row.prob_up)}</td>
                  <td><SignalBadge variant={row.pred_signal === 1 ? 'buy' : 'flat'} /></td>
                  <td>{fmtPct(row.pred_return)}</td>
                  {hasTa && <td className="col-ta">{row.ta_score == null ? '–' : fmtPct(row.ta_score, 0)}</td>}
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
