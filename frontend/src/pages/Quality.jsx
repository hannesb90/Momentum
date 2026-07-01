import { Fragment, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { SegmentedControl } from '../components/SegmentedControl'
import { EmptyState } from '../components/EmptyState'
import { InfoButton } from '../components/InfoButton'
import { fmtNum, cleanName } from '../format'

// Zon-klassificeringen (OT-style värdering) → filter + badge-färg.
const ZONES = [
  { value: 'all', label: 'Alla' },
  { value: 'billig', label: 'Billig' },
  { value: 'rimlig', label: 'Rimlig' },
  { value: 'dyr', label: 'Dyr' },
  { value: 'förlust/hype', label: 'Förlust' },
  { value: 'okänd', label: 'Okänd' },
]

const QUALITY_TIERS = [
  { value: 0, label: 'Alla' },
  { value: 3.5, label: '≥ 3,5' },
  { value: 4.0, label: '≥ 4,0' },
  { value: 4.5, label: '≥ 4,5' },
]

const SORTS = [
  { value: 'composite', label: 'Kvalitet' },
  { value: 'ebitda_multiple', label: 'Billigast' },
  { value: 'mcap_msek', label: 'Minst börsvärde' },
  { value: 'revenue_msek', label: 'Omsättning' },
]

// Kriterie-nycklar → svenska etiketter för detaljvyn.
const CRITERIA = [
  ['understand', 'Lätt att förstå'],
  ['global', 'Global ambition'],
  ['scalable', 'Skalbar'],
  ['moat', 'Konkurrensfördel'],
  ['sales', 'Säljkultur'],
  ['mgmt', 'Ledning'],
  ['market', 'Marknad'],
  ['profit_path', 'Väg till vinst'],
  ['under_radar', 'Under radarn'],
]

function zoneClass(zone) {
  if (zone === 'billig') return 'billig'
  if (zone === 'rimlig') return 'rimlig'
  if (zone === 'dyr') return 'dyr'
  if (zone === 'förlust/hype') return 'forlust'
  return 'okand'
}

const ZONE_LABEL = {
  billig: 'BILLIG',
  rimlig: 'RIMLIG',
  dyr: 'DYR',
  'förlust/hype': 'FÖRLUST',
  okänd: 'OKÄND',
}

function fmtMcap(v) {
  if (v == null || Number.isNaN(Number(v))) return '–'
  const n = Number(v)
  if (n >= 1000) return `${(n / 1000).toLocaleString('sv-SE', { maximumFractionDigits: 1 })} mdr`
  return `${n.toLocaleString('sv-SE', { maximumFractionDigits: 0 })} MSEK`
}

function fmtMult(v) {
  return v == null || Number.isNaN(Number(v)) ? '–' : `${Number(v).toFixed(1)}×`
}

// En liten stapel 1–5 för varje kvalitetskriterium.
function ScoreBar({ value }) {
  const v = Number(value)
  const pct = value == null || Number.isNaN(v) ? 0 : (v / 5) * 100
  return (
    <span className="qscore">
      <span className="qscore__track">
        <span className="qscore__fill" style={{ width: `${pct}%` }} />
      </span>
      <span className="qscore__num">{value == null ? '–' : v}</span>
    </span>
  )
}

function DetailPanel({ row }) {
  const flags = String(row.red_flags || '').split(';').map((s) => s.trim()).filter(Boolean)
  const investors = String(row.mentioned_investors || '').split(';').map((s) => s.trim()).filter(Boolean)
  return (
    <div className="qdetail">
      {row.pitch && <p className="qdetail__pitch">{row.pitch}</p>}
      {row.memo && <p className="qdetail__memo">{row.memo}</p>}

      <div className="qdetail__grid">
        <div className="qdetail__criteria">
          {CRITERIA.map(([key, label]) => (
            <div className="qdetail__crow" key={key}>
              <span className="qdetail__clabel">{label}</span>
              <ScoreBar value={row[key]} />
            </div>
          ))}
        </div>

        <div className="qdetail__facts">
          <div className="qdetail__fact"><span>Omsättning</span><b>{fmtMcap(row.revenue_msek)}</b></div>
          <div className="qdetail__fact"><span>EBITDA</span><b>{fmtMcap(row.ebitda_msek)}</b></div>
          <div className="qdetail__fact"><span>Resultat</span><b>{fmtMcap(row.net_result_msek)}</b></div>
          <div className="qdetail__fact"><span>Börsvärde</span><b>{fmtMcap(row.mcap_msek)}</b></div>
          <div className="qdetail__fact"><span>EBITDA-multipel</span><b>{fmtMult(row.ebitda_multiple)}</b></div>
          {investors.length > 0 && (
            <div className="qdetail__fact"><span>Ägare (nämnda)</span><b>{investors.join(', ')}</b></div>
          )}
        </div>
      </div>

      {flags.length > 0 && (
        <div className="qdetail__flags">
          {flags.map((f, i) => (
            <span className="qflag" key={i}>⚠ {f}</span>
          ))}
        </div>
      )}

      <Link to={`/aktie/${encodeURIComponent(row.ticker)}`} className="qdetail__link">
        Öppna aktiedetalj →
      </Link>
    </div>
  )
}

export function QualityPage() {
  const { data, error, loading } = useApiData(() => api.quality(), [])
  const [query, setQuery] = useState('')
  const [zone, setZone] = useState('all')
  const [minQuality, setMinQuality] = useState(0)
  const [sort, setSort] = useState('composite')
  const [expanded, setExpanded] = useState(null)

  const rows = useMemo(() => {
    if (!data) return []
    let r = data
    if (query.trim()) {
      const q = query.trim().toUpperCase()
      r = r.filter(
        (s) =>
          String(s.ticker).toUpperCase().includes(q) ||
          (s.name && String(s.name).toUpperCase().includes(q)),
      )
    }
    if (zone !== 'all') r = r.filter((s) => s.zone === zone)
    if (minQuality > 0) r = r.filter((s) => Number(s.composite) >= minQuality)
    // "Billigast" sorterar stigande (lägst multipel först), övriga fallande.
    const asc = sort === 'ebitda_multiple' || sort === 'mcap_msek'
    return [...r].sort((a, b) => {
      const av = a[sort],
        bv = b[sort]
      const an = av == null || Number.isNaN(Number(av)) ? (asc ? Infinity : -Infinity) : Number(av)
      const bn = bv == null || Number.isNaN(Number(bv)) ? (asc ? Infinity : -Infinity) : Number(bv)
      return asc ? an - bn : bn - an
    })
  }, [data, query, zone, minQuality, sort])

  if (loading) return <Loading />
  if (error) return <ErrorBlock error={error} />

  if (!data || data.length === 0) {
    return (
      <section className="page">
        <div className="page-head">
          <h1>Kvalitet</h1>
        </div>
        <EmptyState
          title="Ingen kortlista ännu"
          hint="Kör 'python altdata/quality_screener.py score' och sedan 'report' på Pi:n för att generera results/quality_shortlist.csv."
        />
      </section>
    )
  }

  const cheapCount = data.filter((s) => s.zone === 'billig' || s.zone === 'rimlig').length

  return (
    <section className="page">
      <div className="page-head">
        <h1>
          Kvalitet
          <InfoButton title="Fundamental microcap-sållning">
            <p>
              En kvalitativ tratt som letar tidiga, oupptäckta småbolag med 10-bagger-potential.
              Claude läser varje bolags senaste rapport + pressmeddelanden och poängsätter en
              checklista (10-årstest, moat, ledning, väg till vinst m.m.) samt extraherar nyckeltal
              för värdering.
            </p>
            <p>
              <b>Detta är ett urval, inte ett bevisat edge.</b> Till skillnad från momentum-modellen
              kan den inte backtestas – använd den som utgångspunkt för din egen djupanalys, aldrig
              som köpsignal.
            </p>
            <p>
              <b>Kvalitet</b> (composite 1–5) mäter hur bra caset låter. <b>Zon</b> mäter
              värderingen: billig ≤12× EBITDA, rimlig ≤18×, dyr &gt;18×, förlust (går back),
              okänd (saknar underlag). Din kärnregel: hög kvalitet <b>och</b> billig.
            </p>
          </InfoButton>
        </h1>
        <p className="page-subtitle">
          {data.length} bolag poängsatta · {cheapCount} billiga/rimliga
        </p>
      </div>

      <div className="filter-bar">
        <input
          className="search-input"
          type="search"
          placeholder="Sök ticker eller bolagsnamn…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <div className="filter-bar filter-bar--secondary">
        <span className="filter-bar__label">Värderingszon:</span>
        <SegmentedControl options={ZONES} value={zone} onChange={setZone} size="sm" />
      </div>
      <div className="filter-bar filter-bar--secondary">
        <span className="filter-bar__label">Kvalitet:</span>
        <SegmentedControl options={QUALITY_TIERS} value={minQuality} onChange={setMinQuality} size="sm" />
      </div>
      <div className="filter-bar filter-bar--secondary">
        <span className="filter-bar__label">Sortera:</span>
        <SegmentedControl options={SORTS} value={sort} onChange={setSort} size="sm" />
      </div>

      {rows.length === 0 ? (
        <EmptyState title="Inga bolag matchar" hint="Justera filtren eller sökningen." />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Bolag</th>
                <th>Kvalitet</th>
                <th>Zon</th>
                <th>Börsvärde</th>
                <th>EBITDA×</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const open = expanded === row.ticker
                return (
                  <Fragment key={row.ticker}>
                    <tr
                      className={`qrow${open ? ' qrow--open' : ''}`}
                      onClick={() => setExpanded(open ? null : row.ticker)}
                    >
                      <td className="ticker-cell">
                        <span className="ticker-link__name">{cleanName(row.name, row.ticker)}</span>
                        <span className="ticker-link__ticker">{row.ticker}</span>
                      </td>
                      <td className="qcomposite">{fmtNum(row.composite, 2)}</td>
                      <td>
                        <span className={`zonebadge zonebadge--${zoneClass(row.zone)}`}>
                          {ZONE_LABEL[row.zone] ?? String(row.zone).toUpperCase()}
                        </span>
                      </td>
                      <td>{fmtMcap(row.mcap_msek)}</td>
                      <td>{fmtMult(row.ebitda_multiple)}</td>
                    </tr>
                    {open && (
                      <tr className="qrow-detail">
                        <td colSpan={5}>
                          <DetailPanel row={row} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
