import { useState, useEffect, useRef } from 'react'
import { Routes, Route } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import { OverviewPage } from './pages/Overview'
import { SignalsPage } from './pages/Signals'
import { PortfolioPage } from './pages/Portfolio'
import { SectorsPage } from './pages/Sectors'
import { AnalysisPage } from './pages/Analysis'
import { WatchlistPage } from './pages/Watchlist'
import { QualityPage } from './pages/Quality'
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

  // Svep horisontellt för att toggla segment (vänster = nästa, höger = föregående)
  const touch = useRef(null)
  function onTouchStart(e) {
    const t = e.changedTouches[0]
    touch.current = { x: t.clientX, y: t.clientY }
  }
  function onTouchEnd(e) {
    if (!touch.current) return
    const t = e.changedTouches[0]
    const dx = t.clientX - touch.current.x
    const dy = t.clientY - touch.current.y
    touch.current = null
    if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 1.5) return // ignorera vertikalt/små
    const ids = SEGMENTS.map((s) => s.id)
    const i = ids.indexOf(segment)
    if (dx < 0 && i < ids.length - 1) setSegment(ids[i + 1])
    else if (dx > 0 && i > 0) setSegment(ids[i - 1])
  }

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
      <main
        className="app__content"
        key={segment}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/signaler" element={<SignalsPage />} />
          <Route path="/portfolj" element={<PortfolioPage />} />
          <Route path="/sektorer" element={<SectorsPage />} />
          <Route path="/analys" element={<AnalysisPage />} />
          <Route path="/bevakning" element={<WatchlistPage />} />
          <Route path="/kvalitet" element={<QualityPage />} />
          <Route path="/aktie/:ticker" element={<StockDetailPage />} />
        </Routes>
      </main>
    </div>
  )
}
