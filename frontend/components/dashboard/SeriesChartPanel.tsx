'use client';

import SectionCard from '@/components/dashboard/SectionCard';
import { TimeSeriesPoint } from '@/types/dashboard';
import {
  Area,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ComposedChart,
} from 'recharts';

interface SeriesChartPanelProps {
  title: string;
  subtitle: string;
  data: TimeSeriesPoint[];
  color: string;
  valueFormatter?: (value: number) => string;
  chartType?: 'line' | 'area';
}

export default function SeriesChartPanel({
  title,
  subtitle,
  data,
  color,
  valueFormatter = (value) => value.toFixed(3),
  chartType = 'line',
}: SeriesChartPanelProps) {
  return (
    <SectionCard title={title} subtitle={subtitle}>
      <div className="h-56 w-full">
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 4" stroke="rgba(129, 140, 153, 0.16)" />
            <XAxis
              dataKey="time"
              tick={{ fill: '#8a97a8', fontSize: 11 }}
              minTickGap={20}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: '#8a97a8', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => valueFormatter(Number(v))}
            />
            <Tooltip
              cursor={{ stroke: 'rgba(138, 151, 168, 0.35)' }}
              contentStyle={{
                backgroundColor: 'var(--bg-panel)',
                border: '1px solid var(--border-primary)',
                borderRadius: '10px',
                color: 'var(--text-strong)',
              }}
              formatter={(value: number) => valueFormatter(value)}
            />
            {chartType === 'area' ? (
              <Area
                dataKey="value"
                type="monotone"
                stroke={color}
                fill={color}
                fillOpacity={0.15}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            ) : (
              <Line
                dataKey="value"
                type="monotone"
                stroke={color}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </SectionCard>
  );
}
