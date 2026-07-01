import { useEffect, useState } from 'react'
import { api } from '../api'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { InfoButton } from '../components/InfoButton'

const BUCKETS = [
  { value: 'broad', label: 'Bred kärna (World/US/EM)' },
  { value: 'sweden', label: 'Sverige' },
  { value: 'theme', label: 'Tematiskt' },
  { value: 'leverage', label: 'Hävstång' },
]
const BUCKET_LABEL = Object.fromEntries(BUCKETS.map((b) => [b.value, b.label]))
const fmtKr = (v) => (v == null ? '–' : `${Math.round(v).toLocaleString('sv-SE')} kr`)

export function HoldingsPage() {
  const [holdings, setHoldings] = useState([])
  const [analysis, setAnalysis] = useState(null)
  const [amount, setAmount] = useState(10000)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.portfolio(amount)
      .then((d) => {
        setAnalysis(d)
        setHoldings((d.holdings ?? []).map((h) => ({ ...h })))
      })
      .catch(setError)
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function refreshAmount(a) {
    setAmount(a)
    if (!dirty) api.portfolio(a).then(setAnalysis).catch(() => {})
  }
  function edit(i, field, val) {
    setHoldings((hs) => hs.map((h, j) => (j === i ? { ...h, [field]: val } : h)))
    setDirty(true)
  }
  function addRow() {
    setHoldings((hs) => [...hs, { name: '', value: 0, bucket: 'broad' }])
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
        .map((h) => ({ name: (h.name || '').trim(), value: Number(h.value) || 0, bucket: h.bucket }))
        .filter((h) => h.name && h.value > 0)
      const d = await api.savePortfolio(clean, amount)
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

      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Innehav</th><th>Värde (kr)</th><th>Hink</th><th></th></tr>
          </thead>
          <tbody>
            {holdings.map((h, i) => (
              <tr key={i}>
                <td>
                  <input className="pf-in" value={h.name}
                    onChange={(e) => edit(i, 'name', e.target.value)} placeholder="Namn/ticker" />
                </td>
                <td>
                  <input className="pf-in pf-num" type="number" min="0" value={h.value}
                    onChange={(e) => edit(i, 'value', e.target.value)} />
                </td>
                <td>
                  <select className="pf-in" value={h.bucket} onChange={(e) => edit(i, 'bucket', e.target.value)}>
                    {BUCKETS.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}
                  </select>
                </td>
                <td><button className="pf-del" onClick={() => del(i)} title="Ta bort">✕</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pf-actions">
        <button className="pf-btn" onClick={addRow}>+ Lägg till innehav</button>
        <button className="pf-btn pf-btn--primary" onClick={save} disabled={saving || !dirty}>
          {saving ? 'Sparar…' : dirty ? 'Spara' : 'Sparat'}
        </button>
      </div>

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
          {analysis.warnings.map((w, i) => <span className="qflag" key={i}>⚠ {w}</span>)}
        </div>
      )}

      <h3 className="section-title">Nytt kapital – vart det ska in</h3>
      <div className="newcap__input">
        <label>Månadsbelopp</label>
        <input type="number" min="0" step="500" value={amount}
          onChange={(e) => refreshAmount(Math.max(0, Number(e.target.value) || 0))} />
        <span>kr</span>
        {dirty && <span className="pf-hint">(spara för uppdaterad plan)</span>}
      </div>
      {Object.keys(plan).length === 0 ? (
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
      {Object.keys(broadEtfs).length > 0 && (
        <>
          <p className="footnote" style={{ marginBottom: 4 }}>Bred kärna – dela lika över:</p>
          <div className="table-wrap">
            <table>
              <tbody>
                {Object.entries(broadEtfs).map(([lbl, e]) => (
                  <tr key={lbl}>
                    <td>{lbl}</td>
                    <td className="mono">{e.ticker}</td>
                    <td>{fmtKr(e.kr)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
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
                        <td className="mono">{c.ticker}</td>
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
                        <td className="mono">{c.ticker}</td>
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
      </p>
    </section>
  )
}
