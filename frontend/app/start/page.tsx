'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import AppHeader from '@/components/ui/AppHeader';
import { Meter, Segmented, StatusDot, Switch } from '@/components/ui/primitives';
import { api, type LatencyMode, type SandboxPreset, type SandboxScenario } from '@/lib/api-client';
import { num } from '@/lib/format';
import { saveRunMeta } from '@/lib/run-meta';
import { getApiBaseUrl } from '@/lib/runtime-config';
import { useMarketStore } from '@/store/market-store';

const LATENCY_HELP: Record<LatencyMode, string> = {
  zero: 'No delay. Every order reaches the exchange instantly; useful for debugging strategy logic.',
  deterministic: 'Fixed one-way delay per tier: HFT 1 μs (co-located) up to retail and noise traders in milliseconds.',
  cubic: 'Each tier’s delay plus heavy-tailed congestion jitter, bounded at 50 ms.',
};

const LATENCIES: Array<{ value: LatencyMode; label: string }> = [
  { value: 'zero', label: 'zero' },
  { value: 'deterministic', label: 'deterministic' },
  { value: 'cubic', label: 'cubic' },
];

const clamp = (value: number, fallback: number, min: number, max: number) =>
  Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback;

const total = (preset: SandboxPreset) => Object.values(preset.agents).reduce((sum, n) => sum + Math.max(0, n), 0);
const times = (value: number) => `${num(value, value % 1 ? 2 : 1)}×`;

function Section({ id, title, aside, children }: { id: string; title: string; aside?: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3 rounded-panel bg-ink-2 p-[18px]">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={id} className="m-0 text-[15px] font-semibold">{title}</h2>
        {aside ? <span className="text-xs text-fg-muted">{aside}</span> : null}
      </div>
      {children}
    </section>
  );
}

