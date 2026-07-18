import { describe, it, expect } from 'vitest';
import { fmtPct, fmtNum, fmtSek, fmtDate, toneForSignedPct, cleanName } from './format';

describe('fmtPct', () => {
  it('formats positive numbers correctly', () => {
    expect(fmtPct(0.123)).toBe('12.3%');
    expect(fmtPct(0.1234, 2)).toBe('12.34%');
  });

  it('formats negative numbers correctly', () => {
    expect(fmtPct(-0.05)).toBe('-5.0%');
    expect(fmtPct(-0.05, 0)).toBe('-5%');
  });

  it('handles null and undefined', () => {
    expect(fmtPct(null)).toBe('–');
    expect(fmtPct(undefined)).toBe('–');
  });

  it('handles invalid numbers', () => {
    expect(fmtPct('not a number')).toBe('–');
    expect(fmtPct(NaN)).toBe('–');
  });
});

describe('fmtNum', () => {
  it('formats numbers correctly', () => {
    expect(fmtNum(12.345)).toBe('12.35');
    expect(fmtNum(12, 1)).toBe('12.0');
    expect(fmtNum(0)).toBe('0.00');
  });

  it('handles negative numbers', () => {
    expect(fmtNum(-1.5)).toBe('-1.50');
  });

  it('handles null and undefined', () => {
    expect(fmtNum(null)).toBe('–');
    expect(fmtNum(undefined)).toBe('–');
  });

  it('handles invalid numbers', () => {
    expect(fmtNum('not a number')).toBe('–');
    expect(fmtNum(NaN)).toBe('–');
  });
});

describe('fmtSek', () => {
  it('formats numbers to SEK string', () => {
    const res = fmtSek(12345);
    // Depending on locale, space might be narrow no-break space or normal space
    expect(res).toMatch(/12\s?345 kr/);
  });

  it('handles null and undefined', () => {
    expect(fmtSek(null)).toBe('–');
    expect(fmtSek(undefined)).toBe('–');
  });
});

describe('fmtDate', () => {
  it('formats date correctly', () => {
    const res = fmtDate('2023-01-05');
    // Usually 23-jan. or similar depending on sv-SE, maybe 'jan. 23' depending on environment
    expect(res).toMatch(/23/);
    expect(res).toMatch(/jan/i);
  });
});

describe('toneForSignedPct', () => {
  it('returns neutral for null or undefined', () => {
    expect(toneForSignedPct(null)).toBe('neutral');
    expect(toneForSignedPct(undefined)).toBe('neutral');
  });

  it('returns good for positive numbers and 0', () => {
    expect(toneForSignedPct(0.1)).toBe('good');
    expect(toneForSignedPct(0)).toBe('good');
  });

  it('returns bad for negative numbers', () => {
    expect(toneForSignedPct(-0.1)).toBe('bad');
  });
});

describe('cleanName', () => {
  it('removes legal suffixes', () => {
    expect(cleanName('Acme AB', 'ACME')).toBe('Acme');
    expect(cleanName('Acme (publ)', 'ACME')).toBe('Acme');
    expect(cleanName('Acme AB (publ)', 'ACME')).toBe('Acme');
    expect(cleanName('Acme AB (publ.)', 'ACME')).toBe('Acme');
  });

  it('handles missing name by falling back to ticker', () => {
    expect(cleanName(null, 'ACME')).toBe('ACME');
    expect(cleanName(undefined, 'ACME')).toBe('ACME');
    expect(cleanName('', 'ACME')).toBe('ACME');
  });

  it('returns empty string if both name and ticker are missing', () => {
    expect(cleanName(null, null)).toBe('');
  });
});
