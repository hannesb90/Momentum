import { useState } from 'react'
import { api } from '../api'
import { useApiData } from '../useApiData'
import { Loading, ErrorBlock } from '../components/StatusBlock'
import { EmptyState } from '../components/EmptyState'
import { InfoButton } from '../components/InfoButton'
import { fmtPct } from '../format'

// Volymbaserat flöde (Chaikin Money Flow + relativ volym), token-fritt.
// Faller tillbaka på rank-förändring om volymdata saknas.
function flowLabel(r) {
  const cmf = r.cmf
  const rc = Number(r.rank_change) || 0
  if (cmf == null || Number.isNaN(Number(cmf))) {
    if (rc >= 2) return { text: '↑ in (rank)', cls: 'flow-in' }
    if (rc <= -2) return { text: '↓ ut (rank)', cls: 'flow-out' }
    return { text: '→ stabil', cls: 'flow-flat' }
  }
  const c = Number(cmf)
  const surge = Number(r.relvol) >= 1.3 ? ' +vol' : ''
  if (c >= 0.1) return { text: `↑↑ inflöde${surge}`, cls: 'flow-in' }
  if (c >= 0.03) return { text: `↑ inflöde${surge}`, cls: 'flow-in' }
  if (c <= -0.1) return { text: '↓↓ utflöde', cls: 'flow-out' }
  if (c <= -0.03) return { text: '↓ utflöde', cls: 'flow-out' }
  return { text: '→ stabil', cls: 'flow-flat' }
}

function Stat({ label, value, tone }) {
  return (
    <div className={`macro-stat${tone ? ` macro-${tone}` : ''}`}>
      <div className="macro-stat__val">{value}</div>
      <div className="macro-stat__label">{label}</div>
    </div>
  )
}

