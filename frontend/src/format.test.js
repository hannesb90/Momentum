import { describe, it, expect } from 'vitest'
import { cleanName } from './format.js'

describe('cleanName', () => {
  it('removes legal suffixes like AB and (publ)', () => {
    expect(cleanName('Volvo AB', 'VOLV')).toBe('Volvo')
    expect(cleanName('Ericsson (publ)', 'ERIC')).toBe('Ericsson')
    expect(cleanName('Ericsson (publ.)', 'ERIC')).toBe('Ericsson')
    expect(cleanName('Swedbank AB (publ)', 'SWED')).toBe('Swedbank')
    expect(cleanName('Swedbank AB (publ.)', 'SWED')).toBe('Swedbank')
  })

  it('handles case-insensitivity and extra whitespace', () => {
    expect(cleanName('  H&M ab  (publ)  ', 'HM')).toBe('H&M')
    expect(cleanName('SEB aB', 'SEB')).toBe('SEB')
  })

  it('keeps normal company names intact', () => {
    expect(cleanName('AstraZeneca', 'AZN')).toBe('AstraZeneca')
    expect(cleanName('Assa Abloy', 'ASSA')).toBe('Assa Abloy')
  })

  it('falls back to ticker if name is missing or empty', () => {
    expect(cleanName('', 'VOLV')).toBe('VOLV')
    expect(cleanName(null, 'ERIC')).toBe('ERIC')
    expect(cleanName(undefined, 'INVE')).toBe('INVE')
  })

  it('returns empty string if both name and ticker are missing', () => {
    expect(cleanName(null, null)).toBe('')
    expect(cleanName('', undefined)).toBe('')
    expect(cleanName(undefined, null)).toBe('')
  })

  it('returns ticker if name exactly matches ticker', () => {
    expect(cleanName('VOLV', 'VOLV')).toBe('VOLV')
  })

  it('works correctly when ticker is missing', () => {
    expect(cleanName('Sandvik AB', null)).toBe('Sandvik')
    expect(cleanName('AstraZeneca', undefined)).toBe('AstraZeneca')
  })

  it('falls back to ticker if name becomes empty after cleaning', () => {
    expect(cleanName(' (publ)', 'TICKER')).toBe('TICKER')
  })

  it('falls back to original name if name becomes empty after cleaning and ticker is missing', () => {
    expect(cleanName(' (publ)', null)).toBe(' (publ)')
  })
})
