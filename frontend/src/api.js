const BASE = import.meta.env.VITE_API_BASE ?? '/api'

// Aktivt segment (storbolag/småbolag). Sätts av segment-toggeln och bifogas
// AUTOMATISKT på varje API-anrop, så sidorna behöver inte känna till segment.
let currentSegment = 'large'
export function setApiSegment(s) {
  if (s) currentSegment = s
}

async function getJson(path) {
  // Endpoints kan pinna segment explicit (t.ex. sektorer = alltid 'large');
  // annars bifogas det globala valet.
  if (path.includes('segment=')) {
    const ctrl0 = new AbortController()
    const t0 = setTimeout(() => ctrl0.abort(), 20000)
    try {
      const res0 = await fetch(`${BASE}${path}`, { signal: ctrl0.signal })
      if (!res0.ok) {
        const body = await res0.json().catch(() => ({}))
        throw new Error(body.detail || `${res0.status} ${res0.statusText}`)
      }
      return res0.json()
    } catch (e) {
      throw new Error(e.name === 'AbortError' ? `Tidsgräns (20 s) – ${path} svarade inte` : e.message)
    } finally {
      clearTimeout(t0)
    }
  }
  const sep = path.includes('?') ? '&' : '?'
  // Timeout: en hängande begäran ska ge ett synligt fel, inte en evig spinner.
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 20000)
  let res
  try {
    res = await fetch(`${BASE}${path}${sep}segment=${encodeURIComponent(currentSegment)}`, { signal: ctrl.signal })
  } catch (e) {
    throw new Error(e.name === 'AbortError' ? `Tidsgräns (20 s) – ${path} svarade inte` : e.message)
  } finally {
    clearTimeout(timer)
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

async function postJson(path, payload) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  segments: () => getJson('/segments'),
  health: () => getJson('/health'),
  stats: () => getJson('/stats'),
  latestSignals: () => getJson('/signals/latest'),
  signalHistory: (ticker, limit = 260) =>
    getJson(`/signals/history?${ticker ? `ticker=${encodeURIComponent(ticker)}&` : ''}limit=${limit}`),
  portfolio: (limit = 1000) => getJson(`/portfolio?limit=${limit}`),
  drift: (limit = 260) => getJson(`/drift?limit=${limit}`),
  regime: () => getJson('/regime'),
  // Sektorer är marknadsvyn – alltid bredaste segmentet (ETF-mappad aggregat),
  // oberoende av Storbolag/Småbolag-växlaren (som är gömd på Marknad).
  sectorMomentum: () => getJson('/sector-momentum?segment=large'),
  paperLedger: (limit = 520) => getJson(`/paper-ledger?limit=${limit}`),
  prices: (ticker, limit = 260) =>
    getJson(`/prices?ticker=${encodeURIComponent(ticker)}&limit=${limit}`),
  quality: () => getJson('/quality'),
  quant: () => getJson('/quant'),
  rotation: () => getJson('/rotation'),
  thesis: () => getJson('/thesis'),
  // Egen väg för manuella innehav – /portfolio är backtest-equity-kurvan.
  holdings: (amount) => getJson(`/holdings${amount ? `?amount=${amount}` : ''}`),
  // Coret: ETT rangordnat svar på "var ska nästa krona in?" (hemvyns huvudkort).
  nextBuy: (amount) => getJson(`/next-buy${amount ? `?amount=${amount}` : ''}`),
  // Förifylld Montrose-köpbiljett för EN rad ur Nästa köp-planen. Lägger aldrig
  // en order – returnerar bara en länk du själv öppnar och bekräftar i appen.
  tradeTicket: (ticker, kr) => postJson('/trade-ticket', { ticker, kr }),
  // "Följde jag planen?" – skapade tickets + om köpet landade (idé 8).
  tradeTickets: () => getJson('/trade-tickets'),
  portfolioTarget: () => getJson('/portfolio-target'),
  saveTarget: (target) => postJson('/portfolio-target', target),
  // Rank-modell för "nästa köp" (balanced/buffett/momentum). Ren vy-inställning
  // – ingen omkörning krävs vid växling (all data laddas alltid).
  portfolioModel: () => getJson('/portfolio-model'),
  setPortfolioModel: (model) => postJson('/portfolio-model', { model }),
  universe: () => getJson('/universe'),   // sökbara värdepapper (sök/filtrera vid innehav)
  saveHoldings: (holdings, amount) => postJson('/holdings', { holdings, amount }),
  exitSignals: () => getJson('/exit-signals'),
  // Bedömning-fliken: narrativ per bolag + månatlig förvaltarkommentar.
  insight: () => getJson('/insight'),
  commentary: () => getJson('/commentary'),
  // AI-boxen under Förvaltarkommentaren: fri följdfråga, på-begäran headless
  // Claude (WebSearch), kan ta upp till ~2 min - samma mönster som scannerAnalyze.
  commentaryAsk: (question) => postJson('/commentary/ask', { question }),
  caseChanges: () => getJson('/case-changes'),
  portfolioLog: () => getJson('/portfolio-log'),
  // "Nästa köp" (fyll-mot-mål) vs index – förberäknad på Pi:n (portfolio.py backtest).
  portfolioBacktest: () => getJson('/portfolio-backtest'),
  // Manuell scenario-skanner: valfri aktie + manuell data → värde ur modellerna.
  // Görs ALDRIG mot nätet och sparas ALDRIG (se altdata/manual_scan.py).
  scannerFields: () => getJson('/scanner/fields'),
  // Segment default:ar till appens globala val (Storbolag/Småbolag-toggeln) –
  // styr vilket universum scenariot percentilrankas mot och var förfyllnaden
  // letar först. postJson bifogar inte segment automatiskt (bara getJson gör
  // det via query-param), så det måste in i body:n explicit.
  scannerScan: (ticker, overrides, segment) =>
    postJson('/scanner/scan', { ticker, overrides, segment: segment ?? currentSegment }),
  // AI-analysrutan i Skanner: på-begäran headless Claude (WebSearch), kan
  // ta upp till ~2 min - anropas separat från scannerScan (inte varje
  // skanning ska kosta ett LLM-anrop, bara när du uttryckligen vill ha det).
  scannerAnalyze: (ticker, overrides, segment, amount) =>
    postJson('/scanner/analyze', { ticker, overrides, segment: segment ?? currentSegment, amount }),
  // Aktiedetaljsidans Djupanalys: på-begäran bull/bear + konkurrentkontext
  // för ETT befintligt innehav (headless Claude, WebSearch, ~2 min).
  stockAnalyze: (ticker) => postJson('/stock/analyze', { ticker }),
  // "Fråga om bolaget"-boxen: fri följdfråga scopad till ett bolag, samma
  // mönster som commentaryAsk men per ticker.
  stockAsk: (ticker, question) => postJson('/stock/ask', { ticker, question }),
}
