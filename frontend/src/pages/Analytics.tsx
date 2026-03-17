import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { BarChart3, TrendingUp, Target, Percent } from 'lucide-react'

export default function Analytics() {
  const { data: metrics = {} as any, isLoading } = useQuery<any>({
    queryKey: ['analytics'],
    queryFn: () => api.get('/api/analytics'),
  })
  
  const { data: bySymbol = [] as any } = useQuery<any>({
    queryKey: ['analytics-by-symbol'],
    queryFn: () => api.get('/api/analytics/by-symbol'),
  })
  
  const { data: byStrategy = [] as any } = useQuery<any>({
    queryKey: ['analytics-by-strategy'],
    queryFn: () => api.get('/api/analytics/by-strategy'),
  })
  
  if (isLoading) {
    return <div className="text-center py-10">Loading analytics...</div>
  }
  
  const stats = metrics || {
    total_trades: 0,
    win_rate: 0,
    profit_factor: 0,
    expectancy: 0,
    avg_win: 0,
    avg_loss: 0,
    largest_win: 0,
    largest_loss: 0,
    max_drawdown: 0,
    sharpe_ratio: 0,
  }
  
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Performance Analytics</h1>
      
      {/* Key Metrics */}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard
          icon={<BarChart3 className="w-5 h-5" />}
          label="Total Trades"
          value={stats.total_trades}
        />
        <MetricCard
          icon={<Target className="w-5 h-5" />}
          label="Win Rate"
          value={`${(stats.win_rate * 100).toFixed(1)}%`}
          color={stats.win_rate >= 0.5 ? 'green' : 'red'}
        />
        <MetricCard
          icon={<TrendingUp className="w-5 h-5" />}
          label="Profit Factor"
          value={stats.profit_factor?.toFixed(2) || '-'}
          color={stats.profit_factor >= 1.5 ? 'green' : stats.profit_factor >= 1 ? 'yellow' : 'red'}
        />
        <MetricCard
          icon={<Percent className="w-5 h-5" />}
          label="Expectancy"
          value={`${stats.expectancy?.toFixed(2) || 0}R`}
          color={stats.expectancy > 0 ? 'green' : 'red'}
        />
      </div>
      
      {/* Detailed Stats */}
      <div className="grid grid-cols-2 gap-6">
        <div className="card">
          <div className="card-header">Win/Loss Breakdown</div>
          <div className="grid grid-cols-2 gap-4">
            <StatRow label="Avg Win" value={`$${stats.avg_win?.toFixed(2) || 0}`} color="green" />
            <StatRow label="Avg Loss" value={`$${stats.avg_loss?.toFixed(2) || 0}`} color="red" />
            <StatRow label="Largest Win" value={`$${stats.largest_win?.toFixed(2) || 0}`} color="green" />
            <StatRow label="Largest Loss" value={`$${stats.largest_loss?.toFixed(2) || 0}`} color="red" />
          </div>
        </div>
        
        <div className="card">
          <div className="card-header">Risk Metrics</div>
          <div className="grid grid-cols-2 gap-4">
            <StatRow label="Max Drawdown" value={`${stats.max_drawdown?.toFixed(2) || 0}%`} />
            <StatRow label="Sharpe Ratio" value={stats.sharpe_ratio?.toFixed(2) || '-'} />
            <StatRow label="Avg R:R" value={stats.avg_rr?.toFixed(2) || '-'} />
            <StatRow label="Avg Duration" value={`${stats.avg_duration_min || 0} min`} />
          </div>
        </div>
      </div>
      
      {/* Performance by Symbol */}
      <div className="card">
        <div className="card-header">Performance by Symbol</div>
        {!bySymbol || bySymbol.length === 0 ? (
          <div className="text-center text-[var(--text-muted)] py-8">
            No data yet
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Trades</th>
                <th>Win Rate</th>
                <th>P&L</th>
                <th>Profit Factor</th>
                <th>Avg R</th>
              </tr>
            </thead>
            <tbody>
              {bySymbol.map((row: any) => (
                <tr key={row.symbol}>
                  <td className="font-medium">{row.symbol}</td>
                  <td>{row.trades}</td>
                  <td className={row.win_rate >= 0.5 ? 'text-bullish' : 'text-bearish'}>
                    {(row.win_rate * 100).toFixed(0)}%
                  </td>
                  <td className={row.pnl >= 0 ? 'text-bullish' : 'text-bearish'}>
                    {row.pnl >= 0 ? '+' : ''}${row.pnl?.toFixed(2)}
                  </td>
                  <td>{row.profit_factor?.toFixed(2)}</td>
                  <td>{row.avg_r?.toFixed(2)}R</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      
      {/* Performance by Strategy */}
      <div className="card">
        <div className="card-header">Performance by Strategy</div>
        {!byStrategy || byStrategy.length === 0 ? (
          <div className="text-center text-[var(--text-muted)] py-8">
            No data yet
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Trades</th>
                <th>Win Rate</th>
                <th>P&L</th>
                <th>Profit Factor</th>
                <th>Expectancy</th>
              </tr>
            </thead>
            <tbody>
              {byStrategy.map((row: any) => (
                <tr key={row.strategy}>
                  <td className="font-medium">{row.strategy}</td>
                  <td>{row.trades}</td>
                  <td className={row.win_rate >= 0.5 ? 'text-bullish' : 'text-bearish'}>
                    {(row.win_rate * 100).toFixed(0)}%
                  </td>
                  <td className={row.pnl >= 0 ? 'text-bullish' : 'text-bearish'}>
                    {row.pnl >= 0 ? '+' : ''}${row.pnl?.toFixed(2)}
                  </td>
                  <td>{row.profit_factor?.toFixed(2)}</td>
                  <td>{row.expectancy?.toFixed(2)}R</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function MetricCard({ 
  icon, 
  label, 
  value, 
  color 
}: { 
  icon: React.ReactNode
  label: string
  value: string | number
  color?: 'green' | 'red' | 'yellow'
}) {
  const colorClass = color === 'green' ? 'text-bullish' : color === 'red' ? 'text-bearish' : color === 'yellow' ? 'text-neutral' : ''
  
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[var(--text-muted)]">{icon}</span>
      </div>
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${colorClass}`}>{value}</div>
    </div>
  )
}

function StatRow({ label, value, color }: { label: string; value: string; color?: 'green' | 'red' }) {
  return (
    <div className="flex justify-between items-center py-2">
      <span className="text-[var(--text-muted)]">{label}</span>
      <span className={`font-medium ${color === 'green' ? 'text-bullish' : color === 'red' ? 'text-bearish' : ''}`}>
        {value}
      </span>
    </div>
  )
}
