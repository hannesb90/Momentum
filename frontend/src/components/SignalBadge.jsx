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

export function SignalBadge({ variant }) {
  return <span className={`sigbadge sigbadge--${variant}`}>{LABELS[variant] ?? variant}</span>
}
