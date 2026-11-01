import { useState, useEffect } from 'react'
import { explanationsApi } from '../../services/api'

export function AIInsightsPanel() {
  const [providerInfo, setProviderInfo] = useState<{
    provider: string
    model?: string
    isNim: boolean
    configured: boolean
  }>({
    provider: 'Checking...',
    model: undefined,
    isNim: false,
    configured: false,
  })
  const [liveExplanation, setLiveExplanation] = useState<string | null>(null)
  const [loadingExplanation, setLoadingExplanation] = useState(false)

  useEffect(() => {
    explanationsApi
      .getHealth()
      .then((res) => {
        const isNim = res.data?.active_provider === 'nvidia_nim'
        setProviderInfo({
          provider: isNim ? 'NVIDIA NIM' : 'Template (fallback)',
          model: res.data?.nvidia_nim?.model,
          isNim,
          configured: !!res.data?.nvidia_nim?.configured,
        })
      })
      .catch(() => {
        setProviderInfo({
          provider: 'Template (fallback)',
          isNim: false,
          configured: false,
        })
      })
  }, [])

  const handleGenerateLive = async () => {
    setLoadingExplanation(true)
    try {
      const res = await explanationsApi.generate({
        recommended_route: {
          algorithm: 'neuro_route',
          distance_km: 12.5,
          current_eta_sec: 900,
          predicted_eta_sec: 840,
          congestion_risk: 'low',
        },
        current_congestion: { level: 'moderate', score: 0.42 },
        predicted_congestion: { level: 'free', score: 0.18 },
        reroute_reason: 'dynamic congestion avoidance via NeuroRoute AI',
        road_name: 'Highway 101',
      })
      setLiveExplanation(res.data.explanation)
    } catch (e: any) {
      setLiveExplanation('Failed to generate live explanation. Check backend connection.')
    } finally {
      setLoadingExplanation(false)
    }
  }

  return (
    <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-slate-900 flex items-center gap-2">
          🤖 AI Insights
        </h3>
        <span
          className={`text-xs px-2.5 py-1 rounded-full font-medium ${
            providerInfo.isNim
              ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
              : 'bg-amber-100 text-amber-800 border border-amber-300'
          }`}
        >
          {providerInfo.isNim ? '⚡ NVIDIA NIM' : '📄 Template Fallback'}
        </span>
      </div>

      <div className="space-y-3">
        {liveExplanation && (
          <InsightCard
            title="Live NVIDIA NIM Explanation"
            content={liveExplanation}
            type="recommendation"
          />
        )}

        <InsightCard
          title="Route Recommendation"
          content="Route B (9.2 km) is recommended over Route A (7.8 km). Although Route A is shorter, predicted congestion on R102-R105 will increase travel time from 19 min to 31 min over the next 15 minutes. Route B maintains a stable 23 min ETA."
          type="recommendation"
        />

        <InsightCard
          title="Congestion Alert"
          content="Road R102 congestion rising rapidly (0.35 → 0.72 predicted in 30 min). Upstream propagation affecting R101 (+18%) and R103 (+24%). Consider pre-emptive rerouting."
          type="warning"
        />

        <InsightCard
          title="Incident Impact"
          content="Accident on R102 reduces capacity by 70%. Traffic redistributed: R101 +21%, R103 +34%, R105 +14%. NeuroRoute has recalculated 3 alternative routes."
          type="info"
        />

        <InsightCard
          title="Weather Effect"
          content="Heavy rain reducing speeds by 15-20% across all road types. Highway capacity reduced 25%. Prediction confidence: 89%. Recommend increasing following distance."
          type="info"
        />
      </div>

      <div className="mt-4 p-3 bg-white rounded-lg border border-slate-200 flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs text-slate-600">
          <span>
            Provider: <strong className="text-slate-800">{providerInfo.provider}</strong>
            {providerInfo.model && ` (${providerInfo.model})`}
          </span>
          <button
            onClick={handleGenerateLive}
            disabled={loadingExplanation}
            className="px-2.5 py-1 bg-slate-900 text-white rounded hover:bg-slate-800 text-xs font-medium disabled:opacity-50 transition-colors"
          >
            {loadingExplanation ? 'Generating...' : 'Test NIM Live'}
          </button>
        </div>
      </div>
    </div>
  )
}

function InsightCard({ title, content, type }: { title: string; content: string; type: 'recommendation' | 'warning' | 'info' }) {
  const typeStyles = {
    recommendation: 'bg-blue-50 border-blue-200',
    warning: 'bg-yellow-50 border-yellow-200',
    info: 'bg-green-50 border-green-200',
  }

  const typeIcons = {
    recommendation: '🎯',
    warning: '⚠️',
    info: 'ℹ️',
  }

  return (
    <div className={`p-3 rounded-lg border ${typeStyles[type]}`}>
      <div className="flex items-start gap-2">
        <span className="text-lg">{typeIcons[type]}</span>
        <div className="flex-1">
          <p className="font-medium text-slate-900 text-sm">{title}</p>
          <p className="text-sm text-slate-600 mt-1">{content}</p>
        </div>
      </div>
    </div>
  )
}