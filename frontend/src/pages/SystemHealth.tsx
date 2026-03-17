import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { 
  Activity, 
  Database, 
  Server, 
  Wifi, 
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock
} from 'lucide-react'

export default function SystemHealth() {
  const { data: health = {} as any, isLoading } = useQuery<any>({
    queryKey: ['health-detailed'],
    queryFn: () => api.get('/health/detailed'),
    refetchInterval: 10000,
  })
  
  const { data: agents = {} as any } = useQuery<any>({
    queryKey: ['agents'],
    queryFn: () => api.get('/api/agents'),
    refetchInterval: 10000,
  })
  
  const { data: scheduler = {} as any } = useQuery<any>({
    queryKey: ['scheduler-status'],
    queryFn: () => api.get('/api/scheduler/status'),
    refetchInterval: 10000,
  })
  
  if (isLoading) {
    return <div className="text-center py-10">Loading system health...</div>
  }
  
  const components = health?.components || {}
  const killSwitches = health?.kill_switches || {}
  
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">System Health</h1>
      
      {/* Kill Switches Status */}
      {(killSwitches.system || killSwitches.weekly || killSwitches.daily) && (
        <div className="bg-red-500/20 border border-red-500 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-6 h-6 text-red-500" />
            <div>
              <div className="font-bold text-red-500">KILL SWITCH ACTIVE</div>
              <div className="text-sm text-red-400">
                {killSwitches.system && 'System halt active. '}
                {killSwitches.weekly && 'Weekly drawdown limit reached. '}
                {killSwitches.daily && 'Daily loss limit reached. '}
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Component Status */}
      <div className="grid grid-cols-4 gap-4">
        <ComponentCard
          icon={<Database className="w-5 h-5" />}
          name="Database"
          status={components.database?.status || 'unknown'}
          latency={components.database?.latency_ms}
        />
        <ComponentCard
          icon={<Server className="w-5 h-5" />}
          name="Redis"
          status={components.redis?.status || 'unknown'}
          latency={components.redis?.latency_ms}
        />
        <ComponentCard
          icon={<Wifi className="w-5 h-5" />}
          name="MT5 Bridge"
          status={components.mt5?.status || 'not_configured'}
          latency={components.mt5?.latency_ms}
        />
        <ComponentCard
          icon={<Activity className="w-5 h-5" />}
          name="Scheduler"
          status={components.scheduler?.status || 'unknown'}
        />
      </div>
      
      {/* Scheduler Status */}
      <div className="card">
        <div className="card-header">Workflow Scheduler</div>
        <div className="grid grid-cols-4 gap-4">
          <div>
            <div className="text-xs text-[var(--text-muted)] uppercase mb-1">Status</div>
            <div className="flex items-center gap-2">
              <span className={`status-dot ${scheduler?.is_running ? 'healthy' : 'error'}`} />
              <span>{scheduler?.is_running ? 'Running' : 'Stopped'}</span>
            </div>
          </div>
          <div>
            <div className="text-xs text-[var(--text-muted)] uppercase mb-1">Workflows</div>
            <span className={scheduler?.workflows_enabled ? 'text-bullish' : 'text-bearish'}>
              {scheduler?.workflows_enabled ? 'Enabled' : 'Disabled'}
            </span>
          </div>
          <div>
            <div className="text-xs text-[var(--text-muted)] uppercase mb-1">Last Scan</div>
            <span>{scheduler?.last_scan ? new Date(scheduler.last_scan).toLocaleTimeString() : '-'}</span>
          </div>
          <div>
            <div className="text-xs text-[var(--text-muted)] uppercase mb-1">Scan Interval</div>
            <span>{scheduler?.scan_interval_seconds || 30}s</span>
          </div>
        </div>
      </div>
      
      {/* Agent Status */}
      <div className="card">
        <div className="card-header">Agent Status ({agents?.total_agents || 0} agents)</div>
        {!agents?.agents || agents.agents.length === 0 ? (
          <div className="text-center text-[var(--text-muted)] py-8">
            No agents registered
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Status</th>
                <th>Last Run</th>
                <th>Failures</th>
                <th>Uptime</th>
                <th>Dependencies</th>
              </tr>
            </thead>
            <tbody>
              {agents.agents.map((agent: any) => (
                <tr key={agent.name}>
                  <td className="font-medium">{agent.name}</td>
                  <td>
                    <span className="flex items-center gap-2">
                      {agent.is_healthy ? (
                        <CheckCircle className="w-4 h-4 text-bullish" />
                      ) : (
                        <XCircle className="w-4 h-4 text-bearish" />
                      )}
                      {agent.is_healthy ? 'Healthy' : 'Unhealthy'}
                    </span>
                  </td>
                  <td className="text-sm">
                    {agent.last_run ? new Date(agent.last_run).toLocaleTimeString() : '-'}
                  </td>
                  <td className={agent.consecutive_failures > 0 ? 'text-bearish' : ''}>
                    {agent.consecutive_failures}
                  </td>
                  <td className="text-sm">
                    {agent.uptime_seconds ? formatUptime(agent.uptime_seconds) : '-'}
                  </td>
                  <td className="text-sm text-[var(--text-muted)]">
                    {agent.dependencies?.join(', ') || 'none'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      
      {/* Recent Workflow Results */}
      <div className="card">
        <div className="card-header">Recent Workflow Runs</div>
        {!scheduler?.recent_results || scheduler.recent_results.length === 0 ? (
          <div className="text-center text-[var(--text-muted)] py-8">
            No recent workflow runs
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Workflow</th>
                <th>Started</th>
                <th>Duration</th>
                <th>Status</th>
                <th>Trades Evaluated</th>
                <th>Approved</th>
              </tr>
            </thead>
            <tbody>
              {scheduler.recent_results.map((result: any, i: number) => (
                <tr key={i}>
                  <td className="font-medium">{result.workflow_name}</td>
                  <td className="text-sm">{new Date(result.started_at).toLocaleTimeString()}</td>
                  <td className="text-sm">{result.duration_seconds?.toFixed(2)}s</td>
                  <td>
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      result.status === 'completed' 
                        ? 'bg-green-500/20 text-green-400' 
                        : 'bg-red-500/20 text-red-400'
                    }`}>
                      {result.status}
                    </span>
                  </td>
                  <td>{result.trades_evaluated}</td>
                  <td>{result.trades_approved}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function ComponentCard({ 
  icon, 
  name, 
  status, 
  latency 
}: { 
  icon: React.ReactNode
  name: string
  status: string
  latency?: number
}) {
  const isHealthy = status === 'healthy' || status === 'connected'
  const isUnknown = status === 'unknown' || status === 'not_configured'
  
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <span className={isHealthy ? 'text-bullish' : isUnknown ? 'text-[var(--text-muted)]' : 'text-bearish'}>
          {icon}
        </span>
        <span className={`status-dot ${isHealthy ? 'healthy' : isUnknown ? 'offline' : 'error'}`} />
      </div>
      <div className="font-medium">{name}</div>
      <div className="text-sm text-[var(--text-muted)]">
        {status}
        {latency !== undefined && ` (${latency}ms)`}
      </div>
    </div>
  )
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)}s`
  if (seconds < 3600) return `${(seconds / 60).toFixed(0)}m`
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`
  return `${(seconds / 86400).toFixed(1)}d`
}
