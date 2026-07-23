import { Fragment, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis,
  CartesianGrid, Tooltip, ReferenceLine, ReferenceArea, Cell,
} from 'recharts'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { SegmentedControl } from '../components/SegmentedControl'
import { SignalBadge } from '../components/SignalBadge'
import { EmptyState } from '../components/EmptyState'
import { InfoButton } from '../components/InfoButton'
import { TvLink } from '../components/TvLink'
import { fmtNum, fmtPct, cleanName } from '../format'

// Bolag-sidan (2026-07-22) slår ihop det som tidigare var Signaler + Kvalitet:
// EN rad per bolag, med momentum-modellens signal (prob_up/pred_return/TA),
// den token-fria kvant-screenern (hård data, alla bolag) och Claude-kvaliteten
// (checklista + värderingszon, de bolag screenern hunnit läsa) i samma tabell.
// Tre separata datakällor slås ihop per ticker (samma mönster som gamla
// Quality.jsx redan gjorde för quant+quality - utökat med signals här).

const ZONES = [
  { value: 'all', label: 'Alla' },
  { value: 'billig', label: 'Billig' },
  { value: 'rimlig', label: 'Rimlig' },
  { value: 'dyr', label: 'Dyr' },
  { value: 'okänd', label: 'Okänd' },
]

const QUALITY_TIERS = [
  { value: 0, label: 'Alla' },
  { value: 3.5, label: '≥ 3,5' },
  { value: 4.0, label: '≥ 4,0' },
  { value: 4.5, label: '≥ 4,5' },
]

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
  { value: 'quant_score', label: 'Kvant' },
  { value: 'composite', label: 'Kvalitet' },
  { value: 'ebitda_multiple', label: 'Billigast' },
  { value: 'mcap_msek', label: 'Bolagsvärde' },
  { value: 'price_chg_30m', label: 'Kursutveckling' },
]

const VIEWS = [
  { value: 'table', label: 'Tabell' },
  { value: 'chart', label: 'Diagram' },
]

const ZONE_COLOR = {
  billig: '#22c55e',
  rimlig: '#60a5fa',
  dyr: '#eab308',
  'förlust/hype': '#ef4444',
  okänd: '#94a3b8',
}

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

function zoneFromQuant(r) {
  const ev = Number(r.ev_ebitda)
  if (Number.isFinite(ev) && ev > 0) return ev <= 12 ? 'billig' : ev <= 18 ? 'rimlig' : 'dyr'
  const ps = Number(r.ps)
  if (Number.isFinite(ps) && ps > 0) return ps <= 1.5 ? 'billig' : ps <= 4 ? 'rimlig' : 'dyr'
  return 'okänd'
}

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

function fmtAxis(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  if (Math.abs(n) >= 1000) return `${Math.round(n / 1000)}k`
  return `${Math.round(n)}`
}

function OtTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const p = payload[0].payload
  return (
    <div className="qtooltip">
      <div className="qtooltip__name">
        {p.name} <span>{p.ticker}</span>
      </div>
      <div className="qtooltip__row"><span>Kvalitet</span><b>{fmtNum(p.composite, 2)}</b></div>
      <div className="qtooltip__row"><span>Börsvärde</span><b>{fmtMcap(p.y)}</b></div>
      <div className="qtooltip__row"><span>Vinst ({p.basis || '?'})</span><b>{fmtMcap(p.x)}</b></div>
      <div className="qtooltip__row"><span>Multipel</span><b>{fmtMult(p.mult)}</b></div>
      <div className="qtooltip__row"><span>Omsättning</span><b>{fmtMcap(p.z)}</b></div>
      <span className={`zonebadge zonebadge--${zoneClass(p.zone)}`}>
        {ZONE_LABEL[p.zone] ?? String(p.zone).toUpperCase()}
      </span>
    </div>
  )
}

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

