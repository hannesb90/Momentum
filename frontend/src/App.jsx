import { useState, useEffect } from 'react'
import { Routes, Route } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import { OverviewPage } from './pages/Overview'
import { SignalsPage } from './pages/Signals'
import { PortfolioPage } from './pages/Portfolio'
import { SectorsPage } from './pages/Sectors'
import { AnalysisPage } from './pages/Analysis'
import { WatchlistPage } from './pages/Watchlist'
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

  return (
    <div className="app">
      <NavBar segment={segment} segments={SEGMENTS} onSegmentChange={setSegment} />
      {/* key={segment} -> alla sidor monteras om och hämtar för rätt segment */}
      <main className="app__content" key={segment}>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/signaler" element={<SignalsPage />} />
          <Route path="/portfolj" element={<PortfolioPage />} />
          <Route path="/sektorer" element={<SectorsPage />} />
          <Route path="/analys" element={<AnalysisPage />} />
          <Route path="/bevakning" element={<WatchlistPage />} />
          <Route path="/aktie/:ticker" element={<StockDetailPage />} />
        </Routes>
      </main>
    </div>
  )
}
