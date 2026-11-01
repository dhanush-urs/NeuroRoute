export interface TrafficSnapshot {
  road_id: string
  tick: number
  sim_time: string
  vehicle_count: number
  avg_speed_kmh: number | null
  congestion_score: number | null
  congestion_level: CongestionLevel | null
  travel_time_sec: number | null
}

export type CongestionLevel = 'free' | 'moderate' | 'heavy' | 'congested' | 'severe' | 'closed'

export interface TrafficSummary {
  total_roads: number
  total_vehicles: number
  avg_speed_kmh: number | null
  congestion_distribution: Record<CongestionLevel, number>
  active_incidents: number
  timestamp: string
}

export interface RouteRequest {
  origin_node: string
  destination_node: string
  algorithm?: string
  consider_predictions?: boolean
}

export interface RouteResponse {
  id: string
  origin_node: string
  destination_node: string
  algorithm: string
  route_nodes: string[]
  route_edges: string[]
  distance_km: number
  current_eta_sec: number
  predicted_eta_sec: number
  congestion_risk: string
  score: number
  rank: number
  is_recommended: boolean
  calculation_tick: number
  created_at: string
}

export interface RouteScore {
  route_id: string
  edges: string[]
  distance_km: number
  current_eta_sec: number
  predicted_eta_sec: number
  congestion_risk: string
  score: number
  rank: number
  is_recommended: boolean
  explanation_facts: Record<string, any>
}

export interface SimulationStatus {
  id: string
  seed: number
  scenario_name: string | null
  started_at: string
  ended_at: string | null
  speed_multiplier: number
  current_tick: number
  sim_time: string
  status: string
  config: Record<string, any>
}

export interface Incident {
  id: string
  session_id: string
  incident_type: IncidentType
  road_id: string
  severity: number
  start_tick: number
  end_tick: number | null
  capacity_reduction_pct: number
  affected_radius_km: number
  description: string | null
  status: string
  created_at: string
}

export type IncidentType = 'accident' | 'road_closure' | 'road_work' | 'flood' | 'heavy_rain' | 'special_event'

export interface Prediction {
  id: string
  session_id: string
  road_id: string
  prediction_tick: number
  horizon_minutes: number
  predicted_congestion_score: number
  predicted_vehicle_count: number
  predicted_avg_speed_kmh: number
  confidence: number
  model_version: string
  created_at: string
}

export interface ModelInfo {
  model_name: string
  version: string
  algorithm: string
  metrics: Record<string, number>
  is_active: boolean
  registered_at: string
}

export interface WebSocketMessage {
  type: 'traffic_update' | 'vehicle_update' | 'route_update' | 'incident_update' | 'prediction_update' | 'simulation_tick' | 'status'
  timestamp: string
  data: any
}