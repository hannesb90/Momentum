// TradingView-genväg: mappar vår ticker (Yahoo-format) till TradingViews
// börs:symbol och länkar till en chart. Best effort – okänt suffix skickas som
// bar symbol (TradingView löser oftast den ändå). Ingen datakälla, bara en länk ut.
const EXCHANGE = {
  ST: 'OMXSTO',   // Stockholm
  DE: 'XETR',     // Xetra
  L: 'LSE',       // London
  PA: 'EURONEXT', // Paris
  CO: 'OMXCOP',   // Köpenhamn
  HE: 'OMXHEX',   // Helsingfors
  OL: 'OSL',      // Oslo
  US: '',         // USA – bar symbol
}

export function tvSymbol(ticker) {
  if (!ticker) return ''
  const t = ticker.trim().toUpperCase()
  const dot = t.lastIndexOf('.')
  const suffix = dot > -1 ? t.slice(dot + 1) : ''
  const base = (dot > -1 ? t.slice(0, dot) : t).replace(/-/g, '_')
  const exch = EXCHANGE[suffix]
  return exch ? `${exch}:${base}` : base
}

export function tvUrl(ticker) {
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol(ticker))}`
}

export function TvLink({ ticker, className = '' }) {
  if (!ticker) return null
  return (
    <a
      className={`tv-link ${className}`}
      href={tvUrl(ticker)}
      target="_blank"
      rel="noopener noreferrer"
      title={`Öppna ${tvSymbol(ticker)} i TradingView`}
      onClick={(e) => e.stopPropagation()}
    >
      <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor"
        strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M3 17l5-6 4 4 5-7 4 5" />
      </svg>
      TV
    </a>
  )
}
