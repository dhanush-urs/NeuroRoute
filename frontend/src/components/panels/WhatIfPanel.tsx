import { useState } from 'react'
import { useTrafficData } from '../../hooks'

interface WhatIfPanelProps {
  onRunScenario: (scenario: WhatIfScenarioRequest) => Promise<WhatIfScenarioResponse>
}

interface WhatIfScenarioRequest {
  scenario_type: string
  scenario_params: Record<string, any>
  steps: number
}

interface WhatIfScenarioResponse {
  scenario_type: string
  scenario_params: Record<string, any>
  steps_simulated: number
  baseline: Record<string, any>
  scenario: Record<string, any>
  comparison: Record<string, any>
  simulation_time: string
  ticks_advanced: number
}

const SCENARIO_TYPES = [
  { value: 'accident', label: '💥 Accident', description: 'Simulate a traffic accident', params: ['road_id', 'severity', 'duration'] },
  { value: 'road_closure', label: '🚧 Road Closure', description: 'Close a road completely', params: ['road_id'] },
  { value: 'weather', label: '🌧️ Weather', description: 'Change weather conditions', params: ['weather_type'] },
  { value: 'traffic_surge', label: '📈 Traffic Surge', description: 'Increase traffic demand', params: ['multiplier'] },
  { value: 'event', label: '🎪 Event', description: 'Special event demand', params: ['road_id', 'demand_increase'] },
]

