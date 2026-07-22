import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { InfoButton } from '../components/InfoButton'
import { TvLink } from '../components/TvLink'

const BUCKETS = [
  { value: 'broad', label: 'Bred kärna (World/US/EM)' },
  { value: 'sweden', label: 'Sverige' },
  { value: 'theme', label: 'Tematiskt' },
  { value: 'leverage', label: 'Hävstång' },
]
const BUCKET_LABEL = Object.fromEntries(BUCKETS.map((b) => [b.value, b.label]))
const fmtKr = (v) => (v == null ? '–' : `${Math.round(v).toLocaleString('sv-SE')} kr`)
const fmtPct = (v) => (v == null ? '–' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}%`)

// Klient-sida trancher (speglar portfolio.size_in): lika + dip-viktat, −5%/steg.
function sizeIn(amount, n) {
  n = Math.max(1, n | 0)
  const equal = [...Array(n)].map((_, i) => ({
    steg: i + 1, kr: Math.round(amount / n), trigger: i === 0 ? 'nu' : `vid −${i * 5}%`,
  }))
  const w = [...Array(n)].map((_, i) => i + 1)
  const ws = w.reduce((a, b) => a + b, 0)
  const dip = w.map((wi, i) => ({
    steg: i + 1, kr: Math.round((amount * wi) / ws), trigger: i === 0 ? 'nu' : `vid −${i * 5}% från nu`,
  }))
  return { equal, dip }
}

const TIER = {
  red: { cls: 'exit-red', label: 'END THIS NOW' },
  amber: { cls: 'exit-amber', label: 'Varning' },
}

export function HoldingsPage() {
  const [holdings, setHoldings] = useState([])
  const [analysis, setAnalysis] = useState(null)
  const [exit, setExit] = useState(null)
  const [caseChanges, setCaseChanges] = useState([])
  const [amount, setAmount] = useState(10000)
  const [riskOn, setRiskOn] = useState(false)
  const [sizeAmt, setSizeAmt] = useState(10000)
  const [sizeN, setSizeN] = useState(4)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [universe, setUniverse] = useState([])
  const [search, setSearch] = useState('')

  useEffect(() => {
    api.holdings(amount)
      .then((d) => {
        setAnalysis(d)
        setHoldings((d.holdings ?? []).map((h) => ({ ...h })))
      })
      .catch(setError)
      .finally(() => setLoading(false))
    api.exitSignals().then(setExit).catch(() => {})
    api.universe().then(setUniverse).catch(() => {})
    api.caseChanges().then(setCaseChanges).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Lägg till-flödet: sök i universumet → välj → ange antal + inköpskurs.
  const [addOpen, setAddOpen] = useState(false)
  const [addSel, setAddSel] = useState(null)      // valt värdepapper
  const [addShares, setAddShares] = useState('')
  const [addPrice, setAddPrice] = useState('')
  const [addValue, setAddValue] = useState('')    // manuellt värde (utländska/fonder)
  const [editIdx, setEditIdx] = useState(null)    // rad i redigeringsläge

  // Köp/sälj-flödet: räknar ut nytt vägt snittpris (köp) resp. behåller snittet
  // oförändrat på kvarvarande andel (sälj) – i stället för att du gör det i huvudet.
  const [tradeIdx, setTradeIdx] = useState(null)
  const [tradeMode, setTradeMode] = useState('buy')
  const [tradeShares, setTradeShares] = useState('')
  const [tradePrice, setTradePrice] = useState('')
  const [tradeAmt, setTradeAmt] = useState('')

  function openTrade(i, mode) {
    setTradeIdx(i); setTradeMode(mode)
    setTradeShares(''); setTradePrice(''); setTradeAmt('')
    setEditIdx(null)
  }
  function closeTrade() {
    setTradeIdx(null); setTradeShares(''); setTradePrice(''); setTradeAmt('')
  }
  function confirmTrade() {
    const i = tradeIdx
    const h = holdings[i]
    if (!h) return
    const isShareBased = h.shares != null && h.shares !== '' && Number(h.shares) > 0

    if (isShareBased) {
      const oldShares = Number(h.shares) || 0
      const oldBuyPrice = Number(h.buy_price) || 0
      const oldValue = Number(h.value) || 0
      const oldCost = h.cost != null && h.cost !== '' ? Number(h.cost) : oldShares * oldBuyPrice
      if (tradeMode === 'buy') {
        const addSh = Number(tradeShares) || 0
        const addPx = Number(tradePrice) || 0
        if (addSh <= 0 || addPx <= 0) return
        const newShares = oldShares + addSh
        const newCost = oldCost + addSh * addPx
        // Grov värde-uppskattning tills nattkörningen räknar om mot senaste kurs.
        setHoldings((hs) => hs.map((r, j) => (j === i
          ? { ...r, shares: newShares, cost: newCost, buy_price: newCost / newShares, value: oldValue + addSh * addPx }
          : r)))
        setDirty(true)
      } else {
        const sellSh = Number(tradeShares) || 0
        if (sellSh <= 0) return
        if (sellSh >= oldShares) {
          del(i)
        } else {
          const newShares = oldShares - sellSh
          // Snittkostnaden per kvarvarande aktie är oförändrad – bara antal/insatt krymper.
          const newCost = oldBuyPrice ? oldBuyPrice * newShares : oldCost * (newShares / oldShares)
          const newValue = oldShares > 0 ? oldValue * (newShares / oldShares) : 0
          setHoldings((hs) => hs.map((r, j) => (j === i
            ? { ...r, shares: newShares, cost: newCost, value: newValue }
            : r)))
          setDirty(true)
        }
      }
    } else {
      const oldValue = Number(h.value) || 0
      const oldCost = h.cost != null && h.cost !== '' ? Number(h.cost) : oldValue
      if (tradeMode === 'buy') {
        const addAmt = Number(tradeAmt) || 0
        if (addAmt <= 0) return
        setHoldings((hs) => hs.map((r, j) => (j === i
          ? { ...r, value: oldValue + addAmt, cost: oldCost + addAmt }
          : r)))
        setDirty(true)
      } else {
        const sellAmt = Number(tradeAmt) || 0
        if (sellAmt <= 0) return
        if (sellAmt >= oldValue) {
          del(i)
        } else {
          const frac = oldValue > 0 ? sellAmt / oldValue : 0
          setHoldings((hs) => hs.map((r, j) => (j === i
            ? { ...r, value: oldValue - sellAmt, cost: oldCost * (1 - frac) }
            : r)))
          setDirty(true)
        }
      }
    }
    closeTrade()
  }

  const q = search.trim().toLowerCase()
  const matches = q.length < 2 ? [] : universe
    .filter((u) => u.name.toLowerCase().includes(q) || u.ticker.toLowerCase().includes(q))
    .slice(0, 8)

  function confirmAdd() {
    const sh = Number(addShares) || null
    const bp = Number(addPrice) || null
    const mv = Number(addValue) || 0
    if (!addSel?.name || (!sh && mv <= 0)) return
    setHoldings((hs) => [...hs, {
      name: addSel.name, ticker: addSel.ticker || '', bucket: addSel.bucket || 'broad',
      shares: sh, buy_price: bp, value: mv, cost: sh && bp ? sh * bp : null,
    }])
    setDirty(true)
    setAddOpen(false); setAddSel(null); setSearch(''); setAddShares(''); setAddPrice(''); setAddValue('')
  }

  function refreshAmount(a) {
    setAmount(a)
    if (!dirty) api.holdings(a).then(setAnalysis).catch(() => {})
  }
  function edit(i, field, val) {
    setHoldings((hs) => hs.map((h, j) => (j === i ? { ...h, [field]: val } : h)))
    setDirty(true)
  }
  function del(i) {
    setHoldings((hs) => hs.filter((_, j) => j !== i))
    setDirty(true)
  }
  async function save() {
    setSaving(true)
    try {
      const clean = holdings
        .map((h) => ({
          name: (h.name || '').trim(), value: Number(h.value) || 0, bucket: h.bucket,
          ticker: (h.ticker || '').trim(), cost: h.cost === '' || h.cost == null ? null : Number(h.cost),
          shares: h.shares === '' || h.shares == null ? null : Number(h.shares),
          buy_price: h.buy_price === '' || h.buy_price == null ? null : Number(h.buy_price),
        }))
        .filter((h) => h.name && (h.value > 0 || h.shares))
      const d = await api.saveHoldings(clean, amount)
      setAnalysis(d)
      setHoldings((d.holdings ?? []).map((h) => ({ ...h })))
      setDirty(false)
    } catch (e) {
      setError(e)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Loading />
  if (error) return <ErrorBlock error={error} />

  const total = analysis?.total ?? 0
  const liveTotal = holdings.reduce((s, h) => s + (Number(h.value) || 0), 0)
  const buckets = analysis?.buckets ?? {}
  const target = analysis?.target ?? {}
  const plan = analysis?.newcapital?.plan ?? {}
  const broadEtfs = analysis?.newcapital?.broad_etfs ?? {}
  const riskon = analysis?.riskon ?? null
  const housemoney = analysis?.housemoney ?? []

  // Exit-tier per innehav (matcha på ticker, annars namn).
  const exitRows = exit?.holdings ?? []
  const tierByKey = {}
  exitRows.forEach((e) => {
    if (e.ticker) tierByKey[e.ticker.toUpperCase()] = e
    if (e.name) tierByKey[e.name.toLowerCase()] = e
  })
  const tierOf = (h) => tierByKey[(h.ticker || '').toUpperCase()] || tierByKey[(h.name || '').toLowerCase()]
  const alarms = exitRows.filter((e) => e.tier === 'red' || e.tier === 'amber')
  const sizePlan = sizeIn(sizeAmt, sizeN)

  // Case-förändringar: matcha på ticker mot dina innehav.
  const caseByTicker = {}
  caseChanges.forEach((c) => { if (c.ticker) caseByTicker[c.ticker.toUpperCase()] = c })
  const caseOf = (h) => caseByTicker[(h.ticker || '').toUpperCase()]
  const myCaseChanges = holdings
    .map((h) => ({ h, c: caseOf(h) }))
    .filter(({ c }) => c && c.status !== 'oförändrat')
  const CASE_ACTION = { förbättrat: 'Fortsätt hålla / överväg att bygga vidare', försämrat: 'Bevaka / överväg att minska' }

  return (
    <section className="page">
      <div className="page-head">
        <h1>
          Min portfölj
          <InfoButton title="Portfölj-medveten planering">
            <p>
              Innehaven kan synkas direkt från Montrose (sync_montrose_holdings.py på Pi:n)
              eller läggas in manuellt här. Appen klassar dem per hink, jämför mot en
              diversifierad mål-fördelning och riktar <b>nytt kapital</b> mot det du är
              underviktad i – fyll-mot-mål via inflöden, ingen försäljning.
            </p>
          </InfoButton>
        </h1>
        <p className="page-subtitle">{fmtKr(total)} · {holdings.length} innehav</p>
      </div>

      {/* ── Exit-alarm överst: "END THIS NOW" ─────────────────────────────── */}
      {/* Rullgardin (2026-07-22): tog tidigare upp fast yta överst på sidan
          oavsett om man just då brydde sig om detaljerna - stängd som
          default, men <summary> visar antal + värsta nivå så ett rött larm
          aldrig är osynligt utan att man öppnar. */}
      {alarms.length > 0 && (
        <details className="exit-panel">
          <summary className="section-title" style={{ marginBottom: 8 }}>
            Exit-alarm ({alarms.length}{alarms.some((e) => e.tier === 'red') ? ', varav röda' : ''})
            <InfoButton title="När något bör bort">
              <b>Rött (end this now)</b> = sektorn är svag <b>och</b> kursen är tekniskt brutet
              (under 40-veckors glidande medel med fallande momentum). <b>Gult</b> = en av de två.
              Ett larm, inte en order – bekräfta själv. Kräver att skanningen körts
              (<code>portfolio.py exitscan</code> på Pi:n).
            </InfoButton>
          </summary>
          {alarms.map((e) => (
            <div key={e.ticker || e.name} className={`exit-item ${TIER[e.tier]?.cls}`}>
              <div className="exit-item__head">
                <span className="exit-item__tier">{TIER[e.tier]?.label}</span>
                <b>{e.name}</b>
                {e.ticker && <span className="mono">{e.ticker}</span>}
                {e.ticker && <TvLink ticker={e.ticker} />}
              </div>
              <div className="exit-item__notes">
                <span>Teknik: {e.tech_note}</span>
                {e.sector_note && <span>{e.sector_note}</span>}
              </div>
            </div>
          ))}
        </details>
      )}
      {exit?.generated && (
        <p className="footnote" style={{ marginTop: -4 }}>
          Exit-skanning: {String(exit.generated).slice(0, 16).replace('T', ' ')}
          {alarms.length === 0 && ' · inga larm just nu'}
        </p>
      )}

      {/* ── Har investeringscaset förändrats? ────────────────────────────── */}
      {myCaseChanges.length > 0 && (
        <div className="exit-panel">
          <h3 className="section-title" style={{ marginBottom: 8 }}>
            Caseförändringar
            <InfoButton title="Har investeringscaset förändrats?">
              <p>
                Jämför de senaste 90 dagarnas AI-tolkade pressmeddelanden mot föregående 90 dagar:
                guidance, ledningston, nya riskflaggor, kapitalanskaffning och katalysatorer.
              </p>
              <p>
                Ingen ny AI-analys – bara en aggregering av redan extraherade signaler. Ett
                observationsverktyg, inte en köp-/säljorder – bekräfta själv.
              </p>
            </InfoButton>
          </h3>
          {myCaseChanges.map(({ h, c }) => (
            <div key={h.ticker || h.name} className={`exit-item ${c.status === 'försämrat' ? 'exit-amber' : ''}`}>
              <div className="exit-item__head">
                <span className="exit-item__tier">
                  {c.status === 'förbättrat' ? '▲ Förbättrat' : '▼ Försämrat'}
                </span>
                <b>{h.name}</b>
                {h.ticker && <span className="mono">{h.ticker}</span>}
              </div>
              <div className="exit-item__notes">
                <span>Orsaker: {c.reasons}</span>
                <span>Åtgärd: {CASE_ACTION[c.status]}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Lägg till innehav: sök → antal + inköpskurs ─────────────────── */}
      {!addOpen ? (
        <div className="pf-actions" style={{ margin: '2px 0 12px' }}>
          <button className="pf-btn pf-btn--primary" onClick={() => setAddOpen(true)}>+ Lägg till innehav</button>
          {dirty && (
            <button className="pf-btn" onClick={save} disabled={saving}>
              {saving ? 'Sparar…' : 'Spara ändringar'}
            </button>
          )}
        </div>
      ) : (
        <div className="h-add">
          {!addSel ? (
            <div className="pf-search">
              <input
                autoFocus
                className="pf-in pf-search__input"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Sök namn eller ticker…"
              />
              {matches.length > 0 && (
                <div className="pf-search__drop">
                  {matches.map((u) => (
                    <button key={u.ticker} className="pf-search__item" onClick={() => { setAddSel(u); setSearch('') }}>
                      <span className="pf-search__name">{u.name}</span>
                      <span className="pf-search__meta">
                        <span className="mono">{u.ticker}</span>
                        <span className={`cand-src cand-src--${u.bucket}`}>{BUCKET_LABEL[u.bucket] ?? u.bucket}</span>
                      </span>
                    </button>
                  ))}
                </div>
              )}
              {q.length >= 2 && matches.length === 0 && (
                <div className="pf-search__drop">
                  <button className="pf-search__item" onClick={() => setAddSel({ name: search.trim(), ticker: '', bucket: 'theme' })}>
                    <span className="pf-search__name">Lägg till ”{search.trim()}” manuellt</span>
                    <span className="pf-search__meta"><span className="mono">utanför universumet</span></span>
                  </button>
                </div>
              )}
            </div>
          ) : (
            <>
              <div className="h-add__sel">
                <b>{addSel.name}</b>
                {addSel.ticker && <span className="mono">{addSel.ticker}</span>}
                <button className="pf-del" onClick={() => setAddSel(null)} title="Byt">✕</button>
              </div>
              <div className="h-add__fields">
                <label>Antal
                  <input className="pf-in pf-num" type="number" min="0" inputMode="decimal"
                    value={addShares} onChange={(e) => setAddShares(e.target.value)} placeholder="t.ex. 100" />
                </label>
                <label>Inköpskurs (kr)
                  <input className="pf-in pf-num" type="number" min="0" step="0.01" inputMode="decimal"
                    value={addPrice} onChange={(e) => setAddPrice(e.target.value)} placeholder="t.ex. 12,47" />
                </label>
                {!addSel.ticker?.endsWith('.ST') && (
                  <label>Värde nu (kr)
                    <input className="pf-in pf-num" type="number" min="0" inputMode="decimal"
                      value={addValue} onChange={(e) => setAddValue(e.target.value)} placeholder="om ej svensk ticker" />
                  </label>
                )}
              </div>
              <p className="footnote" style={{ margin: '6px 0' }}>
                Svenska innehav med antal värderas om automatiskt varje natt mot senaste kurs.
                Utländska (EUR-ETF:er) behöver värdet manuellt.
              </p>
            </>
          )}
          <div className="pf-actions" style={{ marginTop: 8 }}>
            {addSel && <button className="pf-btn pf-btn--primary" onClick={confirmAdd}>Lägg till</button>}
            <button className="pf-btn" onClick={() => { setAddOpen(false); setAddSel(null); setSearch('') }}>Avbryt</button>
          </div>
        </div>
      )}

      {/* ── Innehavslista: läskort med Redigera per rad ─────────────────── */}
      <div className="list-card">
        {holdings.length === 0 && <div className="list-card__empty">Inga innehav än – lägg till ovan.</div>}
        {holdings.map((h, i) => {
          const t = tierOf(h)
          const c = caseOf(h)
          const val = Number(h.value) || 0
          const cost = h.cost === '' || h.cost == null ? null : Number(h.cost)
          const gain = cost && cost > 0 ? val / cost - 1 : null
          const share = liveTotal > 0 ? val / liveTotal : 0
          const editing = editIdx === i
          const trading = tradeIdx === i
          const isShareBased = h.shares != null && h.shares !== '' && Number(h.shares) > 0
          return (
            <div key={i} className={`h-card${t ? ` exit-row-${t.tier}` : ''}`}>
              <div className="h-card__top">
                <span className="h-card__name">
                  {h.name} {h.ticker && (
                    <Link to={`/aktie/${encodeURIComponent(h.ticker)}`} className="mono h-card__tk ticker-link">
                      {h.ticker}
                    </Link>
                  )}
                  {h.auto && <span className="h-card__auto" title="Värderas om varje natt">auto</span>}
                  {c && c.status !== 'oförändrat' && (
                    <span className="h-card__auto" style={{
                      background: c.status === 'förbättrat' ? 'var(--good-soft)' : 'var(--bad-soft)',
                      color: c.status === 'förbättrat' ? 'var(--good)' : 'var(--bad)',
                    }} title={c.reasons}>
                      {c.status === 'förbättrat' ? '▲ case' : '▼ case'}
                    </span>
                  )}
                </span>
                <button className="pf-btn pf-btn--sm" onClick={() => { setEditIdx(editing ? null : i); closeTrade() }}>
                  {editing ? 'Klar' : 'Redigera'}
                </button>
              </div>
              {!editing ? (
                <>
                  <div className="h-card__stats">
                    <span><i>Värde</i>{fmtKr(val)}</span>
                    <span className={gain == null ? '' : gain >= 0 ? 'pos' : 'neg'}>
                      <i>Vinst</i>{gain == null ? '–' : fmtPct(gain)}
                    </span>
                    <span><i>Andel</i>{(share * 100).toFixed(0)}%</span>
                    <span><i>Hink</i>{BUCKET_LABEL[h.bucket] ?? h.bucket}</span>
                  </div>
                  {/* Fundamenta-bevakning (steg 3 i modellen): caset intakt eller inte,
                      ur value_screener-datan – inte bara pris/TA. Visas bara för
                      innehav vi faktiskt har värde-data för. */}
                  {h.fundamentals && (
                    <div className={`h-card__fund${h.fundamentals.ok ? '' : ' h-card__fund--warn'}`}>
                      {h.fundamentals.ok
                        ? <>Caset intakt{h.fundamentals.roe != null && <> · ROE {fmtPct(h.fundamentals.roe)}</>}
                            {h.fundamentals.rev_growth_yoy != null && <> · tillväxt {fmtPct(h.fundamentals.rev_growth_yoy)}</>}
                            {h.fundamentals.value_zone && <> · {h.fundamentals.value_zone}</>}</>
                        : <>Caset: {h.fundamentals.issues.join(' · ')}</>}
                    </div>
                  )}
                  <div className="h-card__actions">
                    <button className="pf-btn pf-btn--sm" onClick={() => openTrade(i, 'buy')}>+ Köp</button>
                    <button className="pf-btn pf-btn--sm" onClick={() => openTrade(i, 'sell')}>− Sälj</button>
                  </div>
                  {trading && (
                    <div className="h-card__trade">
                      <div className="h-card__trade-head">
                        <b>{tradeMode === 'buy' ? `Köp mer ${h.name}` : `Sälj ${h.name}`}</b>
                        <button className="pf-del" onClick={closeTrade} title="Avbryt">✕</button>
                      </div>
                      {isShareBased ? (
                        <div className="h-add__fields">
                          <label>Antal
                            <input className="pf-in pf-num" type="number" min="0" inputMode="decimal"
                              value={tradeShares} onChange={(e) => setTradeShares(e.target.value)} placeholder="t.ex. 20" />
                          </label>
                          {tradeMode === 'buy' ? (
                            <label>Pris (kr)
                              <input className="pf-in pf-num" type="number" min="0" step="0.01" inputMode="decimal"
                                value={tradePrice} onChange={(e) => setTradePrice(e.target.value)} placeholder="t.ex. 12,47" />
                            </label>
                          ) : (
                            <button className="pf-btn pf-btn--sm" style={{ alignSelf: 'end' }}
                              onClick={() => setTradeShares(String(h.shares))}>
                              Sälj allt ({h.shares} st)
                            </button>
                          )}
                        </div>
                      ) : (
                        <div className="h-add__fields">
                          <label>{tradeMode === 'buy' ? 'Belopp att lägga till (kr)' : 'Belopp att sälja (kr)'}
                            <input className="pf-in pf-num" type="number" min="0" inputMode="decimal"
                              value={tradeAmt} onChange={(e) => setTradeAmt(e.target.value)} placeholder="t.ex. 5000" />
                          </label>
                          {tradeMode === 'sell' && (
                            <button className="pf-btn pf-btn--sm" style={{ alignSelf: 'end' }}
                              onClick={() => setTradeAmt(String(Math.round(Number(h.value) || 0)))}>
                              Sälj allt ({fmtKr(h.value)})
                            </button>
                          )}
                        </div>
                      )}
                      {tradeMode === 'buy' && (
                        <p className="footnote" style={{ margin: '6px 0 0' }}>
                          Nytt vägt snittpris räknas ut automatiskt av det du redan äger + det nya köpet.
                        </p>
                      )}
                      <div className="pf-actions" style={{ marginTop: 8 }}>
                        <button className="pf-btn pf-btn--primary" onClick={confirmTrade}>
                          {tradeMode === 'buy' ? 'Bekräfta köp' : 'Bekräfta sälj'}
                        </button>
                        <button className="pf-btn" onClick={closeTrade}>Avbryt</button>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="h-card__edit">
                  <label>Antal
                    <input className="pf-in pf-num" type="number" min="0" inputMode="decimal"
                      value={h.shares ?? ''} onChange={(e) => edit(i, 'shares', e.target.value)} placeholder="–" />
                  </label>
                  <label>Inköpskurs
                    <input className="pf-in pf-num" type="number" min="0" step="0.01" inputMode="decimal"
                      value={h.buy_price ?? ''} onChange={(e) => edit(i, 'buy_price', e.target.value)} placeholder="–" />
                  </label>
                  {!h.auto && (
                    <label>Värde (kr)
                      <input className="pf-in pf-num" type="number" min="0" inputMode="decimal"
                        value={h.value} onChange={(e) => edit(i, 'value', e.target.value)} />
                    </label>
                  )}
                  <label>Hink
                    <select className="pf-in" value={h.bucket} onChange={(e) => edit(i, 'bucket', e.target.value)}>
                      {BUCKETS.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}
                    </select>
                  </label>
                  <button className="pf-btn pf-btn--danger" onClick={() => { del(i); setEditIdx(null) }}>
                    Ta bort innehav
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
      {dirty && (
        <div className="pf-actions">
          <button className="pf-btn pf-btn--primary" onClick={save} disabled={saving}>
            {saving ? 'Sparar…' : 'Spara ändringar'}
          </button>
        </div>
      )}
      <p className="footnote">
        Innehav med <b>antal + svensk ticker</b> värderas om automatiskt varje nattlig körning
        (märkta ”auto”) och loggas i din portföljkurva. Inköpskurs behövs för vinst-%, säljvakt
        och house-money.
      </p>

      <h3 className="section-title">Fördelning mot mål</h3>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Hink</th><th>Nu</th><th>Mål</th><th>Diff</th></tr></thead>
          <tbody>
            {BUCKETS.map((b) => {
              const cur = buckets[b.value] ?? 0, tgt = target[b.value] ?? 0
              const diff = cur - tgt
              return (
                <tr key={b.value}>
                  <td>{b.label}</td>
                  <td>{(cur * 100).toFixed(0)}%</td>
                  <td>{(tgt * 100).toFixed(0)}%</td>
                  <td className={diff > 0.02 ? 'flow-out' : diff < -0.02 ? 'flow-in' : 'flow-flat'}>
                    {diff >= 0 ? '+' : ''}{(diff * 100).toFixed(0)}%
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {analysis?.warnings?.length > 0 && (
        <div className="qdetail__flags" style={{ marginTop: 10 }}>
          {analysis.warnings.map((w, i) => <span className="qflag" key={i}>{w}</span>)}
        </div>
      )}
      {(analysis?.months_core_50 != null || analysis?.months_to_core != null) && (
        <p className="footnote" style={{ marginTop: 8 }}>
          Väg till balans vid {fmtKr(analysis.proj_amount)}/mån (fyll-mot-mål, inget säljs):{' '}
          {analysis.months_core_50 === 0
            ? 'kärnan är redan största innehav'
            : `kärnan blir största innehav (~50%) om ~${analysis.months_core_50} mån`}
          {analysis.months_to_core != null && analysis.months_to_core !== 0 && (
            <> · helt i balans om ~{analysis.months_to_core} mån (≈ {(analysis.months_to_core / 12).toFixed(1)} år) – bromsas av din största övervikt (Sverige) som bara späds ut när totalen växer</>
          )}
          . Snabbare med högre insättning eller genom att sälja ned satelliterna.
        </p>
      )}

      <h3 className="section-title">
        Nytt kapital – vart det ska in
        <span className="riskon-toggle">
          <button className={`riskon-btn${!riskOn ? ' riskon-btn--active' : ''}`} onClick={() => setRiskOn(false)}>
            Fyll mot mål
          </button>
          <button className={`riskon-btn riskon-btn--fire${riskOn ? ' riskon-btn--active' : ''}`} onClick={() => setRiskOn(true)}>
            Risk on
          </button>
        </span>
      </h3>

      {/* Rank-modellen (Balanserad/Buffett/Momentum) väljs på Hem-sidan, där
          "Nästa köp"-kortet faktiskt visar de aktier den styr – den plan som
          byggs HÄR (fyll-mot-mål-hinkarna) är modell-oberoende. */}
      <div className="newcap__input">
        <label>Belopp</label>
        <input type="number" min="0" step="500" value={amount}
          onChange={(e) => refreshAmount(Math.max(0, Number(e.target.value) || 0))} />
        <span>kr</span>
        {dirty && <span className="pf-hint">(spara för uppdaterad plan)</span>}
      </div>

      {riskOn ? (
        <>
          <div className="riskon-warn">{riskon?.warning ?? 'RISK ON: koncentrerat, ingen riskberäkning.'}</div>
          {(riskon?.picks?.length ?? 0) === 0 ? (
            <p className="footnote">Inga kandidater – kör screener/rotation först.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Namn</th><th>Ticker</th><th>Belopp</th><th></th></tr></thead>
                <tbody>
                  {riskon.picks.map((p) => (
                    <tr key={p.ticker || p.name}>
                      <td>{p.name}{p.source && <span className={`cand-src cand-src--${p.source}`}>{p.source}</span>}</td>
                      <td className="mono">{p.ticker} <TvLink ticker={p.ticker} /></td>
                      <td>{fmtKr(p.kr)}</td>
                      <td className="flow-flat">{p.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : Object.keys(plan).length === 0 ? (
        <p className="footnote">Ingen underviktad hink – du ligger på/över mål.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Hink</th><th>Andel</th><th>Belopp</th></tr></thead>
            <tbody>
              {Object.entries(plan).sort((a, b) => b[1] - a[1]).map(([b, kr]) => (
                <tr key={b}>
                  <td>{BUCKET_LABEL[b] ?? b}</td>
                  <td>{amount ? Math.round((kr / amount) * 100) : 0}%</td>
                  <td>{fmtKr(kr)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!riskOn && Object.keys(broadEtfs).length > 0 && (
        <>
          <p className="footnote" style={{ marginBottom: 4 }}>Bred kärna – dela lika över:</p>
          <div className="table-wrap">
            <table>
              <tbody>
                {Object.entries(broadEtfs).map(([lbl, e]) => (
                  <tr key={lbl}>
                    <td>{lbl}</td>
                    <td className="mono">{e.ticker} <TvLink ticker={e.ticker} /></td>
                    <td>{fmtKr(e.kr)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Size in: dela köpet i trancher ─────────────────────────────────── */}
      <h3 className="section-title">
        Size in – dela köpet
        <InfoButton title="Köp i omgångar istället för allt på en gång">
          Sprider ut ett köp så att du slipper tajma en enda punkt. <b>Lika</b> = jämnt över
          tiden. <b>Dip-viktat</b> = lägg mer ju djupare kursen faller (−5% per steg).
        </InfoButton>
      </h3>
      <div className="newcap__input">
        <label>Köpbelopp</label>
        <input type="number" min="0" step="1000" value={sizeAmt}
          onChange={(e) => setSizeAmt(Math.max(0, Number(e.target.value) || 0))} />
        <span>kr i</span>
        <input type="number" min="1" max="8" value={sizeN} style={{ width: 60 }}
          onChange={(e) => setSizeN(Math.min(8, Math.max(1, Number(e.target.value) || 1)))} />
        <span>trancher</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Steg</th><th>Lika</th><th>Dip-viktat</th><th>Trigger (dip)</th></tr></thead>
          <tbody>
            {sizePlan.equal.map((t, i) => (
              <tr key={t.steg}>
                <td>{t.steg}</td>
                <td>{fmtKr(t.kr)}</td>
                <td>{fmtKr(sizePlan.dip[i].kr)}</td>
                <td className="flow-flat">{sizePlan.dip[i].trigger}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── House money: sälj vinsten, behåll insatsen ────────────────────── */}
      <h3 className="section-title">
        House money – lås insatsen
        <InfoButton title="Sälj vinsten, behåll ursprungskapitalet">
          När ett innehav gått upp kraftigt: sälj så mycket att din <b>insats</b> kommer hem
          som cash, och låt vinsten (”free carry”) fortsätta rida. Kräver att du fyllt i
          <b> Insatt</b> ovan. Visas per innehav där värdet &gt; insatsen.
        </InfoButton>
      </h3>
      {housemoney.length === 0 ? (
        <p className="footnote">
          Inga innehav med känd vinst än – fyll i <b>Insatt</b> (inköpsbelopp) i tabellen ovan.
        </p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Innehav</th><th>Uppgång</th><th>Sälj för att låsa insats</th><th>Kvar (free carry)</th></tr>
            </thead>
            <tbody>
              {housemoney.map((h) => (
                <tr key={h.ticker || h.name}>
                  <td>{h.name} {h.ticker && <TvLink ticker={h.ticker} />}</td>
                  <td className="flow-in">{fmtPct(h.gain)}</td>
                  <td>{fmtKr(h.sell_sek)} <span className="footnote">({Math.round(h.sell_frac * 100)}%)</span></td>
                  <td>{fmtKr(h.value - h.sell_sek)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(analysis?.candidates?.sweden?.length > 0 || analysis?.candidates?.theme?.length > 0) && (
        <>
          <h3 className="section-title">
            Kandidater från övriga vyer
            <InfoButton title="Konkreta idéer, inte bara breda ETF:er">
              För Sverige-/temadelen: bolag ur Kvalitets-screenern, momentum-signaler och de
              starkaste temana ur Rotation. <b>Idéer att bedöma, inte bevisad edge</b> – den breda
              kärnan är fortfarande basen. Använd dem för den andel du medvetet vill lägga i
              Sverige/tema. <b>Uppdragsanalys</b> (Redeye, Analyst Group m.fl.) är <b>betald av
              bolaget → positivt biased</b>; visas som narrativ, inte signal.
            </InfoButton>
          </h3>
          {analysis.candidates.sweden?.length > 0 && (
            <>
              <p className="footnote" style={{ marginBottom: 4 }}>Sverige – kvalitet + momentum:</p>
              <div className="table-wrap">
                <table>
                  <tbody>
                    {analysis.candidates.sweden.map((c) => (
                      <tr key={c.ticker}>
                        <td>
                          {c.name}
                          {c.source && <span className={`cand-src cand-src--${c.source}`}>{c.source}</span>}
                          {c.analys && (
                            <div className="cand-analys">
                              uppdragsanalys{c.analys.riktkurs ? ` · riktkurs ${c.analys.riktkurs} kr` : ''}
                              {c.analys.date ? ` (${c.analys.date})` : ''} · betald, biased
                            </div>
                          )}
                        </td>
                        <td className="mono">{c.ticker} <TvLink ticker={c.ticker} /></td>
                        <td className="flow-flat">{c.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {analysis.candidates.theme?.length > 0 && (
            <>
              <p className="footnote" style={{ marginBottom: 4, marginTop: 10 }}>Tema – starkaste ur Rotation:</p>
              <div className="table-wrap">
                <table>
                  <tbody>
                    {analysis.candidates.theme.map((c) => (
                      <tr key={c.ticker}>
                        <td>{c.name}</td>
                        <td className="mono">{c.ticker} <TvLink ticker={c.ticker} /></td>
                        <td className="flow-flat">{c.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      <p className="footnote">
        Fyll-mot-mål via inflöden – <b>inget säljs</b>. Koncentrationen späds över tid.
        Beslutsstöd, inte en signal med bevisad edge; en global indexfond är standardvalet.
        <b> Risk on</b>, house-money och exit-alarm är medvetna edge-verktyg – använd med urskiljning.
      </p>
    </section>
  )
}
