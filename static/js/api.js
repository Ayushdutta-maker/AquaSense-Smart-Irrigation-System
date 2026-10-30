/**
 * AquaSense API Client Module
 * Communicates with FastAPI backend with structured error handling and auth headers.
 */

const API = {
  baseUrl: '',

  async request(endpoint, options = {}) {
    const defaultHeaders = {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    };

    const config = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers
      }
    };

    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, config);
      if (!response.ok) {
        let errorData;
        try {
          errorData = await response.json();
        } catch {
          errorData = { detail: `HTTP error ${response.status}: ${response.statusText}` };
        }
        const errorMsg = errorData.detail || errorData.message || 'Request failed';
        throw new Error(errorMsg);
      }
      return await response.json();
    } catch (err) {
      console.warn(`[API Error] ${endpoint}:`, err.message);
      throw err;
    }
  },

  // 1. System Status
  async getStatus() {
    return this.request('/api/status');
  },

  // 2. Latest Reading
  async getLatestReading() {
    return this.request('/api/readings/latest');
  },

  // 3. Historical Telemetry for Charts
  async getHistory(timeframe = '24h', limit = 100) {
    return this.request(`/api/readings/history?timeframe=${timeframe}&limit=${limit}`);
  },

  // 4. Irrigation Settings
  async getSettings() {
    return this.request('/api/settings');
  },

  async updateSettings(settings) {
    return this.request('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(settings)
    });
  },

  // 5. Hardware Commands
  async sendCommand(commandPayload) {
    return this.request('/api/commands', {
      method: 'POST',
      body: JSON.stringify(commandPayload)
    });
  },

  // 6. Irrigation Events
  async getEvents(filters = {}) {
    const params = new URLSearchParams();
    if (filters.event_type) params.append('event_type', filters.event_type);
    if (filters.operating_mode) params.append('operating_mode', filters.operating_mode);
    if (filters.limit) params.append('limit', filters.limit);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return this.request(`/api/events${qs}`);
  },

  // 7. Alerts
  async getAlerts() {
    return this.request('/api/alerts');
  },

  async acknowledgeAlert(alertId) {
    return this.request(`/api/alerts/${alertId}/ack`, {
      method: 'POST'
    });
  },

  // 8. Testing Simulator
  async getSimulatorStatus() {
    return this.request('/api/simulator/status');
  },

  async toggleSimulator(active) {
    return this.request(`/api/simulator/toggle?active=${active}`, {
      method: 'POST'
    });
  },

  async stepSimulator(forceRain = null, forceDry = null) {
    const params = new URLSearchParams();
    if (forceRain !== null) params.append('force_rain', forceRain);
    if (forceDry !== null) params.append('force_dry', forceDry);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return this.request(`/api/simulator/step${qs}`, {
      method: 'POST'
    });
  },

  // 9. Firebase Cloud Sync
  async getFirebaseConfig() {
    return this.request('/api/firebase/config');
  },

  async getFirebaseStatus() {
    return this.request('/api/firebase/status');
  },

  async syncFirebase() {
    return this.request('/api/firebase/sync', {
      method: 'POST'
    });
  }
};

window.API = API;
