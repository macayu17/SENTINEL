'use client';

import type { CSSProperties, PointerEvent } from 'react';
import { useState } from 'react';

const COLUMNS = 14;
const ROWS = 8;
const CELLS = Array.from({ length: COLUMNS * ROWS }, (_, index) => index);

export default function RippleField({ className = '' }: { className?: string }) {
  const [origin, setOrigin] = useState<number | null>(null);

  const moveGlow = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty('--ripple-x', `${event.clientX - rect.left}px`);
    event.currentTarget.style.setProperty('--ripple-y', `${event.clientY - rect.top}px`);
  };

  const startRipple = (event: PointerEvent<HTMLDivElement>) => {
    const cell = (event.target as HTMLElement).closest<HTMLElement>('[data-ripple-cell]');
    if (cell) setOrigin(Number(cell.dataset.rippleCell));
  };

  return <div className={`ripple-field ${className}`} aria-hidden="true" onPointerMove={moveGlow} onClick={startRipple}>
    {CELLS.map((index) => {
      const distance = origin === null ? 99 : Math.abs(index % COLUMNS - origin % COLUMNS) + Math.abs(Math.floor(index / COLUMNS) - Math.floor(origin / COLUMNS));
      return <span
        key={index}
        data-ripple-cell={index}
        data-active={distance <= 4 || undefined}
        onAnimationEnd={() => { if (distance === 4) setOrigin(null); }}
        style={{ '--ripple-delay': `${distance * 32}ms` } as CSSProperties}
      />;
    })}
  </div>;
}
