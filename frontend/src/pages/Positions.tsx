import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { X, Edit2, TrendingUp, TrendingDown } from 'lucide-react'
import { useState } from 'react'

export default function Positions() {
  const queryClient = useQueryClient()
  const [selectedTicket, setSelectedTicket] = useState<number | null>(null)
  
  const { data: positions = [] as any, isLoading } = useQuery<any>({
    queryKey: ['positions'],
    queryFn: () => api.get('/api/positions'),
    refetchInterval: 5000,
  })
  
  const closeMutation = useMutation({
    mutationFn: (ticket: number) => api.post(`/api/positions/${ticket}/close`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['positions'] })
      queryClient.invalidateQueries({ queryKey: ['account'] })
    },
  })
  
  if (isLoading) {
    return <div className="text-center py-10">Loading positions...</div>
  }
  
  const openPositions = positions || []
  const totalPnl = openPositions.reduce((sum: number, p: any) => sum + (p.unrealized_pnl || 0), 0)
  
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Open Positions</h1>
        <div className={`text-lg font-bold ${totalPnl >= 0 ? 'text-bullish' : 'text-bearish'}`}>
          Total: {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
        </div>
      </div>
      
      {openPositions.length === 0 ? (
        <div className="card text-center py-12">
          <div className="text-[var(--text-muted)] text-lg">No open positions</div>
          <div className="text-sm text-[var(--text-muted)] mt-2">
            Positions will appear here when trades are executed
          </div>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="data-table">
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Symbol</th>
                <th>Direction</th>
                <th>Volume</th>
                <th>Entry</th>
                <th>Current</th>
                <th>Stop Loss</th>
                <th>Take Profit</th>
                <th>P&L</th>
                <th>Pips</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {openPositions.map((pos: any) => (
                <tr key={pos.ticket}>
                  <td className="font-mono text-sm">{pos.ticket}</td>
                  <td className="font-medium">{pos.symbol}</td>
                  <td>
                    <span className={`flex items-center gap-1 ${
                      pos.direction === 'long' ? 'text-bullish' : 'text-bearish'
                    }`}>
                      {pos.direction === 'long' ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                      {pos.direction.toUpperCase()}
                    </span>
                  </td>
                  <td>{pos.volume}</td>
                  <td className="font-mono text-sm">{pos.entry_price?.toFixed(5)}</td>
                  <td className="font-mono text-sm">{pos.current_price?.toFixed(5)}</td>
                  <td className="font-mono text-sm text-bearish">{pos.stop_loss?.toFixed(5)}</td>
                  <td className="font-mono text-sm text-bullish">
                    {pos.take_profit?.toFixed(5) || '-'}
                  </td>
                  <td className={`font-bold ${pos.unrealized_pnl >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                    {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl?.toFixed(2)}
                  </td>
                  <td className={pos.unrealized_pips >= 0 ? 'text-bullish' : 'text-bearish'}>
                    {pos.unrealized_pips >= 0 ? '+' : ''}{pos.unrealized_pips?.toFixed(1)}
                  </td>
                  <td>
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => setSelectedTicket(pos.ticket)}
                        className="p-1 hover:bg-[var(--bg-tertiary)] rounded"
                        title="Modify"
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button 
                        onClick={() => {
                          if (confirm(`Close position ${pos.ticket} on ${pos.symbol}?`)) {
                            closeMutation.mutate(pos.ticket)
                          }
                        }}
                        className="p-1 hover:bg-red-500/20 rounded text-red-400"
                        title="Close"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      
      {/* Position Stats */}
      {openPositions.length > 0 && (
        <div className="grid grid-cols-4 gap-4">
          <StatCard 
            label="Positions" 
            value={openPositions.length} 
          />
          <StatCard 
            label="Total Risk" 
            value={`${openPositions.reduce((s: number, p: any) => s + (p.risk_pct || 0), 0).toFixed(2)}%`}
          />
          <StatCard 
            label="Avg MAE" 
            value={`${(openPositions.reduce((s: number, p: any) => s + (p.mae_pips || 0), 0) / openPositions.length).toFixed(1)} pips`}
          />
          <StatCard 
            label="Avg MFE" 
            value={`${(openPositions.reduce((s: number, p: any) => s + (p.mfe_pips || 0), 0) / openPositions.length).toFixed(1)} pips`}
          />
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card text-center">
      <div className="text-xs text-[var(--text-muted)] uppercase mb-1">{label}</div>
      <div className="text-xl font-bold">{value}</div>
    </div>
  )
}
