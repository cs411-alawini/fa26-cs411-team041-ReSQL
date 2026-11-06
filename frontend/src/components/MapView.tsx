import { useEffect, useState, type ReactNode } from 'react';
import { MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Crosshair, Minus, Plus } from 'lucide-react';
import { useTheme } from '../theme/ThemeContext';
import RiskLegend from './RiskLegend';
import { tileLayers } from './mapTiles';

export type LatLon = [number, number];
export type Bounds = { min_lat: number; min_lon: number; max_lat: number; max_lon: number };

const CARTO_KEY = import.meta.env.VITE_CARTO_KEY as string | undefined;

interface Props {
  center?: LatLon;
  zoom?: number;
  fit?: LatLon[] | null;
  onMapClick?: (lat: number, lon: number) => void;
  onBoundsChange?: (b: Bounds) => void;
  legend?: ReactNode | boolean;
  children?: ReactNode;
  overlay?: ReactNode;
  testId?: string;
}

function Fit({ points }: { points: LatLon[] | null | undefined }) {
  const map = useMap();
  useEffect(() => {
    if (points && points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [40, 40] });
    else if (points && points.length === 1) map.setView(points[0], Math.max(map.getZoom(), 12));
  }, [map, points]);
  return null;
}

function Events({ onMapClick, onBoundsChange }: Pick<Props, 'onMapClick' | 'onBoundsChange'>) {
  const map = useMapEvents({
    click: (e) => onMapClick?.(e.latlng.lat, e.latlng.lng),
    moveend: () => report(),
  });
  const report = () => {
    if (!onBoundsChange) return;
    const b = map.getBounds();
    onBoundsChange({ min_lat: b.getSouth(), min_lon: b.getWest(), max_lat: b.getNorth(), max_lon: b.getEast() });
  };
  useEffect(() => { report(); /* initial bounds */ }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

function Controls() {
  const map = useMap();
  const locate = () => {
    navigator.geolocation?.getCurrentPosition((pos) => map.flyTo([pos.coords.latitude, pos.coords.longitude], 13));
  };
  return (
    <div className="map-controls" onDoubleClick={(e) => e.stopPropagation()}>
      <div className="map-zoom">
        <button type="button" aria-label="Zoom in" onClick={(e) => { e.stopPropagation(); map.zoomIn(); }}><Plus size={20} /></button>
        <button type="button" aria-label="Zoom out" onClick={(e) => { e.stopPropagation(); map.zoomOut(); }}><Minus size={20} /></button>
      </div>
      <button type="button" className="map-locate" aria-label="Go to my location"
              onClick={(e) => { e.stopPropagation(); locate(); }}><Crosshair size={20} /></button>
    </div>
  );
}

export default function MapView({ center = [40.1106, -88.2073], zoom = 11, fit, onMapClick, onBoundsChange,
                                  legend = true, children, overlay, testId }: Props) {
  const { theme } = useTheme();
  const [mode, setMode] = useState<'map' | 'satellite'>('map');
  const tiles = tileLayers(mode, theme, CARTO_KEY);

  return (
    <div className="map-shell" data-testid={testId}>
      <MapContainer center={center} zoom={zoom} maxZoom={19} zoomControl={false} className="map" attributionControl>
        {tiles.map((t) => (
          <TileLayer key={t.id} url={t.url} attribution={t.attribution} maxZoom={19} maxNativeZoom={t.maxNativeZoom} />
        ))}
        <Fit points={fit} />
        <Events onMapClick={onMapClick} onBoundsChange={onBoundsChange} />
        <Controls />
        {children}
      </MapContainer>
      <div className="map-mode" role="group" aria-label="Map style">
        <button type="button" className={mode === 'map' ? 'active' : ''} aria-pressed={mode === 'map'}
                onClick={() => setMode('map')}>Map</button>
        <button type="button" className={mode === 'satellite' ? 'active' : ''} aria-pressed={mode === 'satellite'}
                onClick={() => setMode('satellite')}>Satellite</button>
      </div>
      {legend === true ? <RiskLegend /> : legend || null}
      {overlay}
    </div>
  );
}

/** A small round pin used for start, destination and saved places. */
export function pinIcon(kind: 'start' | 'end' | 'saved' | 'report' | 'crash', label?: string): L.DivIcon {
  return L.divIcon({
    className: `pin pin-${kind}`,
    html: `<span>${label ?? ''}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}
