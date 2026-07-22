import { useMemo, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ReferenceArea, ScatterChart, Scatter, ZAxis,
} from 'recharts'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { usePortfolio } from '../usePortfolio'
import { useWatchlist } from '../useWatchlist'
import { Loading } from '../components/StatusBlock'
import { SignalBadge } from '../components/SignalBadge'
import { StatCard } from '../components/StatCard'
import { InfoButton } from '../components/InfoButton'
import { EmptyState } from '../components/EmptyState'
import { TvLink } from '../components/TvLink'
import { fmtPct, fmtNum, fmtDate, fmtSek, cleanName } from '../format'

// Kvant-nyckeltal från /api/quant som visas som tvärsnittspercentil ("hur
// står bolaget mot HELA universumet just nu"). Fälten kommer redan i
// procentform från TradingView-scannern (15.2 = 15.2%), ingen ytterligare
// skalning. higherIsBetter styr om ett HÖGT eller LÅGT värde räknas som
// starkt (P/S och EV/EBITDA: lägre = billigare = starkare).
const QUANT_METRICS = [
  { key: 'quant_score', label: 'Kvantbetyg totalt', higherIsBetter: true, fmt: (v) => `${fmtNum(v, 0)}%` },
  { key: 'roe', label: 'ROE', higherIsBetter: true, fmt: (v) => `${fmtNum(v, 1)}%` },
  { key: 'rev_growth', label: 'Omsättningstillväxt', higherIsBetter: true, fmt: (v) => `${fmtNum(v, 1)}%` },
  { key: 'ebitda_margin', label: 'EBITDA-marginal', higherIsBetter: true, fmt: (v) => `${fmtNum(v, 1)}%` },
  { key: 'ps', label: 'P/S (lägre = billigare)', higherIsBetter: false, fmt: (v) => fmtNum(v, 1) },
  { key: 'ev_ebitda', label: 'EV/EBITDA (lägre = billigare)', higherIsBetter: false, fmt: (v) => fmtNum(v, 1) },
]

// Percentilrank av EN tickers värde mot ALLA rader i samma kortlista (0-1).
// null om fältet saknas för bolaget eller för lite data i universumet.
function percentileRank(rows, ticker, field, higherIsBetter) {
  if (!rows || rows.length < 5) return null
  const own = rows.find((r) => String(r.ticker || '').toUpperCase() === ticker.toUpperCase())
  const ownV = Number(own?.[field])
  if (!Number.isFinite(ownV)) return null
  const vals = rows.map((r) => Number(r[field])).filter((v) => Number.isFinite(v))
  if (vals.length < 5) return null
  const better = higherIsBetter ? vals.filter((v) => v < ownV).length : vals.filter((v) => v > ownV).length
  return { pct: better / vals.length, value: ownV }
}

// Bygger OT Analytics-stilens bubbeldiagram (börsvärde vs EBITDA, storlek =
// omsättning) genom att joina quality_shortlist (revenue_msek/ebitda_msek,
// LLM-screenern) med quant_shortlist (mcap_msek, TradingView) per ticker.
// Samma svenska microcap-universum i båda listorna – ingen ny backend, bara
// en client-side join av två redan hämtade endpoints.
function bubbleUniverse(qualityRows, quantRows) {
  const quantByTicker = new Map((quantRows ?? []).map((r) => [String(r.ticker || '').toUpperCase(), r]))
  const out = []
  for (const q of qualityRows ?? []) {
    const tk = String(q.ticker || '').toUpperCase()
    const quantRow = quantByTicker.get(tk)
    const ebit = Number(q.ebitda_msek)
    const revenue = Number(q.revenue_msek)
    const mcap = Number(quantRow?.mcap_msek)
    if (!Number.isFinite(ebit) || !Number.isFinite(revenue) || !Number.isFinite(mcap) || revenue <= 0) continue
    out.push({ ticker: q.ticker, name: q.name, ebit, revenue, mcap })
  }
  return out
}

function BubbleTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div style={{ background: '#fff', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px', fontSize: 12 }}>
      <div style={{ fontWeight: 600 }}>{cleanName(d.name, d.ticker)}</div>
      <div>Börsvärde: {fmtNum(d.mcap, 0)} Mkr</div>
      <div>EBITDA: {fmtNum(d.ebit, 0)} Mkr</div>
      <div>Omsättning: {fmtNum(d.revenue, 0)} Mkr</div>
    </div>
  )
}

