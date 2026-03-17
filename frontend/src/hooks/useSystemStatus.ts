import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export interface SystemStatus {
  timestamp: string
  trading_mode: 'paper' | 'shadow' | 'live'
  effective_mode: string
  risk_mode: string
  open_positions: number
  today_trades: number
  today_pnl: number
  current_drawdown_pct: number
  kill_switches_active: boolean
  equity?: number
  balance?: number
}

export function useSystemStatus() {
  return useQuery<SystemStatus>({
    queryKey: ['system-status'],
    queryFn: () => api.get('/status'),
    refetchInterval: 5000,
  })
}

export function useHealthCheck() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => api.get('/health/detailed'),
    refetchInterval: 10000,
  })
}
