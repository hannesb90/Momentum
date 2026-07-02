import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { InfoButton } from '../components/InfoButton'
import { TvLink } from '../components/TvLink'

const COLS = [
  { key: 'quant_score', label: 'Betyg' },
  { key: 'quality', label: 'Kval' },
  { key: 'growth', label: 'Tillväxt' },
  { key: 'safety', label: 'Trygghet' },
  { key: 'value', label: 'Värde' },
]

// Token-fri kvant-lista: hård finansdata rankad mot universumet (quant_screener).
export function QuantPage() {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  const [sort, setSort] = useState('quant_score')
  const [q, setQ] = useState('')

  useEffect(() => {
    api.quant().then(setRows).catch(setError)
  }, [])

  const view = useMemo(() => {
    if (!rows) return []
    const f = q.trim().toLowerCase()
    let r = rows
    if (f) {
      r = r.filter(
        (x) => String(x.name).toLowerCase().includes(f) || String(x.ticker).toLowerCase().includes(f),
      )
    }
    return [...r].sort((a, b) => (Number(b[sort]) || 0) - (Number(a[sort]) || 0))
  }, [rows, sort, q])

  if (error) return <ErrorBlock error={error} />
  if (!rows) return <Loading />

  return (
    <section className="page">
      <div className="page-head">
        <h1>
          Kvant-betyg
          <InfoButton title="Token-fritt kvant-betyg (hård data)">
            <p>
              0–100 per bolag ur hård finansdata (TradingViews scanner, gratis): kvalitet
              (marginaler, ROE/ROIC, 40%), tillväxt (omsättning, 20%), trygghet
              (skuld/likviditet, 15%), värdering (P/S, EV/EBITDA, 25%) – rankat mot hela
              universumet. <b>Ingen Claude-token.</b> Pre-revenue-skal och Health Care exkluderade.
              Klicka en kolumn för att sortera.
            </p>
          </InfoButton>
        </h1>
        <p className="page-subtitle">{rows.length} bolag · rankade på hård data</p>
      </div>

      {rows.length === 0 ? (
        <p className="footnote">
          Ingen kvant-lista än – kör <code>quant_screener.py fetch</code> + <code>score</code> på Pi:n.
        </p>
      ) : (
        <>
          <input
            className="pf-in" style={{ maxWidth: 280, marginBottom: 12 }}
            placeholder="Sök namn eller ticker…" value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Bolag</th>
                  {COLS.map((c) => (
                    <th key={c.key} style={{ cursor: 'pointer' }} onClick={() => setSort(c.key)}>
                      {c.label}{sort === c.key ? ' ▾' : ''}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {view.slice(0, 200).map((r) => (
                  <tr key={r.ticker}>
                    <td className="ticker-cell">
                      <span className="ticker-link__name">{r.name}</span>
                      <span className="ticker-link__ticker">{r.ticker} <TvLink ticker={r.ticker} /></span>
                    </td>
                    <td className="qcomposite">{Math.round(r.quant_score)}</td>
                    <td>{Math.round(r.quality)}</td>
                    <td>{Math.round(r.growth)}</td>
                    <td>{Math.round(r.safety)}</td>
                    <td>{Math.round(r.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {view.length > 200 && <p className="footnote">Visar topp 200 av {view.length}.</p>}
        </>
      )}
    </section>
  )
}
