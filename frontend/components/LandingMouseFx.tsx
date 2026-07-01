'use client';

import { useEffect } from 'react';

export default function LandingMouseFx() {
  useEffect(() => {
    if (!window.matchMedia('(pointer: fine)').matches) {
      return;
    }

    let frame = 0;

    const move = (event: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        document.documentElement.style.setProperty('--landing-mouse-x', `${event.clientX}px`);
        document.documentElement.style.setProperty('--landing-mouse-y', `${event.clientY}px`);
        document.documentElement.style.setProperty(
          '--landing-drift-x',
          `${(event.clientX / window.innerWidth - 0.5) * 18}px`,
        );
        document.documentElement.style.setProperty(
          '--landing-drift-y',
          `${(event.clientY / window.innerHeight - 0.5) * 14}px`,
        );
      });
    };

    window.addEventListener('pointermove', move, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('pointermove', move);
    };
  }, []);

  return null;
}
