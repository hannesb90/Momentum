import { useState } from 'react'
import { QualityPage } from './Quality'
import { QuantPage } from './Quant'

const TABS = [
  { id: 'kvalitativ', label: 'Kvalitativ' },
  { id: 'kvant', label: 'Kvant (hård data)' },
]

// "Kvalitet"-flik: LLM-kvalitativ sållning + token-fri kvant-rankning under sub-toggle.
export function QualityHubPage() {
  const [tab, setTab] = useState('kvalitativ')
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
      {tab === 'kvalitativ' ? <QualityPage /> : <QuantPage />}
    </>
  )
}