function NewCapital({ alloc, riskOn, macro }) {
  const [amount, setAmount] = useState(10000)
  const kr = (w) => Math.round(w * amount)
  const fmtKr = (v) => v.toLocaleString('sv-SE')
  const vixStress = macro && macro.vix != null && macro.vix >= 28
  return (
    <div className="newcap">
      <div className="newcap__input">
        <label>Månadsbelopp</label>
        <input
          type="number"
          min="0"
          step="500"
          value={amount}
          onChange={(e) => setAmount(Math.max(0, Number(e.target.value) || 0))}
        />
        <span>kr</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Bred byggsten</th><th>ETF</th><th>Andel</th><th>Belopp</th></tr>
          </thead>
          <tbody>
            {alloc.map((a) => (
              <tr key={a.etf}>
                <td>{a.sleeve}</td>
                <td className="mono">{a.etf}</td>
                <td>{(a.weight * 100).toFixed(0)}%</td>
                <td>{fmtKr(kr(a.weight))} kr</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="footnote">
        Bred fördelning över regioner med en <b>mild</b> lutning mot det som trendar (50%
        likavikt + 50% momentum) – <b>alltid fullinvesterat, ingen koncentration, inga
        teman, ingen hävstång</b>. Det är den enda ansats som överlevt din egen data.
        {' '}För månadssparande: investera oavsett regim (tid i marknaden slår timing).
        {!riskOn || vixStress ? (
          <> <b>Nu är regimen svag</b> – för en STOR engångssumma kan du fasa in den över
          några månader, men fortsätt månadsspara som vanligt.</>
        ) : null}
      </p>
    </div>
  )
}

function MacroPanel({ m }) {
  const pct = (v) => (v == null ? '–' : `${(v * 100).toFixed(1)}%`)
  const curve = m.yield_curve_10y_3m
  const vix = m.vix
  const credit = m.credit_hyg_vs_ief_13w
  return (
    <div className="macro-grid">
      {curve != null && (
        <Stat label="Räntekurva 10y–3m" value={`${curve > 0 ? '+' : ''}${curve}`}
          tone={curve < 0 ? 'bad' : 'good'} />
      )}
      {vix != null && (
        <Stat label={`VIX${m.vix_pctile_1y != null ? ` (p${Math.round(m.vix_pctile_1y * 100)})` : ''}`}
          value={vix.toFixed(1)} tone={vix >= 28 ? 'bad' : vix >= 20 ? 'warn' : 'good'} />
      )}
      {credit != null && (
        <Stat label="Kredit HYG–IEF 13v" value={pct(credit)} tone={credit < 0 ? 'bad' : 'good'} />
      )}
      {m.usd_above_40w != null && (
        <Stat label="USD-trend" value={m.usd_above_40w ? '↑ flight' : 'neutral'}
          tone={m.usd_above_40w ? 'warn' : ''} />
      )}
      {m.copper_gold_13w != null && (
        <Stat label="Koppar–guld 13v" value={pct(m.copper_gold_13w)}
          tone={m.copper_gold_13w >= 0 ? 'good' : 'warn'} />
      )}
      {m.gold_13w != null && <Stat label="Guld 13v" value={pct(m.gold_13w)} />}
      {m.oil_13w != null && <Stat label="Olja 13v" value={pct(m.oil_13w)} />}
    </div>
  )
}

export function RotationPage() {
  const rot = useApiData(() => api.rotation(), [])
  const thesis = useApiData(() => api.thesis(), [])

  if (rot.loading) return <Loading />
  if (rot.error) return <ErrorBlock error={rot.error} />

  const meta = rot.data?.meta
  const rows = rot.data?.rows ?? []
  const ideas = thesis.data ?? []

  if (rows.length === 0) {
    return (
      <section className="page">
        <div className="page-head"><h1>Rotation</h1></div>
        <EmptyState
          title="Ingen rotationssignal ännu"
          hint="Kör 'python etf_rotation.py signal' (och 'etf_thesis.py next') på Pi:n för att generera D-spårets data."
        />
      </section>
    )
  }

  const riskOn = meta?.risk_on
  return (
    <section className="page">
      <div className="page-head">
        <h1>
          Rotation & Trend
          <InfoButton title="ETF/sektor-rotation (D-spåret)">
            <p>
              Roterar mellan globala sektor-/tema-ETF:er på deras egen momentum (relativ),
              men bara när de har egen positiv trend (absolut) – annars defensivt. Ett
              bull/björn-filter går risk-off när breda marknaden bryter sin långa trend.
            </p>
            <p>
              <b>Nästa-trend-idéerna</b> kommer från ett kausalt "världsträd" (AI → kraft →
              kärnkraft osv). Det är <b>hypoteser, inte signaler</b> – en idégenerator du
              bedömer, inte ett bevisat edge. Bekräfta mot flödet till vänster.
            </p>
          </InfoButton>
        </h1>
        {meta && (
          <p className="page-subtitle">
            {meta.date} · håller {meta.held?.length ?? 0} av top-{meta.top_k}
            {meta.defensive_slots > 0 ? ` · ${meta.defensive_slots} defensivt (${meta.defensive})` : ''}
          </p>
        )}
      </div>

      {meta && (
        <div className={`regime-banner ${riskOn ? 'regime-bull' : 'regime-bear'}`}>
          <span className="regime-dot" />
          <div>
            <div className="regime-title">{riskOn ? 'BULL – risk-on' : 'BJÖRN – risk-off'}</div>
            <div className="regime-sub">
              {riskOn
                ? 'Breda marknaden över sin långa trend och ingen makro-stress – rotation aktiv.'
                : `Risk-off – hela boken defensivt (${meta.defensive}). Trend bruten och/eller makro-stress (VIX + kreditspread).`}
            </div>
          </div>
        </div>
      )}

      {meta?.allocation?.length > 0 && (
        <>
          <h3 className="section-title">
            Nytt kapital – vart det ska in
            <InfoButton title="Var ska månadssparandet in?">
              <p>
                Datan visar att koncentrerad rotation, timing och hävstång alla förlorar mot
                att bara vara bred och alltid investerad. Så för nytt kapital föreslås en
                <b> bred fördelning över regioner</b> med en mild lutning mot styrka.
              </p>
              <p>
                <b>Detta är beslutsstöd, inte en signal med bevisad edge.</b> En global/US
                indexfond är fortfarande det ärliga standardvalet.
              </p>
            </InfoButton>
          </h3>
          <NewCapital alloc={meta.allocation} riskOn={riskOn} macro={meta.macro} />
        </>
      )}

      {meta?.macro && (
        <>
          <h3 className="section-title">
            Makroläge
            <InfoButton title="Bakgrundsdata (token-fritt)">
              Fria marknadsdata (räntor, VIX, kredit, USD, råvaror) som göder stress-regimen.
              Regimen tvingas risk-off när VIX är i stress OCH kreditspreadar vidgas – även
              om trenden ännu håller. Recessionskurvan visas som kontext (slår inte av ensam).
            </InfoButton>
          </h3>
          <MacroPanel m={meta.macro} />
        </>
      )}

      <h3 className="section-title">
        Heta sektorer & flöde
        <InfoButton title="Varför skiljer sig detta från Sektorer-vyn?">
          <p>
            Den här vyn rankar <b>ETF:ens egen kurs</b> (europeisk/global) på 6–12 mån (26/52v),
            och sektorerna konkurrerar mot hela poolen inkl. teman och regioner.
          </p>
          <p>
            <b>Sektorer</b>-vyn mäter i stället <b>svenska aktiers</b> momentum per sektor, även
            kortsiktigt (4–13v). Därför kan en sektor ligga högt där men lågt här – de svarar på
            olika frågor: "hur går svenska sektor-aktier" vs "vilken ETF ska jag hålla".
          </p>
        </InfoButton>
      </h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Sektor / tema</th>
              <th>ETF</th>
              <th>
                Rel. mom
                <InfoButton title="Relativ momentum">
                  Sammanvägd 6–12 mån (26/52v) prisavkastning för ETF:en själv. Den relativa
                  styrkan som avgör rankningen – de starkaste hålls.
                </InfoButton>
              </th>
              <th>
                Abs 52v
                <InfoButton title="Absolut momentum (52v)">
                  ETF:ens egen 52-veckorsavkastning. Absolut-filtret: är den under tröskeln (≈0)
                  hålls sektorn inte även om den rankas högt – slotten går defensivt.
                </InfoButton>
              </th>
              <th>
                Flöde (volym)
                <InfoButton title="Kapitalflöde ur pris + volym (token-fritt)">
                  <p>
                    Chaikin Money Flow (13v): väger var i veckans spann stängningen sker gånger
                    volymen → <b>ackumulation (kapital in)</b> vs distribution (ut). "+vol" = relativ
                    volym-spik (senaste 4v mot 26v-snitt) – kapitalet rusar in.
                  </p>
                  <p>
                    Byggt enbart på dagsfärsk EOD-data, inga tokens/NLP. Faller tillbaka på
                    rank-förändring om volymdata saknas för ETF:en.
                  </p>
                </InfoButton>
              </th>
              <th>
                Global bredd
                <InfoButton title="Global sektor-bredd (bekräftelse)">
                  Hur står sig sektorn i BÅDE Europa och USA (EU- + US-sektor-ETF). "2/2 ↑" =
                  trenden bekräftas globalt (starkare case); "1/2" = splittrat, en region bär.
                  Rankningen styrs av ETF:ens egen kurs – detta är ett bekräftelse-lager. Gäller
                  bara GICS-sektorer, inte teman/regioner.
                </InfoButton>
              </th>
              <th>
                Håll
                <InfoButton title="Håll">
                  ★ = ingår i portföljen nu (topp-K med positiv absolut trend, i bull-regim).
                </InfoButton>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const f = flowLabel(r)
              return (
                <tr key={r.etf} className={r.hold ? 'row-held' : ''}>
                  <td>{r.rank}</td>
                  <td>{r.sector}</td>
                  <td className="mono">{r.etf}</td>
                  <td>{fmtPct(r.rel_mom)}</td>
                  <td>{fmtPct(r.abs_mom)}</td>
                  <td className={f.cls}>{f.text}</td>
                  <td>{
                    r.breadth_total
                      ? (() => {
                          const up = Number(r.breadth_up), tot = Number(r.breadth_total)
                          const cls = up === tot ? 'flow-in' : up === 0 ? 'flow-out' : 'flow-flat'
                          return <span className={cls}>{up}/{tot} {fmtPct(r.breadth_mom, 0)}</span>
                        })()
                      : <span className="flow-flat">—</span>
                  }</td>
                  <td>{r.hold ? '★' : ''}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <h3 className="section-title">
        Nästa-trend – idéer ur världsträdet
        <InfoButton title="Hypoteser, inte signaler">
          Kausala kedjor från det som är hett nu till vad som kan komma härnäst. LLM-byggt →
          look-ahead → EJ backtestbart. Använd som uppslag, bekräfta mot flödet ovan.
        </InfoButton>
      </h3>
      {ideas.length === 0 ? (
        <EmptyState title="Inga trend-idéer ännu" hint="Kör 'python etf_thesis.py next' på Pi:n." />
      ) : (
        <div className="idea-list">
          {ideas.map((i) => (
            <div className="idea" key={`${i.rank}-${i.node}`}>
              <div className="idea-head">
                <span className="idea-node">{i.node}</span>
                {i.etf && <span className="idea-etf mono">{i.etf}</span>}
                {Number(i.headwind) ? <span className="idea-hw">motvind</span> : null}
                <span className="idea-score">{Number(i.score).toFixed(2)}</span>
              </div>
              <div className="idea-chain">{i.chain}</div>
            </div>
          ))}
        </div>
      )}
      <p className="footnote">
        Rotationen (vänster) är mekanisk och backtestbar. Trend-idéerna (höger) är en
        diskretionär idégenerator – inget bevisat edge. Guldkornet: en idé som ännu inte är
        het men börjar få "kapital in" i flödet.
      </p>
    </section>
  )
}
