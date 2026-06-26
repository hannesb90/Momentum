/**
 * Härleder signalvariant för ett innehav utifrån modellens senaste signal.
 * held = äger användaren aktien? sig = rad från /signals/latest (kan vara null).
 * Returnerar 'buy' | 'hold' | 'sell' | 'flat' | 'unknown'.
 */
export function holdingSignal(held, sig) {
  if (!sig) return 'unknown'
  if (sig.pred_signal === 1) return held ? 'hold' : 'buy'
  return held ? 'sell' : 'flat'
}
