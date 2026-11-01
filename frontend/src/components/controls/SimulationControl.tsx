import { useState, useRef, useEffect } from 'react'

interface SimulationControlProps {
  running: boolean
  speed: number
  onToggle: (running: boolean) => void
  onSpeedChange: (speed: number) => void
  onReset: () => void
  onScenario: (scenario: string) => Promise<boolean | void> | void
}

interface Scenario {
  id: string
  label: string
  description: string
  icon: string
}

const SCENARIOS: Scenario[] = [
  { id: 'normal', label: 'Normal Traffic', description: 'Baseline traffic conditions', icon: '🚗' },
  { id: 'rush_hour', label: 'Morning Rush', description: 'Peak hour traffic buildup', icon: '🌅' },
  { id: 'major_jam', label: 'Major Jam', description: 'Severe bottleneck formation', icon: '🚦' },
  { id: 'accident', label: 'Accident', description: 'High-severity incident with capacity reduction', icon: '💥' },
  { id: 'road_closure', label: 'Road Closure', description: 'Major road closed, traffic redistributes', icon: '🚧' },
  { id: 'heavy_rain', label: 'Heavy Rain', description: 'Speed/capacity reductions across network', icon: '🌧️' },
  { id: 'traffic_surge', label: 'Traffic Surge', description: '30% demand increase city-wide', icon: '📈' },
  { id: 'major_event', label: 'Major Event', description: 'Unusual demand around venue', icon: '🎪' },
]

export function SimulationControl({ running, speed, onToggle, onSpeedChange, onReset, onScenario }: SimulationControlProps) {
  const [isDemoOpen, setIsDemoOpen] = useState(false)
  const [loadingScenarioId, setLoadingScenarioId] = useState<string | null>(null)
  const [activeScenarioId, setActiveScenarioId] = useState<string | null>('normal')
  const [feedback, setFeedback] = useState<{ message: string; isError?: boolean } | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const feedbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDemoOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Close dropdown on Escape key
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsDemoOpen(false)
      }
    }

    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [])

  const handleScenarioClick = async (scenario: Scenario) => {
    if (loadingScenarioId) return // Prevent duplicate submissions

    setLoadingScenarioId(scenario.id)
    try {
      await onScenario(scenario.id)
      setActiveScenarioId(scenario.id)
      setFeedback({ message: `Active: ${scenario.label}` })
      
      if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current)
      feedbackTimerRef.current = setTimeout(() => {
        setFeedback(null)
      }, 4000)
    } catch (err: any) {
      setFeedback({ message: `Failed to apply ${scenario.label}`, isError: true })
    } finally {
      setLoadingScenarioId(null)
      setIsDemoOpen(false)
    }
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button
        onClick={() => onToggle(!running)}
        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
          running
            ? 'bg-red-500 text-white hover:bg-red-600'
            : 'bg-green-500 text-white hover:bg-green-600'
        }`}
      >
        {running ? '⏸ Pause' : '▶ Start'}
      </button>

      <select
        value={speed}
        onChange={(e) => onSpeedChange(Number(e.target.value))}
        className="px-2 py-1.5 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-primary-500"
      >
        <option value={1}>1x</option>
        <option value={5}>5x</option>
        <option value={10}>10x</option>
        <option value={30}>30x</option>
      </select>

      <button 
        onClick={() => {
          setActiveScenarioId('normal')
          setFeedback(null)
          onReset()
        }}
        className="px-3 py-1.5 rounded-lg text-sm font-medium bg-slate-200 text-slate-700 hover:bg-slate-300 transition-colors"
      >
        ↻ Reset
      </button>

      <div className="relative" ref={dropdownRef}>
        <button 
          id="demo-scenarios-btn"
          onClick={() => setIsDemoOpen(!isDemoOpen)}
          disabled={loadingScenarioId !== null}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors flex items-center gap-1.5 ${
            loadingScenarioId
              ? 'bg-amber-400 text-white cursor-wait opacity-90'
              : 'bg-amber-500 text-white hover:bg-amber-600'
          }`}
          aria-expanded={isDemoOpen}
          aria-haspopup="true"
        >
          {loadingScenarioId ? (
            <svg className="animate-spin h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
            </svg>
          ) : (
            <span>🎬</span>
          )}
          <span>Demo</span>
          {loadingScenarioId && <span className="text-xs opacity-90">...</span>}
          <svg className={`w-3 h-3 transition-transform ${isDemoOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        {isDemoOpen && (
          <div 
            className="absolute top-full left-0 mt-1 z-30 bg-white border border-slate-200 rounded-lg shadow-xl py-1 min-w-[220px]"
            role="menu"
            aria-orientation="vertical"
          >
            {SCENARIOS.map((scenario) => {
              const isSelected = activeScenarioId === scenario.id
              const isLoadingThis = loadingScenarioId === scenario.id

              return (
                <button
                  key={scenario.id}
                  onClick={() => handleScenarioClick(scenario)}
                  disabled={loadingScenarioId !== null}
                  className={`w-full px-3 py-2 text-left text-sm transition-colors flex items-center gap-2.5 ${
                    isSelected ? 'bg-amber-50 text-amber-900 font-medium' : 'text-slate-700 hover:bg-slate-100'
                  } ${loadingScenarioId ? 'cursor-not-allowed opacity-75' : ''}`}
                  role="menuitem"
                >
                  <span className="text-base">{isLoadingThis ? '⏳' : scenario.icon}</span>
                  <div className="flex flex-col flex-1">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-slate-800">{scenario.label}</span>
                      {isSelected && <span className="text-xs text-amber-600 font-bold ml-1">●</span>}
                    </div>
                    <span className="text-xs text-slate-500 leading-tight">{scenario.description}</span>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {feedback && (
        <div 
          className={`text-xs px-2.5 py-1 rounded-md font-medium flex items-center gap-1.5 transition-all duration-300 ${
            feedback.isError 
              ? 'bg-red-100 text-red-800 border border-red-200' 
              : 'bg-emerald-50 text-emerald-800 border border-emerald-200'
          }`}
          role="status"
        >
          <span>{feedback.isError ? '⚠️' : '✓'}</span>
          <span>{feedback.message}</span>
        </div>
      )}
    </div>
  )
}
