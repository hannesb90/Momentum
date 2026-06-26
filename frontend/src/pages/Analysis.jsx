import { useState } from 'react'
import { SegmentedControl } from '../components/SegmentedControl'
import { BacktestPage } from './Backtest'
import { RobustnessPage } from './Robustness'
import { RegimesPage } from './Regimes'

const TABS = [
  { value: 'backtest', label: 'Backtest' },
  { value: 'robusthet', label: 'Robusthet' },
  { value: 'regimer', label: 'Regimer' },
]

export function AnalysisPage() {
  const [tab, setTab] = useState('backtest')

  return (
    <section className="page">
      <div className="filter-bar filter-bar--tabs">
        <SegmentedControl options={TABS} value={tab} onChange={setTab} />
      </div>
      {tab === 'backtest' && <BacktestPage />}
      {tab === 'robusthet' && <RobustnessPage />}
      {tab === 'regimer' && <RegimesPage />}
    </section>
  )
}
