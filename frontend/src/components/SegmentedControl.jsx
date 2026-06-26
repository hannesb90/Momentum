/**
 * Pill-formad segmenterad kontroll för filter och underflikar (bank-app-stil).
 * options: [{ value, label }], value: aktivt värde, onChange: (value) => void
 */
export function SegmentedControl({ options, value, onChange, size = 'md' }) {
  return (
    <div className={`segmented segmented--${size}`} role="tablist">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="tab"
          aria-selected={value === opt.value}
          className={`segmented__item${value === opt.value ? ' segmented__item--active' : ''}`}
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
