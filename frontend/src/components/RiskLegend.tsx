import { RISK_COLORS, RISK_LABELS } from '../utils/format';
import type { RiskLevel } from '../api/types';

const LEVELS: RiskLevel[] = ['low', 'moderate', 'high', 'very_high'];

export default function RiskLegend({ title = 'Route Risk Level' }: { title?: string }) {
  return (
    <div className="map-legend" aria-label={title}>
      <strong>{title}</strong>
      <ul>
        {LEVELS.map((l) => (
          <li key={l}><span className="dot" style={{ background: RISK_COLORS[l] }} aria-hidden />{RISK_LABELS[l]}</li>
        ))}
      </ul>
    </div>
  );
}
