import { describe, it, expect } from 'vitest'
import {
  fmtPct,
  fmtNum,
  fmtSek,
  fmtDate,
  toneForSignedPct,
  cleanName
} from './format'

describe('format.js', () => {
  describe('fmtNum', () => {
    it('formats positive integers', () => {
      expect(fmtNum(42)).toBe('42.00')
    })

    it('formats decimals with default 2 digits', () => {
      expect(fmtNum(42.1234)).toBe('42.12')
      expect(fmtNum(42.1)).toBe('42.10')
    })

    it('formats numbers with custom digits', () => {
      expect(fmtNum(42.1234, 3)).toBe('42.123')
      expect(fmtNum(42.1234, 0)).toBe('42')
    })

    it('handles negative numbers', () => {
      expect(fmtNum(-42.5)).toBe('-42.50')
    })

    it('handles null and undefined', () => {
      expect(fmtNum(null)).toBe('–')
      expect(fmtNum(undefined)).toBe('–')
    })

    it('handles invalid numbers (NaN)', () => {
      expect(fmtNum(NaN)).toBe('–')
      expect(fmtNum('not a number')).toBe('–')
    })

    it('handles string numbers', () => {
      expect(fmtNum('42.5')).toBe('42.50')
    })
  })

  describe('fmtPct', () => {
    it('formats decimals to percentages with default 1 digit', () => {
      expect(fmtPct(0.4215)).toBe('42.1%')
      expect(fmtPct(1)).toBe('100.0%')
    })

    it('formats to percentages with custom digits', () => {
      expect(fmtPct(0.42156, 2)).toBe('42.16%')
      expect(fmtPct(0.42156, 0)).toBe('42%')
    })

    it('handles negative numbers', () => {
      expect(fmtPct(-0.152)).toBe('-15.2%')
    })

    it('handles null and undefined', () => {
      expect(fmtPct(null)).toBe('–')
      expect(fmtPct(undefined)).toBe('–')
    })

    it('handles invalid numbers (NaN)', () => {
      expect(fmtPct(NaN)).toBe('–')
      expect(fmtPct('invalid')).toBe('–')
    })

    it('handles string numbers', () => {
      expect(fmtPct('0.5')).toBe('50.0%')
    })
  })

  describe('fmtSek', () => {
    it('formats numbers to SEK correctly', () => {
      expect(fmtSek(1234.56)).toBe('1\u00A0235 kr') // toLocaleString('sv-SE') uses non-breaking space
    })

    it('handles null and undefined', () => {
      expect(fmtSek(null)).toBe('–')
      expect(fmtSek(undefined)).toBe('–')
    })

    it('handles string numbers', () => {
      expect(fmtSek('1000')).toBe('1\u00A0000 kr')
    })
  })

  describe('fmtDate', () => {
    it('formats date strings correctly', () => {
      expect(fmtDate('2023-01-15T00:00:00Z')).toMatch(/Jan.? 23/i)
    })

    it('formats Date objects correctly', () => {
      const date = new Date('2023-12-25T12:00:00Z')
      expect(fmtDate(date)).toMatch(/Dec.? 23/i)
    })
  })

  describe('toneForSignedPct', () => {
    it('returns neutral for null/undefined', () => {
      expect(toneForSignedPct(null)).toBe('neutral')
      expect(toneForSignedPct(undefined)).toBe('neutral')
    })

    it('returns good for positive numbers and zero', () => {
      expect(toneForSignedPct(0)).toBe('good')
      expect(toneForSignedPct(0.5)).toBe('good')
      expect(toneForSignedPct('1')).toBe('good')
    })

    it('returns bad for negative numbers', () => {
      expect(toneForSignedPct(-0.1)).toBe('bad')
      expect(toneForSignedPct('-5')).toBe('bad')
    })
  })

  describe('cleanName', () => {
    it('returns ticker if name is missing or same as ticker', () => {
      expect(cleanName(null, 'TICKER')).toBe('TICKER')
      expect(cleanName(undefined, 'TICKER')).toBe('TICKER')
      expect(cleanName('', 'TICKER')).toBe('TICKER')
      expect(cleanName('TICKER', 'TICKER')).toBe('TICKER')
    })

    it('removes legal suffixes', () => {
      expect(cleanName('Company AB (publ)', 'TICKER')).toBe('Company')
      expect(cleanName('Company AB (publ.)', 'TICKER')).toBe('Company')
      expect(cleanName('Company (publ)', 'TICKER')).toBe('Company')
      expect(cleanName('Company AB', 'TICKER')).toBe('Company')
    })

    it('falls back to ticker if name becomes empty after cleaning', () => {
      expect(cleanName(' AB (publ)', 'TICKER')).toBe('TICKER')
    })

    it('leaves normal names alone', () => {
      expect(cleanName('Apple Inc.', 'AAPL')).toBe('Apple Inc.')
    })
  })
})
