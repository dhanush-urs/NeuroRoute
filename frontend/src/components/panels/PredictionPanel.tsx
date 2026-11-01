import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { predictionsApi, trafficApi } from '../../services/api'

interface PredictionPoint {
  time: string
  current: number
  predicted5: number
  predicted15: number
  predicted30: number
}

interface ModelInfo {
  name: string
  version: string
  algorithm: string
  metrics: Record<string, number>
  is_active: boolean
}

export function PredictionPanel() {
  const [predictionData, setPredictionData] = useState<PredictionPoint[]>([])
  const [activeModel, setActiveModel] = useState<ModelInfo | null>(null)
  const [availableRoads, setAvailableRoads] = useState<string[]>([])
  const [selectedRoadId, setSelectedRoadId] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch available models and roads on mount
  useEffect(() => {
    const initData = async () => {
      try {
        const [modelsRes, trafficRes] = await Promise.all([
          predictionsApi.getModels().catch(() => ({ data: [] })),
          trafficApi.getCurrent().catch(() => ({ data: [] }))
        ])
        const models = Array.isArray(modelsRes.data) ? modelsRes.data : []
        const active = models.find((m: ModelInfo) => m.is_active) || models[0] || null
        setActiveModel(active)

        const roads = Array.isArray(trafficRes.data) ? trafficRes.data : []
        const roadIds = roads.map((r: any) => r.road_id).filter(Boolean).slice(0, 20)
        setAvailableRoads(roadIds)
        if (roadIds.length > 0 && !selectedRoadId) {
          setSelectedRoadId(roadIds[0])
        }
      } catch (err: any) {
        console.warn('Prediction panel init warning:', err)
      }
    }
    initData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Fetch predictions whenever selectedRoadId changes
  useEffect(() => {
    if (!selectedRoadId) return

    let cancelled = false
    const fetchPredictions = async () => {
      try {
        setLoading(true)
        const predRes = await predictionsApi.getRoad(selectedRoadId).catch(() => null)
        const roadPreds = predRes?.data

        if (cancelled) return

        const predsList = roadPreds?.predictions || []
        const p5 = predsList.find((p: any) => p.horizon_minutes === 5)?.predicted_congestion_score ?? 0.12
        const p15 = predsList.find((p: any) => p.horizon_minutes === 15)?.predicted_congestion_score ?? 0.18
        const p30 = predsList.find((p: any) => p.horizon_minutes === 30)?.predicted_congestion_score ?? 0.25

        // Build time series data from predictions
        const timePoints = ['Now', '+5min', '+10min', '+15min', '+20min', '+25min', '+30min']
        const data: PredictionPoint[] = timePoints.map((time, idx) => {
          const currentCongestion = idx === 0 ? p5 : 0
          return {
            time,
            current: currentCongestion,
            predicted5: p5,
            predicted15: p15,
            predicted30: p30,
          }
        })

        setPredictionData(data)
        setError(null)
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || 'Waiting for prediction data')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    fetchPredictions()
    return () => { cancelled = true }
  }, [selectedRoadId])

  if (loading) {
    return (
      <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
        <h3 className="font-semibold text-slate-900 mb-3">🔮 Congestion Predictions</h3>
        <p className="text-sm text-slate-500 text-center py-8">Loading predictions...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
        <h3 className="font-semibold text-slate-900 mb-3">🔮 Congestion Predictions</h3>
        <p className="text-red-600 text-sm text-center py-4">Failed to load predictions: {error}</p>
      </div>
    )
  }

  const activeModelName = activeModel 
    ? `${activeModel.algorithm} v${activeModel.version} (${activeModel.metrics?.r2 ? (activeModel.metrics.r2 * 100).toFixed(1) + '%' : 'N/A'} R²)`
    : 'No active model'

  return (
    <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-slate-900">🔮 Congestion Predictions</h3>
      </div>

      {availableRoads.length > 0 && (
        <div className="mb-3">
          <label className="block text-xs font-medium text-slate-600 mb-1">Target Road</label>
          <select
            value={selectedRoadId}
            onChange={(e) => setSelectedRoadId(e.target.value)}
            className="w-full px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-primary-500 font-mono text-slate-800"
          >
            {availableRoads.map((rid, idx) => (
              <option key={rid} value={rid}>
                Road #{idx + 1} ({rid.slice(0, 8)}...)
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={predictionData} margin={{ top: 5, right: 30, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="time" stroke="#64748b" fontSize={10} />
            <YAxis 
              domain={[0, 1]} 
              stroke="#64748b" 
              fontSize={10}
              tickFormatter={(value) => `${Math.round(value * 100)}%`}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#fff', 
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)'
              }}
              formatter={(value: number) => [`${Math.round(value * 100)}%`, 'Congestion']}
            />
            <Line 
              type="monotone" 
              dataKey="current" 
              stroke="#0ea5e9" 
              strokeWidth={2}
              dot={false}
              name="Current"
            />
            <Line 
              type="monotone" 
              dataKey="predicted5" 
              stroke="#22c55e" 
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={false}
              name="+5 min"
            />
            <Line 
              type="monotone" 
              dataKey="predicted15" 
              stroke="#f97316" 
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={false}
              name="+15 min"
            />
            <Line 
              type="monotone" 
              dataKey="predicted30" 
              stroke="#ef4444" 
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={false}
              name="+30 min"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <LegendItem color="#0ea5e9" label="Current" />
        <LegendItem color="#22c55e" label="+5 min" dashed />
        <LegendItem color="#f97316" label="+15 min" dashed />
        <LegendItem color="#ef4444" label="+30 min" dashed />
      </div>

      <div className="mt-4 p-3 bg-white rounded-lg border border-slate-200">
        <div className="flex justify-between text-sm">
          <span className="text-slate-600">Model:</span>
          <span className="font-medium text-slate-900">{activeModelName}</span>
        </div>
        <div className="flex justify-between text-sm mt-1">
          <span className="text-slate-600">Algorithm:</span>
          <span className="font-medium text-slate-900">{activeModel?.algorithm ?? 'N/A'}</span>
        </div>
        <div className="flex justify-between text-sm mt-1">
          <span className="text-slate-600">MAE:</span>
          <span className="font-medium text-slate-900">{activeModel?.metrics?.mae?.toFixed(4) ?? 'N/A'}</span>
        </div>
        <div className="flex justify-between text-sm mt-1">
          <span className="text-slate-600">R²:</span>
          <span className="font-medium text-slate-900">{activeModel?.metrics?.r2 ? (activeModel.metrics.r2 * 100).toFixed(1) + '%' : 'N/A'}</span>
        </div>
      </div>
    </div>
  )
}

function LegendItem({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <div className="flex items-center gap-1 text-xs text-slate-600">
      <div 
        className="w-6 h-1 rounded" 
        style={{ 
          backgroundColor: color,
          borderTop: dashed ? '2px dashed' : '2px solid',
        }} 
      />
      {label}
    </div>
  )
}