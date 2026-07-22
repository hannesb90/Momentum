import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApiData } from '../useApiData'

export function TickerSearch() {
  // latestSignalsAll (inte latestSignals): autoifyllningslistan ska täcka
  // BÅDA segmenten, inte bara det globalt aktiva (som numera bara Analys/
  // Skanner ens visar växlaren för) - samma fix som Watchlist/Signaler fick.
  const { data } = useApiData(() => api.latestSignalsAll(), [])
  const navigate = useNavigate()
  const [value, setValue] = useState('')

  const tickers = useMemo(() => (data ?? []).map((s) => s.ticker), [data])

  function submit(q) {
    const t = q.trim().toUpperCase()
    if (!t) return
    navigate(`/bolag?q=${encodeURIComponent(t)}`)
    setValue('')
  }

  return (
    <form
      className="navbar__search"
      onSubmit={(e) => {
        e.preventDefault()
        submit(value)
      }}
    >
      <input
        className="navbar__search-input"
        type="search"
        list="navbar-tickers"
        placeholder="Sök bolag…"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-label="Sök bolag"
      />
      <datalist id="navbar-tickers">
        {tickers.map((t) => (
          <option key={t} value={t} />
        ))}
      </datalist>
    </form>
  )
}
