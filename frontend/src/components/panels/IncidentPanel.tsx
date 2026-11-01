import { useCallback } from 'react'

const typeIcons: Record<string, string> = {
  accident: '🚗',
  road_closure: '🚫',
  road_work: '🚧',
  flood: '🌊',
  heavy_rain: '🌧️',
  special_event: '🎪',
}

const typeLabels: Record<string, string> = {
  accident: 'Accident',
  road_closure: 'Road Closure',
  road_work: 'Road Work',
  flood: 'Flood',
  heavy_rain: 'Heavy Rain',
  special_event: 'Special Event',
}

interface IncidentPanelProps {
  incidents: any[]
  onTriggerIncident: (type: string) => void
  onResolveIncident?: (id: string) => void
}

export function IncidentPanel({ incidents, onTriggerIncident, onResolveIncident }: IncidentPanelProps) {
  const handleTriggerIncident = useCallback((type: string) => {
    onTriggerIncident(type)
  }, [onTriggerIncident])

  return (
    <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-slate-900">⚠️ Active Incidents</h3>
        <span className={`text-xs px-2 py-0.5 rounded ${
          incidents.length > 0 ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'
        }`}>
          {incidents.length} Active
        </span>
      </div>

      {incidents.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-4">No active incidents</p>
      ) : (
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {incidents.map((incident) => (
            <IncidentCard 
              key={incident.incident_id} 
              incident={incident} 
              onResolve={onResolveIncident}
            />
          ))}
        </div>
      )}

      <div className="mt-4 pt-4 border-t border-slate-200">
        <h4 className="text-sm font-medium text-slate-900 mb-2">Trigger Incident</h4>
        <div className="grid grid-cols-2 gap-2">
          <IncidentButton type="accident" icon="🚗" label="Accident" onClick={handleTriggerIncident} />
          <IncidentButton type="road_closure" icon="🚫" label="Road Closure" onClick={handleTriggerIncident} />
          <IncidentButton type="road_work" icon="🚧" label="Road Work" onClick={handleTriggerIncident} />
          <IncidentButton type="heavy_rain" icon="🌧️" label="Heavy Rain" onClick={handleTriggerIncident} />
        </div>
      </div>
    </div>
  )
}

function IncidentCard({ incident, onResolve }: { incident: any; onResolve?: (id: string) => void }) {
  const severityColors = {
    low: 'bg-green-100 text-green-700',
    medium: 'bg-yellow-100 text-yellow-700',
    high: 'bg-red-100 text-red-700',
  }

  const getSeverityClass = (severity: number) => {
    if (severity < 0.3) return severityColors.low
    if (severity < 0.7) return severityColors.medium
    return severityColors.high
  }

  return (
    <div className="bg-white rounded-lg p-3 border border-slate-200">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-lg">{typeIcons[incident.incident_type] || '⚠️'}</span>
          <div>
            <p className="font-medium text-slate-900 text-sm">{typeLabels[incident.incident_type] || incident.incident_type}</p>
            <p className="text-xs text-slate-500 font-mono">Road: {incident.road_id ? incident.road_id.slice(0, 8) + '...' : 'N/A'}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${getSeverityClass(incident.severity)}`}>
            {Math.round(incident.severity * 100)}%
          </span>
          {onResolve && (
            <button
              onClick={() => onResolve(incident.incident_id)}
              className="px-1.5 py-0.5 rounded text-xs text-slate-400 hover:text-red-600 hover:bg-red-50 border border-slate-200 transition-colors"
              title="Resolve Incident"
            >
              ✕
            </button>
          )}
        </div>
      </div>
      <div className="mt-2 text-xs text-slate-500">
        Capacity reduction: {incident.capacity_reduction_pct}% | Started at tick {incident.start_tick}
      </div>
    </div>
  )
}

function IncidentButton({ type, icon, label, onClick }: { type: string; icon: string; label: string; onClick: (type: string) => void }) {
  return (
    <button 
      className="px-3 py-2 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 transition-colors text-left"
      onClick={() => onClick(type)}
    >
      <div className="flex items-center gap-2">
        <span className="text-lg">{icon}</span>
        <span className="text-sm font-medium text-slate-700">{label}</span>
      </div>
    </button>
  )
}