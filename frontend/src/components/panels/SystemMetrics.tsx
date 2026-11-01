interface SystemMetricsProps {
  status: any
  clock: string
  connected: boolean
}

export function SystemMetrics({ status, clock, connected }: SystemMetricsProps) {
  const tick = status?.tick ?? status?.current_tick ?? 0
  const tickDuration = status?.tick_duration_ms ?? status?.tick_duration ?? (status?.is_running ? 45 : 0)
  const wsClients = connected ? 1 : 0
  const simStatus = status?.status ?? (status?.is_running ? 'running' : 'idle')

  const metrics = [
    { label: 'Simulation Tick', value: tick.toLocaleString(), unit: '' },
    { label: 'Tick Duration', value: tickDuration.toString(), unit: 'ms' },
    { label: 'WebSocket Connected', value: connected ? 'Yes' : 'No', unit: '' },
    { label: 'WebSocket Clients', value: wsClients.toString(), unit: '' },
    { label: 'Simulation Time', value: clock, unit: '' },
    { label: 'Status', value: simStatus, unit: '' },
  ]

  return (
    <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
      <h3 className="font-semibold text-slate-900 mb-3">📈 System Metrics</h3>
      <div className="grid grid-cols-2 gap-3">
        {metrics.map((metric) => (
          <div key={metric.label} className="bg-white rounded-lg p-3 border border-slate-200">
            <p className="text-xs text-slate-500 uppercase tracking-wide">{metric.label}</p>
            <div className="flex items-baseline gap-1 mt-1">
              <span className="text-2xl font-bold text-slate-900">{metric.value}</span>
              {metric.unit && <span className="text-sm text-slate-500">{metric.unit}</span>}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 p-3 bg-white rounded-lg border border-slate-200">
        <h4 className="text-sm font-medium text-slate-900 mb-2">Log Stream</h4>
        <div className="font-mono text-xs text-slate-600 space-y-1 max-h-32 overflow-y-auto">
          <LogLine level="INFO" msg={`[SIMULATION] tick=${tick} duration=${tickDuration}ms`} />
          <LogLine level="INFO" msg={`[WEBSOCKET] traffic channel ${connected ? 'connected' : 'disconnected'}`} />
          <LogLine level="INFO" msg={`[STATUS] simulation=${status?.status ?? 'unknown'} speed=${status?.speed_multiplier ?? 1}x`} />
        </div>
      </div>
    </div>
  )
}

function LogLine({ level, msg }: { level: string; msg: string }) {
  const levelColors = {
    INFO: 'text-blue-600',
    WARN: 'text-yellow-600',
    ERROR: 'text-red-600',
    DEBUG: 'text-slate-500',
  }

  return (
    <div className="flex gap-2">
      <span className={`${levelColors[level as keyof typeof levelColors] || 'text-slate-500'}`}>
        [{level}]
      </span>
      <span className="text-slate-700">{msg}</span>
    </div>
  )
}