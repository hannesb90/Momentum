import { InfoButton } from './InfoButton'

export function StatCard({ label, value, tone = 'neutral', info }) {
  return (
    <div className={`stat-card stat-card--${tone}`}>
      <div className="stat-card__label">
        {label}
        {info && <InfoButton title={label}>{info}</InfoButton>}
      </div>
      <div className="stat-card__value">{value}</div>
    </div>
  )
}