export function WhatIfPanel({ onRunScenario }: WhatIfPanelProps) {
  const [selectedScenario, setSelectedScenario] = useState<string>('accident')
  const [params, setParams] = useState<Record<string, any>>({})
  const [steps, setSteps] = useState(30)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const { traffic } = useTrafficData()

  const scenarioConfig = SCENARIO_TYPES.find(s => s.value === selectedScenario)

  const handleParamChange = (key: string, value: any) => {
    setParams(prev => ({ ...prev, [key]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setResult(null)
    
    try {
      const response = await onRunScenario({
        scenario_type: selectedScenario,
        scenario_params: params,
        steps
      })
      setResult(response)
    } catch (err: any) {
      setError(err.message || 'Failed to run scenario')
    } finally {
      setLoading(false)
    }
  }

  const renderParams = () => {
    if (!scenarioConfig) return null
    
    // Get road IDs from traffic data for dynamic road selection
    const availableRoadIds = Array.from(traffic.keys()).slice(0, 10)
    
    return scenarioConfig.params.map((param, index) => {
      const label = param.charAt(0).toUpperCase() + param.slice(1).replace('_', ' ')
      switch (param) {
        case 'road_id':
          return (
            <div key={`param-${param}-${index}`} className="mb-3">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                {label} (Road ID)
              </label>
              <select
                value={params[param] || ''}
                onChange={(e) => handleParamChange(param, e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="">Select a road...</option>
                {availableRoadIds.map((roadId, idx) => (
                  <option key={`road-${idx}`} value={roadId}>
                    {roadId.slice(0, 8)}... (Major)
                  </option>
                ))}
              </select>
            </div>
          )
        case 'weather_type':
          return (
            <div key={`param-${param}-${index}`} className="mb-3">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                {label}
              </label>
              <select
                value={params[param] || ''}
                onChange={(e) => handleParamChange(param, e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="clear">Clear</option>
                <option value="light_rain">Light Rain</option>
                <option value="heavy_rain">Heavy Rain</option>
                <option value="fog">Fog</option>
                <option value="snow">Snow</option>
              </select>
            </div>
          )
        case 'severity':
          return (
            <div key={`param-${param}-${index}`} className="mb-3">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                {label} (0.1 - 1.0)
              </label>
              <input
                type="range"
                min="0.1"
                max="1.0"
                step="0.1"
                value={params[param] || 0.8}
                onChange={(e) => handleParamChange(param, parseFloat(e.target.value))}
                className="w-full"
              />
            </div>
          )
        case 'duration':
          return (
            <div key={`param-${param}-${index}`} className="mb-3">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                {label} (minutes)
              </label>
              <input
                type="number"
                min="5"
                max="120"
                value={params[param] || 30}
                onChange={(e) => handleParamChange(param, parseInt(e.target.value))}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          )
        case 'multiplier':
          return (
            <div key={`param-${param}-${index}`} className="mb-3">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                {label} (1.0 - 2.0)
              </label>
              <input
                type="range"
                min="1.0"
                max="2.0"
                step="0.1"
                value={params[param] || 1.3}
                onChange={(e) => handleParamChange(param, parseFloat(e.target.value))}
                className="w-full"
              />
              <p className="text-xs text-slate-500 mt-1">Current: {params[param] || 1.3}x</p>
            </div>
          )
        case 'demand_increase':
          return (
            <div key={`param-${param}-${index}`} className="mb-3">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                {label} (1.0 - 3.0)
              </label>
              <input
                type="range"
                min="1.0"
                max="3.0"
                step="0.1"
                value={params[param] || 2.0}
                onChange={(e) => handleParamChange(param, parseFloat(e.target.value))}
                className="w-full"
              />
              <p className="text-xs text-slate-500 mt-1">Current: {params[param] || 2.0}x</p>
            </div>
          )
        default:
          return (
            <div key={`param-${param}-${index}`} className="mb-3">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                {label}
              </label>
              <input
                type="text"
                value={params[param] || ''}
                onChange={(e) => handleParamChange(param, e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          )
      }
    })
  }

  const renderResult = () => {
    if (!result) return null
    
    const comparison = result.comparison
    const baseline = result.baseline
    const scenario = result.scenario
    
    return (
      <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg animate-fade-in">
        <h4 className="font-medium text-green-800 mb-3">Scenario Results</h4>
        
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="bg-white p-3 rounded-lg">
            <p className="text-xs text-slate-500">Baseline</p>
            <p className="font-mono text-lg">Congestion: {baseline.avg_congestion?.toFixed(3) || '0'}</p>
            <p className="text-xs text-slate-500">Vehicles: {baseline.total_vehicles}</p>
          </div>
          <div className="bg-white p-3 rounded-lg">
            <p className="text-xs text-slate-500">Scenario</p>
            <p className="font-mono text-lg">{scenario.avg_congestion?.toFixed(3) || '0'}</p>
            <p className="text-xs text-slate-500">Vehicles: {scenario.total_vehicles}</p>
          </div>
        </div>
        
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span>Congestion Change:</span>
            <span className={`font-mono ${comparison.congestion_change > 0 ? 'text-red-600' : 'text-green-600'}`}>
              {comparison.congestion_change > 0 ? '+' : ''}{comparison.congestion_change.toFixed(4)}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Vehicle Change:</span>
            <span className="font-mono">{comparison.vehicle_change > 0 ? '+' : ''}{comparison.vehicle_change}</span>
          </div>
          <div className="flex justify-between">
            <span>Vehicle Change %:</span>
            <span className="font-mono">{comparison.summary.vehicle_change_pct > 0 ? '+' : ''}{comparison.summary.vehicle_change_pct.toFixed(1)}%</span>
          </div>
          <div className="flex justify-between">
            <span>Significant Change:</span>
            <span className={`font-mono ${comparison.summary.significant_change ? 'text-red-600' : 'text-green-600'}`}>
              {comparison.summary.significant_change ? 'Yes' : 'No'}
            </span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4">
      <h3 className="font-semibold text-slate-900 mb-4 flex items-center gap-2">
        <span>🔮</span>
        What-If Simulation
      </h3>
      
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">
            Scenario Type
          </label>
          <select
            value={selectedScenario}
            onChange={(e) => {
              setSelectedScenario(e.target.value)
              setParams({})
            }}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            {SCENARIO_TYPES.map(s => (
              <option key={s.value} value={s.value}>
                {s.label} - {s.description}
              </option>
            ))}
          </select>
        </div>
        
        <div className="border-t border-slate-200 pt-4">
          <h4 className="font-medium text-slate-700 mb-3">Parameters</h4>
          {renderParams()}
        </div>
        
        <div className="mb-4">
          <label className="block text-sm font-medium text-slate-700 mb-2">
            Simulation Steps ({steps})
          </label>
          <input
            type="range"
            min="1"
            max="200"
            value={steps}
            onChange={(e) => setSteps(Number(e.target.value))}
            className="w-full"
          />
          <p className="text-xs text-slate-500 mt-1">Each step = 1 simulated minute</p>
        </div>
        
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2 px-4 bg-primary-500 text-white rounded-lg font-medium hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Running scenario...
            </>
          ) : (
            'Run What-If Scenario'
          )}
        </button>
        
        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}
        
        {renderResult()}
      </form>
    </div>
  )
}