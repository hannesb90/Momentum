import { useMemo, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { SegmentedControl } from '../components/SegmentedControl'
import { SignalBadge } from '../components/SignalBadge'
import { EmptyState } from '../components/EmptyState'
import { InfoButton } from '../components/InfoButton'
import { fmtPct, fmtSek, cleanName } from '../format'

const SIGNAL_FILTERS = [
  { value: 'all', label: 'Alla' },
  { value: 'buy', label: 'Köp' },
  { value: 'flat', label: 'Neutrala' },
]

const SEGMENT_FILTERS = [
  { value: 'all', label: 'Alla bolag' },
  { value: 'large', label: 'Storbolag' },
  { value: 'small', label: 'Småbolag' },
]
const SEGMENT_LABEL = { large: 'Stor', small: 'Liten' }

const SORTS = [
  { value: 'prob_up', label: 'P(upp)' },
  { value: 'pred_return', label: 'Förv. avk.' },
  { value: 'position_size', label: 'Storlek' },
  { value: 'mcap_msek', label: 'Bolagsvärde' },
  { value: 'price_chg_30m', label: 'Kursutveckling' },
]

// Range-filtren (bolagsvärde/antal aktier/kursutveckling) delar samma
// min/max-fältpar - egen komponent i stället för att upprepa JSX:en tre ggr.
function RangeFilter({ label, unit, min, max, onMin, onMax }) {
  return (
    <label className="range-filter">
      <span className="range-filter__label">{label}{unit ? ` (${unit})` : ''}</span>
      <span className="range-filter__inputs">
        <input type="number" inputMode="decimal" placeholder="Min" value={min}
          onChange={(e) => onMin(e.target.value)} />
        <span>–</span>
        <input type="number" inputMode="decimal" placeholder="Max" value={max}
          onChange={(e) => onMax(e.target.value)} />
      </span>
    </label>
  )
}

const EMPTY_RANGES = { mcapMin: '', mcapMax: '', sharesMin: '', sharesMax: '', chgMin: '', chgMax: '' }

export function SignalsPage() {
  // Bägge segmenten i EN lista (se api.latestSignalsAll) - den globala
  // stor/småbolags-växlaren styr inte den här sidan längre (döljs i App.jsx),
  // ett eget filter nedan väljer i stället inom den redan hämtade listan.
  const { data, error, loading } = useApiData(() => api.latestSignalsAll(), [])
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState(searchParams.get('q') ?? '')
  const [signalFilter, setSignalFilter] = useState('all')
  const [segmentFilter, setSegmentFilter] = useState('all')
  const [sort, setSort] = useState('prob_up')
  const [filterOpen, setFilterOpen] = useState(false)
  // Bolagsvärde (mcap_msek)/antal aktier (shares_million)/kursutveckling
  // (price_chg_30m, ~30 mån) - kommer från value-/quality-screenrarna, inte
  // momentum-modellen själv (se api._signal_screener_enrichment i backend).
  const [ranges, setRanges] = useState(EMPTY_RANGES)
  const setRange = (k) => (v) => setRanges((r) => ({ ...r, [k]: v }))

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
    if (segmentFilter !== 'all') r = r.filter((s) => s.segment === segmentFilter)
    // Saknar en rad fältet (screenern har inte körts/täcker inte bolaget)
    // exkluderas den när filtret är aktivt - kan inte bekräfta att den
    // uppfyller kravet, samma "hellre omarkerad än fel" som backend.
    if (ranges.mcapMin) r = r.filter((s) => Number(s.mcap_msek) >= Number(ranges.mcapMin))
    if (ranges.mcapMax) r = r.filter((s) => Number(s.mcap_msek) <= Number(ranges.mcapMax))
    if (ranges.sharesMin) r = r.filter((s) => Number(s.shares_million) >= Number(ranges.sharesMin))
    if (ranges.sharesMax) r = r.filter((s) => Number(s.shares_million) <= Number(ranges.sharesMax))
    if (ranges.chgMin) r = r.filter((s) => Number(s.price_chg_30m) * 100 >= Number(ranges.chgMin))
    if (ranges.chgMax) r = r.filter((s) => Number(s.price_chg_30m) * 100 <= Number(ranges.chgMax))
    // P(upp)/förv. avk. kommer från TVÅ SEPARATA modeller (en per segment) -
    // inte direkt jämförbara på absolutnivå, men sorteringen är ändå
    // meningsfull inom vardera segmentet och som grov gemensam rangordning.
    return [...r].sort((a, b) => (Number(b[sort]) || 0) - (Number(a[sort]) || 0))
  }, [data, query, signalFilter, segmentFilter, ranges, sort])

  const activeFilterCount =
    (signalFilter !== 'all' ? 1 : 0) +
    (segmentFilter !== 'all' ? 1 : 0) +
    Object.values(ranges).filter((v) => v !== '').length

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
              Stor- och småbolag tränas som två SEPARATA modeller – P(upp) och förväntad avkastning
              är därför inte direkt jämförbara mellan segmenten, bara inom vardera. Filtrera på
              segment nedan om du vill se dem var för sig.
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
        <button
          type="button"
          className={`btn filter-toggle${activeFilterCount ? ' filter-toggle--active' : ''}`}
          onClick={() => setFilterOpen((v) => !v)}
          aria-expanded={filterOpen}
        >
          Filter{activeFilterCount ? ` (${activeFilterCount})` : ''}
        </button>
      </div>

      {filterOpen && (
        <div className="filter-panel">
          <div className="filter-panel__row">
            <span className="filter-bar__label">Signal</span>
            <SegmentedControl options={SIGNAL_FILTERS} value={signalFilter} onChange={setSignalFilter} size="sm" />
          </div>
          <div className="filter-panel__row">
            <span className="filter-bar__label">Segment</span>
            <SegmentedControl options={SEGMENT_FILTERS} value={segmentFilter} onChange={setSegmentFilter} size="sm" />
          </div>
          <div className="filter-panel__row">
            <span className="filter-bar__label">Sortera</span>
            <SegmentedControl options={SORTS} value={sort} onChange={setSort} size="sm" />
          </div>
          <div className="filter-panel__ranges">
            <RangeFilter label="Bolagsvärde" unit="Mkr"
              min={ranges.mcapMin} max={ranges.mcapMax}
              onMin={setRange('mcapMin')} onMax={setRange('mcapMax')} />
            <RangeFilter label="Kursutveckling" unit="%, ~30 mån"
              min={ranges.chgMin} max={ranges.chgMax}
              onMin={setRange('chgMin')} onMax={setRange('chgMax')} />
            <RangeFilter label="Antal aktier" unit="miljoner"
              min={ranges.sharesMin} max={ranges.sharesMax}
              onMin={setRange('sharesMin')} onMax={setRange('sharesMax')} />
          </div>
          <p className="footnote" style={{ margin: '2px 0 0' }}>
            Bolagsvärde/kursutveckling/antal aktier kommer från värde-/kvalitetsscreenrarna,
            inte momentum-modellen – saknar ett bolag data för ett aktivt fält visas det inte.
          </p>
          {activeFilterCount > 0 && (
            <button type="button" className="btn" style={{ marginTop: 8 }}
              onClick={() => { setSignalFilter('all'); setSegmentFilter('all'); setRanges(EMPTY_RANGES) }}>
              Rensa filter
            </button>
          )}
        </div>
      )}

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
                <tr key={`${row.segment}-${row.ticker}`}>
                  <td className="ticker-cell">
                    <Link to={`/aktie/${encodeURIComponent(row.ticker)}`} className="ticker-link">
                      <span className="ticker-link__name">{cleanName(row.name, row.ticker)}</span>
                      <span className="ticker-link__ticker">
                        {row.ticker}
                        {segmentFilter === 'all' && (
                          <span className="badge badge--flat" style={{ marginLeft: 6 }}>
                            {SEGMENT_LABEL[row.segment] ?? row.segment}
                          </span>
                        )}
                      </span>
                      {(row.mcap_msek != null || row.price_chg_30m != null) && (
                        <span className="ticker-link__ticker" style={{ opacity: 0.75 }}>
                          {row.mcap_msek != null
                            ? `${Number(row.mcap_msek).toLocaleString('sv-SE', { maximumFractionDigits: 0 })} Mkr`
                            : ''}
                          {row.mcap_msek != null && row.price_chg_30m != null ? ' · ' : ''}
                          {row.price_chg_30m != null ? `${fmtPct(row.price_chg_30m, 0)} (~30 mån)` : ''}
                        </span>
                      )}
                    </Link>
                  </td>
                  <td>{fmtPct(row.prob_up)}</td>
                  <td><SignalBadge variant={row.pred_signal === 1 ? 'buy' : 'flat'} /></td>
                  <td>{fmtPct(row.pred_return)}</td>
                  {hasTa && <td className="col-ta">{row.ta_score == null ? '–' : fmtPct(row.ta_score, 0)}</td>}
                  <td>
                    {fmtPct(row.position_size)}
                    {row.pred_signal === 1 && row.limit_price != null && (
                      <span className="limit-note">köp ≤ {fmtSek(row.limit_price)}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
