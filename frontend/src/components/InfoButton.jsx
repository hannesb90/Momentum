import { useEffect, useRef, useState } from 'react'

export function InfoButton({ title, children }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    function onOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    function onEscape(e) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onOutside)
    document.addEventListener('touchstart', onOutside)
    document.addEventListener('keydown', onEscape)
    return () => {
      document.removeEventListener('mousedown', onOutside)
      document.removeEventListener('touchstart', onOutside)
      document.removeEventListener('keydown', onEscape)
    }
  }, [open])

  return (
    <span className="info-btn-wrap" ref={ref}>
      <button
        type="button"
        className="info-btn"
        aria-label={`Mer information: ${title}`}
        aria-expanded={open}
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setOpen((v) => !v)
        }}
      >
        ?
      </button>
      {open && (
        <div className="info-popover" role="tooltip">
          <div className="info-popover__title">{title}</div>
          <div className="info-popover__body">{children}</div>
        </div>
      )}
    </span>
  )
}
