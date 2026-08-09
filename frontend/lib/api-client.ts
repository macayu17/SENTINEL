import { getApiBaseUrl } from '@/lib/runtime-config';
import type {
  SandboxCreateRequest,
  SandboxPreset,
  SandboxScenario,
} from '@/types/api';

export type {
  LatencyMode,
  SandboxCreateRequest,
  SandboxPreset,
  SandboxScenario,
} from '@/types/api';

class SentinelAPI {
  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const baseUrl = getApiBaseUrl();
    const url = `${baseUrl}${path}`;
    let response: Response;

    try {
      response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
      });
    } catch {
      throw new Error(
        `Backend unavailable at ${baseUrl}. Start it with: py -3.11 -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000`,
      );
    }

    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const payload = await response.json() as { detail?: string; error?: string };
        detail = payload.detail ?? payload.error ?? detail;
      } catch {
        // keep status text fallback
      }
      throw new Error(`API error: ${detail}`);
    }
    return response.json();
  }

  async health() {
    return this.request<{
      status: string;
      simulation_active: boolean;
      connected_clients: number;
    }>('/api/health');
  }

  async stopSimulation() {
    return this.request<{ status: string }>('/api/simulation/stop', { method: 'POST' });
  }

  async getSandboxPresets() {
    return this.request<Record<string, SandboxPreset>>('/api/sandbox/presets');
  }

  async getSandboxScenarios() {
    return this.request<{ scenarios: SandboxScenario[] }>('/api/sandbox/scenarios');
  }

  async createSandbox(config: SandboxCreateRequest) {
    return this.request<{
      status: string;
      preset: string;
      agents: number;
      oracle_enabled: boolean;
      speed: number;
      scenario: string;
    }>('/api/sandbox/create', {
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

  async exportSimulation() {
    return this.request<Record<string, unknown>>('/api/simulation/export');
  }
}

export const api = new SentinelAPI();
