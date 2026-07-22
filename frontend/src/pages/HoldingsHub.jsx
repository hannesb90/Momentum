import { useState } from 'react'
import { HoldingsPage } from './Holdings'
import { WatchlistPage } from './Watchlist'

const TABS = [
  { id: 'innehav', label: 'Innehav' },
  { id: 'bevakning', label: 'Bevakning' },
]

// "Innehav"-flik med Bevakning som sub-toggle (2026-07-22, samma mönster som
// tidigare Signaler/Bevakning - färre flikar i huvudmenyn).
export function HoldingsHubPage() {
  const [tab, setTab] = useState('innehav')
  return (
    <>
      <div className="subtabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`subtab${tab === t.id ? ' subtab--active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'innehav' ? <HoldingsPage /> : <WatchlistPage />}
    </>
  )
}