export default function StartPage() {
  const router = useRouter();
  const resetSimulationData = useMarketStore((s) => s.resetSimulationData);
  const setSimulationRunning = useMarketStore((s) => s.setSimulationRunning);
  const [presets, setPresets] = useState<Record<string, SandboxPreset>>({});
  const [scenarios, setScenarios] = useState<SandboxScenario[]>([]);
  const [preset, setPreset] = useState('balanced');
  const [scenario, setScenario] = useState('normal');
  const [latency, setLatency] = useState<LatencyMode>('deterministic');
  const [oracle, setOracle] = useState(false);
  const [initialPrice, setInitialPrice] = useState('100.00');
  const [seed, setSeed] = useState('');
  const [speed, setSpeed] = useState('1');
  const [backend, setBackend] = useState<'checking' | 'ready' | 'running' | 'offline'>('checking');
  const [error, setError] = useState('');
  const [launching, setLaunching] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getSandboxPresets(), api.getSandboxScenarios(), api.health()])
      .then(([nextPresets, nextScenarios, health]) => {
        if (cancelled) return;
        const first = nextPresets.balanced ? 'balanced' : Object.keys(nextPresets)[0];
        setPresets(nextPresets);
        setScenarios(nextScenarios.scenarios);
        setPreset(first);
        setLatency(nextPresets[first].latency);
        setOracle(nextPresets[first].oracle);
        setBackend(health.simulation_active ? 'running' : 'ready');
      })
      .catch(() => { if (!cancelled) setBackend('offline'); });
    return () => { cancelled = true; };
  }, []);

  const selected = presets[preset];
  const selectedScenario = scenarios.find((s) => s.name === scenario);
  const composition = useMemo(() => Object.entries(selected?.agents ?? {}), [selected]);
  const largest = Math.max(1, ...composition.map(([, n]) => n));
  const host = useMemo(() => { try { return new URL(getApiBaseUrl()).host; } catch { return 'backend'; } }, []);

  const pickPreset = (key: string) => {
    setPreset(key);
    setLatency(presets[key].latency);
    setOracle(presets[key].oracle);
  };

  const launch = async () => {
    setLaunching(true);
    setError('');
    const seedValue = seed.trim() === '' ? undefined : Math.trunc(Number(seed));
    try {
      const response = await api.createSandbox({
        preset,
        scenario,
        initial_price: clamp(Number(initialPrice), 100, 0.01, 1_000_000),
        oracle_enabled: oracle,
        latency_mode: latency,
        speed: clamp(Number(speed), 1, 0.1, 20),
        ...(seedValue !== undefined && Number.isFinite(seedValue) ? { seed: seedValue } : {}),
      });
      // The create response also carries the seed the backend chose.
      const chosenSeed = (response as { seed?: number }).seed ?? seedValue ?? null;
      saveRunMeta({ preset, presetName: selected?.name ?? preset, scenario, seed: chosenSeed, agents: response.agents, latency, oracle });
      resetSimulationData();
      setSimulationRunning(true);
      router.push('/dashboard');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Launch failed.');
      setLaunching(false);
    }
  };

  const status = {
    checking: 'Checking backend…',
    ready: `Backend ready · ${host}`,
    running: `Session running · ${host}`,
    offline: `Backend offline · ${host}`,
  }[backend];

  return (
    <div className="min-h-screen bg-ink text-fg [font-variant-numeric:tabular-nums]">
      <AppHeader context={<span className="text-fg-muted">New simulation session</span>} actions={<StatusDot live={backend === 'ready' || backend === 'running'} label={status} />} />

      <main className="mx-auto flex max-w-[1320px] flex-wrap items-start gap-4 px-4 pb-14 pt-7 sm:px-6">
        <div className="flex min-w-0 flex-[999_1_640px] flex-col gap-4">
          <div className="flex flex-col gap-1 pb-2">
            <h1 className="m-0 font-display text-[34px] font-semibold tracking-[-0.02em]">Configure a run</h1>
            <p className="m-0 text-fg-muted">Choose an agent population, a market scenario and the run parameters. The same seed reproduces the same run.</p>
          </div>

          <Section id="preset" title="1 · Agent preset" aside="GET /api/sandbox/presets">
            <div role="radiogroup" aria-labelledby="preset" className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 170px), 1fr))' }}>
              {Object.entries(presets).map(([key, item]) => {
                const on = key === preset;
                return (
                  <button key={key} type="button" role="radio" aria-checked={on} onClick={() => pickPreset(key)}
                    className={`flex flex-col gap-0.5 rounded-xl border p-3.5 text-left ${on ? 'border-accent bg-accent-wash' : 'border-line bg-ink'}`}>
                    <span className="font-bold">{item.name}</span>
                    <span className="font-display text-[26px] font-semibold">{total(item)} agents</span>
                    <span className="text-xs text-fg-muted">oracle {item.oracle ? 'on' : 'off'} · latency {item.latency}</span>
                  </button>
                );
              })}
              {!Object.keys(presets).length && <p className="m-0 text-fg-muted">{backend === 'offline' ? 'Presets load from the backend once it is running.' : 'Loading presets…'}</p>}
            </div>
          </Section>

          <Section id="scenario" title="2 · Market scenario" aside="multipliers vs. normal session">
            <div className="overflow-x-auto">
              <table role="radiogroup" aria-labelledby="scenario" className="data-table min-w-[680px]">
                <thead><tr><th scope="col">Scenario</th><th scope="col" className="num">Spread</th><th scope="col" className="num">Volatility</th><th scope="col" className="num">Seed depth</th><th scope="col" className="num">Order TTL</th><th scope="col">Notes</th></tr></thead>
                <tbody>
                  {scenarios.map((item) => {
                    const on = item.name === scenario;
                    return (
                      <tr key={item.name} role="radio" aria-checked={on} tabIndex={0} onClick={() => setScenario(item.name)}
                        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setScenario(item.name); } }}
                        className="cursor-pointer" style={{ background: on ? 'var(--accent-wash)' : undefined }}>
                        <td>
                          <span className="flex items-center gap-2.5">
                            <span aria-hidden="true" className="inline-flex size-3.5 items-center justify-center rounded-full border-[1.5px]" style={{ borderColor: on ? 'var(--accent)' : 'var(--line-dim)' }}>
                              <span className="size-1.5 rounded-full" style={{ background: on ? 'var(--accent)' : 'transparent' }} />
                            </span>
                            <span className="flex flex-col"><span className="font-semibold">{item.label}</span><span className="text-[11px] text-fg-muted">{item.name}</span></span>
                          </span>
                        </td>
                        <td className="num">{times(item.spread_multiplier)}</td>
                        <td className="num">{times(item.oracle_sigma_multiplier)}</td>
                        <td className="num">{times(item.seed_depth_multiplier)}</td>
                        <td className="num">{num(item.order_ttl_seconds, 0)} s</td>
                        <td className="text-fg-muted">{item.description}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Section>

          <Section id="params" title="3 · Run parameters">
            <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 160px), 1fr))' }}>
              <label className="flex flex-col gap-1.5 text-xs text-fg-muted">Initial price
                <input className="field" type="number" min="0.01" step="0.01" value={initialPrice} onChange={(e) => setInitialPrice(e.target.value)} />
              </label>
              <label className="flex flex-col gap-1.5 text-xs text-fg-muted">Random seed
                <input className="field" type="number" step="1" placeholder="random" value={seed} onChange={(e) => setSeed(e.target.value)} />
              </label>
              <label className="flex flex-col gap-1.5 text-xs text-fg-muted">Speed multiplier
                <input className="field" type="number" min="0.1" max="20" step="0.25" value={speed} onChange={(e) => setSpeed(e.target.value)} />
              </label>
              <label className="flex flex-col gap-1.5 text-xs text-fg-muted">Duration (s)
                <input className="field opacity-60" type="text" readOnly value="server default" aria-describedby="duration-note" />
                <span id="duration-note" className="text-[11px]">Set by SIMULATION_DURATION on the backend.</span>
              </label>
            </div>
            <div className="flex flex-col gap-2">
              <span className="text-xs text-fg-muted">Latency model</span>
              <Segmented label="Latency model" options={LATENCIES} value={latency} onChange={setLatency} />
              <span className="text-[13px] text-fg-2">{LATENCY_HELP[latency]}</span>
            </div>
            <div className="flex items-center justify-between gap-4 border-t border-line pt-3.5">
              <span className="flex flex-col">
                <span className="font-semibold">Fundamental value oracle</span>
                <span className="text-[13px] text-fg-muted">Gives informed agents a noisy read of the latent fair value; enables mispricing measurements.</span>
              </span>
              <Switch label="Fundamental value oracle" checked={oracle} onChange={setOracle} />
            </div>
          </Section>
        </div>

        <aside aria-labelledby="summary" className="flex min-w-0 flex-[1_1_340px] flex-col gap-3.5 rounded-panel bg-ink-2 p-[18px] lg:sticky lg:top-4">
          <h2 id="summary" className="m-0 text-[15px] font-semibold">Run configuration</h2>
          <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[13px]">
            {[
              ['Preset', selected ? `${selected.name} · ${total(selected)}` : '—'],
              ['Scenario', scenario],
              ['Latency', latency],
              ['Oracle', oracle ? 'on' : 'off'],
              ['Seed', seed.trim() || 'random'],
            ].map(([label, value]) => (
              <div key={label} className="contents"><dt className="text-fg-muted">{label}</dt><dd className="m-0 text-right font-semibold">{value}</dd></div>
            ))}
          </dl>
          <div className="flex flex-col gap-1.5 border-t border-line pt-3">
            <span className="text-xs text-fg-muted">Agent composition</span>
            {composition.map(([type, count]) => (
              <div key={type} className="grid grid-cols-[120px_1fr_36px] items-center gap-2.5 text-[13px]">
                <span className="truncate">{type}</span>
                <Meter value={count / largest} color={type === 'Spoofing' ? 'var(--accent)' : 'var(--fg-2)'} />
                <span className="text-right font-semibold">{count}</span>
              </div>
            ))}
          </div>
          {selectedScenario?.enable_spoofing && (
            <p className="m-0 rounded-[10px] bg-alert-bg px-3 py-2.5 text-[13px] text-alert-fg">This scenario adds Spoofing agents (quote layering) on top of the preset.</p>
          )}
          {selectedScenario && selectedScenario.institutional_multiplier !== 1 && (
            <p className="m-0 text-[13px] text-fg-muted">Institutional activity × {num(selectedScenario.institutional_multiplier, 2)} in this scenario.</p>
          )}
          {backend === 'running' && <p className="m-0 text-[13px] text-fg-muted">A session is already running. Launching replaces it.</p>}
          {error && <p role="alert" className="m-0 text-[13px] text-alert-fg">{error}</p>}
          <button type="button" onClick={launch} disabled={launching || backend === 'offline' || !selected}
            className="btn btn-accent min-h-12 rounded-xl text-[15px] font-bold">
            {launching ? 'Launching…' : 'Launch session'}
          </button>
          <span className="text-center text-xs text-fg-muted">POST /api/sandbox/create</span>
        </aside>
      </main>
    </div>
  );
}
