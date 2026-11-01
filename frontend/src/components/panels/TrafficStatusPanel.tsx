import { useMemo } from 'react'

interface TrafficStatusPanelProps {
  traffic: Map<string, any>
  summary: any
}

export function TrafficStatusPanel({ traffic, summary }: TrafficStatusPanelProps) {
  // Compute summary from traffic Map if backend summary not available
  const computedSummary = useMemo(() => summary || computeSummary(traffic), [traffic, summary])

  if (!computedSummary || computedSummary.total_roads === 0) {
    return (
      <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
        <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
          📊 Traffic Status
        </h3>
        <div className="text-center py-6 text-slate-500 text-sm">
          <div className="animate-pulse flex flex-col items-center gap-2">
            <span className="text-xl">⏳</span>
            <span>Awaiting traffic data...</span>
          </div>
        </div>
      </div>
    )
  }

  const totalVehicles = Math.round(computedSummary.total_vehicles ?? 0)
  const avgSpeed = computedSummary.avg_speed_kmh != null ? Math.round(computedSummary.avg_speed_kmh) : null
  const congestionDist = computedSummary.congestion_distribution || {}
  const totalRoads = computedSummary.total_roads ?? traffic.size
  
  const congestedCount = 
    (congestionDist.congested ?? 0) + 
    (congestionDist.severe ?? 0) + 
    (congestionDist.closed ?? 0)
  
  const freeCount = congestionDist.free ?? 0
  const freePercent = totalRoads > 0 ? Math.round((freeCount / totalRoads) * 100) : 0

  const congestionLevels = [
    { key: 'free', label: 'FREE', color: '#22c55e' },
    { key: 'moderate', label: 'MODERATE', color: '#eab308' },
    { key: 'heavy', label: 'HEAVY', color: '#f97316' },
    { key: 'congested', label: 'CONGESTED', color: '#ef4444' },
    { key: 'severe', label: 'SEVERE', color: '#991b1b' },
    { key: 'closed', label: 'CLOSED', color: '#374151' },
  ]

  return (
    <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
      <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
        📊 Traffic Status
      </h3>
      <div className="grid grid-cols-2 gap-3">
        <StatCard label="Total Vehicles" value={totalVehicles.toLocaleString()} />
        <StatCard label="Avg Speed" value={avgSpeed !== null ? `${avgSpeed} km/h` : '—'} />
        <StatCard label="Congested Roads" value={congestedCount.toString()} />
        <StatCard label="Free Flow" value={`${freePercent}%`} />
      </div>
      <div className="mt-4 space-y-2">
        {congestionLevels.map(({ key, label, color }) => (
          <CongestionBar
            key={key}
            label={label}
            color={color}
            count={congestionDist[key] ?? 0}
            value={totalRoads > 0 ? Math.round(((congestionDist[key] ?? 0) / totalRoads) * 100) : 0}
          />
        ))}
      </div>
    </div>
  )
}

function computeSummary(traffic: Map<string, any>) {
  if (traffic.size === 0) return null

  let totalVehicles = 0
  let totalSpeed = 0
  let speedCount = 0
  const dist: Record<string, number> = {
    free: 0,
    moderate: 0,
    heavy: 0,
    congested: 0,
    severe: 0,
    closed: 0,
  }

  traffic.forEach((road) => {
    totalVehicles += Number(road.vehicle_count) || 0
    if (road.avg_speed_kmh && road.avg_speed_kmh > 0) {
      totalSpeed += road.avg_speed_kmh
      speedCount++
    }
    const level = road.congestion_level || 'free'
    if (level in dist) {
      dist[level]++
    } else {
      dist.free++
    }
  })

  return {
    total_roads: traffic.size,
    total_vehicles: Math.round(totalVehicles),
    avg_speed_kmh: speedCount > 0 ? Math.round(totalSpeed / speedCount) : null,
    congestion_distribution: dist,
    active_incidents: 0,
    timestamp: new Date().toISOString(),
  }
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-lg p-3 border border-slate-200">
      <p className="text-xs text-slate-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-slate-900">{value}</p>
    </div>
  )
}

function CongestionBar({ label, color, value, count }: { label: string; color: string; value: number; count: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-16 text-xs font-medium text-slate-600">{label}</span>
      <div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${value}%`, backgroundColor: color }}
        />
      </div>
      <span className="w-20 text-xs text-slate-500 text-right font-mono">{count} ({value}%)</span>
    </div>
  )
}