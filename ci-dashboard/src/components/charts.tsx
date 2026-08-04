import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip,
  XAxis, YAxis, Legend, ReferenceLine, LabelList,
} from 'recharts';
import type { DayPoint } from '../lib/metrics';
import { EmptyState } from './ui';

const AXIS = { stroke: '#c3c2b7', fontSize: 11, tickLine: false as const };
const GRID = { stroke: '#e1e0d9', strokeDasharray: '0', vertical: false as const };
const TOOLTIP_STYLE = {
  background: '#fcfcfb', border: '1px solid #e1e0d9', borderRadius: 8, fontSize: 12,
  boxShadow: '0 2px 8px rgba(11,11,11,0.08)',
};

/** Call volume: current period (solid) vs comparison period (dashed, aligned by day index). */
export function VolumeTrend({ current, previous, height = 220 }: { current: DayPoint[]; previous: DayPoint[]; height?: number }) {
  if (!current.some((d) => d.calls > 0)) return <EmptyState message="No analysed calls in this period." />;
  const data = current.map((d, i) => ({ label: d.label, current: d.calls, comparison: previous[i]?.calls ?? null }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="label" {...AXIS} interval="preserveStartEnd" minTickGap={40} />
        <YAxis {...AXIS} allowDecimals={false} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ fontSize: 11.5 }} />
        <Line isAnimationActive={false} name="Current period" type="monotone" dataKey="current" stroke="#2a78d6" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
        <Line isAnimationActive={false} name="Comparison period" type="monotone" dataKey="comparison" stroke="#898781" strokeWidth={1.5} strokeDasharray="5 4" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Sentiment mix over time. Positive/negative use the reserved status hues (state, not series); text legend always on. */
export function SentimentTrend({ days, height = 220 }: { days: DayPoint[]; height?: number }) {
  if (!days.some((d) => d.calls > 0)) return <EmptyState message="No analysed calls in this period." />;
  const data = days.map((d) => ({
    label: d.label,
    Positive: d.calls ? Math.round((d.positive / d.calls) * 100) : null,
    Negative: d.calls ? Math.round((d.negative / d.calls) * 100) : null,
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="label" {...AXIS} interval="preserveStartEnd" minTickGap={40} />
        <YAxis {...AXIS} unit="%" domain={[0, 100]} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${v}% of day's analysed calls`]} />
        <Legend wrapperStyle={{ fontSize: 11.5 }} />
        <Line isAnimationActive={false} name="Positive %" type="monotone" dataKey="Positive" stroke="#0ca30c" strokeWidth={2} dot={false} connectNulls />
        <Line isAnimationActive={false} name="Negative %" type="monotone" dataKey="Negative" stroke="#d03b3b" strokeWidth={2} dot={false} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  );
}

export interface ScatterPoint { name: string; x: number; y: number; n: number }

/** Performance relationship scatter (e.g. agent quality vs conversion). */
export function RelationScatter({ points, xLabel, yLabel, xUnit = '', yUnit = '%', height = 260, onPoint }: {
  points: ScatterPoint[]; xLabel: string; yLabel: string; xUnit?: string; yUnit?: string; height?: number; onPoint?: (name: string) => void;
}) {
  if (points.length < 2) return <EmptyState message="Not enough segments with sufficient sample size for this comparison." />;
  const avgX = points.reduce((s, p) => s + p.x, 0) / points.length;
  const avgY = points.reduce((s, p) => s + p.y, 0) / points.length;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 10, right: 20, left: -8, bottom: 6 }}>
        <CartesianGrid stroke="#e1e0d9" />
        <XAxis type="number" dataKey="x" name={xLabel} {...AXIS} domain={['auto', 'auto']} unit={xUnit}
          label={{ value: xLabel, position: 'insideBottom', offset: -4, fontSize: 11, fill: '#52514e' }} />
        <YAxis type="number" dataKey="y" name={yLabel} {...AXIS} domain={['auto', 'auto']} unit={yUnit} />
        <ReferenceLine x={avgX} stroke="#c3c2b7" strokeDasharray="4 4" />
        <ReferenceLine y={avgY} stroke="#c3c2b7" strokeDasharray="4 4" />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ strokeDasharray: '3 3' }}
          formatter={(value, name) => [`${typeof value === 'number' ? value.toFixed(1) : value}${name === xLabel ? xUnit : yUnit}`, String(name)]}
          labelFormatter={() => ''}
          content={({ payload }) => {
            const p = payload?.[0]?.payload as ScatterPoint | undefined;
            if (!p) return null;
            return (
              <div style={{ ...TOOLTIP_STYLE, padding: '8px 10px' }}>
                <strong>{p.name}</strong>
                <div>{xLabel}: {p.x.toFixed(1)}{xUnit}</div>
                <div>{yLabel}: {p.y.toFixed(1)}{yUnit}</div>
                <div style={{ color: '#898781' }}>n = {p.n} calls</div>
              </div>
            );
          }} />
        <Scatter isAnimationActive={false} data={points} fill="#2a78d6" onClick={onPoint ? (d) => onPoint((d as unknown as ScatterPoint).name) : undefined} cursor={onPoint ? 'pointer' : undefined}>
          <LabelList dataKey="name" position="top" style={{ fontSize: 10, fill: '#52514e' }} />
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}

/** Within-call sentiment journey: opening → mid → closing (text-based scores). */
export function SentimentJourney({ opening, mid, closing }: { opening: number; mid: number; closing: number }) {
  const data = [
    { stage: 'Opening', score: opening },
    { stage: 'Mid-call', score: mid },
    { stage: 'Closing', score: closing },
  ];
  return (
    <ResponsiveContainer width="100%" height={150}>
      <LineChart data={data} margin={{ top: 10, right: 16, left: -18, bottom: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="stage" {...AXIS} />
        <YAxis {...AXIS} domain={[-1, 1]} ticks={[-1, 0, 1]} />
        <ReferenceLine y={0} stroke="#c3c2b7" />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${Number(v).toFixed(2)} (−1 to +1, text-based)`, 'Sentiment']} />
        <Line isAnimationActive={false} type="monotone" dataKey="score" stroke="#2a78d6" strokeWidth={2} dot={{ r: 4, fill: '#2a78d6' }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** 100% horizontal sentiment split bar with labels (not colour-alone). */
export function SentimentSplit({ positive, neutral, negative }: { positive: number; neutral: number; negative: number }) {
  const total = positive + neutral + negative;
  if (!total) return <EmptyState message="No analysed calls." />;
  const seg = (n: number, color: string, label: string) => (
    n > 0 && <div title={`${label}: ${n} calls (${((n / total) * 100).toFixed(0)}%)`}
      style={{ width: `${(n / total) * 100}%`, background: color, height: 18, borderRadius: 3 }} />
  );
  return (
    <div>
      <div style={{ display: 'flex', gap: 2 }}>
        {seg(positive, '#0ca30c', 'Positive')}
        {seg(neutral, '#c3c2b7', 'Neutral')}
        {seg(negative, '#d03b3b', 'Negative')}
      </div>
      <div className="legend-row">
        <span><span className="swatch" style={{ background: '#0ca30c' }} />Positive {((positive / total) * 100).toFixed(0)}% ({positive})</span>
        <span><span className="swatch" style={{ background: '#c3c2b7' }} />Neutral {((neutral / total) * 100).toFixed(0)}% ({neutral})</span>
        <span><span className="swatch" style={{ background: '#d03b3b' }} />Negative {((negative / total) * 100).toFixed(0)}% ({negative})</span>
      </div>
    </div>
  );
}
