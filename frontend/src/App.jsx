import { Routes, Route } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import { SignalsPage } from './pages/Signals'
import { BacktestPage } from './pages/Backtest'
import { RobustnessPage } from './pages/Robustness'
import { RegimesPage } from './pages/Regimes'

export default function App() {
  return (
    <div className="app">
      <NavBar />
      <main className="app__content">
        <Routes>
          <Route path="/" element={<SignalsPage />} />
          <Route path="/backtest" element={<BacktestPage />} />
          <Route path="/robusthet" element={<RobustnessPage />} />
          <Route path="/regimer" element={<RegimesPage />} />
        </Routes>
      </main>
    </div>
  )
}
