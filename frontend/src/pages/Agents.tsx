import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { RefreshCw, Brain, TrendingUp, Shield, Target, BarChart3, Activity, Eye, Zap } from 'lucide-react'

// Agent definitions with personalities
const AGENTS = [
  {
    id: 'technical_analyst',
    name: 'Technical Analyst',
    icon: BarChart3,
    color: 'text-blue-400',
    role: 'Analyzes price action, indicators, and chart patterns across M30/H1/H4/D1',
    looks_for: 'Trend alignment, RSI divergences, MA crossovers, support/resistance',
  },
  {
    id: 'structure_analyst', 
    name: 'Structure Analyst',
    icon: Target,
    color: 'text-purple-400',
    role: 'Identifies key support/resistance levels and market structure',
    looks_for: 'Swing highs/lows, order blocks, liquidity zones, break of structure',
  },
  {
    id: 'regime_detector',
    name: 'Regime Detector',
    icon: Activity,
    color: 'text-yellow-400',
    role: 'Classifies current market conditions and volatility',
    looks_for: 'Trending vs ranging, volatility regime, session characteristics',
  },
  {
    id: 'risk_manager',
    name: 'Risk Manager',
    icon: Shield,
    color: 'text-red-400',
    role: 'Evaluates risk and has VETO power over all trades',
    looks_for: 'Position sizing, drawdown limits, correlation risk, news events',
  },
  {
    id: 'orchestrator',
    name: 'Orchestrator (Me)',
    icon: Brain,
    color: 'text-green-400',
    role: 'Central decision maker - combines all agent inputs for final call',
    looks_for: 'Confluence across agents, optimal entry timing, trade management',
  },
  {
    id: 'execution_agent',
    name: 'Execution Agent',
    icon: Zap,
    color: 'text-orange-400',
    role: 'Handles order placement and trade management',
    looks_for: 'Spread conditions, slippage, order fill quality, position status',
  },
]

