import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { Calendar, Filter } from 'lucide-react'
import { useState } from 'react'

export default function Journal() {
  const [symbolFilter, setSymbolFilter] = useState('')
  
  const { data: entries = [] as any, isLoading } = useQuery<any>({
    queryKey: ['journal', symbolFilter],
    queryFn: () => api.get(`/api/journal${symbolFilter ? `?symbol=${symbolFilter}` : ''}`),
  })
  
  if (isLoading) {
    return <div className="text-center py-10">Loading journal...</div>
  }
  
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Trade Journal</h1>
        <div className="flex items-center gap-4">
          <select 
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
            className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg px-3 py-2"
          >
            <option value="">All Symbols</option>
            {['EURUSD', 'GBPUSD', 'USDJPY', 'GBPJPY', 'USDCHF', 'USDCAD', 'EURAUD', 'AUDNZD', 'AUDUSD'].map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>
      
      {!entries || entries.length === 0 ? (
        <div className="card text-center py-12">
          <Calendar className="w-12 h-12 mx-auto mb-4 text-[var(--text-muted)]" />
          <div className="text-[var(--text-muted)] text-lg">No journal entries yet</div>
          <div className="text-sm text-[var(--text-muted)] mt-2">
            Journal entries are created automatically after trades close
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {entries.map((entry: any) => (
            <JournalCard key={entry.journal_id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  )
}

function JournalCard({ entry }: { entry: any }) {
  const isWin = (entry.result_pnl || 0) >= 0
  
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="font-bold text-lg">{entry.symbol}</span>
          <span className={`px-2 py-0.5 rounded text-sm ${
            entry.direction === 'long' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
          }`}>
            {entry.direction?.toUpperCase()}
          </span>
          <span className="text-sm text-[var(--text-muted)]">{entry.strategy_name}</span>
        </div>
        <div className="text-right">
          <div className={`text-lg font-bold ${isWin ? 'text-bullish' : 'text-bearish'}`}>
            {isWin ? '+' : ''}${entry.result_pnl?.toFixed(2)}
          </div>
          <div className="text-sm text-[var(--text-muted)]">
            {entry.result_r ? `${entry.result_r > 0 ? '+' : ''}${entry.result_r.toFixed(2)}R` : ''}
          </div>
        </div>
      </div>
      
      <div className="grid grid-cols-6 gap-4 text-sm mb-4">
        <div>
          <div className="text-[var(--text-muted)]">Entry</div>
          <div className="font-mono">{entry.entry_price?.toFixed(5)}</div>
        </div>
        <div>
          <div className="text-[var(--text-muted)]">Exit</div>
          <div className="font-mono">{entry.exit_price?.toFixed(5) || '-'}</div>
        </div>
        <div>
          <div className="text-[var(--text-muted)]">Stop Loss</div>
          <div className="font-mono">{entry.stop_loss?.toFixed(5)}</div>
        </div>
        <div>
          <div className="text-[var(--text-muted)]">Exit Type</div>
          <div>{entry.exit_type || '-'}</div>
        </div>
        <div>
          <div className="text-[var(--text-muted)]">MAE</div>
          <div className="text-bearish">{entry.mae_pips?.toFixed(1)} pips</div>
        </div>
        <div>
          <div className="text-[var(--text-muted)]">MFE</div>
          <div className="text-bullish">{entry.mfe_pips?.toFixed(1)} pips</div>
        </div>
      </div>
      
      <div className="flex items-center justify-between text-sm text-[var(--text-muted)]">
        <div>
          {new Date(entry.created_at).toLocaleDateString()} • {entry.session} session • Regime: {entry.regime}
        </div>
        <div>
          Score: {(entry.confluence_score * 100).toFixed(0)}%
        </div>
      </div>
    </div>
  )
}
