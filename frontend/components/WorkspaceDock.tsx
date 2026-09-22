'use client';

import type { CSSProperties } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, BarChart3, BookOpen, FileText, FlaskConical, Gauge, ListTree, ShieldAlert, Users, type LucideIcon } from 'lucide-react';
import { motion, useReducedMotion } from 'motion/react';

type DockMode = 'simulation' | 'docs';
interface DockItem { id: string; label: string; icon: LucideIcon }

function DockLink({ item, active, mouseX, reduceMotion, onSelect }: { item: DockItem; active: boolean; mouseX: number | null; reduceMotion: boolean | null; onSelect: () => void }) {
  const ref = useRef<HTMLAnchorElement>(null);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    if (reduceMotion || mouseX === null || !ref.current) { setScale(1); return; }
    const rect = ref.current.getBoundingClientRect();
    const distance = Math.abs(mouseX - (rect.left + rect.width / 2));
    setScale(distance < 140 ? 1 + 0.18 * Math.cos((distance / 140) * (Math.PI / 2)) : 1);
  }, [mouseX, reduceMotion]);

  return <motion.a ref={ref} href={`#${item.id}`} className={active ? 'is-active' : ''} aria-current={active ? 'location' : undefined} onClick={onSelect} animate={{ scale }} whileHover={reduceMotion ? undefined : { y: -4 }} whileTap={reduceMotion ? undefined : { scale: 0.94 }} transition={{ type: 'spring', stiffness: 420, damping: 30 }}>
    {active ? <motion.span className="workspace-dock-indicator" layoutId="workspace-dock-active" transition={reduceMotion ? { duration: 0 } : { type: 'spring', stiffness: 430, damping: 34 }} aria-hidden="true" /> : null}
    <item.icon size={17} strokeWidth={1.7} />
    <span className="workspace-dock-label">{item.label}</span>
  </motion.a>;
}

const SIMULATION_ITEMS: DockItem[] = [
  { id: 'market', label: 'Market', icon: BarChart3 },
  { id: 'signals', label: 'Signals', icon: Activity },
  { id: 'agents', label: 'Agents', icon: Users },
  { id: 'execution', label: 'Execution', icon: ListTree },
  { id: 'experiment', label: 'Experiment', icon: FlaskConical },
];
const DOC_ITEMS: DockItem[] = [
  { id: 'quick-start', label: 'Start', icon: Gauge },
  { id: 'modes', label: 'Modes', icon: Activity },
  { id: 'market', label: 'Market', icon: BarChart3 },
  { id: 'signals', label: 'Signals', icon: Activity },
  { id: 'reports', label: 'Reports', icon: FileText },
  { id: 'warnings', label: 'Warnings', icon: ShieldAlert },
  { id: 'glossary', label: 'Glossary', icon: BookOpen },
];

export default function WorkspaceDock({ mode }: { mode: DockMode }) {
  const reduceMotion = useReducedMotion();
  const [mouseX, setMouseX] = useState<number | null>(null);
  const items = useMemo(() => mode === 'docs' ? DOC_ITEMS : SIMULATION_ITEMS, [mode]);
  const [active, setActive] = useState(items[0].id);

  useEffect(() => {
    const fromHash = window.location.hash.slice(1);
    if (items.some((item) => item.id === fromHash)) setActive(fromHash);
    const sections = items.map((item) => document.getElementById(item.id)).filter(Boolean) as HTMLElement[];
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (visible) setActive(visible.target.id);
    }, { rootMargin: '-18% 0px -68%', threshold: [0, 0.2, 0.6] });
    sections.forEach((section) => observer.observe(section));
    const syncHash = () => setActive(window.location.hash.slice(1) || items[0].id);
    window.addEventListener('hashchange', syncHash);
    return () => { observer.disconnect(); window.removeEventListener('hashchange', syncHash); };
  }, [items]);

  const activeIndex = Math.max(0, items.findIndex((item) => item.id === active));
  return <motion.nav layout className={`workspace-dock workspace-dock--${mode}`} aria-label={mode === 'docs' ? 'Documentation chapters' : 'Dashboard sections'} onMouseMove={(event) => setMouseX(event.clientX)} onMouseLeave={() => setMouseX(null)} style={{ '--dock-index': activeIndex, '--dock-count': items.length } as CSSProperties}>
    {items.map((item) => <DockLink key={item.id} item={item} active={active === item.id} mouseX={mouseX} reduceMotion={reduceMotion} onSelect={() => setActive(item.id)} />)}
  </motion.nav>;
}
