export function StatCard({ label, value, tone = 'neutral' }) {
  return (
    <div className={`stat-card stat-card--${tone}`}>
      <div className="stat-card__label">{label}</div>
      <div className="stat-card__value">{value}</div>
    </div>
  )
}