// "Djupanalys": på-begäran bull/bear + konkurrentkontext för ETT befintligt
// innehav (headless Claude, WebSearch) – samma på-begäran-mönster som
// Skannerns AI-analysruta och Förvaltarbrevets följdfrågebox. Aldrig
// automatisk (kostar ett LLM-anrop, ~2 min), bara vid klick.
function DeepDiveBox({ ticker }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function run() {
    setLoading(true)
    setError(null)
    // Ett gammalt fel-resultat ska inte stå kvar bredvid "Analyserar…" –
    // men ett lyckat behålls synligt under omkörningen (stale-while-revalidate).
    setResult((r) => (r?.error ? null : r))
    try {
      const r = await api.stockAnalyze(ticker)
      setResult(r)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="list-card" style={{ padding: 12 }}>
      <h3 className="section-title" style={{ marginTop: 0 }}>
        Djupanalys
        <InfoButton title="Bull/bear i klartext">
          <p>
            Ärligt motställda argument för och emot att fortsätta äga bolaget just nu, plus kort
            konkurrentkontext – grundat i modellens redan beräknade betyg, caseförändring och
            färska nyheter (WebSearch fyller på med bredare kontext).
          </p>
          <p>
            <b>Ren narrativ, aldrig ett råd.</b> Ingen ny köp/sälj-signal – bara två sidor av
            samma mynt i klartext. Kan ta upp till ~2 minuter.
          </p>
        </InfoButton>
      </h3>

      {/* Visas även efter ett fel-svar (result satt men utan bull_case) –
          annars finns ingen väg att försöka igen utan att ladda om sidan. */}
      {!result?.bull_case && !loading && (
        <button className="btn" onClick={run}>Analysera bolaget</button>
      )}
      {loading && <div className="list-card__empty">Analyserar… (kan ta upp till ~2 min)</div>}
      {error && (
        <div className="status-block status-block--error" style={{ marginTop: 8 }}>
          Kunde inte analysera: {error}
        </div>
      )}
      {result?.error && (
        <div className="status-block status-block--error" style={{ marginTop: 8 }}>
          Kunde inte analysera: {result.error}
        </div>
      )}
      {result?.bull_case && (
        <div style={{ display: 'grid', gap: 12, marginTop: loading ? 0 : 4 }}>
          <div>
            <p style={{ margin: '0 0 4px', fontWeight: 600, color: 'var(--good)' }}>Talar för</p>
            <p style={{ margin: 0, lineHeight: 1.6 }}>{result.bull_case}</p>
          </div>
          <div>
            <p style={{ margin: '0 0 4px', fontWeight: 600, color: 'var(--bad)' }}>Talar emot</p>
            <p style={{ margin: 0, lineHeight: 1.6 }}>{result.bear_case}</p>
          </div>
          {result.competitors && (
            <div>
              <p style={{ margin: '0 0 4px', fontWeight: 600 }}>Konkurrentkontext</p>
              <p style={{ margin: 0, lineHeight: 1.6 }}>{result.competitors}</p>
            </div>
          )}
          <button className="btn" style={{ justifySelf: 'start' }} onClick={run} disabled={loading}>
            Analysera igen
          </button>
        </div>
      )}
    </div>
  )
}

// "Fråga om bolaget": fri följdfråga scopad till ETT bolag – samma mönster
// som Bedömning-flikens CommentaryAskBox, bara med bolagets eget underlag
// (modellbetyg, caseförändring, nyheter) i stället för hela portföljen.
function AskAboutStockBox({ ticker }) {
  const [question, setQuestion] = useState('')
  const [thread, setThread] = useState([])
  const [asking, setAsking] = useState(false)

  async function submit(e) {
    e.preventDefault()
    const q = question.trim()
    if (!q || asking) return
    setAsking(true)
    setQuestion('')
    try {
      const r = await api.stockAsk(ticker, q)
      if (r.error && !r.answer) {
        setThread((t) => [...t, { question: q, error: r.error }])
      } else {
        setThread((t) => [...t, { question: q, answer: r.answer }])
      }
    } catch (err) {
      setThread((t) => [...t, { question: q, error: err.message }])
    } finally {
      setAsking(false)
    }
  }

  return (
    <div className="list-card" style={{ marginTop: 12, padding: 12 }}>
      <h3 className="section-title" style={{ marginTop: 0 }}>Fråga om bolaget</h3>
      {thread.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          {thread.map((t, i) => (
            <div key={i} style={{ marginBottom: 12 }}>
              <p style={{ margin: 0, fontWeight: 600 }}>{t.question}</p>
              {t.answer && <p style={{ margin: '4px 0 0' }}>{t.answer}</p>}
              {t.error && (
                <div className="status-block status-block--error" style={{ marginTop: 6 }}>
                  Kunde inte svara: {t.error}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <form onSubmit={submit} style={{ display: 'flex', gap: 8 }}>
        <input
          className="pf-in"
          style={{ flex: 1 }}
          type="text"
          placeholder="T.ex. vad var bakgrunden till senaste kvartalet?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={asking}
        />
        <button type="submit" className="btn" disabled={asking || !question.trim()}>
          {asking ? 'Svarar…' : 'Fråga'}
        </button>
      </form>
    </div>
  )
}

// ETF-sammansättning (reducerad vy): ~10 största innehav + sektor-/
// geografisk fördelning, på-begäran (WebSearch, cachas 7 dagar server-
// sidan - se stock_deep_dive.etf_composition). Samma på-begäran-mönster
// som DeepDiveBox ovan, bara för ETF:er i stället för enskilda bolag.
function EtfCompositionBox({ ticker, name, onResult }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function run() {
    setLoading(true)
    setError(null)
    setResult((r) => (r?.error ? null : r))
    try {
      const r = await api.etfComposition(ticker, name)
      setResult(r)
      onResult?.(r)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const rows = (kind) => (result?.[kind] ?? [])
  const hasData = (result?.top_holdings?.length ?? 0) > 0

  return (
    <div className="list-card" style={{ padding: 12 }}>
      <h3 className="section-title" style={{ marginTop: 0 }}>
        ETF-sammansättning
        <InfoButton title="Innehav, sektorer, regioner">
          <p>
            De ungefär 10 största innehaven i fonden, plus sektor- och geografisk fördelning –
            uppslaget via sökning (fondbolagets egen sida, justETF, Morningstar m.fl.), inte en
            direkt datakälla, så siffrorna kan vara någon vecka gamla. Cachas 7 dagar.
          </p>
        </InfoButton>
      </h3>
      {!hasData && !loading && (
        <button className="btn" onClick={run}>Visa sammansättning</button>
      )}
      {loading && <div className="list-card__empty">Söker… (kan ta upp till ~3 min)</div>}
      {error && (
        <div className="status-block status-block--error" style={{ marginTop: 8 }}>
          Kunde inte hämta: {error}
        </div>
      )}
      {result?.error && (
        <div className="status-block status-block--error" style={{ marginTop: 8 }}>
          Kunde inte hämta: {result.error}
        </div>
      )}
      {hasData && (
        <div style={{ display: 'grid', gap: 16, marginTop: loading ? 0 : 4 }}>
          <div>
            <p style={{ margin: '0 0 4px', fontWeight: 600 }}>Största innehav</p>
            {rows('top_holdings').map((h, i) => (
              <div key={i} className="list-row" style={{ padding: '4px 0' }}>
                <div className="list-row__main"><span className="list-row__ticker">{h.name}</span></div>
                <div className="list-row__side">
                  <span className="list-row__num">{h.weight_pct != null ? `${h.weight_pct}%` : '–'}</span>
                </div>
              </div>
            ))}
          </div>
          {rows('sectors').length > 0 && (
            <div>
              <p style={{ margin: '0 0 4px', fontWeight: 600 }}>Sektorer</p>
              {rows('sectors').map((s, i) => (
                <div key={i} className="list-row" style={{ padding: '4px 0' }}>
                  <div className="list-row__main"><span className="list-row__ticker">{s.name}</span></div>
                  <div className="list-row__side">
                    <span className="list-row__num">{s.weight_pct != null ? `${s.weight_pct}%` : '–'}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {rows('regions').length > 0 && (
            <div>
              <p style={{ margin: '0 0 4px', fontWeight: 600 }}>Regioner</p>
              {rows('regions').map((r, i) => (
                <div key={i} className="list-row" style={{ padding: '4px 0' }}>
                  <div className="list-row__main"><span className="list-row__ticker">{r.name}</span></div>
                  <div className="list-row__side">
                    <span className="list-row__num">{r.weight_pct != null ? `${r.weight_pct}%` : '–'}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="footnote">
            {result.source ? `Källa: ${result.source}` : ''}
            {result.as_of ? ` · per ${result.as_of}` : ''}
          </p>
          <button className="btn" style={{ justifySelf: 'start' }} onClick={run} disabled={loading}>
            Hämta om
          </button>
        </div>
      )}
    </div>
  )
}

// ETF-djupanalys (reducerad vy): LLM-bedömt kvalitetsbetyg för de STÖRSTA
// INNEHAVEN sammantaget (EN NY bedömning, INTE ett snitt av modellens
// per-aktie-betyg - de täcker bara svenska bolag, en global ETF:s
// megabolagsinnehav som Nvidia/Apple har ingen sådan poäng att snitta
// över) + bull/bear. Visas först EFTER EtfCompositionBox (se hasComposition
// i StockDetailPage) så etf_analyze() nästan alltid träffar en varm
// composition-cache i stället för dubbla WebSearch-anrop.
function EtfDeepDiveBox({ ticker, name }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function run() {
    setLoading(true)
    setError(null)
    setResult((r) => (r?.error ? null : r))
    try {
      const r = await api.etfAnalyze(ticker, name)
      setResult(r)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="list-card" style={{ padding: 12 }}>
      <h3 className="section-title" style={{ marginTop: 0 }}>
        Djupanalys
        <InfoButton title="Kvalitetsbedömning av innehaven + bull/bear">
          <p>
            Ett kvalitetsbetyg (1-5) för fondens största innehav SAMMANTAGET, plus ärligt
            motställda argument för och emot att fortsätta äga fonden just nu – en ny bedömning
            via sökning, INTE ett snitt av modellens egna aktiebetyg (som bara täcker svenska
            bolag). Kan ta upp till ~5 min om sammansättningen ovan inte redan hämtats.
          </p>
        </InfoButton>
      </h3>
      {!result?.bull_case && !loading && (
        <button className="btn" onClick={run}>Analysera innehaven</button>
      )}
      {loading && <div className="list-card__empty">Analyserar… (kan ta upp till ~5 min)</div>}
      {error && (
        <div className="status-block status-block--error" style={{ marginTop: 8 }}>
          Kunde inte analysera: {error}
        </div>
      )}
      {result?.error && (
        <div className="status-block status-block--error" style={{ marginTop: 8 }}>
          Kunde inte analysera: {result.error}
        </div>
      )}
      {result?.bull_case && (
        <div style={{ display: 'grid', gap: 12, marginTop: loading ? 0 : 4 }}>
          {result.quality != null && (
            <div>
              <p style={{ margin: '0 0 4px', fontWeight: 600 }}>
                Kvalitetsbetyg (innehaven sammantaget): {result.quality}/5
              </p>
              {result.quality_reasoning && (
                <p style={{ margin: 0, lineHeight: 1.6 }}>{result.quality_reasoning}</p>
              )}
            </div>
          )}
          <div>
            <p style={{ margin: '0 0 4px', fontWeight: 600, color: 'var(--good)' }}>Talar för</p>
            <p style={{ margin: 0, lineHeight: 1.6 }}>{result.bull_case}</p>
          </div>
          <div>
            <p style={{ margin: '0 0 4px', fontWeight: 600, color: 'var(--bad)' }}>Talar emot</p>
            <p style={{ margin: 0, lineHeight: 1.6 }}>{result.bear_case}</p>
          </div>
          {result.concentration_note && (
            <div>
              <p style={{ margin: '0 0 4px', fontWeight: 600 }}>Koncentrationsrisk</p>
              <p style={{ margin: 0, lineHeight: 1.6 }}>{result.concentration_note}</p>
            </div>
          )}
          <button className="btn" style={{ justifySelf: 'start' }} onClick={run} disabled={loading}>
            Analysera igen
          </button>
        </div>
      )}
    </div>
  )
}

// Kursgraf, fristående från modellens signalhistorik (bygger bara på
// prices/dev) - delas mellan den fulla vyn OCH reducerad-vyn nedan
// (tickers utanför modellens universum, t.ex. innehavda ETF:er, som ändå
// har prisdata via /api/prices Avanza/Yahoo-fallback).
function PriceChartCard({ priceSeries, dev }) {
  return (
    <div className="chart-card">
      <h3>
        Kursutveckling
        {dev != null && (
          <span className={`chart-legend ${dev >= 0 ? 'pos' : 'neg'}`}>
            {' '}— {dev >= 0 ? '+' : ''}{fmtPct(dev)} på perioden
          </span>
        )}
        <InfoButton title="Kursutveckling">
          Aktiens stängningskurs över tid (senaste ~5 åren). Detta är den faktiska priskurvan,
          inte modellens prognos.
        </InfoButton>
      </h3>
      {priceSeries.length < 2 ? (
        <div className="list-card__empty">
          Kursdata genereras vid nästa modellkörning – kom tillbaka efter en uppdatering.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={priceSeries} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.4} />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e1e8e3" />
            <XAxis dataKey="date" tickFormatter={fmtDate} stroke="#8aa094" minTickGap={40} />
            <YAxis stroke="#8aa094" domain={['auto', 'auto']} tick={{ fontSize: 12 }} />
            <Tooltip
              contentStyle={{ background: '#16241d', border: '1px solid #e1e8e3', borderRadius: 8 }}
              labelFormatter={fmtDate}
              formatter={(v) => [fmtNum(v, 2), 'Kurs']}
            />
            <Area type="monotone" dataKey="close" stroke="var(--accent)" strokeWidth={1.5} fill="url(#priceFill)" />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

export function StockDetailPage() {
  const { ticker } = useParams()
  const history = useApiData(() => api.signalHistory(ticker), [ticker])
  const prices = useApiData(() => api.prices(ticker), [ticker])
  const stats = useApiData(() => api.stats(), [])
  // Redan hämtad data (nattliga jobb) – filtreras client-side för just denna
  // ticker, ingen ny backend krävs för dessa tre sektioner.
  const insight = useApiData(() => api.insight(), [])
  const caseChanges = useApiData(() => api.caseChanges(), [])
  const quant = useApiData(() => api.quant(), [])
  const quality = useApiData(() => api.quality(), [])
  const { addHolding } = usePortfolio()
  const { addToWatchlist } = useWatchlist()
  // Styr när EtfDeepDiveBox (reducerad vy) visas - först EFTER att
  // sammansättningen hämtats, så etf_analyze() nästan alltid träffar en
  // varm composition-cache i stället för att göra dubbla WebSearch-anrop.
  const [hasComposition, setHasComposition] = useState(false)

  const insightRow = useMemo(() => {
    const row = (insight.data?.companies ?? []).find((c) => c.ticker?.toUpperCase() === ticker.toUpperCase())
    // insight_report.py skriver denna placeholder när nattjobbets generering
    // misslyckades – ett felmeddelande, inte en narrativ. Visa inget i stället.
    const summary = (row?.summary ?? '').trim()
    if (!summary || summary === 'Kunde inte generera sammanfattning.') return null
    return row
  }, [insight.data, ticker])
  const caseRow = useMemo(
    () => (caseChanges.data ?? []).find((c) => c.ticker?.toUpperCase() === ticker.toUpperCase()),
    [caseChanges.data, ticker],
  )
  const quantMetrics = useMemo(() => {
    const rows = quant.data ?? []
    return QUANT_METRICS
      .map((m) => ({ ...m, rank: percentileRank(rows, ticker, m.key, m.higherIsBetter) }))
      .filter((m) => m.rank != null)
  }, [quant.data, ticker])

  // OT Analytics-stilens bubbeldiagram: börsvärde vs EBITDA, bubblans
  // storlek = omsättning. Universum = svenska microcap-bolag med data i
  // BÅDA kortlistorna (quality_shortlist ∩ quant_shortlist).
  const bubbleAll = useMemo(() => bubbleUniverse(quality.data, quant.data), [quality.data, quant.data])
  const bubbleMine = useMemo(
    () => bubbleAll.filter((b) => b.ticker.toUpperCase() === ticker.toUpperCase()),
    [bubbleAll, ticker],
  )
  const bubbleOthers = useMemo(
    () => bubbleAll.filter((b) => b.ticker.toUpperCase() !== ticker.toUpperCase()),
    [bubbleAll, ticker],
  )
  // Rundade till heltal – dels för prydliga axeletiketter, dels för att
  // ReferenceLine (ifOverflow="discard" som default) annars kan tappa en
  // hel linje om flyttalsbrus knuffar en klippt slutpunkt EN nanometer
  // utanför domänen (verkligt fall: 25x-linjen försvann helt spårlöst
  // p.g.a. 1782.0000000000002 vs 1782.0000000000005).
  const bubbleXMax = useMemo(
    () => Math.round(Math.max(10, ...bubbleAll.map((b) => b.ebit)) * 1.1),
    [bubbleAll],
  )
  const bubbleXMin = useMemo(
    () => Math.round(Math.min(0, ...bubbleAll.map((b) => b.ebit)) * 1.1),
    [bubbleAll],
  )
  const bubbleYMax = useMemo(
    () => Math.round(Math.max(100, ...bubbleAll.map((b) => b.mcap)) * 1.1),
    [bubbleAll],
  )
  // Klipper varje multipel-linje mot BÅDA axlarna (min av var den lämnar
  // plotten på x- resp. y-led) så linjen + dess "Nx"-etikett alltid hamnar
  // innanför synligt fält, oavsett hur brant multipeln är.
  const bubbleMultiples = useMemo(
    () => [10, 25].map((mult) => {
      const x = Math.min(bubbleXMax, bubbleYMax / mult)
      return { mult, x, y: mult * x }
    }),
    [bubbleXMax, bubbleYMax],
  )

  const horizon = stats.data?.horizon_weeks ?? 4

  const sigSeries = useMemo(() => {
    if (!history.data) return []
    return history.data.map((r) => ({
      date: r.date,
      // Relativ styrka (tvärsnitts-percentil av rå modellpoäng) när den finns –
      // kalibrerad prob_up är en isotonic-trappa som vid svag signal står platt
      // på basfrekvensen (~34%) i åratal och ser trasig ut. Percentilen varierar
      // alltid och är det urvalet faktiskt rankar på. Fallback: gamla prob_up.
      prob: r.prob_rank != null ? r.prob_rank * 100
        : (r.prob_up != null ? r.prob_up * 100 : null),
      ret: r.pred_return != null ? r.pred_return * 100 : null,
      signal: r.pred_signal,
    }))
  }, [history.data])
  const hasRank = useMemo(() => (history.data ?? []).some((r) => r.prob_rank != null), [history.data])

  const priceSeries = useMemo(() => {
    if (!prices.data) return []
    return prices.data.map((r) => ({ date: r.date, close: r.close }))
  }, [prices.data])

  const dev = useMemo(() => {
    if (priceSeries.length < 2) return null
    const first = priceSeries[0].close
    const last = priceSeries[priceSeries.length - 1].close
    return first ? last / first - 1 : null
  }, [priceSeries])

  if (history.loading) return <Loading />
  if (history.error) {
    // Utanför modellens universum (t.ex. en innehavd ETF - VVSM.DE/IUSQ.DE
    // m.fl. handlas aldrig av modellen) - INGEN anledning att blockera HELA
    // sidan för det. Kursgrafen (Avanza/Yahoo-fallback i /api/prices, oberoende
    // av modellens signals.csv) och lägg-till-knapparna funkar ändå, bara
    // de modell-specifika sektionerna (P(upp), kvant-/kvalitetspercentil,
    // signalhistorik-graf) nedanför saknar underlag att visa.
    return (
      <section className="page">
        <div className="page-head">
          <Link to="/signaler" className="section-head__link">← Tillbaka</Link>
          <h1>{ticker}</h1>
          <p className="page-subtitle">
            <TvLink ticker={ticker} />
          </p>
        </div>
        <div className="add-form">
          <button className="btn btn--primary" onClick={() => addHolding({ ticker, shares: null })}>
            + Lägg till i portfölj
          </button>
          <button className="btn" onClick={() => addToWatchlist(ticker)}>
            + Bevaka
          </button>
        </div>
        <EmptyState
          title="Ingen modelldata för denna ticker"
          hint="Aktien ingår inte i modellens universum (t.ex. en ETF eller ett utländskt bolag) – bara kursgrafen, sammansättningen och djupanalysen nedan är tillgängliga, inga signaler/betyg."
        />
        <PriceChartCard priceSeries={priceSeries} dev={dev} />
        <EtfCompositionBox ticker={ticker} onResult={(r) => setHasComposition((r?.top_holdings?.length ?? 0) > 0)} />
        {hasComposition && <EtfDeepDiveBox ticker={ticker} />}
      </section>
    )
  }

  const latest = history.data[history.data.length - 1] ?? {}
  const isBuy = latest.pred_signal === 1
  const displayName = cleanName(latest.name, ticker)

  return (
    <section className="page">
      <div className="page-head">
        <Link to="/signaler" className="section-head__link">← Tillbaka</Link>
        <h1>
          {displayName} <SignalBadge variant={isBuy ? 'buy' : 'flat'} />
        </h1>
        <p className="page-subtitle">
          {displayName !== ticker && <span className="page-subtitle__ticker">{ticker} · </span>}
          {latest.sector ?? 'Okänd sektor'}
          {stats.data?.last_signal_date && ` · senaste signal ${stats.data.last_signal_date}`}
          {' · '}<TvLink ticker={ticker} />
        </p>
      </div>

      <div className="add-form">
        <button className="btn btn--primary" onClick={() => addHolding({ ticker, shares: null })}>
          + Lägg till i portfölj
        </button>
        <button className="btn" onClick={() => addToWatchlist(ticker)}>
          + Bevaka
        </button>
      </div>

      {/* Narrativ sammanfattning (nattlig insight_report.py) + caseförändring
          – redan hämtad data, samma "ren narrativ" text som Bedömning-fliken
          men filtrerad till just detta bolag. */}
      {(insightRow || caseRow) && (
        <div className="list-card" style={{ padding: '14px 16px' }}>
          {insightRow && <p style={{ margin: 0, lineHeight: 1.6 }}>{insightRow.summary}</p>}
          {caseRow && (
            <p className={`footnote ${caseRow.status === 'förbättrat' ? 'pos' : caseRow.status === 'försämrat' ? 'neg' : ''}`}
               style={{ marginTop: insightRow ? 8 : 0 }}>
              Caset senaste 90 dagarna: <b>{caseRow.status}</b> – {caseRow.reasons}
            </p>
          )}
        </div>
      )}

      {/* Nyckeltal från senaste signalen */}
      <div className="stat-grid">
        <StatCard
          label={`P(upp) nästa ${horizon}v`}
          value={fmtPct(latest.prob_up)}
          tone={isBuy ? 'good' : 'neutral'}
          info={`Modellens sannolikhet att aktien stiger mer än tröskeln under de kommande ${horizon} veckorna (en period = ${horizon} veckor, uppdateras varje vecka).`}
        />
        <StatCard
          label={`Förv. avk. ${horizon}v`}
          value={fmtPct(latest.pred_return)}
          info={`Modellens prognos för aktiens prisförändring under de kommande ${horizon} veckorna.`}
        />
        <StatCard
          label="Föreslagen storlek"
          value={fmtPct(latest.position_size)}
          info="Hur stor andel av portföljen modellen föreslår i denna aktie, efter risk-/likviditetshänsyn. 0% = ingen position just nu."
        />
        {isBuy && latest.limit_price != null && (
          <StatCard
            label="Köp upp till (limit)"
            value={fmtSek(latest.limit_price)}
            tone="good"
            info="Lägg en LIMITORDER på max denna kurs. Edgen sitter på kvartalshorisont, så jaga inte en aktie som gapat upp – fyller priset inte ≤ gränsen avstår du (nästa ombalansering fångar den annars)."
          />
        )}
        {!isBuy && latest.sell_limit != null && (
          <StatCard
            label="Sälj-limit (om du äger)"
            value={fmtSek(latest.sell_limit)}
            info="Aktien är inte längre rekommenderad. Om du äger den och vill ut: lägg en sälj-LIMITORDER på MINST denna kurs så du inte dumpar in i ett tillfälligt gap-ned."
          />
        )}
        {latest.ta_score != null && latest.ta_score !== 1 && (
          <StatCard
            label="TA-score"
            value={fmtPct(latest.ta_score, 0)}
            info="Tekniskt analyspoäng – hur starkt aktiens pris-/volymmönster ser ut just nu."
          />
        )}
      </div>

      {/* Kursutveckling */}
      <PriceChartCard priceSeries={priceSeries} dev={dev} />

      {/* Fundamenta i kontext: tvärsnittspercentil mot HELA quant-universumet
          just nu (inte bolagets egen historik – den loggas inte historiskt
          ännu). Bara synligt om bolaget finns i quant_shortlist.csv
          (microcap-screenern, inte ETF:er/globala index). */}
      {quantMetrics.length > 0 && (
        <div className="list-card">
          <div style={{ padding: '14px 16px 0' }}>
            <h3 className="section-title" style={{ marginTop: 0 }}>
              Fundamenta i kontext
              <InfoButton title="Percentil mot universumet">
                <p>
                  Hur bolagets nyckeltal (hård data, token-fri kvantscreener) rankar mot ALLA
                  bolag i samma kortlista just nu. 90% = starkare/billigare än 90% av bolagen.
                </p>
                <p>
                  Tvärsnitt idag, inte bolagets egen 5-årshistorik (den loggas inte ännu) – ett
                  jämförelsemått, inte en trend.
                </p>
              </InfoButton>
            </h3>
          </div>
          {quantMetrics.map((m) => (
            <div key={m.key} className="pctl-row">
              <div className="pctl-row__head">
                <span className="pctl-row__label">{m.label}</span>
                <span className="pctl-row__value">{m.fmt(m.rank.value)} · {Math.round(m.rank.pct * 100)}:e percentilen</span>
              </div>
              <div className="pctl-row__track">
                <div className="pctl-row__fill" style={{ width: `${Math.round(m.rank.pct * 100)}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* OT Analytics-stilens bubbeldiagram: börsvärde vs EBITDA, bubbelstorlek
          = omsättning, mot resten av samma svenska microcap-universum.
          Ögonblicksbild (inte en tidsserie som originalet – EBITDA/omsättning
          loggas inte historiskt ännu). Bara synligt om bolaget finns i BÅDA
          kortlistorna (quality ∩ quant). */}
      {bubbleMine.length > 0 && (
        <div className="chart-card">
          <h3>
            Värdering i sammanhang (bubbeldiagram)
            <InfoButton title="Börsvärde vs EBITDA, bubbelstorlek = omsättning">
              <p>
                Samma typ av diagram som OT Analytics (otanalytics.se) är kända för: börsvärde mot
                EBITDA, där bubblans storlek visar omsättningen. Ljusgrå bubblor är andra svenska
                microcap-bolag i samma kortlistor, {displayName} är markerad i grönt.
              </p>
              <p>
                De streckade linjerna är referens-multiplar (börsvärde/EBITDA) – ingen
                värderingsdom, bara ett mått på var bolaget ligger i förhållande till andra.
              </p>
              <p>
                Ögonblicksbild, inte en tidsserie över år som i originalet – EBITDA/omsättning
                loggas inte historiskt ännu.
              </p>
            </InfoButton>
          </h3>
          <ResponsiveContainer width="100%" height={340}>
            <ScatterChart margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e1e8e3" />
              {bubbleXMin < 0 && (
                <ReferenceArea
                  x1={bubbleXMin} x2={0} fill="var(--bad)" fillOpacity={0.06}
                  label={{ value: 'Förlust', position: 'insideTopLeft', fill: 'var(--bad)', fontSize: 11 }}
                />
              )}
              {bubbleMultiples.map(({ mult, x, y }) => (
                <ReferenceLine
                  key={mult}
                  segment={[{ x: 0, y: 0 }, { x, y }]}
                  ifOverflow="visible"
                  stroke="#c9d4cd" strokeDasharray="4 4"
                  label={{ value: `${mult}x`, position: 'insideTopRight', fill: '#8aa094', fontSize: 11 }}
                />
              ))}
              <XAxis type="number" dataKey="ebit" name="EBITDA" unit=" Mkr"
                domain={[bubbleXMin, bubbleXMax]} stroke="#8aa094" tick={{ fontSize: 12 }} />
              <YAxis type="number" dataKey="mcap" name="Börsvärde" unit=" Mkr"
                domain={[0, bubbleYMax]} stroke="#8aa094" tick={{ fontSize: 12 }} />
              <ZAxis type="number" dataKey="revenue" range={[30, 900]} name="Omsättning" unit=" Mkr" />
              <Tooltip content={<BubbleTooltip />} cursor={{ strokeDasharray: '3 3' }} />
              <Scatter name="Övriga bolag" data={bubbleOthers} fill="var(--text-muted)" fillOpacity={0.35} />
              <Scatter name={displayName} data={bubbleMine} fill="var(--accent)" stroke="var(--accent-2)" strokeWidth={2} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Signalhistorik – relativ styrka (percentil) när tillgänglig, annars P(upp) */}
      <div className="chart-card">
        <h3>
          {hasRank ? 'Relativ styrka i universumet' : 'Modellens signalhistorik'}
          <InfoButton title={hasRank ? 'Relativ styrka (percentil)' : 'Signalhistorik'}>
            {hasRank ? (
              <>
                <p>
                  Aktiens <b>percentilrank</b> i modellens rå-poäng, per vecka: 90% = starkare än
                  90% av alla bolag just då. Det är så modellen faktiskt väljer – den håller de
                  ~10 relativt starkaste, oavsett absolut nivå.
                </p>
                <p>
                  Vi visar percentilen i stället för den kalibrerade sannolikheten, som vid svag
                  signal låser sig på basfrekvensen (~34%) och ser platt ut i åratal.
                </p>
              </>
            ) : (
              <>Hur modellens uppgångssannolikhet P(upp) utvecklats över tid. Den streckade linjen är
              köptröskeln – när P(upp) ligger ovanför den ger modellen köpsignal.</>
            )}
          </InfoButton>
        </h3>
        {sigSeries.length < 2 ? (
          <div className="list-card__empty">För lite signalhistorik att visa än.</div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={sigSeries} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e1e8e3" />
              <XAxis dataKey="date" tickFormatter={fmtDate} stroke="#8aa094" minTickGap={40} />
              <YAxis domain={[0, 100]} stroke="#8aa094" tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
              <Tooltip
                contentStyle={{ background: '#16241d', border: '1px solid #e1e8e3', borderRadius: 8 }}
                labelFormatter={fmtDate}
                formatter={(v, name) => [`${Number(v).toFixed(1)}%`,
                  name === 'prob' ? (hasRank ? 'Relativ styrka' : 'P(upp)') : 'Förv. avk.']}
              />
              {hasRank ? (
                <ReferenceLine
                  y={80}
                  stroke="#f59e0b"
                  strokeDasharray="4 4"
                  label={{ value: 'topp-20%', fill: '#f59e0b', fontSize: 11, position: 'insideTopRight' }}
                />
              ) : (stats.data?.threshold?.buy_threshold != null && (
                <ReferenceLine
                  y={stats.data.threshold.buy_threshold * 100}
                  stroke="#f59e0b"
                  strokeDasharray="4 4"
                  label={{ value: 'köptröskel', fill: '#f59e0b', fontSize: 11, position: 'insideTopRight' }}
                />
              ))}
              <Line type="monotone" dataKey="prob" stroke="var(--good)" dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="section-head"><h2>Lär känna bolaget</h2></div>
      <DeepDiveBox ticker={ticker} />
      <AskAboutStockBox ticker={ticker} />
    </section>
  )
}
