import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { CheckCircle, XCircle, Clock, AlertTriangle } from 'lucide-react'

export default function TradeIdeas() {
  const { data: ideas = [] as any, isLoading } = useQuery<any>({
    queryKey: ['trade-ideas'],
    queryFn: () => api.get('/api/trade-ideas'),
    refetchInterval: 30000,
  })
  
  const { data: rejections = [] as any } = useQuery<any>({
    queryKey: ['rejections'],
    queryFn: () => api.get('/api/rejections?limit=20'),
  })
  
  if (isLoading) {
    return <div className="text-center py-10">Loading trade ideas...</div>
  }
  
  const approved = ideas?.filter((i: any) => i.decision === 'BUY' || i.decision === 'SELL') || []
  const watchlist = ideas?.filter((i: any) => i.decision === 'WATCHLIST') || []
  
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Trade Ideas</h1>
      
      {/* Approved Ideas */}
      <div className="card">
        <div className="card-header flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-bullish" />
          Approved ({approved.length})
        </div>
        {approved.length === 0 ? (
          <div className="text-center text-[var(--text-muted)] py-8">
            No approved trade ideas currently
          </div>
        ) : (
          <div className="space-y-4">
            {approved.map((idea: any, i: number) => (
              <IdeaCard key={i} idea={idea} />
            ))}
          </div>
        )}
      </div>
      
      {/* Watchlist */}
      <div className="card">
        <div className="card-header flex items-center gap-2">
          <Clock className="w-4 h-4 text-neutral" />
          Watchlist ({watchlist.length})
        </div>
        {watchlist.length === 0 ? (
          <div className="text-center text-[var(--text-muted)] py-8">
            No ideas on watchlist
          </div>
        ) : (
          <div className="space-y-4">
            {watchlist.map((idea: any, i: number) => (
              <IdeaCard key={i} idea={idea} isWatchlist />
            ))}
          </div>
        )}
      </div>
      
      {/* Recent Rejections */}
      <div className="card">
        <div className="card-header flex items-center gap-2">
          <XCircle className="w-4 h-4 text-bearish" />
          Recent Rejections ({rejections?.length || 0})
        </div>
        {!rejections || rejections.length === 0 ? (
          <div className="text-center text-[var(--text-muted)] py-8">
            No recent rejections
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Direction</th>
                <th>Strategy</th>
                <th>Score</th>
                <th>Rejection Reason</th>
              </tr>
            </thead>
            <tbody>
              {rejections.map((rej: any, i: number) => (
                <tr key={i}>
                  <td className="text-sm text-[var(--text-muted)]">
                    {new Date(rej.timestamp).toLocaleTimeString()}
                  </td>
                  <td className="font-medium">{rej.symbol}</td>
                  <td className={rej.proposed_direction === 'long' ? 'text-bullish' : 'text-bearish'}>
                    {rej.proposed_direction?.toUpperCase()}
                  </td>
                  <td>{rej.proposed_strategy}</td>
                  <td>{(rej.confluence_score * 100).toFixed(0)}%</td>
                  <td className="text-sm text-bearish">
                    {rej.rejection_reasons?.[0] || rej.rejection_stage}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function IdeaCard({ idea, isWatchlist = false }: { idea: any; isWatchlist?: boolean }) {
  const plan = idea.trade_plan
  
  return (
    <div className={`p-4 rounded-lg border ${
      isWatchlist 
        ? 'border-yellow-500/30 bg-yellow-500/5' 
        : 'border-green-500/30 bg-green-500/5'
    }`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="font-bold text-lg">{plan?.symbol}</span>
          <span className={`px-2 py-0.5 rounded text-sm font-medium ${
            plan?.direction === 'long' 
              ? 'bg-green-500/20 text-green-400' 
              : 'bg-red-500/20 text-red-400'
          }`}>
            {plan?.direction?.toUpperCase()}
          </span>
          <span className="text-sm text-[var(--text-muted)]">{plan?.strategy_name}</span>
        </div>
        <div className="text-right">
          <div className="text-sm font-medium">
            Score: {(idea.confluence_score * 100).toFixed(0)}%
          </div>
          <div className="text-xs text-[var(--text-muted)]">
            R:R {plan?.risk_reward_ratio?.toFixed(1) || '-'}
          </div>
        </div>
      </div>
      
      <div className="grid grid-cols-4 gap-4 text-sm">
        <div>
          <div className="text-[var(--text-muted)]">Entry</div>
          <div className="font-mono">{plan?.entry_price?.toFixed(5) || 'Market'}</div>
        </div>
        <div>
          <div className="text-[var(--text-muted)]">Stop Loss</div>
          <div className="font-mono text-bearish">{plan?.stop_loss?.toFixed(5)}</div>
        </div>
        <div>
          <div className="text-[var(--text-muted)]">Take Profit</div>
          <div className="font-mono text-bullish">{plan?.take_profit_1?.toFixed(5) || '-'}</div>
        </div>
        <div>
          <div className="text-[var(--text-muted)]">Risk</div>
          <div>{plan?.risk_percent?.toFixed(2)}% / {plan?.lot_size} lots</div>
        </div>
      </div>
      
      {plan?.summary && (
        <div className="mt-3 text-sm text-[var(--text-secondary)]">
          {plan.summary}
        </div>
      )}
      
      {idea.warnings?.length > 0 && (
        <div className="mt-3 flex items-center gap-2 text-sm text-yellow-500">
          <AlertTriangle className="w-4 h-4" />
          {idea.warnings[0]}
        </div>
      )}
    </div>
  )
}
