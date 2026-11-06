import { describe, expect, it } from 'vitest';
import { conditionLabel, formatDistance, formatDuration, formatHour, formatScore, placeName, riskColor, riskLabel, shortCoords } from './format';

describe('format helpers', () => {
  it('formats durations', () => {
    expect(formatDuration(59)).toBe('1 min');
    expect(formatDuration(45 * 60)).toBe('45 min');
    expect(formatDuration(3600)).toBe('1 h');
    expect(formatDuration(9115)).toBe('2 h 32 min');
  });

  it('formats distances in both unit systems', () => {
    expect(formatDistance(1609.344)).toBe('1.0 mi');
    expect(formatDistance(202548)).toBe('126 mi');
    expect(formatDistance(5500, 'metric')).toBe('5.5 km');
    expect(formatDistance(202548, 'metric')).toBe('203 km');
  });

  it('maps risk levels to colours and labels', () => {
    expect(riskLabel('very_high')).toBe('Very High');
    expect(riskLabel(null)).toBe('Unknown');
    expect(riskColor('low')).toBe('#22a447');
    expect(riskColor(undefined)).toBe('#94a3b8');
  });

  it('formats scores, hours, coordinates and conditions', () => {
    expect(formatScore(62.44)).toBe('62');
    expect(formatScore(null)).toBe('—');
    expect(formatHour(0)).toBe('12 AM');
    expect(formatHour(13)).toBe('1 PM');
    expect(formatHour(99)).toBe('Unknown time');
    expect(shortCoords(40.110612, -88.207301)).toBe('40.1106, -88.2073');
    expect(conditionLabel('wet', 'dark')).toBe('Rain · Dark');
  });

  it('shows all-capital place names in title case and leaves others alone', () => {
    expect(placeName('CHAMPAIGN')).toBe('Champaign');
    expect(placeName('ST. CLAIR')).toBe('St. Clair');
    expect(placeName('DE KALB')).toBe('De Kalb');
    expect(placeName('MCLEAN')).toBe('McLean');
    expect(placeName("O'BRIEN")).toBe("O'Brien");
    expect(placeName('MIAMI-DADE')).toBe('Miami-Dade');
    expect(placeName('Champaign')).toBe('Champaign');
    expect(placeName('DeKalb')).toBe('DeKalb');
    expect(placeName('')).toBe('');
  });
});
