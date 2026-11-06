/**
 * Map tile layers.
 *
 * CARTO's basemaps stopped serving tiles without a key on 25 September 2026 (they show "API KEY REQUIRED"
 * instead). A free key for non-commercial use comes from https://carto.com/basemaps/apikey; put it in
 * frontend/.env as VITE_CARTO_KEY to use CARTO Voyager (closest to the mockup) and Dark Matter.
 * Without a key the app uses Esri's tiles, which need no key: World Street Map in light mode and
 * Dark Gray Canvas (with a labels layer) in dark mode.
 */
export type MapMode = 'map' | 'satellite';
export type Theme = 'light' | 'dark';

export interface TileDef {
  id: string;
  url: string;
  attribution: string;
  maxNativeZoom?: number;
}

const OSM = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const CARTO = `${OSM} &copy; <a href="https://carto.com/attributions">CARTO</a>`;
const esri = (service: string) => `https://server.arcgisonline.com/ArcGIS/rest/services/${service}/MapServer/tile/{z}/{y}/{x}`;

export function tileLayers(mode: MapMode, theme: Theme, cartoKey?: string): TileDef[] {
  if (mode === 'satellite') {
    return [{
      id: 'esri-imagery',
      url: esri('World_Imagery'),
      attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics',
    }];
  }
  const key = cartoKey?.trim();
  if (key) {
    const k = encodeURIComponent(key);
    return theme === 'dark'
      ? [{ id: 'carto-dark', url: `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?key=${k}`, attribution: CARTO }]
      : [{ id: 'carto-voyager', url: `https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?key=${k}`, attribution: CARTO }];
  }
  if (theme === 'dark') {
    const attribution = `Tiles &copy; <a href="https://www.esri.com">Esri</a> &mdash; Esri, HERE, Garmin, ${OSM}`;
    return [
      { id: 'esri-dark-base', url: esri('Canvas/World_Dark_Gray_Base'), attribution, maxNativeZoom: 16 },
      { id: 'esri-dark-labels', url: esri('Canvas/World_Dark_Gray_Reference'), attribution: '', maxNativeZoom: 16 },
    ];
  }
  return [{
    id: 'esri-street',
    url: esri('World_Street_Map'),
    attribution: `Tiles &copy; <a href="https://www.esri.com">Esri</a> &mdash; Source: Esri, HERE, Garmin, USGS, ${OSM}, and the GIS User Community`,
  }];
}
