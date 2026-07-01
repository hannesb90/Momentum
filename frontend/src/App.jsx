import { useState, useEffect } from 'react'
import { Routes, Route } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import { OverviewPage } from './pages/Overview'
import { SignalsHubPage } from './pages/SignalsHub'
import { SectorsPage } from './pages/Sectors'
import { AnalysisPage } from './pages/Analysis'
import { WatchlistPage } from './pages/Watchlist'
import { QualityPage } from './pages/Quality'
import { RotationPage } from './pages/Rotation'
import { MarketPage } from './pages/Market'
import { HoldingsPage } from './pages/Holdings'
import { StockDetailPage } from './pages/StockDetail'
import { setApiSegment } from './api'

const SEGMENTS = [
  { id: 'large', label: 'Storbolag' },
  { id: 'small', label: 'Småbolag' },
]

export default function App() {
  const [segment, setSegment] = useState(
    () => localStorage.getItem('segment') || 'large',
  )

  // Bifoga segmentet på alla API-anrop INNAN barnen renderar/hämtar.
  setApiSegment(segment)

  useEffect(() => {
    localStorage.setItem('segment', segment)
  }, [segment])

  // Segmentbyte sker enbart via knapparna (swipe-toggeln borttagen – den
  // krockade med sido-scroll i breda vyer).
  return (
    <div className="app">
      <NavBar />
      <div className="segment-bar">
        {SEGMENTS.map((s) => (
          <button
            key={s.id}
            type="button"
            className={`segment-toggle__btn${segment === s.id ? ' segment-toggle__btn--active' : ''}`}
            onClick={() => setSegment(s.id)}
          >
            {s.label}
          </button>
        ))}
      </div>
      {/* key={segment} -> alla sidor monteras om och hämtar för rätt segment */}
      <main className="app__content" key={segment}>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/signaler" element={<SignalsHubPage />} />
          <Route path="/marknad" element={<MarketPage />} />
          <Route path="/kvalitet" element={<QualityPage />} />
          <Route path="/innehav" element={<HoldingsPage />} />
          <Route path="/analys" element={<AnalysisPage />} />
          {/* Deep-link-vägar (nås via sub-flikar men behåller egna URL:er) */}
          <Route path="/sektorer" element={<SectorsPage />} />
          <Route path="/rotation" element={<RotationPage />} />
          <Route path="/bevakning" element={<WatchlistPage />} />
          <Route path="/aktie/:ticker" element={<StockDetailPage />} />
        </Routes>
      </main>
    </div>
  )
}
