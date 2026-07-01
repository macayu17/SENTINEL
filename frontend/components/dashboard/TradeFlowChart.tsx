'use client';

import SectionCard from '@/components/dashboard/SectionCard';
import { TradeFlowPoint } from '@/types/dashboard';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

interface TradeFlowChartProps {
  data: TradeFlowPoint[];
}

export default function TradeFlowChart({ data }: TradeFlowChartProps) {
  return (
    <SectionCard title="Trade Flow" subtitle="Buy and sell aggressor volume over recent steps">
      <div className="h-56 w-full">
        <ResponsiveContainer>
          <BarChart data={data} barGap={2} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 4" stroke="rgba(129, 140, 153, 0.16)" />
            <XAxis
              dataKey="time"
              tick={{ fill: '#8a97a8', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              minTickGap={22}
            />
            <YAxis tick={{ fill: '#8a97a8', fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--bg-panel)',
                border: '1px solid var(--border-primary)',
                borderRadius: '10px',
                color: 'var(--text-strong)',
              }}
            />
            <Bar dataKey="buyVolume" fill="#63d4a4" radius={[4, 4, 0, 0]} name="Buy Volume" />
            <Bar dataKey="sellVolume" fill="#f28686" radius={[4, 4, 0, 0]} name="Sell Volume" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </SectionCard>
  );
}
