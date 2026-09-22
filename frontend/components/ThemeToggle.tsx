'use client';
import { useEffect, useRef, useState } from 'react';

interface ThemeWave {
  id: number;
  x: number;
  y: number;
  light: boolean;
}

export default function ThemeToggle({ className = '' }: { className?: string }) {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [wave, setWave] = useState<ThemeWave | null>(null);
  const waveTimer = useRef<number | null>(null);
  useEffect(() => {
    let saved = 'light';
    try { saved = localStorage.getItem('sentinel-theme') || 'light'; } catch { /* Storage can be disabled. */ }
    const next = saved === 'dark' ? 'dark' : 'light';
    setTheme(next);
    document.documentElement.classList.toggle('theme-dark', next === 'dark');
    document.documentElement.classList.toggle('theme-light', next === 'light');
  }, []);
  useEffect(() => () => {
    if (waveTimer.current !== null) window.clearTimeout(waveTimer.current);
  }, []);
  const toggle = (event: React.MouseEvent<HTMLButtonElement>) => {
    const next = theme === 'light' ? 'dark' : 'light';
    setWave({ id: Date.now(), x: event.clientX, y: event.clientY, light: next === 'light' });
    setTheme(next);
    document.documentElement.classList.toggle('theme-dark', next === 'dark');
    document.documentElement.classList.toggle('theme-light', next === 'light');
    try { localStorage.setItem('sentinel-theme', next); } catch { /* Theme still works without persistence. */ }
    if (waveTimer.current !== null) window.clearTimeout(waveTimer.current);
    waveTimer.current = window.setTimeout(() => setWave(null), 850);
  };
  return <>
    <button type="button" className={`text-button ${className}`} onClick={toggle} aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}>{theme === 'light' ? 'Dark mode' : 'Light mode'}</button>
    {wave ? <span key={wave.id} className={`theme-wave ${wave.light ? 'theme-wave--light' : 'theme-wave--dark'}`} style={{ left: wave.x, top: wave.y }} aria-hidden="true" /> : null}
  </>;
}
