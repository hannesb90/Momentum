import { useState, useEffect } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import { OverviewPage } from './pages/Overview'
import { CompaniesPage } from './pages/Companies'
import { SectorsPage } from './pages/Sectors'
import { AnalysisPage } from './pages/Analysis'
import { WatchlistPage } from './pages/Watchlist'
import { RotationPage } from './pages/Rotation'
import { MarketPage } from './pages/Market'
import { HoldingsHubPage } from './pages/HoldingsHub'
import { AssessmentPage } from './pages/Assessment'
import { StockDetailPage } from './pages/StockDetail'
import { ScannerPage } from './pages/Scanner'
import { setApiSegment } from './api'
import { InfoButton } from './components/InfoButton'

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

  // Segmenttoggeln göms där den inte styr något: hemvyn (Core:t är segment-
  // oberoende), Innehav (din portfölj är din portfölj), Marknad/Sektorer/
  // Rotation (ETF-/marknadsvy – sektordatan är pinnad till bredaste segmentet)
  // och Bolag/Bevakning (2026-07-22: Bolag slog ihop gamla Signaler+Kvalitet
  // och hämtar numera BÅDA segmenten i en sammanslagen lista med eget filter,
  // se api.latestSignalsAll/quantAll - den globala växlaren styr inte längre
  // något där). På kvarvarande forskningsvyer (Analys/Skanner) styr den
  // fortfarande visat segment.
  const { pathname } = useLocation()
  const showSegments = !['/', '/innehav', '/bedomning', '/marknad', '/sektorer', '/rotation', '/bolag']
    .some((p) => pathname === p || (p !== '/' && pathname.startsWith(p)))

  return (
    <div className="app">
      <NavBar />
      {showSegments && (
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
          <InfoButton title="Välkommen">Detta är Momentum ML-dashboard. Välj mellan Storbolag och Småbolag för att filtrera marknaden.</InfoButton>
        </div>
      )}
      {/* key={segment} -> alla sidor monteras om och hämtar för rätt segment */}
      <main className="app__content" key={segment}>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/bolag" element={<CompaniesPage />} />
          {/* 2026-07-22: Signaler+Kvalitet slogs ihop till /bolag - gamla
              länkar/bokmärken vidarebefordras i stället för att 404:a. */}
          <Route path="/signaler" element={<Navigate to="/bolag" replace />} />
          <Route path="/kvalitet" element={<Navigate to="/bolag" replace />} />
          <Route path="/marknad" element={<MarketPage />} />
          {/* 2026-07-22: Bevakning flyttad hit som sub-flik (HoldingsHubPage,
              samma mönster som gamla Signaler/Bevakning) - inte längre egen
              huvudflik. /bevakning-routen nedan är kvar som deep-link. */}
          <Route path="/innehav" element={<HoldingsHubPage />} />
          <Route path="/bedomning" element={<AssessmentPage />} />
          <Route path="/analys" element={<AnalysisPage />} />
          <Route path="/skanner" element={<ScannerPage />} />
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