// Range-filtren (bolagsvärde/antal aktier/kursutveckling) - samma
// min/max-fältpar-komponent som Signaler-sidan.
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

function DetailPanel({ row }) {
  const flags = String(row.red_flags || '').split(';').map((s) => s.trim()).filter(Boolean)
  const investors = String(row.mentioned_investors || '').split(';').map((s) => s.trim()).filter(Boolean)
  const hasMomentum = row.prob_up != null
  return (
    <div className="qdetail">
      {row.pitch && <p className="qdetail__pitch">{row.pitch}</p>}
      {row.memo && <p className="qdetail__memo">{row.memo}</p>}

      {hasMomentum && (
        <div className="qdetail__facts" style={{ marginBottom: 10 }}>
          <div className="qdetail__fact"><span>P(upp), 4v</span><b>{fmtPct(row.prob_up)}</b></div>
          <div className="qdetail__fact"><span>Förv. avkastning</span><b>{fmtPct(row.pred_return)}</b></div>
          {row.ta_score != null && (
            <div className="qdetail__fact"><span>TA-score</span><b>{fmtPct(row.ta_score, 0)}</b></div>
          )}
          <div className="qdetail__fact"><span>Positionsstorlek</span><b>{fmtPct(row.position_size)}</b></div>
        </div>
      )}

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
          {row.ebit_msek != null && (
            <div className="qdetail__fact"><span>Rörelseresultat (EBIT)</span><b>{fmtMcap(row.ebit_msek)}</b></div>
          )}
          <div className="qdetail__fact"><span>Årets resultat</span><b>{fmtMcap(row.net_result_msek)}</b></div>
          <div className="qdetail__fact"><span>Börsvärde</span><b>{fmtMcap(row.mcap_msek)}</b></div>
          <div className="qdetail__fact">
            <span>Multipel{row.earnings_basis ? ` (${row.earnings_basis})` : ''}</span>
            <b>{fmtMult(row.ebitda_multiple)}</b>
          </div>
          {row.price_chg_30m != null && (
            <div className="qdetail__fact"><span>Kursutveckling (~30 mån)</span><b>{fmtPct(row.price_chg_30m, 0)}</b></div>
          )}
          {row.shares_million != null && (
            <div className="qdetail__fact"><span>Antal aktier</span><b>{fmtNum(row.shares_million, 1)} milj.</b></div>
          )}
          {investors.length > 0 && (
            <div className="qdetail__fact"><span>Ägare (nämnda)</span><b>{investors.join(', ')}</b></div>
          )}
          {row.quant_score != null && (
            <div className="qdetail__fact"><span>Kvant-betyg (hård data)</span><b>{Math.round(row.quant_score)}/100</b></div>
          )}
          {row.ebitda_margin != null && (
            <div className="qdetail__fact"><span>EBITDA-marginal</span><b>{Number(row.ebitda_margin).toFixed(1)}%</b></div>
          )}
          {row.rev_growth != null && (
            <div className="qdetail__fact"><span>Omsättningstillväxt</span><b>{Number(row.rev_growth).toFixed(1)}%</b></div>
          )}
          {row.roe != null && (
            <div className="qdetail__fact"><span>ROE</span><b>{Number(row.roe).toFixed(1)}%</b></div>
          )}
        </div>
      </div>
      {row.composite == null && (
        <p className="footnote" style={{ marginTop: 8 }}>
          Endast kvant-data (hård finansdata) – ingen kvalitativ Claude-analys för detta bolag ännu.
        </p>
      )}
      {row.composite != null && row.quality_source === 'soft' && (
        <p className="footnote" style={{ marginTop: 8 }}>
          Kvalitetsbetyget är det <b>tokenfria destillatet</b> (soft_signals: ML/lexikon tränat på
          Claude-betygen, samma 0–5-skala) – ingen Claude-läsning av just detta bolag ännu.
          Claude-betyget ersätter det automatiskt när screenern hunnit dit.
        </p>
      )}

      {flags.length > 0 && (
        <div className="qdetail__flags">
          {flags.map((f, i) => (
            <span className="qflag" key={i}>{f}</span>
          ))}
        </div>
      )}

      <Link to={`/aktie/${encodeURIComponent(row.ticker)}`} className="qdetail__link">
        Öppna aktiedetalj →
      </Link>
    </div>
  )
}

