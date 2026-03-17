import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { useSystemStatus } from '../hooks/useSystemStatus'
import { Save, AlertTriangle, RefreshCw } from 'lucide-react'

export default function Settings() {
  const queryClient = useQueryClient()
  const { data: status = {} as any } = useSystemStatus()
  
  const [riskSettings, setRiskSettings] = useState({
    defaultRiskPct: 0.35,
    maxDailyLossPct: 2.0,
    maxWeeklyDrawdownPct: 4.0,
    maxPositions: 5,
  })
  
  const saveMutation = useMutation({
    mutationFn: (settings: typeof riskSettings) => 
      api.post('/api/settings/risk', settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })
  
  const resetMutation = useMutation({
    mutationFn: () => api.post('/api/system/reset-daily'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-status'] })
    },
  })
  
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>
      
      {/* Trading Mode Warning */}
      {status?.trading_mode === 'live' && (
        <div className="bg-red-500/20 border border-red-500 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="w-6 h-6 text-red-500" />
          <div>
            <div className="font-bold text-red-500">LIVE TRADING MODE</div>
            <div className="text-sm text-red-400">
              Changes to settings will affect real money trades.
            </div>
          </div>
        </div>
      )}
      
      {/* Risk Settings */}
      <div className="card">
        <div className="card-header">Risk Management</div>
        <div className="grid grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium mb-2">Default Risk Per Trade (%)</label>
            <input
              type="number"
              step="0.05"
              min="0.1"
              max="1"
              value={riskSettings.defaultRiskPct}
              onChange={(e) => setRiskSettings(s => ({ ...s, defaultRiskPct: parseFloat(e.target.value) }))}
              className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg px-3 py-2"
            />
            <div className="text-xs text-[var(--text-muted)] mt-1">
              Recommended: 0.25-0.50%
            </div>
          </div>
          
          <div>
            <label className="block text-sm font-medium mb-2">Max Daily Loss (%)</label>
            <input
              type="number"
              step="0.5"
              min="1"
              max="5"
              value={riskSettings.maxDailyLossPct}
              onChange={(e) => setRiskSettings(s => ({ ...s, maxDailyLossPct: parseFloat(e.target.value) }))}
              className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg px-3 py-2"
            />
            <div className="text-xs text-[var(--text-muted)] mt-1">
              Trading halts when reached
            </div>
          </div>
          
          <div>
            <label className="block text-sm font-medium mb-2">Max Weekly Drawdown (%)</label>
            <input
              type="number"
              step="0.5"
              min="2"
              max="10"
              value={riskSettings.maxWeeklyDrawdownPct}
              onChange={(e) => setRiskSettings(s => ({ ...s, maxWeeklyDrawdownPct: parseFloat(e.target.value) }))}
              className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg px-3 py-2"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium mb-2">Max Simultaneous Positions</label>
            <input
              type="number"
              min="1"
              max="10"
              value={riskSettings.maxPositions}
              onChange={(e) => setRiskSettings(s => ({ ...s, maxPositions: parseInt(e.target.value) }))}
              className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg px-3 py-2"
            />
          </div>
        </div>
        
        <div className="mt-6 flex justify-end">
          <button
            onClick={() => saveMutation.mutate(riskSettings)}
            disabled={saveMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--accent-blue)] rounded-lg hover:bg-blue-600 disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            Save Risk Settings
          </button>
        </div>
      </div>
      
      {/* System Controls */}
      <div className="card">
        <div className="card-header">System Controls</div>
        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 bg-[var(--bg-tertiary)] rounded-lg">
            <div>
              <div className="font-medium">Reset Daily Counters</div>
              <div className="text-sm text-[var(--text-muted)]">
                Reset daily loss tracking and trade counts
              </div>
            </div>
            <button
              onClick={() => {
                if (confirm('Reset daily counters?')) {
                  resetMutation.mutate()
                }
              }}
              disabled={resetMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg hover:bg-[var(--bg-tertiary)]"
            >
              <RefreshCw className="w-4 h-4" />
              Reset
            </button>
          </div>
          
          <div className="flex items-center justify-between p-4 bg-[var(--bg-tertiary)] rounded-lg">
            <div>
              <div className="font-medium">Trading Mode</div>
              <div className="text-sm text-[var(--text-muted)]">
                Current: {status?.trading_mode?.toUpperCase() || 'PAPER'}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">
              Change in config file
            </div>
          </div>
          
          <div className="flex items-center justify-between p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
            <div>
              <div className="font-medium text-red-400">Emergency Stop</div>
              <div className="text-sm text-[var(--text-muted)]">
                Halt all trading immediately
              </div>
            </div>
            <button
              onClick={() => {
                if (confirm('EMERGENCY STOP: This will halt ALL trading. Continue?')) {
                  api.post('/api/system/emergency-stop')
                }
              }}
              className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600"
            >
              STOP
            </button>
          </div>
        </div>
      </div>
      
      {/* Symbols */}
      <div className="card">
        <div className="card-header">Monitored Symbols</div>
        <div className="flex flex-wrap gap-2">
          {['EURUSD', 'GBPUSD', 'USDJPY', 'GBPJPY', 'USDCHF', 'USDCAD', 'EURAUD', 'AUDNZD', 'AUDUSD'].map(symbol => (
            <span 
              key={symbol}
              className="px-3 py-1 bg-[var(--bg-tertiary)] rounded-full text-sm"
            >
              {symbol}
            </span>
          ))}
        </div>
        <div className="text-xs text-[var(--text-muted)] mt-3">
          Edit config/trading_config.yaml to modify
        </div>
      </div>
    </div>
  )
}
