import { useState } from 'react'
import { SectorsPage } from './Sectors'
import { RotationPage } from './Rotation'

const TABS = [
  { id: 'sektorer', label: 'Sektorer' },
  { id: 'rotation', label: 'Rotation' },
]

// Samlad "Marknad"-flik: sektor-momentum + ETF/sektor-rotation under en sub-toggle
// (färre flikar i huvudmenyn, återanvänder befintliga vyer oförändrat).
export function MarketPage() {
  const [tab, setTab] = useState('sektorer')
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
      {tab === 'sektorer' ? <SectorsPage /> : <RotationPage />}
    </>
  )
}
