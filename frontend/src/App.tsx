import { useState, useEffect, useCallback } from 'react'
import { TrafficMap } from './components/map/TrafficMap'
import { SimulationControl } from './components/controls/SimulationControl'
import { TrafficStatusPanel } from './components/panels/TrafficStatusPanel'
import { RoutePlanner } from './components/panels/RoutePlanner'
import { IncidentPanel } from './components/panels/IncidentPanel'
import { PredictionPanel } from './components/panels/PredictionPanel'
import { AIInsightsPanel } from './components/panels/AIInsightsPanel'
import { SystemMetrics } from './components/panels/SystemMetrics'
import { WhatIfPanel } from './components/panels/WhatIfPanel'
import { useWebSocket, useTrafficData, useSimulation, useVehicles } from './hooks'

type TabType = 'traffic' | 'routing' | 'predictions' | 'incidents' | 'ai' | 'metrics' | 'whatif' | 'all'

const TABS: { id: TabType; label: string; icon: string }[] = [
  { id: 'traffic', label: 'Traffic', icon: '📊' },
  { id: 'routing', label: 'Routing', icon: '🗺️' },
  { id: 'predictions', label: 'Predictions', icon: '🔮' },
  { id: 'incidents', label: 'Incidents', icon: '⚠️' },
  { id: 'ai', label: 'AI Insights', icon: '🤖' },
  { id: 'metrics', label: 'Metrics', icon: '📈' },
  { id: 'whatif', label: 'What-If', icon: '⚡' },
  { id: 'all', label: 'All', icon: '📑' },
]

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('traffic')
  const [simulationRunning, setSimulationRunning] = useState(false)
  const [simulationSpeed, setSimulationSpeed] = useState(1)
  const [selectedOrigin, setSelectedOrigin] = useState<string | null>(null)
  const [selectedDestination, setSelectedDestination] = useState<string | null>(null)
  const [activeRoute, setActiveRoute] = useState<any | null>(null)

  const { connected, connectedChannels, lastMessage } = useWebSocket()
  const { traffic, summary, handleTrafficUpdate } = useTrafficData()
  const { status, clock, handleSimulationTick } = useSimulation()
  const { vehicles, setVehicles, handleVehicleUpdate } = useVehicles()

  // Shared state for incident data
  const [incidents, setIncidents] = useState<any[]>([])

  // Handle traffic, vehicle, and incident updates
  useEffect(() => {
    if (lastMessage) {
      if (lastMessage.type === 'traffic_update') {
        handleTrafficUpdate(lastMessage.data)
      } else if (lastMessage.type === 'vehicle_update') {
        handleVehicleUpdate(lastMessage.data)
      } else if (lastMessage.type === 'simulation_tick') {
        handleSimulationTick(lastMessage.data)
      } else if (lastMessage.type === 'incident_update') {
        const incList = Array.isArray(lastMessage.data) ? lastMessage.data : (lastMessage.data?.incidents || [])
        setIncidents(incList)
      }
    }
  }, [lastMessage, handleTrafficUpdate, handleVehicleUpdate, handleSimulationTick])

  // Sync simulationRunning state with status
  useEffect(() => {
    if (status) {
      setSimulationRunning(status.status === 'running' || status.is_running === true)
    }
  }, [status])

  // Initial fetch of simulation status, current traffic, active incidents, and vehicles on mount
  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        const [simRes, trafficRes, incRes, vehRes] = await Promise.all([
          fetch('/api/v1/simulation/status').then(r => r.ok ? r.json() : null).catch(() => null),
          fetch('/api/v1/traffic/current?limit=892').then(r => r.ok ? r.json() : null).catch(() => null),
          fetch('/api/v1/incidents/active').then(r => r.ok ? r.json() : null).catch(() => null),
          fetch('/api/v1/traffic/vehicles').then(r => r.ok ? r.json() : null).catch(() => null),
        ])
        if (simRes) {
          handleSimulationTick(simRes)
          setSimulationRunning(simRes.status === 'running' || simRes.is_running === true)
        }
        if (trafficRes && Array.isArray(trafficRes)) {
          handleTrafficUpdate(trafficRes)
        }
        if (incRes) {
          const incList = Array.isArray(incRes) ? incRes : incRes.incidents || []
          setIncidents(incList)
        }
        if (vehRes?.vehicles && Array.isArray(vehRes.vehicles)) {
          handleVehicleUpdate(vehRes.vehicles)
        }
      } catch (err) {
        console.warn('Initial data load error:', err)
      }
    }
    fetchInitialData()
  }, [handleSimulationTick, handleTrafficUpdate, handleVehicleUpdate])

  // Expose connected channels for debugging
  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.__WS_DEBUG__ = { connectedChannels }
    }
  }, [connectedChannels])

  const handleStartSimulation = useCallback(async () => {
    try {
      const statRes = await fetch('/api/v1/simulation/status').then(r => r.json()).catch(() => null)
      if (statRes && statRes.status === 'paused') {
        await fetch('/api/v1/simulation/resume', { method: 'POST' })
        handleSimulationTick({ ...status, status: 'running', is_running: true })
      } else {
        const response = await fetch('/api/v1/simulation/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ seed: 42, speed_multiplier: simulationSpeed })
        })
        if (!response.ok) throw new Error('Failed to start simulation')
        handleSimulationTick({ ...status, status: 'running', is_running: true })
      }
      setSimulationRunning(true)
    } catch (error) {
      console.error('Failed to start simulation:', error)
    }
  }, [handleSimulationTick, simulationSpeed, status])

  const handlePauseSimulation = useCallback(async () => {
    try {
      await fetch('/api/v1/simulation/pause', { method: 'POST' })
      handleSimulationTick({ ...status, status: 'paused', is_running: false })
      setSimulationRunning(false)
    } catch (error) {
      console.error('Failed to pause simulation:', error)
    }
  }, [handleSimulationTick, status])

  const handleSpeedChange = useCallback(async (speed: number) => {
    setSimulationSpeed(speed)
    try {
      await fetch('/api/v1/simulation/speed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ speed_multiplier: speed }),
      })
    } catch (err) {
      console.error('Failed to update speed on backend:', err)
    }
  }, [])

  const handleResetSimulation = useCallback(async () => {
    try {
      await fetch('/api/v1/simulation/reset', { method: 'POST' })
      setSimulationRunning(false)
      setSelectedOrigin(null)
      setSelectedDestination(null)
      setActiveRoute(null)
      setVehicles([])
      setIncidents([])
      // Refresh fresh state from backend
      const [simRes, trafficRes] = await Promise.all([
        fetch('/api/v1/simulation/status').then(r => r.ok ? r.json() : null),
        fetch('/api/v1/traffic/current?limit=892').then(r => r.ok ? r.json() : null)
      ])
      if (simRes) handleSimulationTick(simRes)
      if (trafficRes) handleTrafficUpdate(trafficRes)
    } catch (error) {
      console.error('Failed to reset simulation:', error)
    }
  }, [handleSimulationTick, handleTrafficUpdate, setVehicles])

  const handleResolveIncident = useCallback(async (incidentId: string) => {
    try {
      await fetch(`/api/v1/incidents/${incidentId}`, { method: 'DELETE' })
      const incRes = await fetch('/api/v1/incidents/active')
      if (incRes.ok) {
        const incData = await incRes.json()
        setIncidents(incData.incidents || [])
      }
    } catch (err) {
      console.error('Failed to resolve incident:', err)
    }
  }, [])

  const handleToggleSimulation = useCallback(async (running: boolean) => {
    if (running) {
      await handleStartSimulation()
    } else {
      await handlePauseSimulation()
    }
  }, [handleStartSimulation, handlePauseSimulation])

  const handleTriggerIncident = useCallback(async (type: string) => {
    try {
      // Create incident on first available road or via scenario
      const response = await fetch('/api/v1/traffic/current?limit=1')
      const roads = await response.json()
      const roadId = Array.isArray(roads) && roads.length > 0 ? roads[0].road_id : undefined

      const res = await fetch('/api/v1/incidents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          incident_type: type,
          road_id: roadId,
          severity: 0.8,
          duration_ticks: 60,
        }),
      })

      if (!res.ok) {
        // Fallback to simulation/scenario
        await fetch('/api/v1/simulation/scenario', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            scenario_name: type, 
            seed: 42, 
            speed_multiplier: 1 
          }),
        })
      }

      // Refresh incidents
      const incRes = await fetch('/api/v1/incidents/active')
      if (incRes.ok) {
        const incData = await incRes.json()
        setIncidents(incData.incidents || [])
      }
    } catch (error) {
      console.error('Failed to trigger incident:', error)
    }
  }, [])

  const handleNodeClick = useCallback((nodeId: string) => {
    setSelectedOrigin((prevOrigin) => {
      if (!prevOrigin) {
        return nodeId
      }
      setSelectedDestination((prevDest) => {
        if (!prevDest && nodeId !== prevOrigin) {
          return nodeId
        }
        return null
      })
      if (prevOrigin && nodeId !== prevOrigin) {
        return prevOrigin
      }
      setActiveRoute(null)
      return nodeId
    })
  }, [])

  return (
    <div className="h-screen w-screen flex flex-col bg-slate-50">
      <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-4 shadow-sm z-10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-primary-500 rounded-lg flex items-center justify-center">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <h1 className="text-xl font-bold text-slate-900">NeuroRoute</h1>
          <span className="text-xs text-slate-500 px-2 py-1 bg-slate-100 rounded">AI Traffic Brain</span>
        </div>
        <div className="flex items-center gap-4">
          <SimulationControl
            running={simulationRunning}
            speed={simulationSpeed}
            onToggle={handleToggleSimulation}
            onSpeedChange={handleSpeedChange}
            onReset={handleResetSimulation}
            onScenario={async (scenarioId) => {
              try {
                const response = await fetch('/api/v1/simulation/scenario', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ scenario_name: scenarioId, seed: 42, speed_multiplier: simulationSpeed }),
                })
                if (!response.ok) {
                  const errData = await response.json().catch(() => ({}))
                  throw new Error(errData.detail || 'Failed to run scenario')
                }
                setSimulationRunning(true)

                // Immediately synchronize frontend incidents with backend state
                if (scenarioId === 'normal') {
                  setIncidents([])
                } else {
                  const activeRes = await fetch('/api/v1/incidents/active').then(r => r.ok ? r.json() : null).catch(() => null)
                  const incList = Array.isArray(activeRes) ? activeRes : (activeRes?.incidents || [])
                  setIncidents(incList)
                }
                return true
              } catch (error) {
                console.error('Failed to run scenario:', error)
                throw error
              }
            }}
          />
          <div className="text-sm text-slate-600 font-mono" id="simulation-clock">
            SIM: {clock}
          </div>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <main className="flex-1 relative min-w-0">
          <TrafficMap
            onNodeClick={handleNodeClick}
            selectedOrigin={selectedOrigin}
            selectedDestination={selectedDestination}
            traffic={traffic}
            vehicles={vehicles}
            incidents={incidents}
            activeRoute={activeRoute}
          />
        </main>

        <aside className="w-96 bg-white border-l border-slate-200 flex flex-col overflow-y-auto">
          <nav className="border-b border-slate-200 bg-slate-50/50">
            <ul className="flex overflow-x-auto no-scrollbar" role="tablist">
              {TABS.map((tab) => {
                const isActive = activeTab === tab.id
                return (
                  <li key={tab.id} role="presentation">
                    <button
                      role="tab"
                      aria-selected={isActive}
                      onClick={() => setActiveTab(tab.id)}
                      className={`px-3 py-2.5 text-xs font-semibold whitespace-nowrap border-b-2 transition-all flex items-center gap-1.5 ${
                        isActive
                          ? 'text-primary-600 border-primary-500 bg-white'
                          : 'text-slate-600 border-transparent hover:text-slate-900 hover:border-slate-300'
                      }`}
                    >
                      <span>{tab.icon}</span>
                      <span>{tab.label}</span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </nav>

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {(activeTab === 'traffic' || activeTab === 'all') && (
              <TrafficStatusPanel traffic={traffic} summary={summary} />
            )}

            {(activeTab === 'routing' || activeTab === 'all') && (
              <RoutePlanner
                origin={selectedOrigin}
                destination={selectedDestination}
                onClear={() => {
                  setSelectedOrigin(null)
                  setSelectedDestination(null)
                  setActiveRoute(null)
                }}
                onClearOrigin={() => {
                  setSelectedOrigin(null)
                  setActiveRoute(null)
                }}
                onClearDestination={() => {
                  setSelectedDestination(null)
                  setActiveRoute(null)
                }}
                onSelectPair={(orig, dest) => {
                  setSelectedOrigin(orig)
                  setSelectedDestination(dest)
                }}
                onRouteCalculated={setActiveRoute}
              />
            )}

            {(activeTab === 'predictions' || activeTab === 'all') && (
              <PredictionPanel />
            )}

            {(activeTab === 'incidents' || activeTab === 'all') && (
              <IncidentPanel 
                incidents={incidents}
                onTriggerIncident={handleTriggerIncident}
                onResolveIncident={handleResolveIncident}
              />
            )}

            {(activeTab === 'ai' || activeTab === 'all') && (
              <AIInsightsPanel />
            )}

            {(activeTab === 'metrics' || activeTab === 'all') && (
              <SystemMetrics status={status} clock={clock} connected={connected} />
            )}

            {(activeTab === 'whatif' || activeTab === 'all') && (
              <WhatIfPanel
                onRunScenario={async (scenario) => {
                  const response = await fetch('/api/v1/simulation/what-if', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(scenario),
                  })
                  if (!response.ok) {
                    const err = await response.json().catch(() => ({ detail: 'Failed to run scenario' }))
                    throw new Error(err.detail || 'Failed to run scenario')
                  }
                  return response.json()
                }}
              />
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}

export default App