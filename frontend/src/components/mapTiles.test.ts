import { describe, expect, it } from 'vitest';
import { tileLayers } from './mapTiles';

const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services';

describe('tileLayers', () => {
  it('uses keyless Esri maps when there is no CARTO key: colourful streets in light mode, dark gray in dark mode', () => {
    for (const key of [undefined, '', '   ']) {
      const light = tileLayers('map', 'light', key);
      expect(light.map((l) => l.url)).toEqual([`${ESRI}/World_Street_Map/MapServer/tile/{z}/{y}/{x}`]);
      expect(light[0].attribution).toContain('Esri');
      expect(light[0].attribution).toContain('OpenStreetMap');

      const dark = tileLayers('map', 'dark', key);
      expect(dark.map((l) => l.url)).toEqual([
        `${ESRI}/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
        `${ESRI}/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`,
      ]);
      expect([...light, ...dark].every((l) => !l.url.includes('cartocdn'))).toBe(true);
    }
  });

  it('uses CARTO Voyager and Dark Matter with the key when one is configured', () => {
    const [light] = tileLayers('map', 'light', 'abc 123');
    expect(light.url).toBe('https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?key=abc%20123');
    expect(light.attribution).toContain('CARTO');
    const [dark] = tileLayers('map', 'dark', 'k');
    expect(dark.url).toBe('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?key=k');
  });

  it('shows satellite imagery in either theme, with or without a key', () => {
    for (const layers of [tileLayers('satellite', 'light'), tileLayers('satellite', 'dark', 'k')]) {
      expect(layers).toHaveLength(1);
      expect(layers[0].url).toContain('World_Imagery');
    }
  });

  it('gives every layer a distinct id so switching styles replaces the tiles', () => {
    const ids = (['light', 'dark'] as const).flatMap((t) => [...tileLayers('map', t), ...tileLayers('map', t, 'k')].map((l) => l.id));
    expect(new Set(ids).size).toBe(ids.length);
  });
});
