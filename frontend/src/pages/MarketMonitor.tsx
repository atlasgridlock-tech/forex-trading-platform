import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { RefreshCw, TrendingUp, TrendingDown, Minus, Activity } from 'lucide-react'

const SYMBOLS = [
  'EURUSD', 'GBPUSD', 'USDJPY', 'GBPJPY', 'USDCHF', 
  'USDCAD', 'EURAUD', 'AUDNZD', 'AUDUSD'
]

export default function MarketMonitor() {
  const { data: marketData = {} as any, isLoading, refetch, isFetching } = useQuery<any>({
    queryKey: ['market-data'],
    queryFn: () => api.get('/api/market-data'),
    refetchInterval: 2000,  // Update every 2 seconds
  })
  
  const snapshots = marketData?.snapshots || {}
  const hasData = Object.keys(snapshots).length > 0
  
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Market Monitor</h1>
        <div className="flex items-center gap-4">
          {hasData && (
            <span className="flex items-center gap-2 text-sm text-green-400">
              <Activity className="w-4 h-4 animate-pulse" />
              Live
            </span>
          )}
          <button 
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-secondary)] rounded-lg hover:bg-[var(--bg-tertiary)] disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>
      
      {isLoading ? (
        <div className="text-center py-10">Loading market data...</div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {SYMBOLS.map(symbol => {
            const data = snapshots[symbol]
            return (
              <SymbolCard 
                key={symbol} 
                symbol={symbol} 
                data={data}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

function SymbolCard({ symbol, data }: { symbol: string; data?: any }) {
  const hasData = data && data.bid && data.ask
  
  // Calculate pip size based on symbol
  const isJPY = symbol.includes('JPY')
  const pipSize = isJPY ? 0.01 : 0.0001
  const decimals = isJPY ? 3 : 5
  
  const bid = data?.bid || 0
  const ask = data?.ask || 0
  const spread = data?.spread || 0
  const lastUpdate = data?.updated_at ? new Date(data.updated_at) : null
  
  // Determine trend based on spread (just for visual, real analysis would be more complex)
  const spreadStatus = spread < 10 ? 'good' : spread < 20 ? 'normal' : 'wide'
  
  return (
    <div className={`card ${hasData ? 'border-green-500/30' : 'border-gray-500/30'}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-bold text-lg">{symbol}</h3>
        {hasData ? (
          <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" title="Live" />
        ) : (
          <span className="w-2 h-2 bg-gray-500 rounded-full" title="No data" />
        )}
      </div>
      
      {hasData ? (
        <>
          {/* Bid/Ask Prices */}
          <div className="flex justify-between items-center mb-3">
            <div>
              <div className="text-xs text-[var(--text-muted)]">BID</div>
              <div className="text-lg font-mono text-red-400">{bid.toFixed(decimals)}</div>
            </div>
            <div className="text-right">
              <div className="text-xs text-[var(--text-muted)]">ASK</div>
              <div className="text-lg font-mono text-green-400">{ask.toFixed(decimals)}</div>
            </div>
          </div>
          
          {/* Spread */}
          <div className="flex justify-between items-center py-2 border-t border-[var(--border-color)]">
            <span className="text-[var(--text-muted)]">Spread</span>
            <span className={`font-medium ${
              spreadStatus === 'good' ? 'text-green-400' : 
              spreadStatus === 'normal' ? 'text-yellow-400' : 'text-red-400'
            }`}>
              {spread.toFixed(1)} pips
            </span>
          </div>
          
          {/* Last Update */}
          {lastUpdate && (
            <div className="text-xs text-[var(--text-muted)] text-center mt-2">
              Updated: {lastUpdate.toLocaleTimeString()}
            </div>
          )}
        </>
      ) : (
        <div className="text-center py-4 text-[var(--text-muted)]">
          Waiting for data...
        </div>
      )}
    </div>
  )
}
