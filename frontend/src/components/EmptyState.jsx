export function EmptyState({ title, hint, children }) {
  return (
    <div className="empty-state">
      <div className="empty-state__title">{title}</div>
      {hint && <div className="empty-state__hint">{hint}</div>}
      {children}
    </div>
  )
}
