import axios from 'axios'

// Use relative URLs so that Vite's proxy handles routing in dev mode,
// and the production server can serve the frontend and proxy /api itself.
// VITE_API_URL can be set to an absolute URL only when the frontend is
// hosted on a completely different origin from the backend.
const API_BASE = import.meta.env.VITE_API_URL || ''

export const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

export const trafficApi = {
  getCurrent: () => api.get('/traffic/current'),
  getSummary: () => api.get('/traffic/summary'),
  getRoad: (roadId: string) => api.get(`/traffic/${roadId}`),
  getHistory: (roadId: string) => api.get(`/traffic/history/${roadId}`),
}

export const routingApi = {
  calculate: (params: { origin: string; destination: string; algorithm?: string }) => 
    api.get('/routes/calculate', { params }),
  getRoute: (routeId: string) => api.get(`/routes/${routeId}`),
  calculateAll: (params: { origin: string; destination: string }) => 
    api.get('/routes/calculate-all', { params }),
  recommend: (params: { origin: string; destination: string }) => 
    api.get('/routes/recommend', { params }),
}

export const simulationApi = {
  start: (data: any) => api.post('/simulation/start', data),
  pause: () => api.post('/simulation/pause'),
  resume: () => api.post('/simulation/resume'),
  reset: () => api.post('/simulation/reset'),
  setSpeed: (speed: number) => api.post('/simulation/speed', { speed_multiplier: speed }),
  runScenario: (data: any) => api.post('/simulation/scenario', data),
  getStatus: () => api.get('/simulation/status'),
}

export const incidentsApi = {
  getActive: () => api.get('/incidents/active'),
  create: (data: any) => api.post('/incidents', data),
  update: (incidentId: string, data: any) => api.patch(`/incidents/${incidentId}`, data),
  resolve: (incidentId: string) => api.delete(`/incidents/${incidentId}`),
}

export const predictionsApi = {
  getRoad: (roadId: string) => api.get(`/predictions/${roadId}`),
  getBatch: (data: any) => api.post('/predictions/batch', data),
  getModels: () => api.get('/predictions/models'),
}

export const analyticsApi = {
  getOverview: () => api.get('/analytics/overview'),
  getCongestion: () => api.get('/analytics/congestion'),
  getRouting: () => api.get('/analytics/routing'),
  getPredictions: () => api.get('/analytics/predictions'),
}

export const explanationsApi = {
  generate: (data: any) => api.post('/explanations/generate', data),
  getModels: () => api.get('/explanations/models'),
  getHealth: () => api.get('/explanations/health'),
  testFallback: () => api.post('/explanations/test-fallback'),
}