import { useState } from 'react'
import { routingApi } from '../../services/api'

const formatTime = (seconds: number) => {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins} min ${secs > 0 ? `${secs} sec` : ''}`
}

interface RoutePlannerProps {
  origin: string | null
  destination: string | null
  onClear: () => void
  onClearOrigin?: () => void
  onClearDestination?: () => void
  onSelectPair?: (origin: string, destination: string) => void
  onRouteCalculated?: (route: any) => void
}

export function RoutePlanner({ origin, destination, onClear, onClearOrigin, onClearDestination, onSelectPair, onRouteCalculated }: RoutePlannerProps) {
  const [loading, setLoading] = useState(false)
  const [algorithm, setAlgorithm] = useState<string>('all')
  const [recommended, setRecommended] = useState<any>(null)
  const [alternatives, setAlternatives] = useState<any[]>([])
  const [activeRouteId, setActiveRouteId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleCalculateRoutes = async () => {
    if (!origin || !destination) return
    
    setLoading(true)
    setError(null)
    
    try {
      if (algorithm === 'all') {
        const response = await routingApi.recommend({ origin, destination })
        const data = response.data
        if (data?.recommended) {
          setRecommended(data.recommended)
          setAlternatives(data.alternatives || [])
          setActiveRouteId(data.recommended.route_id)
          onRouteCalculated?.(data.recommended)
        } else {
          setError('No route found between selected points')
          onRouteCalculated?.(null)
        }
      } else {
        const response = await routingApi.calculate({ origin, destination, algorithm })
        const route = response.data
        if (route && route.nodes && route.nodes.length >= 2) {
          setRecommended(route)
          setAlternatives([])
          setActiveRouteId(route.route_id)
          onRouteCalculated?.(route)
        } else {
          setError(`No route found using ${algorithm} algorithm`)
          onRouteCalculated?.(null)
        }
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to calculate routes')
      onRouteCalculated?.(null)
    } finally {
      setLoading(false)
    }
  }

  const handleSelectRoute = (route: any) => {
    setActiveRouteId(route.route_id)
    onRouteCalculated?.(route)
  }

  const handleQuickSelect = (orig: string, dest: string) => {
    onSelectPair?.(orig, dest)
  }

  return (
    <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-slate-900">🗺️ Route Planner</h3>
        {origin || destination ? (
          <button 
            onClick={() => {
              setRecommended(null)
              setAlternatives([])
              setActiveRouteId(null)
              onClear()
            }} 
            className="text-xs text-primary-500 hover:text-primary-600 font-medium"
          >
            Clear
          </button>
        ) : null}
      </div>

      {(!origin || !destination) && onSelectPair && (
        <div className="mb-3 p-2 bg-slate-100 rounded-lg text-xs flex items-center justify-between">
          <span className="text-slate-600">Sample route:</span>
          <button
            onClick={() => handleQuickSelect('node_9181607984', 'node_42448558')}
            className="px-2 py-1 bg-white border border-slate-300 rounded text-slate-800 hover:bg-slate-50 font-medium"
          >
            Battery Park → SoHo / Canal
          </button>
        </div>
      )}

      <div className="space-y-3">
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-slate-600">Origin</label>
            {origin && (
              <button
                onClick={() => {
                  setRecommended(null)
                  setAlternatives([])
                  setActiveRouteId(null)
                  onClearOrigin?.()
                }}
                className="text-[11px] text-slate-400 hover:text-slate-700"
                title="Clear origin"
              >
                Clear ✕
              </button>
            )}
          </div>
          <div className={`px-3 py-2 rounded-lg border ${
            origin ? 'bg-green-50 border-green-300' : 'bg-white border-slate-300'
          }`}>
            {origin ? (
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-900">{origin}</span>
                <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">Set</span>
              </div>
            ) : (
              <span className="text-sm text-slate-400">Click a node on map or choose sample</span>
            )}
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-slate-600">Destination</label>
            {destination && (
              <button
                onClick={() => {
                  setRecommended(null)
                  setAlternatives([])
                  setActiveRouteId(null)
                  onClearDestination?.()
                }}
                className="text-[11px] text-slate-400 hover:text-slate-700"
                title="Clear destination"
              >
                Clear ✕
              </button>
            )}
          </div>
          <div className={`px-3 py-2 rounded-lg border ${
            destination ? 'bg-red-50 border-red-300' : 'bg-white border-slate-300'
          }`}>
            {destination ? (
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-900">{destination}</span>
                <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">Set</span>
              </div>
            ) : (
              <span className="text-sm text-slate-400">Click a node on map or choose sample</span>
            )}
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Routing Algorithm</label>
          <select
            value={algorithm}
            onChange={(e) => setAlgorithm(e.target.value)}
            className="w-full px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-primary-500 font-medium text-slate-800"
          >
            <option value="all">★ All (NeuroRoute Recommended + Alternatives)</option>
            <option value="neuroroute">⚡ NeuroRoute AI</option>
            <option value="dijkstra">📏 Dijkstra Shortest Path</option>
            <option value="astar">🎯 A* Heuristic</option>
            <option value="astar_predicted">🔮 A* Predicted Congestion</option>
          </select>
        </div>

        {origin && destination && (
          <button 
            onClick={handleCalculateRoutes}
            disabled={loading}
            className="w-full bg-primary-500 text-white py-2 rounded-lg font-medium hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Calculating...' : 'Calculate Routes'}
          </button>
        )}

        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        {recommended && (
          <div className="mt-4 p-3 bg-white rounded-lg border border-slate-200">
            <h4 className="text-sm font-medium text-slate-900 mb-2">Route Comparison</h4>
            <div className="space-y-2 text-xs">
              <div onClick={() => handleSelectRoute(recommended)} className="cursor-pointer">
                <RouteRow 
                  name="NeuroRoute (Recommended)" 
                  distance={`${recommended.distance_km} km`} 
                  eta={formatTime(recommended.current_eta_sec)} 
                  predicted={formatTime(recommended.predicted_eta_sec)} 
                  risk={recommended.congestion_risk} 
                  recommended={true}
                  isSelected={activeRouteId === recommended.route_id}
                />
              </div>
              {alternatives.map((alt: any) => (
                <div key={alt.route_id} onClick={() => handleSelectRoute(alt)} className="cursor-pointer">
                  <RouteRow 
                    name={`${alt.algorithm} (Alt)`} 
                    distance={`${alt.distance_km} km`} 
                    eta={formatTime(alt.current_eta_sec)} 
                    predicted={formatTime(alt.predicted_eta_sec)} 
                    risk={alt.congestion_risk} 
                    isSelected={activeRouteId === alt.route_id}
                  />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function RouteRow({ name, distance, eta, predicted, risk, recommended, isSelected }: {
  name: string
  distance: string
  eta: string
  predicted: string
  risk: string
  recommended?: boolean
  isSelected?: boolean
}) {
  const riskColors = {
    LOW: 'text-green-600 bg-green-100',
    MEDIUM: 'text-yellow-600 bg-yellow-100',
    HIGH: 'text-red-600 bg-red-100',
    low: 'text-green-600 bg-green-100',
    medium: 'text-yellow-600 bg-yellow-100',
    high: 'text-red-600 bg-red-100',
  }

  return (
    <div className={`flex items-center gap-2 p-2 rounded transition-colors ${
      isSelected 
        ? 'bg-primary-100 border-2 border-primary-500 shadow-sm' 
        : recommended 
          ? 'bg-primary-50 border border-primary-200 hover:bg-primary-100/50' 
          : 'hover:bg-slate-100 border border-transparent'
    }`}>
      {recommended && <span className="text-xs bg-primary-500 text-white px-1.5 py-0.5 rounded">★</span>}
      <span className="font-medium text-slate-900 w-28 truncate">{name}</span>
      <span className="text-slate-600 w-16">{distance}</span>
      <span className="text-slate-600 w-12">{eta}</span>
      <span className="text-slate-600 w-14">{predicted}</span>
      <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${riskColors[risk as keyof typeof riskColors] || 'text-slate-600 bg-slate-100'}`}>
        {risk}
      </span>
    </div>
  )
}