import { useState } from 'react';
import { TrendingUp } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { HourCount, MonthCount } from '../api/types';
import { formatHour, MONTHS } from '../utils/format';

interface Props {
  byMonth?: MonthCount[];
  byHour?: HourCount[];
  highlightMonths?: number[] | null;
}

export default function RiskOverTime({ byMonth, byHour, highlightMonths }: Props) {
  const [view, setView] = useState<'month' | 'hour'>('month');
  const data = view === 'month'
    ? (byMonth ?? []).map((m) => ({ label: MONTHS[m.month - 1], crashes: m.crashes }))
    : (byHour ?? []).map((h) => ({ label: formatHour(h.hour), crashes: h.crashes }));
  const empty = data.length === 0;

  return (
    <section className="panel chart-panel" aria-labelledby="risk-time-title">
      <div className="chart-head">
        <h2 id="risk-time-title" className="panel-title"><TrendingUp size={22} aria-hidden /> Risk over time</h2>
        <span className="muted chart-caption">
          {empty ? 'Analyze a route to see when crashes happen along it'
                 : `Fatal crashes along the route, by ${view === 'month' ? 'month' : 'hour of day'}`}
          {highlightMonths && view === 'month' ? ` · selected: ${highlightMonths.map((m) => MONTHS[m - 1]).join(', ')}` : ''}
        </span>
        <select aria-label="Chart view" value={view} onChange={(e) => setView(e.target.value as 'month' | 'hour')}>
          <option value="month">By month</option>
          <option value="hour">By hour of day</option>
        </select>
      </div>
      <div className="chart-body" data-testid="risk-chart">
        {empty ? (
          <div className="chart-empty" aria-hidden>
            <svg viewBox="0 0 400 80" preserveAspectRatio="none"><path d="M0 60 C60 40 100 55 160 45 S260 25 320 35 400 50 400 50" /></svg>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id="riskFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.03} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} className="chart-grid" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} interval={view === 'hour' ? 2 : 0} fontSize={12} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={12} />
              <Tooltip formatter={(v: number) => [`${v} crashes`, 'Fatal crashes']} />
              <Area type="monotone" dataKey="crashes" stroke="#3b82f6" strokeWidth={2} fill="url(#riskFill)"
                    dot={{ r: 3, fill: '#3b82f6' }} activeDot={{ r: 5 }} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
