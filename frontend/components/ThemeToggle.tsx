'use client';

import { useEffect, useState } from 'react';

interface Wave {
  id: number;
  x: number;
  y: number;
  light: boolean;
}

export default function ThemeToggle({ className = '' }: { className?: string }) {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    if (typeof window === 'undefined') return 'dark';
    const saved = window.localStorage.getItem('sentinel-theme');
    return saved === 'dark' || saved === 'light' ? saved : 'dark';
  });
  const [wave, setWave] = useState<Wave | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle('theme-light', theme === 'light');
    document.documentElement.classList.toggle('theme-dark', theme === 'dark');
    window.localStorage.setItem('sentinel-theme', theme);
  }, [theme]);

  const toggleTheme = (event: React.MouseEvent<HTMLButtonElement>) => {
    const nextTheme = theme === 'light' ? 'dark' : 'light';
    setWave({
      id: Date.now(),
      x: event.clientX,
      y: event.clientY,
      light: nextTheme === 'light',
    });
    setTheme(nextTheme);
    window.setTimeout(() => setWave(null), 850);
  };

  return (
    <>
      <button
        type="button"
        onClick={toggleTheme}
        className={`theme-toggle ${className}`}
        aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
      >
        <span aria-hidden="true">{theme === 'light' ? '☾' : '☀'}</span>
      </button>
      {wave ? (
        <span
          key={wave.id}
          className={`theme-wave ${wave.light ? 'theme-wave--light' : 'theme-wave--dark'}`}
          style={{ left: wave.x, top: wave.y }}
        />
      ) : null}
    </>
  );
}
