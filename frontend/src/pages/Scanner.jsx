import { useState, useEffect } from 'react'
import { api } from '../api'
import { InfoButton } from '../components/InfoButton'
import { fmtPct, fmtNum, fmtSek } from '../format'

const GROUPS = [
  { title: 'Grunduppgifter', fields: ['name', 'price', 'currency', 'fx_rate'] },
  { title: 'Resultat & balans (Mkr, bolagets egen valuta)',
    fields: ['revenue', 'revenue_prior', 'net_profit', 'equity', 'liabilities',
             'depreciation_amortization', 'shares_outstanding', 'period'] },
  { title: 'Manuella betyg (bara om bolaget inte redan är spårat hos oss)',
    fields: ['quality', 'quant', 'prob_up', 'research'] },
]

const PERIOD_OPTIONS = ['', 'Q1', 'Q2', 'Q3', 'Q4', 'H1', '9M', 'Helår']
const MODEL_LABELS = { balanced: 'Balanserad', buffett: 'Buffett', momentum: 'Momentum' }
const BUCKET_LABEL = { broad: 'Bred kärna', sweden: 'Sverige', theme: 'Tematiskt', leverage: 'Hävstång' }

export function ScannerPage() {
  const [fieldMeta, setFieldMeta] = useState(null)
  const [universe, setUniverse] = useState([])
  // Sök-och-välj (namn ELLER ticker), samma mönster som Innehav-sidans
  // "lägg till innehav"-sök. tickerSel = valt kandidat ur universumet;
  // saknas en träff (t.ex. en utländsk aktie vi inte spårar) kan man ändå
  // fortsätta med den fritt skrivna texten som ticker – Skannern stödjer
  // uttryckligen bolag utanför vårt universum.
  const [tickerSel, setTickerSel] = useState(null)
  const [tickerQuery, setTickerQuery] = useState('')
  const [values, setValues] = useState({})
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.scannerFields()
      .then((d) => setFieldMeta(Object.fromEntries((d.fields ?? []).map((f) => [f.key, f]))))
      .catch(() => {})
    api.universe().then(setUniverse).catch(() => {})
  }, [])

  const q = tickerQuery.trim().toLowerCase()
  const matches = tickerSel || q.length < 2 ? [] : universe
    .filter((u) => u.name.toLowerCase().includes(q) || u.ticker.toLowerCase().includes(q))
    .slice(0, 8)

  function selectTicker(u) {
    setTickerSel(u)
    setTickerQuery('')
    if (u.name && !values.name) setField('name', u.name)
  }

  function clearTicker() {
    setTickerSel(null)
    setTickerQuery('')
  }

  function setField(k, v) {
    setValues((prev) => ({ ...prev, [k]: v }))
  }

  async function runScan(e) {
    e.preventDefault()
    const ticker = (tickerSel?.ticker || tickerQuery).trim().toUpperCase()
    if (!ticker || loading) return
    setLoading(true)
    setError(null)
    try {
      const overrides = Object.fromEntries(
        Object.entries(values).filter(([, v]) => v !== '' && v != null),
      )
      const r = await api.scannerScan(ticker, overrides)
      setResult(r)
    } catch (err) {
      setError(err.message)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="page">
      <div className="section-head">
        <h2>
          Skanner
          <InfoButton title="Manuell scenario-skanner">
            <p>
              Testa VILKEN aktie som helst – även en vi inte redan spårar. Ange tickern och
              fyll i det som saknas manuellt; är aktien redan spårad hos oss förfylls resten
              automatiskt (märkt "cachad" i fältlistan nedan). Inget nätanrop görs och inget
              sparas – det här är ett engångs "vad om"-svar, inte ett permanent tillstånd.
            </p>
            <p>
              Ange belopp i Mkr, i bolagets EGNA rapportvaluta. Rapporterar bolaget inte i
              SEK, ange valutakod + fx_rate (SEK per enhet, t.ex. 10.5 för USD) SJÄLV – vi
              gissar aldrig en växelkurs, det hade kunnat ge en tyst 8-10x felräkning.
            </p>
          </InfoButton>
        </h2>
      </div>

      <form className="scan-form" onSubmit={runScan}>
        <div className="scan-form__field scan-form__field--ticker">
          <span>Aktie</span>
          {tickerSel ? (
            <div className="h-add__sel">
              <b>{tickerSel.name}</b>
              <span className="mono">{tickerSel.ticker}</span>
              <button type="button" className="pf-del" title="Byt" onClick={clearTicker}>✕</button>
            </div>
          ) : (
            <div className="pf-search">
              <input
                className="pf-in pf-search__input" type="text"
                placeholder="Sök namn eller ticker – t.ex. Volvo, NVDA.US, AAA.ST…"
                value={tickerQuery}
                onChange={(e) => setTickerQuery(e.target.value)}
              />
              {matches.length > 0 && (
                <div className="pf-search__drop">
                  {matches.map((u) => (
                    <button key={u.ticker} type="button" className="pf-search__item" onClick={() => selectTicker(u)}>
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
                  <button
                    type="button" className="pf-search__item"
                    onClick={() => selectTicker({ ticker: tickerQuery.trim().toUpperCase(), name: tickerQuery.trim() })}
                  >
                    <span className="pf-search__name">Fortsätt med "{tickerQuery.trim()}" som ticker</span>
                    <span className="pf-search__meta"><span className="mono">utanför vårt universum</span></span>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
        {GROUPS.map((g) => (
          <fieldset key={g.title} className="scan-form__group">
            <legend>{g.title}</legend>
            <div className="scan-form__grid">
              {g.fields.map((k) => {
                const meta = fieldMeta?.[k]
                return (
                  <label key={k} className="scan-form__field">
                    <span>{k}</span>
                    {k === 'period' ? (
                      <select className="pf-in" value={values[k] ?? ''}
                              onChange={(e) => setField(k, e.target.value)}>
                        {PERIOD_OPTIONS.map((p) => (
                          <option key={p || 'unknown'} value={p}>{p || '(okänd)'}</option>
                        ))}
                      </select>
                    ) : meta?.type === 'bool' ? (
                      <input
                        type="checkbox" checked={!!values[k]}
                        onChange={(e) => setField(k, e.target.checked ? 'true' : '')}
                      />
                    ) : (
                      <input
                        className={`pf-in${meta?.type === 'number' ? ' pf-num' : ''}`}
                        type={meta?.type === 'number' ? 'number' : 'text'}
                        step={meta?.type === 'number' ? 'any' : undefined}
                        value={values[k] ?? ''}
                        onChange={(e) => setField(k, e.target.value)}
                      />
                    )}
                    {meta?.help && <span className="scan-form__hint">{meta.help}</span>}
                  </label>
                )
              })}
            </div>
          </fieldset>
        ))}
        <button className="btn btn--primary" type="submit" disabled={loading}>
          {loading ? 'Skannar…' : 'Skanna'}
        </button>
      </form>

      {error && <div className="status-block status-block--error">Kunde inte skanna: {error}</div>}
      {result && <ScanResult result={result} />}
    </section>
  )
}

function ScanResult({ result }) {
  const vm = result.value_metrics
  const anyExcludedButScored = Object.values(result.models)
    .some((mo) => mo.excluded_reason && mo.score != null)

  return (
    <div className="scan-result">
      <h3 className="section-title">{result.ticker} – {result.name}</h3>

      {result.warnings?.length > 0 && (
        <div className="list-card" style={{ marginBottom: 12 }}>
          {result.warnings.map((w, i) => (
            <div key={i} className="list-row" style={{ opacity: 0.85 }}>
              <div className="list-row__main"><span className="list-row__sub">⚠ {w}</span></div>
            </div>
          ))}
        </div>
      )}

      <div className="tile-grid">
        <div className="tile">
          <div className="tile__label">ROE</div>
          <div className={`tile__value ${vm.meets_roe_bar ? 'tile__value--good' : ''}`}>
            {vm.roe != null ? fmtPct(vm.roe) : '–'}
          </div>
        </div>
        <div className="tile">
          <div className="tile__label">Skuld/EK</div>
          <div className={`tile__value ${vm.debt_equity != null && !vm.meets_debt_bar ? 'tile__value--bad' : ''}`}>
            {vm.debt_equity != null ? fmtNum(vm.debt_equity) : '–'}
          </div>
        </div>
        <div className="tile">
          <div className="tile__label">Owner earnings</div>
          <div className="tile__value">
            {vm.owner_earnings_msek != null ? fmtSek(vm.owner_earnings_msek * 1e6) : '–'}
          </div>
        </div>
        <div className="tile">
          <div className="tile__label">Multipel · zon</div>
          <div className="tile__value">
            {vm.mult != null ? `${fmtNum(vm.mult)}x` : '–'}{' '}
            <span style={{ fontSize: '0.55em', opacity: 0.7 }}>[{vm.zone}]</span>
          </div>
        </div>
      </div>

      <p className="footnote">
        Klarar ROE-bar: <b className={vm.meets_roe_bar ? 'pos' : 'neg'}>{vm.meets_roe_bar ? 'Ja' : 'Nej'}</b>
        {' · '}Klarar skuld-bar: <b className={vm.meets_debt_bar ? 'pos' : 'neg'}>{vm.meets_debt_bar ? 'Ja' : 'Nej'}</b>
        {result.value_score != null && <> · value_score {fmtNum(result.value_score, 1)}</>}
        {' · '}Period: {vm.period || 'okänd'} (årsfaktor {vm.annual_factor})
      </p>

      <h3 className="section-title" style={{ marginTop: 16 }}>Modeller</h3>
      <div className="list-card">
        {Object.entries(result.models).map(([m, mo]) => (
          <div key={m} className="list-row">
            <div className="list-row__main">
              <span className="list-row__ticker">{MODEL_LABELS[m] ?? m}</span>
              <span className="list-row__sub">
                {mo.why || mo.excluded_reason || 'inget fundament-betyg angivet'}
              </span>
            </div>
            <div className="list-row__side">
              <span className="list-row__num">{mo.score != null ? fmtNum(mo.score, 3) : '—'}</span>
            </div>
          </div>
        ))}
      </div>
      {anyExcludedButScored && (
        <p className="footnote">
          "Skulle uteslutas" = poängen visas ändå (illustrativt), men bolaget hade INTE
          kvalificerat sig i den riktiga Buffett-grinden i Nästa köp.
        </p>
      )}

      <details className="alloc-editor" style={{ marginTop: 12 }}>
        <summary>Fält som användes (källa)</summary>
        <div style={{ padding: '8px 2px' }}>
          {Object.entries(result.fields)
            .filter(([, v]) => v.value != null)
            .map(([k, v]) => (
              <div key={k} className="list-row" style={{ padding: '4px 0' }}>
                <div className="list-row__main">
                  <span className="list-row__sub">{k}: {String(v.value)}</span>
                </div>
                <div className="list-row__side">
                  <span className="footnote" style={{ margin: 0 }}>{v.source}</span>
                </div>
              </div>
            ))}
        </div>
      </details>
    </div>
  )
}
