'use client';
import { useEffect, useRef } from 'react';

export default function CharacterField() {
  const ref = useRef<HTMLPreElement>(null);
  useEffect(() => {
    const media = matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    const draw = () => {
      if (!ref.current || document.hidden) return;
      if (!media.matches) frame += 0.06;
      const chars = ' .:+*#';
      let output = '';
      for (let row = 0; row < 25; row++) {
        for (let col = 0; col < 48; col++) {
          const x = col / 47, y = row / 24;
          const ridge = Math.exp(-Math.pow((x - .5 - .1 * Math.sin(y * 5 + frame)) / .19, 2));
          const density = ridge * (.55 + .45 * Math.sin(y * 13 - x * 8 + frame));
          output += chars[Math.min(5, Math.floor(density * 6))];
        }
        output += '\n';
      }
      ref.current.textContent = output;
    };
    draw();
    const timer = window.setInterval(draw, 120);
    return () => clearInterval(timer);
  }, []);
  return <pre className="hero-field" ref={ref} aria-hidden="true" />;
}
