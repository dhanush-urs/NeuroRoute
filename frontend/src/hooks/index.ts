import { useEffect, useRef, useState, useCallback } from 'react'
import { WebSocketService, WS_URL } from '../services/websocket'
import { WebSocketMessage } from '../types'

export function useWebSocket() {
  const wsRef = useRef<WebSocketService | null>(null)
  const [connectedChannels, setConnectedChannels] = useState<Record<string, boolean>>({})
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null)

  // Helper to check if any channel is connected
  const connected = Object.values(connectedChannels).some(v => v)

  useEffect(() => {
    const ws = new WebSocketService({ url: WS_URL })
    wsRef.current = ws

    // Subscribe to connection events BEFORE connecting
    const unsubOpen = ws.subscribe('open', ({ channel }: { channel: string }) => {
      setConnectedChannels(prev => ({ ...prev, [channel]: true }))
    })
    const unsubClose = ws.subscribe('close', ({ channel }: { channel: string }) => {
      setConnectedChannels(prev => ({ ...prev, [channel]: false }))
    })
    
    // Subscribe to specific message types that the backend sends
    const unsubTraffic = ws.subscribe('traffic_update', (data: any) => {
      setLastMessage({ type: 'traffic_update', data, timestamp: new Date().toISOString() })
    })
    const unsubVehicles = ws.subscribe('vehicle_update', (data: any) => {
      setLastMessage({ type: 'vehicle_update', data, timestamp: new Date().toISOString() })
    })
    const unsubSimulation = ws.subscribe('simulation_tick', (data: any) => {
      setLastMessage({ type: 'simulation_tick', data, timestamp: new Date().toISOString() })
    })
    const unsubIncidents = ws.subscribe('incident_update', (data: any) => {
      setLastMessage({ type: 'incident_update', data, timestamp: new Date().toISOString() })
    })
    const unsubRoute = ws.subscribe('route_update', (data: any) => {
      setLastMessage({ type: 'route_update', data, timestamp: new Date().toISOString() })
    })

    // NOW connect - after all subscriptions are registered
    const connect = async () => {
      await ws.connect()
    }
    connect()

    return () => {
      unsubOpen()
      unsubClose()
      unsubTraffic()
      unsubVehicles()
      unsubSimulation()
      unsubIncidents()
      unsubRoute()
      ws.disconnect()
    }
  }, [])

  return { connected, connectedChannels, lastMessage, ws: wsRef.current }
}

export function useTrafficData() {
  const [traffic, setTraffic] = useState<Map<string, any>>(new Map())
  const [summary, setSummary] = useState<any>(null)

  const handleTrafficUpdate = useCallback((data: any) => {
    if (Array.isArray(data)) {
      // Batch all updates into a single setTraffic call to avoid batching issues
      setTraffic(prev => {
        const next = new Map(prev)
        data.forEach((road: any) => {
          next.set(road.road_id, road)
        })
        return next
      })
    }
  }, [])

  const handleSummaryUpdate = useCallback((data: any) => {
    setSummary(data)
  }, [])

  return { traffic, summary, handleTrafficUpdate, handleSummaryUpdate }
}

export function useSimulation() {
  const [status, setStatus] = useState<any>(null)
  const [clock, setClock] = useState<string>('00:00 AM')

  const handleSimulationTick = useCallback((data: any) => {
    const simTimeStr = data?.sim_time || data?.simulation_time
    if (simTimeStr) {
      const date = new Date(simTimeStr)
      if (!isNaN(date.getTime())) {
        const hours = date.getHours()
        const minutes = date.getMinutes().toString().padStart(2, '0')
        const ampm = hours >= 12 ? 'PM' : 'AM'
        const displayHours = hours % 12 || 12
        setClock(`${displayHours}:${minutes} ${ampm}`)
      }
    }
    setStatus(data)
  }, [])

  return { status, clock, handleSimulationTick }
}

export interface VehicleItem {
  vehicle_id: string
  road_id: string
  longitude: number
  latitude: number
  bearing: number
  speed: number
  state: string
}

export function useVehicles() {
  const [vehicles, setVehicles] = useState<VehicleItem[]>([])

  const handleVehicleUpdate = useCallback((data: any) => {
    if (Array.isArray(data)) {
      setVehicles(data)
    }
  }, [])

  return { vehicles, setVehicles, handleVehicleUpdate }
}

// Simplified hook for components that only need incidents from props
export function useIncidentsFromProps(initialIncidents: any[] = []) {
  const [incidents, setIncidents] = useState<any[]>(initialIncidents)
  const [loading, setLoading] = useState(initialIncidents.length === 0)

  const updateIncidents = useCallback((newIncidents: any[]) => {
    setIncidents(newIncidents)
    setLoading(false)
  }, [])

  return { incidents, loading, updateIncidents }
}