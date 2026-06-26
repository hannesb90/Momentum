import { Routes, Route } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import { OverviewPage } from './pages/Overview'
import { SignalsPage } from './pages/Signals'
import { PortfolioPage } from './pages/Portfolio'
import { SectorsPage } from './pages/Sectors'
import { AnalysisPage } from './pages/Analysis'
import { WatchlistPage } from './pages/Watchlist'
import { StockDetailPage } from './pages/StockDetail'

export default function App() {
  return (
    <div className="app">
      <NavBar />
      <main className="app__content">
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
