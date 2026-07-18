import { useState } from 'react'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { InfoButton } from '../components/InfoButton'
import { fmtSek, fmtPct } from '../format'

const BUCKET_LABEL = { broad: 'Bred kärna', sweden: 'Sverige', theme: 'Tematiskt', leverage: 'Hävstång' }
const TIER_ICON = { red: '🔴', amber: '🟡', unknown: '⚪', ok: '🟢' }
const TICKET_STATUS = {
  pending: { icon: '⏳', label: 'väntar på Montrose-synk' },
  landed: { icon: '✅', label: 'landade' },
  expired: { icon: '✗', label: 'aldrig bekräftad (>14 dagar)' },
}

function fmtWhen(iso) {
  if (!iso) return null
  const d = new Date(iso)
  return d.toLocaleDateString('sv-SE', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

// AI-box för fria följdfrågor på förvaltarkommentaren – på-begäran headless
// Claude (WebSearch), samma mönster som Skannerns AI-analysruta. Håller en
// egen liten historik i state (inte sparad någonstans) så flera följdfrågor
// i rad syns i tur och ordning, senaste sist.
function CommentaryAskBox() {
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
      const r = await api.commentaryAsk(q)
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
      <h3 className="section-title" style={{ marginTop: 0 }}>
        Fråga om analysen
        <InfoButton title="Följdfrågor på förvaltarkommentaren">
          <p>
            Ställ en fri fråga om kommentaren ovan eller portföljen – headless Claude svarar
            grundat i samma underlag kommentaren byggdes från, och söker vid behov (WebSearch)
            för att förklara VARFÖR något hänt.
          </p>
          <p>
            Samma "ren narrativ, aldrig signal"-disciplin som resten av appen: inget nytt
            köp/sälj-råd, bara vad datan/planen redan säger i klartext. Kan ta upp till ~2
            minuter att svara.
          </p>
        </InfoButton>
      </h3>

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
          placeholder="T.ex. varför föll Acconeer den här veckan?"
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

export function AssessmentPage() {
  const holdings = useApiData(() => api.holdings(), [])
  const exitSignals = useApiData(() => api.exitSignals(), [])
  const nextBuy = useApiData(() => api.nextBuy(), [])
  const insight = useApiData(() => api.insight(), [])
  const commentary = useApiData(() => api.commentary(), [])
  const tickets = useApiData(() => api.tradeTickets(), [])

  if (holdings.loading) return <Loading />
  if (holdings.error) return <ErrorBlock error={holdings.error} />

  const d = holdings.data
  const sellWatch = (nextBuy.data?.sell_watch ?? []).filter((s) => (s.level ?? 0) >= 1)
  const exits = (exitSignals.data?.holdings ?? []).filter((e) => e.tier !== 'ok')
  const companies = insight.data?.companies ?? []
  const heldCompanies = companies.filter((c) => c.held)
  const candidateCompanies = companies.filter((c) => !c.held)

  return (
    <section className="page">
      <div className="page-head">
        <h1>
          Bedömning
          <InfoButton title="Din portfölj i klartext">
            <p>
              Samlar det som redan finns utspritt (hink-drift, varningar, exit-alarm, säljvakt) plus
              två narrativa lager: en färsk sammanfattning per bolag (pressmeddelanden + nyheter/social
              ton, hämtat nattligt) och en veckovis förvaltarkommentar.
            </p>
            <p>
              <b>Rent sammanhang, aldrig en signal.</b> Inget här driver modellens rankningar eller
              köpplanen – det är läsvärt bakgrund, inte nytt investeringsråd.
            </p>
          </InfoButton>
        </h1>
        <p className="page-subtitle">{fmtSek(d?.total)} · {(d?.holdings ?? []).length} innehav</p>
      </div>

      {/* Förvaltarkommentar */}
      <div className="section-head"><h2>Förvaltarkommentar</h2></div>
      <div className="list-card">
        {commentary.loading && <div className="list-card__empty">Hämtar…</div>}
        {!commentary.loading && !commentary.data?.commentary && (
          <div className="list-card__empty">
            Ingen kommentar genererad än – körs veckovis på Pi:n (portfolio_commentary.py).
          </div>
        )}
        {commentary.data?.commentary && (
          <div style={{ padding: '14px 16px' }}>
            <p style={{ margin: 0, lineHeight: 1.6 }}>{commentary.data.commentary}</p>
            <p className="footnote" style={{ marginTop: 8 }}>
              {fmtWhen(commentary.data.generated_at)}
            </p>
          </div>
        )}
      </div>
      <CommentaryAskBox />

      {/* Hink-drift + varningar */}
      <div className="section-head"><h2>Hink-drift</h2></div>
      <div className="list-card">
        {(['broad', 'sweden', 'theme', 'leverage']).map((b) => {
          const cur = d?.buckets?.[b] ?? 0
          const tgt = d?.target?.[b] ?? 0
          return (
            <div key={b} className="list-row">
              <div className="list-row__main">
                <span className="list-row__ticker">{BUCKET_LABEL[b]}</span>
                <span className="list-row__sub">mål {fmtPct(tgt)}</span>
              </div>
              <div className="list-row__side">
                <span className={`list-row__num ${cur > tgt + 0.05 ? 'neg' : ''}`}>{fmtPct(cur)}</span>
              </div>
            </div>
          )
        })}
        {(d?.warnings ?? []).map((w, i) => (
          <div key={i} className="list-row" style={{ opacity: 0.8 }}>
            <div className="list-row__main"><span className="list-row__sub neg">⚠ {w}</span></div>
          </div>
        ))}
      </div>

      {/* Exit-alarm + säljvakt ihopsamlat */}
      {(exits.length > 0 || sellWatch.length > 0) && (
        <>
          <div className="section-head"><h2>Vad skaver</h2></div>
          <div className="list-card">
            {exits.map((e) => (
              <div key={`exit-${e.ticker}`} className="list-row">
                <div className="list-row__main">
                  <span className="list-row__ticker">{TIER_ICON[e.tier] ?? '⚪'} {e.name}</span>
                  <span className="list-row__sub">{e.tech_note} · {e.sector_note}</span>
                </div>
              </div>
            ))}
            {sellWatch.map((s) => (
              <div key={`sw-${s.ticker}`} className="list-row">
                <div className="list-row__main">
                  <span className="list-row__ticker">
                    {{ 1: '⚠', 2: '⚠⚠', 3: '⛔' }[s.level] ?? '⚠'} {s.name}
                  </span>
                  <span className="list-row__sub">{s.action} · {(s.reasons ?? []).join(' · ')}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Följde jag planen? */}
      {(tickets.data ?? []).length > 0 && (
        <>
          <div className="section-head">
            <h2>
              Följde jag planen?
              <InfoButton title="Skapade köpbiljetter">
                <p>
                  Varje "Skapa ticket" i Nästa köp loggas här. Vid nästa Montrose-synk kollas om
                  antalet aktier faktiskt ökade – landade den inte inom 14 dagar räknas den som
                  aldrig bekräftad i Montrose-appen.
                </p>
              </InfoButton>
            </h2>
          </div>
          <div className="list-card">
            {tickets.data.map((t, i) => {
              const st = TICKET_STATUS[t.status] ?? TICKET_STATUS.pending
              return (
                <div key={i} className="list-row">
                  <div className="list-row__main">
                    <span className="list-row__ticker">{st.icon} {t.ticker}</span>
                    <span className="list-row__sub">{fmtWhen(t.created_at)} · {st.label}</span>
                  </div>
                  <div className="list-row__side">
                    <span className="list-row__num">{fmtSek(t.kr)}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}

      {/* Narrativ per innehav */}
      <div className="section-head">
        <h2>
          Innehaven i klartext
          {insight.data?.generated_at && (
            <span className="footnote" style={{ marginLeft: 8, fontWeight: 400 }}>
              uppdaterad {fmtWhen(insight.data.generated_at)}
            </span>
          )}
        </h2>
      </div>
      <div className="list-card">
        {insight.loading && <div className="list-card__empty">Hämtar…</div>}
        {!insight.loading && heldCompanies.length === 0 && (
          <div className="list-card__empty">
            Ingen narrativ rapport genererad än – körs nattligt på Pi:n (insight_report.py).
          </div>
        )}
        {heldCompanies.map((c) => (
          <div key={c.ticker} className="list-row" style={{ alignItems: 'flex-start' }}>
            <div className="list-row__main">
              <span className="list-row__ticker">{c.name}</span>
              <span className="list-row__sub">{c.summary}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Narrativ per kandidat (modellens topplista, inte ägda) */}
      {candidateCompanies.length > 0 && (
        <>
          <div className="section-head"><h2>Modellens topplista i klartext</h2></div>
          <div className="list-card">
            {candidateCompanies.map((c) => (
              <div key={c.ticker} className="list-row" style={{ alignItems: 'flex-start' }}>
                <div className="list-row__main">
                  <span className="list-row__ticker">{c.name}</span>
                  <span className="list-row__sub">{c.summary}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
