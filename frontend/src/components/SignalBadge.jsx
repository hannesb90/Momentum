/**
 * Enhetlig signal-badge. variant: 'buy' | 'hold' | 'sell' | 'flat' | 'unknown'
 */
const LABELS = {
  buy: 'KÖP',
  hold: 'BEHÅLL',
  sell: 'SÄLJ',
  flat: 'NEUTRAL',
  unknown: 'INGEN DATA',
}

export function SignalBadge({ variant, round }) {
  const label = LABELS[variant] ?? variant
  if (round) {
    return (
      <span className={`sigbadge sigbadge--${variant} sigbadge--round`} title={label}>
        {label.charAt(0)}
      </span>
    )
  }
  return <span className={`sigbadge sigbadge--${variant}`}>{label}</span>
}
