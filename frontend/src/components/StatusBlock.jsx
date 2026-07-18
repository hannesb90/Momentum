export function Loading() {
  return (
    <div className="status-block status-block--loading" role="status" aria-live="polite">
      Laddar…
    </div>
  )
}

export function ErrorBlock({ error }) {
  return (
    <div className="status-block status-block--error" role="alert">
      Kunde inte hämta data: {error.message}
      <div className="status-block__hint">
        Kör <code>python main.py</code> och starta API:et med{' '}
        <code>uvicorn api.main:app --port 8001</code> i <code>momentum_ml/</code>.
      </div>
    </div>
  )
}
