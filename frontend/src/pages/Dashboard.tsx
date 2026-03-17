import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useSystemStatus } from '../hooks/useSystemStatus'
import { 
  TrendingUp, 
  TrendingDown, 
  AlertCircle,
  CheckCircle,
  Clock,
  Target
} from 'lucide-react'

export default function Dashboard() {
  const { data: status = {} as any, isLoading: statusLoading } = useSystemStatus()
  
  const { data: account = {} as any } = useQuery<any>({
    queryKey: ['account'],
    queryFn: () => api.get('/api/account'),
    refetchInterval: 5000,
  })
  
  const { data: positions = [] as any } = useQuery<any>({
    queryKey: ['positions'],
    queryFn: () => api.get('/api/positions'),
    refetchInterval: 5000,
  })
  
  const { data: recentTrades = [] as any } = useQuery<any>({
    queryKey: ['recent-trades'],
    queryFn: () => api.get('/api/trades/recent?limit=5'),
  })
  
  if (statusLoading) {
    return <div className="text-center py-10">Loading...</div>
  }
  
  const equity = account?.equity || status?.equity || 10000
  const todayPnl = account?.realized_pnl_today || status?.today_pnl || 0
  const drawdown = account?.current_drawdown_pct || status?.current_drawdown_pct || 0
  const openPositions = positions?.length || status?.open_positions || 0
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <Clock className="w-4 h-4" />
          Last updated: {new Date().toLocaleTimeString()}
        </div>
      </div>
      
      {/* Kill Switch Warning */}
      {status?.kill_switches_active && (
        <div className="bg-red-500/20 border border-red-500 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-6 h-6 text-red-500" />
          <div>
            <div className="font-bold text-red-500">TRADING HALTED</div>
            <div className="text-sm text-red-400">Kill switch is active. Check system health for details.</div>
          </div>
        </div>
      )}
      
      {/* Key Metrics */}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard 
          label="Equity"
          value={`$${equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
          icon={<Target className="w-5 h-5" />}
        />
        <MetricCard 
          label="Today's P&L"
          value={`${todayPnl >= 0 ? '+' : ''}$${todayPnl.toFixed(2)}`}
          color={todayPnl >= 0 ? 'green' : 'red'}
          icon={todayPnl >= 0 ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
        />
        <MetricCard 
          label="Drawdown"
          value={`${drawdown.toFixed(2)}%`}
          color={drawdown > 2 ? 'red' : drawdown > 1 ? 'yellow' : 'green'}
          icon={<AlertCircle className="w-5 h-5" />}
        />
        <MetricCard 
          label="Open Positions"
          value={openPositions.toString()}
          icon={<CheckCircle className="w-5 h-5" />}
        />
      </div>
      
      {/* Main Content Grid */}
      <div className="grid grid-cols-2 gap-6">
        {/* Open Positions */}
        <div className="card">
          <div className="card-header">Open Positions</div>
          {!positions || positions.length === 0 ? (
            <div className="text-center text-[var(--text-muted)] py-8">
              No open positions
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Direction</th>
                  <th>Size</th>
                  <th>P&L</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos: any) => (
                  <tr key={pos.ticket}>
                    <td className="font-medium">{pos.symbol}</td>
                    <td className={pos.direction === 'long' ? 'text-bullish' : 'text-bearish'}>
                      {pos.direction.toUpperCase()}
                    </td>
                    <td>{pos.volume}</td>
                    <td className={pos.unrealized_pnl >= 0 ? 'text-bullish' : 'text-bearish'}>
                      {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl?.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        
        {/* Recent Activity */}
        <div className="card">
          <div className="card-header">Recent Activity</div>
          {!recentTrades || recentTrades.length === 0 ? (
            <div className="text-center text-[var(--text-muted)] py-8">
              No recent trades
            </div>
          ) : (
            <div className="space-y-3">
              {recentTrades.map((trade: any, i: number) => (
                <div key={i} className="flex items-center justify-between py-2 border-b border-[var(--border-color)] last:border-0">
                  <div>
                    <div className="font-medium">{trade.symbol}</div>
                    <div className="text-xs text-[var(--text-muted)]">{trade.strategy_name}</div>
                  </div>
                  <div className="text-right">
                    <div className={trade.result_pnl >= 0 ? 'text-bullish' : 'text-bearish'}>
                      {trade.result_pnl >= 0 ? '+' : ''}${trade.result_pnl?.toFixed(2)}
                    </div>
                    <div className="text-xs text-[var(--text-muted)]">
                      {trade.result_r ? `${trade.result_r > 0 ? '+' : ''}${trade.result_r.toFixed(2)}R` : ''}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      
      {/* System Status */}
      <div className="card">
        <div className="card-header">System Status</div>
        <div className="grid grid-cols-5 gap-4">
          <StatusItem label="Trading Mode" value={status?.trading_mode?.toUpperCase() || 'PAPER'} />
          <StatusItem label="Risk Mode" value={status?.risk_mode || 'Normal'} />
          <StatusItem label="Today's Trades" value={status?.today_trades || 0} />
          <StatusItem 
            label="Kill Switches" 
            value={status?.kill_switches_active ? 'ACTIVE' : 'Clear'} 
            status={status?.kill_switches_active ? 'error' : 'healthy'}
          />
          <StatusItem label="Last Scan" value="Just now" status="healthy" />
        </div>
      </div>
    </div>
  )
}

function MetricCard({ 
  label, 
  value, 
  color = 'default',
  icon 
}: { 
  label: string
  value: string
  color?: 'green' | 'red' | 'yellow' | 'default'
  icon?: React.ReactNode
}) {
  const colorClasses = {
    green: 'text-bullish',
    red: 'text-bearish',
    yellow: 'text-neutral',
    default: 'text-[var(--text-primary)]',
  }
  
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <span className="metric-label">{label}</span>
        <span className={colorClasses[color]}>{icon}</span>
      </div>
      <div className={`metric-value ${colorClasses[color]}`}>{value}</div>
    </div>
  )
}

function StatusItem({ 
  label, 
  value, 
  status 
}: { 
  label: string
  value: string | number
  status?: 'healthy' | 'warning' | 'error'
}) {
  return (
    <div className="text-center">
      <div className="text-xs text-[var(--text-muted)] uppercase mb-1">{label}</div>
      <div className="flex items-center justify-center gap-2">
        {status && <span className={`status-dot ${status}`} />}
        <span className="font-medium">{value}</span>
      </div>
    </div>
  )
}
