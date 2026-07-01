import { useEffect, useState } from 'react'
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
  const [amount, setAmount] = useState(10000)
  const [riskOn, setRiskOn] = useState(false)
  const [sizeAmt, setSizeAmt] = useState(10000)
  const [sizeN, setSizeN] = useState(4)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.holdings(amount)
      .then((d) => {
        setAnalysis(d)
        setHoldings((d.holdings ?? []).map((h) => ({ ...h })))
      })
      .catch(setError)
      .finally(() => setLoading(false))
    api.exitSignals().then(setExit).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function refreshAmount(a) {
    setAmount(a)
    if (!dirty) api.holdings(a).then(setAnalysis).catch(() => {})
  }
  function edit(i, field, val) {
    setHoldings((hs) => hs.map((h, j) => (j === i ? { ...h, [field]: val } : h)))
    setDirty(true)
  }
  function addRow() {
    setHoldings((hs) => [...hs, { name: '', value: 0, bucket: 'broad', ticker: '', cost: '' }])
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
        }))
        .filter((h) => h.name && h.value > 0)
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

  return (
    <section className="page">
      <div className="page-head">
        <h1>
          Min portfölj
          <InfoButton title="Portfölj-medveten planering">
            <p>
              Lägg in dina innehav manuellt (Montrose saknar API). Appen klassar dem per hink,
              jämför mot en diversifierad mål-fördelning och riktar <b>nytt kapital</b> mot det
              du är underviktad i – fyll-mot-mål via inflöden, ingen försäljning.
            </p>
          </InfoButton>
        </h1>
        <p className="page-subtitle">{fmtKr(total)} · {holdings.length} innehav</p>
      </div>

      {/* ── Exit-alarm överst: "END THIS NOW" ─────────────────────────────── */}
      {alarms.length > 0 && (
        <div className="exit-panel">
          <h3 className="section-title" style={{ marginBottom: 8 }}>
            Exit-alarm
            <InfoButton title="När något bör bort">
              <b>Rött (end this now)</b> = sektorn är svag <b>och</b> kursen är tekniskt brutet
              (under 40-veckors glidande medel med fallande momentum). <b>Gult</b> = en av de två.
              Ett larm, inte en order – bekräfta själv. Kräver att skanningen körts
              (<code>portfolio.py exitscan</code> på Pi:n).
            </InfoButton>
          </h3>
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
        </div>
      )}
      {exit?.generated && (
        <p className="footnote" style={{ marginTop: -4 }}>
          Exit-skanning: {String(exit.generated).slice(0, 16).replace('T', ' ')}
          {alarms.length === 0 && ' · inga larm just nu'}
        </p>
      )}

      <div className="table-wrap pf-holdings">
        <table>
          <thead>
            <tr><th>Innehav</th><th>Ticker</th><th>Värde</th><th>Insatt</th><th>Hink</th><th></th></tr>
          </thead>
          <tbody>
            {holdings.map((h, i) => {
              const t = tierOf(h)
              const rowCls = t && (t.tier === 'red' || t.tier === 'amber') ? `exit-row-${t.tier}` : ''
              return (
                <tr key={i} className={rowCls} title={t ? `${TIER[t.tier]?.label} · ${t.tech_note}` : undefined}>
                  <td>
                    <input className="pf-in" value={h.name}
                      onChange={(e) => edit(i, 'name', e.target.value)} placeholder="Namn" />
                  </td>
                  <td>
                    <input className="pf-in pf-tk" value={h.ticker || ''}
                      onChange={(e) => edit(i, 'ticker', e.target.value)} placeholder="auto" />
                  </td>
                  <td>
                    <input className="pf-in pf-num" type="number" min="0" value={h.value}
                      onChange={(e) => edit(i, 'value', e.target.value)} />
                  </td>
                  <td>
                    <input className="pf-in pf-num" type="number" min="0" value={h.cost ?? ''}
                      onChange={(e) => edit(i, 'cost', e.target.value)} placeholder="–" />
                  </td>
                  <td>
                    <select className="pf-in" value={h.bucket} onChange={(e) => edit(i, 'bucket', e.target.value)}>
                      {BUCKETS.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}
                    </select>
                  </td>
                  <td><button className="pf-del" onClick={() => del(i)} title="Ta bort">✕</button></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="pf-actions">
        <button className="pf-btn" onClick={addRow}>+ Lägg till innehav</button>
        <button className="pf-btn pf-btn--primary" onClick={save} disabled={saving || !dirty}>
          {saving ? 'Sparar…' : dirty ? 'Spara' : 'Sparat'}
        </button>
      </div>
      <p className="footnote">
        <b>Ticker</b> fylls i automatiskt från namnet när du sparar (går att skriva över).
        <b> Insatt</b> = ditt inköpsbelopp – behövs för house-money nedan.
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
