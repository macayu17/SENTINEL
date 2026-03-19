const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class SentinelAPI {
  private baseUrl: string;

  constructor(baseUrl: string = API_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });
    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }
    return response.json();
  }

  async health() {
    return this.request<{ status: string; simulation_active: boolean; connected_clients: number }>('/api/health');
  }

  async startSimulation() {
    return this.request<{ status: string; agents: number; initial_price: number }>('/api/simulation/start', { method: 'POST' });
  }

  async stopSimulation() {
    return this.request<{ status: string }>('/api/simulation/stop', { method: 'POST' });
  }

  async setSimulationMode(mode: 'SANDBOX' | 'LIVE_SHADOW') {
    return this.request<{ status: string; mode: string }>('/api/simulation/mode', {
      method: 'POST',
      body: JSON.stringify({ mode }),
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