export default function Agents() {
  const { data: analysis = {} as any, isLoading, refetch, isFetching } = useQuery<any>({
    queryKey: ['analysis'],
    queryFn: () => api.get('/api/analysis'),
    refetchInterval: 5000,
  })

  const { data: status = {} as any } = useQuery<any>({
    queryKey: ['status'],
    queryFn: () => api.get('/status'),
    refetchInterval: 5000,
  })

  // Generate agent states based on current analysis
  const getAgentState = (agentId: string) => {
    const symbols = Object.keys(analysis)
    if (symbols.length === 0) return { status: 'waiting', message: 'Waiting for market data...' }

    switch(agentId) {
      case 'technical_analyst': {
        const aligned = symbols.filter(s => analysis[s]?.mtf_alignment_score >= 0.7)
        const highConf = symbols.filter(s => analysis[s]?.confluence_score >= 0.65)
        return {
          status: aligned.length > 0 ? 'active' : 'monitoring',
          message: `${aligned.length} symbols with strong MTF alignment. ${highConf.length} above confluence threshold.`,
          details: aligned.length > 0 ? `Strong: ${aligned.join(', ')}` : 'No strong setups currently'
        }
      }
      case 'structure_analyst': {
        const nearLevels = symbols.filter(s => {
          const a = analysis[s]
          if (!a?.current_price || !a?.indicators?.M30) return false
          const range = a.indicators.M30.sma_20 - a.indicators.M30.sma_50
          return Math.abs(range) < 0.001 // Near key levels
        })
        return {
          status: 'monitoring',
          message: `Tracking S/R levels across ${symbols.length} pairs.`,
          details: 'Swing highs/lows updated every 30s'
        }
      }
      case 'regime_detector': {
        const lowVol = symbols.filter(s => analysis[s]?.volatility === 'low')
        const normalVol = symbols.filter(s => analysis[s]?.volatility === 'normal')
        const highVol = symbols.filter(s => analysis[s]?.volatility === 'high')
        return {
          status: 'active',
          message: `Low: ${lowVol.length} | Normal: ${normalVol.length} | High: ${highVol.length}`,
          details: lowVol.length > normalVol.length ? '⚠️ Low volatility environment' : '✅ Normal trading conditions'
        }
      }
      case 'risk_manager': {
        const drawdown = status?.current_drawdown_pct || 0
        const positions = status?.open_positions || 0
        return {
          status: drawdown > 2 ? 'alert' : 'active',
          message: `Drawdown: ${drawdown.toFixed(2)}% | Open: ${positions} positions`,
          details: drawdown > 2 ? '⚠️ Elevated drawdown - increased caution' : '✅ Risk within limits'
        }
      }
      case 'orchestrator': {
        const tradeable = symbols.filter(s => analysis[s]?.confluence_score >= 0.65)
        const watchlist = symbols.filter(s => {
          const score = analysis[s]?.confluence_score || 0
          return score >= 0.5 && score < 0.65
        })
        return {
          status: tradeable.length > 0 ? 'active' : 'monitoring',
          message: `${tradeable.length} tradeable | ${watchlist.length} on watchlist`,
          details: tradeable.length > 0 
            ? `🎯 Ready: ${tradeable.join(', ')}`
            : 'Waiting for confluence threshold (0.65)'
        }
      }
      case 'execution_agent': {
        return {
          status: status?.trading_mode === 'paper' ? 'standby' : 'active',
          message: `Mode: ${(status?.trading_mode || 'paper').toUpperCase()}`,
          details: status?.trading_mode === 'paper' 
            ? '📝 Paper trading - simulated execution'
            : '⚡ Live execution enabled'
        }
      }
      default:
        return { status: 'unknown', message: 'Unknown agent' }
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Agent Status</h1>
        <button 
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-secondary)] rounded-lg hover:bg-[var(--bg-tertiary)] disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Summary */}
      <div className="card bg-gradient-to-r from-[var(--bg-secondary)] to-[var(--bg-tertiary)]">
        <div className="flex items-center gap-3 mb-2">
          <Brain className="w-6 h-6 text-green-400" />
          <h2 className="text-lg font-bold">System Overview</h2>
        </div>
        <p className="text-[var(--text-secondary)]">
          {Object.keys(analysis).length} symbols being analyzed | 
          Mode: {(status?.trading_mode || 'paper').toUpperCase()} | 
          Kill Switches: {status?.kill_switches_active ? '🔴 ACTIVE' : '🟢 Clear'}
        </p>
      </div>

      {/* Agent Cards */}
      {isLoading ? (
        <div className="text-center py-10">Loading agent states...</div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {AGENTS.map(agent => {
            const state = getAgentState(agent.id)
            const Icon = agent.icon
            
            return (
              <div key={agent.id} className="card">
                <div className="flex items-start gap-3">
                  <div className={`p-2 rounded-lg bg-[var(--bg-tertiary)] ${agent.color}`}>
                    <Icon className="w-6 h-6" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-bold">{agent.name}</h3>
                      <StatusBadge status={state.status} />
                    </div>
                    <p className="text-sm text-[var(--text-muted)] mt-1">{agent.role}</p>
                  </div>
                </div>
                
                <div className="mt-4 p-3 bg-[var(--bg-tertiary)] rounded-lg">
                  <div className="text-sm font-medium">{state.message}</div>
                  {state.details && (
                    <div className="text-xs text-[var(--text-muted)] mt-1">{state.details}</div>
                  )}
                </div>

                <div className="mt-3 text-xs text-[var(--text-muted)]">
                  <Eye className="w-3 h-3 inline mr-1" />
                  Looking for: {agent.looks_for}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Top Opportunities */}
      <div className="card">
        <h2 className="text-lg font-bold mb-4">🎯 Top Opportunities</h2>
        <div className="space-y-2">
          {Object.entries(analysis)
            .sort(([,a]: any, [,b]: any) => (b.confluence_score || 0) - (a.confluence_score || 0))
            .slice(0, 5)
            .map(([symbol, data]: [string, any]) => (
              <div key={symbol} className="flex items-center justify-between p-2 bg-[var(--bg-secondary)] rounded">
                <div className="flex items-center gap-3">
                  <span className="font-mono font-bold">{symbol}</span>
                  <span className={`text-sm ${data.overall_bias === 'bullish' ? 'text-green-400' : data.overall_bias === 'bearish' ? 'text-red-400' : 'text-gray-400'}`}>
                    {data.overall_bias?.toUpperCase()}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-sm">
                  <span>MTF: {((data.mtf_alignment_score || 0) * 100).toFixed(0)}%</span>
                  <span className={data.confluence_score >= 0.65 ? 'text-green-400 font-bold' : ''}>
                    Score: {((data.confluence_score || 0) * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            ))
          }
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    active: 'bg-green-500/20 text-green-400',
    monitoring: 'bg-blue-500/20 text-blue-400',
    waiting: 'bg-gray-500/20 text-gray-400',
    standby: 'bg-yellow-500/20 text-yellow-400',
    alert: 'bg-red-500/20 text-red-400',
  }
  
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[status] || colors.waiting}`}>
      {status.toUpperCase()}
    </span>
  )
}
