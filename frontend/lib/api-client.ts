import { getApiBaseUrl } from '@/lib/runtime-config';

export type SimulationMode = 'SANDBOX' | 'LIVE_SHADOW';
export type LatencyMode = 'zero' | 'deterministic' | 'cubic';

export interface SandboxPreset {
  name: string;
  description: string;
  icon: string;
  agents: Record<string, number>;
  oracle: boolean;
  latency: LatencyMode;
}

export interface SandboxCreateRequest {
  preset: string;
  initial_price: number;
  oracle_enabled: boolean;
  oracle_kappa: number;
  oracle_sigma: number;
  latency_mode: LatencyMode;
  speed: number;
  custom_agents?: Record<string, number> | null;
}

export interface AbidesSandboxCreateRequest {
  initial_price: number;
  oracle_enabled: boolean;
  oracle_kappa: number;
  oracle_sigma: number;
  latency_mode: LatencyMode;
  speed: number;
  market_makers: number;
  noise_agents: number;
  informed_agents: number;
}

class SentinelAPI {
  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const url = `${getApiBaseUrl()}${path}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });
    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText} (${url})`);
    }
    return response.json();
  }

  async health() {
    return this.request<{
      status: string;
      simulation_active: boolean;
      connected_clients: number;
      mode: SimulationMode;
    }>('/api/health');
  }

  async startSimulation() {
    return this.request<{ status: string; agents: number; initial_price: number }>('/api/simulation/start', { method: 'POST' });
  }

  async stopSimulation() {
    return this.request<{ status: string }>('/api/simulation/stop', { method: 'POST' });
  }

  async setSimulationMode(mode: SimulationMode) {
    return this.request<{ status: string; mode: string }>('/api/simulation/mode', {
      method: 'POST',
      body: JSON.stringify({ mode }),
    });
  }

  async getSandboxPresets() {
    return this.request<Record<string, SandboxPreset>>('/api/sandbox/presets');
  }

  async getSandboxCapabilities() {
    return this.request<{ abides: boolean }>('/api/sandbox/capabilities');
  }

  async createSandbox(config: SandboxCreateRequest) {
    return this.request<{
      status: string;
      preset: string;
      agents: number;
      oracle_enabled: boolean;
      speed: number;
    }>('/api/sandbox/create', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async createAbidesSandbox(config: AbidesSandboxCreateRequest) {
    return this.request<{
      status: string;
      engine: 'ABIDES';
      oracle_enabled: boolean;
      speed: number;
      agents: number;
    }>('/api/sandbox/abides/create', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async setSandboxSpeed(speed: number) {
    return this.request<{ speed: number } | { error: string }>('/api/sandbox/speed', {
      method: 'PUT',
      body: JSON.stringify({ speed }),
    });
  }

  async setAbidesSpeed(speed: number) {
    return this.request<{ speed: number } | { error: string }>('/api/sandbox/abides/speed', {
      method: 'PUT',
      body: JSON.stringify({ speed }),
    });
  }

  async getLiquidityPrediction() {
    return this.request('/api/prediction/liquidity');
  }

  async getLargeOrderDetection() {
    return this.request('/api/prediction/large-order');
  }

  async getAgentMetrics() {
    return this.request('/api/agents/metrics');
  }

  async getMarketSnapshot() {
    return this.request('/api/market/snapshot');
  }
}

export const api = new SentinelAPI();
