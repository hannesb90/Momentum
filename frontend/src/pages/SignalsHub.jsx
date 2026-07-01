import { useState } from 'react'
import { SignalsPage } from './Signals'
import { WatchlistPage } from './Watchlist'

const TABS = [
  { id: 'signaler', label: 'Signaler' },
  { id: 'bevakning', label: 'Bevakning' },
]

// "Signaler"-flik med Bevakning som sub-toggle (färre flikar i huvudmenyn).
export function SignalsHubPage() {
  const [tab, setTab] = useState('signaler')
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
      {tab === 'signaler' ? <SignalsPage /> : <WatchlistPage />}
    </>
  )
}
