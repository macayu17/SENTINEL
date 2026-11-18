/**
 * Launch details the market_update feed does not carry (preset, seed, agent count).
 * /start writes them on launch; the dashboard reads them. Per-tab, best effort.
 */
export interface RunMeta {
  preset: string;
  presetName: string;
  scenario: string;
  seed: number | null;
  agents: number;
  latency: string;
  oracle: boolean;
}

const KEY = 'sentinel-run';

export function saveRunMeta(meta: RunMeta): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(meta));
  } catch {
    // storage blocked: the dashboard falls back to what the feed provides
  }
}

export function loadRunMeta(): RunMeta | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as RunMeta) : null;
  } catch {
    return null;
  }
}
