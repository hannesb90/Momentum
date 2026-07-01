import { useEffect, useLayoutEffect, useRef, useState } from 'react'

const WIDTH = 290
const MARGIN = 8

export function InfoButton({ title, children }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState(null)
  const wrapRef = useRef(null)
  const btnRef = useRef(null)

  // Positionera popovern viewport-relativt (position: fixed) och klamra in den så
  // den ALDRIG hamnar utanför skärmen eller klipps av en scroll-container (tabeller).
  useLayoutEffect(() => {
    if (!open) return
    function place() {
      const b = btnRef.current?.getBoundingClientRect()
      if (!b) return
      const vw = window.innerWidth
      const vh = window.innerHeight
      const width = Math.min(WIDTH, vw - 2 * MARGIN)
      let left = b.left + b.width / 2 - width / 2
      left = Math.max(MARGIN, Math.min(left, vw - width - MARGIN))
      const spaceBelow = vh - b.bottom
      const spaceAbove = b.top
      const below = spaceBelow >= spaceAbove
      const maxHeight = Math.min(340, (below ? spaceBelow : spaceAbove) - MARGIN - 6)
      setPos({
        left,
        width,
        maxHeight,
        top: below ? b.bottom + 6 : undefined,
        bottom: below ? undefined : vh - b.top + 6,
      })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true) // capture: följ med i alla scroll-containrar
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    function onOutside(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
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
    <span className="info-btn-wrap" ref={wrapRef}>
      <button
        type="button"
        ref={btnRef}
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
      {open && pos && (
        <div
          className="info-popover"
          role="tooltip"
          style={{
            left: pos.left,
            width: pos.width,
            maxHeight: pos.maxHeight,
            top: pos.top,
            bottom: pos.bottom,
          }}
        >
          <div className="info-popover__title">{title}</div>
          <div className="info-popover__body">{children}</div>
        </div>
      )}
    </span>
  )
}