export function CompaniesPage() {
  const qRes = useApiData(() => api.quality(), [])
  const qnRes = useApiData(() => api.quantAll(), [])
  const sigRes = useApiData(() => api.latestSignalsAll(), [])
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState(searchParams.get('q') ?? '')
  const [zone, setZone] = useState('all')
  const [minQuality, setMinQuality] = useState(0)
  const [signalFilter, setSignalFilter] = useState('all')
  const [segmentFilter, setSegmentFilter] = useState('all')
  const [sort, setSort] = useState('prob_up')
  const [view, setView] = useState('table')
  const [expanded, setExpanded] = useState(null)
  const [filterOpen, setFilterOpen] = useState(false)
  const [ranges, setRanges] = useState(EMPTY_RANGES)
  const setRange = (k) => (v) => setRanges((r) => ({ ...r, [k]: v }))

  const loading = qRes.loading || qnRes.loading || sigRes.loading
  const error = qRes.error && qnRes.error && sigRes.error ? (qRes.error || qnRes.error || sigRes.error) : null

  // Tre källor, EN rad per ticker: kvant (bred bas, hård data, alla bolag i
  // universumet) < signaler (momentum-modellens P(upp)/TA/segment, bifogar
  // också mcap/kursutveckling/aktier från värde-/kvalitetsscreenrarna, se
  // api/main.py::_signal_screener_enrichment) < kvalitet (Claude/soft, rikast
  // men färre bolag). Senare källor vinner vid krock (samma precedens som
  // gamla Kvalitet-sidan redan hade för quant→quality).
  const data = useMemo(() => {
    const quant = Array.isArray(qnRes.data) ? qnRes.data : []
    const signals = Array.isArray(sigRes.data) ? sigRes.data : []
    const llm = Array.isArray(qRes.data) ? qRes.data : []
    const map = {}
    for (const r of quant) {
      if (!r.ticker) continue
      map[r.ticker] = {
        ticker: r.ticker, name: r.name, segment: r.segment, quant_score: r.quant_score,
        q_quality: r.quality, q_growth: r.growth, q_safety: r.safety, q_value: r.value,
        ebitda_margin: r.ebitda_margin, rev_growth: r.rev_growth, roe: r.roe,
        ps: r.ps, ev_ebitda: r.ev_ebitda, mcap_msek: r.mcap_msek,
        ebitda_multiple: Number(r.ev_ebitda) > 0 ? r.ev_ebitda : null,
        zone: zoneFromQuant(r), composite: null,
      }
    }
    for (const s of signals) {
      if (!s.ticker) continue
      const base = map[s.ticker] || {}
      map[s.ticker] = {
        ...base,
        ticker: s.ticker, name: s.name ?? base.name, segment: s.segment ?? base.segment,
        prob_up: s.prob_up, pred_return: s.pred_return, pred_signal: s.pred_signal,
        ta_score: s.ta_score, position_size: s.position_size,
        mcap_msek: s.mcap_msek ?? base.mcap_msek,
        price_chg_30m: s.price_chg_30m, shares_million: s.shares_million,
      }
    }
    for (const s of llm) {
      if (!s.ticker) continue
      const base = map[s.ticker] || {}
      map[s.ticker] = {
        ...base, ...s,
        quant_score: base.quant_score ?? null,
        segment: base.segment ?? s.segment,
        zone: s.zone && s.zone !== 'okänd' ? s.zone : (base.zone ?? s.zone ?? 'okänd'),
        mcap_msek: s.mcap_msek ?? base.mcap_msek,
        ebitda_multiple: s.ebitda_multiple ?? base.ebitda_multiple,
      }
    }
    return Object.values(map)
  }, [qRes.data, qnRes.data, sigRes.data])

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
    if (signalFilter === 'buy') r = r.filter((s) => s.pred_signal === 1)
    if (signalFilter === 'flat') r = r.filter((s) => s.pred_signal != null && s.pred_signal !== 1)
    if (segmentFilter !== 'all') r = r.filter((s) => s.segment === segmentFilter)
    if (ranges.mcapMin) r = r.filter((s) => Number(s.mcap_msek) >= Number(ranges.mcapMin))
    if (ranges.mcapMax) r = r.filter((s) => Number(s.mcap_msek) <= Number(ranges.mcapMax))
    if (ranges.sharesMin) r = r.filter((s) => Number(s.shares_million) >= Number(ranges.sharesMin))
    if (ranges.sharesMax) r = r.filter((s) => Number(s.shares_million) <= Number(ranges.sharesMax))
    if (ranges.chgMin) r = r.filter((s) => Number(s.price_chg_30m) * 100 >= Number(ranges.chgMin))
    if (ranges.chgMax) r = r.filter((s) => Number(s.price_chg_30m) * 100 <= Number(ranges.chgMax))
    const asc = sort === 'ebitda_multiple'
    return [...r].sort((a, b) => {
      const av = a[sort], bv = b[sort]
      const an = av == null || Number.isNaN(Number(av)) ? (asc ? Infinity : -Infinity) : Number(av)
      const bn = bv == null || Number.isNaN(Number(bv)) ? (asc ? Infinity : -Infinity) : Number(bv)
      return asc ? an - bn : bn - an
    })
  }, [data, query, zone, minQuality, signalFilter, segmentFilter, ranges, sort])

  const activeFilterCount =
    (zone !== 'all' ? 1 : 0) + (minQuality > 0 ? 1 : 0) +
    (signalFilter !== 'all' ? 1 : 0) + (segmentFilter !== 'all' ? 1 : 0) +
    Object.values(ranges).filter((v) => v !== '').length

  const chartData = useMemo(
    () =>
      rows
        .filter((r) => r.mcap_msek != null && r.earnings_msek != null)
        .map((r) => ({
          x: Number(r.earnings_msek),
          y: Number(r.mcap_msek),
          z: Math.max(Number(r.revenue_msek) || 0, 1),
          ticker: r.ticker,
          name: cleanName(r.name, r.ticker),
          zone: r.zone,
          composite: r.composite,
          mult: r.ebitda_multiple,
          basis: r.earnings_basis,
        })),
    [rows],
  )
  const xmax = chartData.length ? Math.max(...chartData.map((p) => p.x), 0) : 0
  const xmin = chartData.length ? Math.min(...chartData.map((p) => p.x), 0) : 0

  if (loading) return <Loading />
  if (error) return <ErrorBlock error={error} />

  if (!data || data.length === 0) {
    return (
      <section className="page">
        <div className="page-head">
          <h1>Bolag</h1>
        </div>
        <EmptyState
          title="Ingen data ännu"
          hint="Kör nattens pipeline på Pi:n (main.py + altdata-screenrarna) för att generera underlaget."
        />
      </section>
    )
  }

  const buyCount = data.filter((s) => s.pred_signal === 1).length
  const cheapCount = data.filter((s) => s.zone === 'billig' || s.zone === 'rimlig').length

  return (
    <section className="page">
      <div className="page-head">
        <h1>
          Bolag
          <InfoButton title="Bolag – allt på ett ställe">
            <p>
              Momentum-modellens signal (P(upp), uppdateras vecka för vecka), den token-fria
              kvant-screenern (hård finansdata, alla bolag) och Claude-kvaliteten (checklista +
              värdering, de bolag screenern hunnit läsa) i EN tabell i stället för separata sidor.
            </p>
            <p>
              Stor- och småbolag tränas som två SEPARATA momentum-modeller – P(upp) är därför bara
              jämförbart inom respektive segment, inte mellan dem.
            </p>
            <p>
              <b>Kvalitet/zon är ett urval, inte ett bevisat edge</b> – kan inte backtestas som
              momentum-modellen. Använd det som utgångspunkt för egen analys, aldrig som köpsignal
              ensamt.
            </p>
          </InfoButton>
        </h1>
        <p className="page-subtitle">
          {data.length} bolag · {buyCount} köpsignaler · {cheapCount} billiga/rimliga
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
        <SegmentedControl options={VIEWS} value={view} onChange={setView} size="sm" />
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
            <span className="filter-bar__label">Värderingszon</span>
            <SegmentedControl options={ZONES} value={zone} onChange={setZone} size="sm" />
          </div>
          <div className="filter-panel__row">
            <span className="filter-bar__label">Kvalitet</span>
            <SegmentedControl options={QUALITY_TIERS} value={minQuality} onChange={setMinQuality} size="sm" />
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
          {activeFilterCount > 0 && (
            <button type="button" className="btn" style={{ marginTop: 4 }}
              onClick={() => {
                setZone('all'); setMinQuality(0); setSignalFilter('all')
                setSegmentFilter('all'); setRanges(EMPTY_RANGES)
              }}>
              Rensa filter
            </button>
          )}
        </div>
      )}

      {rows.length === 0 ? (
        <EmptyState title="Inga bolag matchar" hint="Justera filtren eller sökningen." />
      ) : view === 'chart' ? (
        chartData.length === 0 ? (
          <EmptyState
            title="Inget att rita ännu"
            hint="Bolagen i urvalet saknar börsvärde eller vinstsiffra. Kör Claude-screenern på Pi:n eller vidga filtren."
          />
        ) : (
          <div className="qchart">
            <ResponsiveContainer width="100%" height={460}>
              <ScatterChart margin={{ top: 16, right: 26, bottom: 30, left: 14 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e1e8e3" />
                <XAxis
                  type="number"
                  dataKey="x"
                  name="Vinst"
                  stroke="#8aa094"
                  tickFormatter={fmtAxis}
                  label={{ value: 'Vinst (EBITDA/EBIT/resultat), MSEK', position: 'insideBottom', offset: -16, fill: '#64748b', fontSize: 12 }}
                />
                <YAxis
                  type="number"
                  dataKey="y"
                  name="Börsvärde"
                  stroke="#8aa094"
                  tickFormatter={fmtAxis}
                  label={{ value: 'Börsvärde (MSEK)', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 12 }}
                />
                <ZAxis type="number" dataKey="z" range={[45, 430]} name="Omsättning" />
                {xmin < 0 && <ReferenceArea x1={xmin} x2={0} fill="#ef4444" fillOpacity={0.06} />}
                {xmax > 0 && (
                  <ReferenceLine
                    segment={[{ x: 0, y: 0 }, { x: xmax, y: 12 * xmax }]}
                    stroke="#94a3b8"
                    strokeDasharray="5 4"
                    ifOverflow="extendDomain"
                    label={{ value: '12×', fill: '#64748b', fontSize: 11, position: 'insideTopRight' }}
                  />
                )}
                {xmax > 0 && (
                  <ReferenceLine
                    segment={[{ x: 0, y: 0 }, { x: xmax, y: 18 * xmax }]}
                    stroke="#475569"
                    strokeDasharray="5 4"
                    ifOverflow="extendDomain"
                    label={{ value: '18×', fill: '#64748b', fontSize: 11, position: 'insideTopRight' }}
                  />
                )}
                <Tooltip cursor={{ strokeDasharray: '3 3' }} content={<OtTooltip />} />
                <Scatter
                  data={chartData}
                  onClick={(node) => {
                    const t = node?.ticker ?? node?.payload?.ticker
                    if (t) {
                      setExpanded(t)
                      setView('table')
                    }
                  }}
                >
                  {chartData.map((p) => (
                    <Cell
                      key={p.ticker}
                      fill={ZONE_COLOR[p.zone] ?? '#94a3b8'}
                      fillOpacity={0.5}
                      stroke={ZONE_COLOR[p.zone] ?? '#94a3b8'}
                    />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
            <p className="qchart__hint">
              Bubbelstorlek = omsättning. Linjerna <b>12×</b>/<b>18×</b> är vinstmultiplar (OT-style):
              under 12× = billigt, 12–18× = rimligt, över = dyrt. Rött fält vänster om 0 = förlust/hype
              (negativ vinst). Färg = zon. Klicka en bubbla för detalj. Diagrammet följer filtren ovan.
            </p>
          </div>
        )
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Bolag</th>
                <th>
                  P(upp)
                  <InfoButton title="P(upp) – nästa 4 veckor">
                    Momentum-modellens sannolikhet att aktien stiger de kommande 4 veckorna.
                    Uppdateras varje vecka. Saknas för bolag utan momentum-täckning.
                  </InfoButton>
                </th>
                <th>
                  Kvant
                  <InfoButton title="Kvant-betyg (hård data, token-fritt)">
                    0–100 ur hård finansdata: kvalitet, tillväxt, trygghet och värdering, rankat mot
                    hela universumet. Finns för alla bolag – ingen Claude-token.
                  </InfoButton>
                </th>
                <th>
                  Kvalitet
                  <InfoButton title="Kvalitet (composite 1–5)">
                    Snittet av 9 kvalitativa kriterier som Claude poängsatt ur bolagets rapport.
                    Klicka en rad för delbetygen. Betyg märkta <b>mjuk</b> är det tokenfria
                    destillatet för bolag Claude inte hunnit läsa än.
                  </InfoButton>
                </th>
                <th>
                  Zon
                  <InfoButton title="Värderingszon">
                    Lönsamma bolag zonas på vinstmultipel: billig ≤12×, rimlig ≤18×, dyr &gt;18×.
                    Förlustbolag zonas på P/S och får en <b>förlust</b>-tagg.
                  </InfoButton>
                </th>
                <th>Börsvärde</th>
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
                        <span className="ticker-link__ticker">
                          {row.ticker} <TvLink ticker={row.ticker} />
                          {row.segment && (
                            <span className="badge badge--flat" style={{ marginLeft: 6 }}>
                              {SEGMENT_LABEL[row.segment] ?? row.segment}
                            </span>
                          )}
                        </span>
                      </td>
                      <td>
                        {row.prob_up != null ? fmtPct(row.prob_up) : '–'}
                        {row.pred_signal === 1 && <SignalBadge variant="buy" round />}
                      </td>
                      <td className="qcomposite">{row.quant_score == null ? '–' : Math.round(row.quant_score)}</td>
                      <td className="qcomposite">
                        {row.composite == null ? '–' : fmtNum(row.composite, 2)}
                        {row.composite != null && row.quality_source === 'soft' ? (
                          <span className="softchip" title="Tokenfritt destillat (soft_signals) – inte Claude-läst">mjuk</span>
                        ) : null}
                      </td>
                      <td>
                        <span
                          className={`zonebadge zonebadge--${zoneClass(row.zone)} zonebadge--round`}
                          title={ZONE_LABEL[row.zone] ?? String(row.zone).toUpperCase()}
                        >
                          {(ZONE_LABEL[row.zone] ?? String(row.zone).toUpperCase()).charAt(0)}
                        </span>
                        {row.loss ? <span className="losschip" title="Går med förlust – zonad på P/S">förlust</span> : null}
                      </td>
                      <td>{fmtMcap(row.mcap_msek)}</td>
                    </tr>
                    {open && (
                      <tr className="qrow-detail">
                        <td colSpan={6}>
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
